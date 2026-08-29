"""启动时后台检查更新：对比 update_url 指向的 JSON 清单与本地版本。

清单格式：{"version": "1.2.0", "url": "https://.../PopTrans.exe", "notes": "..."}
托管位置不限（GitHub raw / 对象存储 / 任意静态服务）。失败一律静默。
"""
import json
import re
import urllib.request

from .config import APP_VERSION


def parse_version(s: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", s or "")][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def check_update(url: str, timeout: int = 10) -> dict | None:
    """有新版本返回清单 dict，否则返回 None；网络/格式错误抛异常由调用方处理。"""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        manifest = json.load(r)
    latest = str(manifest.get("version", "")).strip()
    if not latest or parse_version(latest) <= parse_version(APP_VERSION):
        return None
    return manifest
