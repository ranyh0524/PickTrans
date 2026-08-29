"""语言检测：Unicode 书写系统启发式 + 翻译方向规则。"""

LANG_NAMES = {
    "zh": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "ar": "阿拉伯语",
}

# range 的 in 判定是 O(1)；不要用 list（线性扫描，长文本下明显卡顿）
_CYRILLIC = range(0x0400, 0x0500)
_ARABIC = range(0x0600, 0x0700)
_HANGUL = range(0xAC00, 0xD7B0)
_KANA = range(0x3040, 0x3100)
_HAN_BASIC = range(0x4E00, 0xA000)
_HAN_EXT_A = range(0x3400, 0x4DC0)


def detect(text: str) -> str:
    """返回语言代码：zh/ja/ko/ru/ar/en。"""
    if not text:
        return "en"
    han = kana = hangul = cyrillic = arabic = latin = 0
    for ch in text:
        cp = ord(ch)
        if cp in _HAN_BASIC or cp in _HAN_EXT_A:
            han += 1
        elif cp in _KANA:
            kana += 1
        elif cp in _HANGUL:
            hangul += 1
        elif cp in _CYRILLIC:
            cyrillic += 1
        elif cp in _ARABIC:
            arabic += 1
        elif ch.isalpha():
            latin += 1
    if kana:
        return "ja"  # 日语混用汉字，假名才是决定性特征
    if hangul:
        return "ko"
    if han:
        return "zh"
    if cyrillic:
        return "ru"
    if arabic:
        return "ar"
    return "en"


def target_for(text: str, config, source_lang: str | None = None) -> str:
    """按配置决定目标语言；源和目标相同时回退到中英互换。"""
    src = source_lang or detect(text)
    if config.get("direction_mode") == "fixed":
        target = config.get("fixed_target", "zh")
    else:
        target = "en" if src == "zh" else "zh"
    if target == src:
        target = "en" if target == "zh" else "zh"
    return target
