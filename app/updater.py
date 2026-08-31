"""启动时后台检查更新：对比 update_url 指向的 JSON 清单与本地版本。

清单格式：{"version": "1.2.0", "url": "https://.../PickTrans.exe", "notes": "..."}
托管位置不限（GitHub raw / 对象存储 / 任意静态服务）。失败一律静默。
"""
import json
import re
import urllib.request

from .config import APP_VERSION

MAX_MANIFEST_BYTES = 65536  # 清单只有几十字节，超限说明地址配错了


def parse_version(s: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", s or "")][:3]
    return tuple(nums + [0] * (3 - len(nums)))


def check_update(url: str, timeout: int = 10) -> dict | None:
    """有新版本返回清单 dict，否则返回 None；网络/格式错误抛异常由调用方处理。"""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        raw = r.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES or raw.lstrip()[:1] in (b"<", b""):
        raise ValueError("更新地址返回的不是 JSON 清单（请填 version.json 的直链）")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"更新清单不是有效 JSON：{e}") from e
    latest = str(manifest.get("version", "")).strip()
    if not latest or parse_version(latest) <= parse_version(APP_VERSION):
        return None
    return manifest
