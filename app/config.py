"""配置管理：JSON 持久化到 %APPDATA%/PickTrans/config.json。"""
import json
import os
import threading
from typing import Any

APP_NAME = "PickTrans"
APP_DISPLAY = "PickTrans 划词翻译"
APP_VERSION = "1.0.0"

# 各家 OpenAI 兼容接口示例（README 里有完整说明）
PRESETS = {
    "智谱 GLM": {
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "DeepSeek": {
        "api_base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "OpenAI": {
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "Kimi (月之暗面)": {
        "api_base": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "通义千问": {
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
    },
}

DEFAULTS: dict[str, Any] = {
    # API
    "api_base": PRESETS["智谱 GLM"]["api_base"],
    "api_key": "",
    "model": PRESETS["智谱 GLM"]["model"],
    "temperature": 0.3,
    # 翻译方向：auto = 中文↔英文自动；fixed = 固定目标语言
    "direction_mode": "auto",
    "fixed_target": "zh",
    # 划词
    "selection_enabled": True,
    # Ctrl+C 会打断终端，默认拉黑常见终端
    "blacklist": ["cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "conhost.exe"],
    "max_selection_len": 5000,
    # 全局热键：直接翻译当前选中文本（跳过迷你按钮）
    "hotkey_enabled": True,
    "hotkey": "ctrl+alt+y",
    # OCR 取词：热键后框选屏幕区域识别文字并翻译
    "ocr_enabled": True,
    "ocr_hotkey": "ctrl+alt+o",
    # 开机自启（写入 HKCU Run 注册表项）
    "autostart": False,
    # 更新清单地址（JSON：version/url/notes），空串表示不检查
    "update_url": "",
    # UI
    "card_width": 440,
    "card_theme": "light",
    "card_font_size": 14,
    "auto_copy": False,
    "button_timeout_ms": 4000,
}

_STRING_KEYS = {"api_base", "api_key", "model", "hotkey", "ocr_hotkey", "update_url"}
_BOOL_KEYS = {"selection_enabled", "hotkey_enabled", "ocr_enabled", "autostart", "auto_copy"}


def _validated(data: object) -> dict[str, Any]:
    """只接受已知且类型有效的配置项，损坏项回退默认值。"""
    if not isinstance(data, dict):
        return {}
    result = {}
    for key, value in data.items():
        if key not in DEFAULTS:
            continue
        if key in _STRING_KEYS and isinstance(value, str):
            result[key] = value
        elif key in _BOOL_KEYS and isinstance(value, bool):
            result[key] = value
        elif key == "blacklist" and isinstance(value, list):
            result[key] = [item for item in value if isinstance(item, str)]
        elif key == "temperature" and isinstance(value, (int, float)) and not isinstance(value, bool):
            result[key] = min(2.0, max(0.0, float(value)))
        elif key == "max_selection_len" and isinstance(value, int) and not isinstance(value, bool):
            result[key] = min(100_000, max(1, value))
        elif key == "button_timeout_ms" and isinstance(value, int) and not isinstance(value, bool):
            result[key] = min(60_000, max(500, value))
        elif key == "card_width" and isinstance(value, int) and not isinstance(value, bool):
            result[key] = min(1200, max(280, value))
        elif key == "card_font_size" and isinstance(value, int) and not isinstance(value, bool):
            result[key] = min(20, max(12, value))
        elif key == "direction_mode" and value in {"auto", "fixed"}:
            result[key] = value
        elif key == "fixed_target" and value in {"zh", "en", "ja", "ko", "fr", "de", "es", "ru", "ar"}:
            result[key] = value
        elif key == "card_theme" and value in {"light", "dark", "sepia", "green", "highcontrast"}:
            result[key] = value
    return result


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


class Config:
    """线程安全的快照式配置；读者只会看到完整的旧配置或新配置。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        loaded = dict(DEFAULTS)
        loaded.update(_validated(data))
        with self._lock:
            self._data = loaded

    @staticmethod
    def _write(data: dict[str, Any]):
        directory = config_dir()
        path = config_path()
        tmp = path + ".tmp"
        os.makedirs(directory, exist_ok=True)
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def save(self):
        self._write(self.snapshot())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def update(self, values: dict[str, Any], persist: bool = False):
        """一次性更新多个键；persist 时仅在落盘成功后发布新快照。"""
        clean = _validated(values)
        with self._lock:
            candidate = dict(self._data)
            candidate.update(clean)
        if persist:
            self._write(candidate)
        with self._lock:
            self._data = candidate

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any):
        self.update({key: value})
