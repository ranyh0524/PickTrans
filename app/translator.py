"""OpenAI 兼容流式翻译客户端（QThread + 信号）。"""
import threading
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal
from openai import OpenAI

from .config import DEFAULTS
from .detector import LANG_NAMES


def _lang_display(code: str) -> str:
    return LANG_NAMES.get(code, code)


def build_system_prompt(source_lang: str, target_lang: str) -> str:
    src, tgt = _lang_display(source_lang), _lang_display(target_lang)
    return (
        f"你是专业翻译引擎。把用户发送的文本从{src}翻译成{tgt}。\n"
        "要求：\n"
        "1. 只输出译文，不要任何解释、前缀、后缀或引号。\n"
        "2. 忠实保留原文的换行、列表和格式。\n"
        "3. 译文自然、地道，符合目标语言的表达习惯。\n"
        "4. 如果原文是单个单词或短语，先给出最合适的译法，"
        "再另起一行以「其他含义：」开头列出其余常见义项（没有则省略该行）。\n"
        "5. 原文可能复制自 PDF/网页，公式的上下标已丢失（如 \"ai\" 实为 a_i、"
        "\"Hg i\" 实为 H^g_i、\"x2\" 实为 x^2）。遇到含公式的文本，先按数学语义恢复上下标，"
        "译文中的公式一律用 LaTeX 记法（_{...}、^{...}）书写。"
    )


def test_connection(api_base: str, api_key: str, model: str) -> str:
    """阻塞式连通性测试，返回给用户看的结果文本（在子线程中调用）。"""
    try:
        client = OpenAI(base_url=api_base, api_key=api_key, timeout=15, max_retries=0)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
            stream=False,
        )
        return f"连接成功，{model} 可用"
    except Exception as e:
        return f"连接失败：{_short_error(e)}"


def fetch_models(api_base: str, api_key: str) -> list[str]:
    """拉取服务商的真实模型列表（/models 端点），失败抛异常由调用方处理。"""
    client = OpenAI(base_url=api_base, api_key=api_key, timeout=20, max_retries=0)
    names: set[str] = set()
    page = client.models.list()
    while True:
        names.update(m.id for m in page.data)
        if len(names) >= 2000 or not getattr(page, "has_next_page", lambda: False)():
            break
        page = client.models.list(after=page.data[-1].id)
    return sorted(names)


def _short_error(e: Exception) -> str:
    text = str(e)
    # openai 的异常串通常很长，截取最后一段关键信息
    for marker in ("Error code:", "Message:"):
        idx = text.rfind(marker)
        if idx != -1:
            text = text[idx:]
            break
    return text[:300]


class TranslateWorker(QThread):
    """一次翻译请求。流式产出 chunk 信号；cancel() 后尽快停止。"""

    chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config: dict[str, Any], text: str, source_lang: str,
                 target_lang: str, parent=None):
        super().__init__(parent)
        self._config = config
        self._text = text
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._cancelled = threading.Event()
        self._resource_lock = threading.Lock()
        self._client = None
        self._stream = None

    def cancel(self):
        self._cancelled.set()
        with self._resource_lock:
            stream, client = self._stream, self._client
        for resource in (stream, client):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass

    def run(self):
        client = None
        stream = None
        try:
            if self._cancelled.is_set():
                return
            client = OpenAI(
                base_url=self._config.get("api_base") or DEFAULTS["api_base"],
                api_key=self._config.get("api_key"),
                timeout=60,
                max_retries=1,
            )
            with self._resource_lock:
                self._client = client
            if self._cancelled.is_set():
                return
            stream = client.chat.completions.create(
                model=self._config.get("model") or DEFAULTS["model"],
                temperature=float(self._config.get("temperature", 0.3)),
                stream=True,
                messages=[
                    {
                        "role": "system",
                        "content": build_system_prompt(self._source_lang, self._target_lang),
                    },
                    {"role": "user", "content": self._text},
                ],
            )
            with self._resource_lock:
                self._stream = stream
            if self._cancelled.is_set():
                return
            parts = []
            with stream:
                for event in stream:
                    if self._cancelled.is_set():
                        return
                    if not event.choices:
                        continue
                    delta = event.choices[0].delta
                    if delta and delta.content:
                        parts.append(delta.content)
                        self.chunk.emit(delta.content)
            if self._cancelled.is_set():
                return
            self.finished_ok.emit("".join(parts))
        except Exception as e:
            if not self._cancelled.is_set():
                self.failed.emit(_short_error(e))
        finally:
            with self._resource_lock:
                self._stream = None
                self._client = None
            for resource in (stream, client):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass
