"""配置管理：JSON 持久化到 %APPDATA%/PopTrans/config.json。"""
import json
import os

APP_NAME = "PopTrans"
APP_DISPLAY = "PopTrans 划词翻译"
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

DEFAULTS = {
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


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


class Config:
    """线程安全的只读快照式配置：写只发生在设置界面（主线程），读可在任意线程。"""

    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        for k, v in data.items():
            if k in DEFAULTS:
                self._data[k] = v

    def save(self):
        os.makedirs(config_dir(), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value
