"""翻译结果缓存：避免同一句话重复调用大模型 API。

键 = 原文 + 源/目标语言 + 模型 + 温度 的 SHA-256（任一变化都会重新翻译）；
LRU 淘汰，持久化到 %APPDATA%/PickTrans/cache.json，写盘延迟 2 秒合并。
"""
import hashlib
import json
import os

from PyQt6.QtCore import QObject, QTimer

MAX_ENTRIES = 500


def _key(text: str, source_lang: str, target_lang: str, model: str, temperature) -> str:
    raw = json.dumps(
        [text.strip(), source_lang, target_lang, model, str(temperature)],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TranslationCache(QObject):
    """主线程使用的内存缓存 + 延迟落盘。"""

    def __init__(self, path: str, max_entries: int = MAX_ENTRIES, parent=None):
        super().__init__(parent)
        self._path = path
        self._max = max_entries
        self._entries: dict[str, str] = {}
        self._load()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(2000)
        self._save_timer.timeout.connect(self.save)

    def get(self, text, source_lang, target_lang, model, temperature) -> str | None:
        k = _key(text, source_lang, target_lang, model, temperature)
        value = self._entries.pop(k, None)
        if value is None:
            return None
        self._entries[k] = value  # 移到末尾，保持 LRU 顺序
        return value

    def put(self, text, source_lang, target_lang, model, temperature, result: str):
        if not result.strip():
            return
        k = _key(text, source_lang, target_lang, model, temperature)
        self._entries.pop(k, None)
        self._entries[k] = result
        while len(self._entries) > self._max:
            del self._entries[next(iter(self._entries))]
        self._save_timer.start()

    def clear(self) -> int:
        n = len(self._entries)
        self._entries.clear()
        self._save_timer.stop()
        self.save()
        return n

    def __len__(self):
        return len(self._entries)

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, dict):
            self._entries = {k: v for k, v in entries.items() if isinstance(v, str)}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "entries": self._entries}, f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError:
            pass
