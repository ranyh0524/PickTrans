"""OCR 取词：屏幕截图 + 离线识别。

默认引擎 RapidOCR（PaddleOCR 模型 + ONNX Runtime，中文与小字识别更准）；
RapidOCR 未安装或识别为空时自动回退 Windows 自带 OCR（Windows.Media.Ocr）。
"""
import asyncio
import os
import sys
import threading

from PyQt6.QtCore import QBuffer, QIODevice

DEBUG = os.environ.get("POPTRANS_DEBUG") == "1"


def _dlog(msg: str):
    if DEBUG:
        print(f"[ocr] {msg}", file=sys.stderr, flush=True)


def image_to_png_bytes(image) -> bytes:
    """QImage/QPixmap -> PNG 字节（线程均可，QImage 跨线程安全）。"""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


OCR_TIMEOUT_S = 20

_rapid_engine = None
_rapid_lock = threading.Lock()


def _rapid():
    """惰性加载 RapidOCR（首次加载模型约 1-2s），跨调用复用。"""
    global _rapid_engine
    with _rapid_lock:
        if _rapid_engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _rapid_engine = RapidOCR()
        return _rapid_engine


def warmup():
    """启动时后台预加载模型，避免首次框选等待；失败不影响回退引擎。"""
    try:
        _rapid()
        _dlog("rapidocr warmup done")
    except Exception as e:
        _dlog(f"rapidocr warmup failed: {e!r}")


def _recognize_rapid(png_bytes: bytes) -> str:
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("图像解码失败")
    result, _elapse = _rapid()(img)
    if not result:
        return ""
    return "\n".join(line[1] for line in result).strip()


def recognize_png(png_bytes: bytes, lang_tag: str | None = None) -> str:
    """阻塞式识别 PNG 字节中的文字，返回按行拼接的文本。

    优先 RapidOCR；不可用或识别为空时回退 Windows 自带 OCR。
    必须在普通后台线程调用：Qt 主线程的 STA COM 会让 WinRT 异步操作死锁。
    """
    try:
        text = _recognize_rapid(png_bytes)
        if text:
            return text
    except ImportError:
        _dlog("rapidocr not installed, fallback to windows ocr")
    except Exception as e:
        _dlog(f"rapidocr failed ({e!r}), fallback to windows ocr")
    return _recognize_windows(png_bytes, lang_tag)


def _recognize_windows(png_bytes: bytes, lang_tag: str | None) -> str:
    async def with_timeout():
        return await asyncio.wait_for(
            _recognize_async(png_bytes, lang_tag), timeout=OCR_TIMEOUT_S
        )

    return asyncio.run(with_timeout())


async def _recognize_async(png_bytes: bytes, lang_tag: str | None) -> str:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    engine = None
    if lang_tag:
        engine = OcrEngine.try_create_from_language(Language(lang_tag))
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError(
            "本机没有可用的 OCR 语言包。请到 系统设置 → 时间和语言 → 语言和地区，"
            "为对应语言勾选安装“文本识别”功能。"
        )

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png_bytes)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    if result.lines:
        return "\n".join(line.text for line in result.lines).strip()
    return (result.text or "").strip()
