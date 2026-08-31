"""全局鼠标监听与划词取词。

工作方式：pynput 在低级钩子线程里回调，回调绝不能阻塞（Windows 会摘除钩子），
所以取词的剪贴板轮询放到独立的守护线程中执行。

取词原理：保存剪贴板 -> 清空 -> 模拟 Ctrl+C -> 轮询剪贴板变化 -> 取到后延时恢复原剪贴板。
"""
import ctypes
import ctypes.wintypes
import os
import sys
import threading
import time

DEBUG = os.environ.get("PICKTRANS_DEBUG") == "1"


def debug_log(msg: str):
    if DEBUG:
        print(f"[listener] {msg}", file=sys.stderr, flush=True)

import pyperclip
from pynput import mouse
from pynput.keyboard import Controller as KbController, Key

from PyQt6.QtCore import QObject, pyqtSignal

DRAG_THRESHOLD_PX = 10        # 按下到释放位移超过该值才算拖选
DOUBLE_CLICK_MS = 500         # 双击判定时间窗（与 Windows GetDoubleClickTime 默认一致）
DOUBLE_CLICK_DIST = 12        # 双击判定位移
DEBOUNCE_S = 1.5              # 两次取词最小间隔
COPY_POLL_S = 0.4             # 等待 Ctrl+C 生效的最长时间
POLL_INTERVAL_S = 0.03
RESTORE_DELAY_S = 0.6         # 取到文本后多久恢复原剪贴板

_GMEM_MOVEABLE = 0x0002
_HWND_MESSAGE = ctypes.c_void_p(-3)
_STANDARD_HGLOBAL_FORMATS = (8, 17, 15, 13)  # CF_DIB, CF_DIBV5, CF_HDROP, CF_UNICODETEXT
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_user32.CreateWindowExW.argtypes = [
    ctypes.wintypes.DWORD, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.wintypes.HWND, ctypes.wintypes.HMENU, ctypes.wintypes.HINSTANCE,
    ctypes.c_void_p,
]
_user32.CreateWindowExW.restype = ctypes.c_void_p
_user32.DestroyWindow.argtypes = [ctypes.c_void_p]
_user32.OpenClipboard.argtypes = [ctypes.c_void_p]
_user32.GetClipboardSequenceNumber.restype = ctypes.wintypes.DWORD
_user32.EnumClipboardFormats.argtypes = [ctypes.wintypes.UINT]
_user32.EnumClipboardFormats.restype = ctypes.wintypes.UINT
_user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]
_user32.GetClipboardData.restype = ctypes.c_void_p
_user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.c_void_p]
_user32.SetClipboardData.restype = ctypes.c_void_p
_kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
_kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = ctypes.c_void_p
_kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
_kernel32.GlobalFree.restype = ctypes.c_void_p


def _create_clipboard_owner() -> int:
    """创建不显示的 message-only 窗口，供 EmptyClipboard/SetClipboardData 持有所有权。"""
    return int(_user32.CreateWindowExW(
        0, "STATIC", "PickTransClipboardOwner", 0,
        0, 0, 0, 0, _HWND_MESSAGE, None, None, None,
    ) or 0)


def _open_clipboard(owner: int) -> bool:
    if not owner:
        return False
    for _ in range(5):
        if _user32.OpenClipboard(ctypes.c_void_p(owner)):
            return True
        time.sleep(0.02)
    return False


def _clipboard_sequence() -> int:
    return int(_user32.GetClipboardSequenceNumber())


def _snapshot_and_clear_clipboard(owner: int) -> list[tuple[int, bytes]] | None:
    """深拷贝可用 HGLOBAL 格式并清空剪贴板；无法安全备份时返回 None。"""
    if not _open_clipboard(owner):
        return None
    snapshot: list[tuple[int, bytes]] = []
    try:
        formats = []
        fmt = 0
        while True:
            fmt = int(_user32.EnumClipboardFormats(fmt))
            if not fmt:
                break
            formats.append(fmt)
        # Windows 可从 CF_BITMAP 等格式按需合成 DIB；显式请求以保住图片内容。
        for fmt in _STANDARD_HGLOBAL_FORMATS:
            if fmt not in formats and _user32.IsClipboardFormatAvailable(fmt):
                formats.append(fmt)
        # 仅有 GDI/metafile 句柄且系统无法合成 DIB 时不能安全克隆，放弃取词。
        if any(fmt in formats for fmt in (2, 3, 14)) and not any(
            fmt in formats for fmt in (8, 17)
        ):
            return None
        for fmt in formats:
            handle = _user32.GetClipboardData(fmt)
            if not handle:
                continue
            size = int(_kernel32.GlobalSize(handle))
            if size <= 0:
                continue  # 位图句柄等非 HGLOBAL 格式由其合成的 DIB 负责保存
            ptr = _kernel32.GlobalLock(handle)
            if not ptr:
                continue
            try:
                snapshot.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                _kernel32.GlobalUnlock(handle)
        if not _user32.EmptyClipboard():
            return None
        return snapshot
    finally:
        _user32.CloseClipboard()


def _restore_clipboard(owner: int, snapshot: list[tuple[int, bytes]],
                       expected_sequence: int) -> bool:
    """仅当剪贴板未再次变化时恢复快照；空快照会恢复为空剪贴板。"""
    if _clipboard_sequence() != expected_sequence or not _open_clipboard(owner):
        return False
    try:
        if _clipboard_sequence() != expected_sequence or not _user32.EmptyClipboard():
            return False
        restored = 0
        for fmt, data in snapshot:
            handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
            if not handle:
                continue
            ptr = _kernel32.GlobalLock(handle)
            if not ptr:
                _kernel32.GlobalFree(handle)
                continue
            try:
                ctypes.memmove(ptr, data, len(data))
            finally:
                _kernel32.GlobalUnlock(handle)
            if _user32.SetClipboardData(fmt, handle):
                restored += 1
            else:
                _kernel32.GlobalFree(handle)
        return restored == len(snapshot)
    finally:
        _user32.CloseClipboard()


def foreground_process_name() -> str:
    """返回前台窗口的进程名（如 notepad.exe），失败返回空串。"""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = ctypes.wintypes.DWORD(512)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value.replace("/", "\\").rsplit("\\", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""
    return ""


class CaptureBus(QObject):
    """跨线程信号桥：监听/热键线程 -> Qt 主线程。"""

    # x, y（仅作参考，UI 定位请用捕获坐标）, text, direct（True=热键直翻）
    textCaptured = pyqtSignal(int, int, str, bool)
    # OCR 热键触发（热键线程发出）
    ocrRequested = pyqtSignal()
    # 热键注册结果：功能名, 组合键, 是否注册成功（热键线程发出）
    hotkeyStatus = pyqtSignal(str, str, bool)


class SelectionListener:
    def __init__(self, config, bus: CaptureBus):
        self.config = config
        self.bus = bus
        self.kb = KbController()
        self._mouse = mouse.Controller()
        self._listener = None
        self._lock = threading.Lock()
        self._press_pos = None
        self._dragged = False
        self._is_double = False
        self._last_click_time = 0.0
        self._last_click_pos = (0, 0)
        self._debounce_until = 0.0
        self._suppressed = False
        self._stopping = False
        self._clipboard_owner = _create_clipboard_owner()
        self._capture_threads: set[threading.Thread] = set()
        self._restore_jobs: dict[
            threading.Timer, tuple[list[tuple[int, bytes]], int]
        ] = {}

    # ---------- 生命周期 ----------

    def start(self):
        with self._lock:
            self._stopping = False
        self._listener = mouse.Listener(on_move=self._on_move, on_click=self._on_click)
        self._listener.daemon = True
        self._listener.start()
        debug_log("mouse listener started")

    def stop(self):
        with self._lock:
            self._stopping = True
        if self._listener:
            self._listener.stop()
        with self._lock:
            threads = list(self._capture_threads)
        for thread in threads:
            thread.join(timeout=1.0)
        with self._lock:
            jobs = list(self._restore_jobs.items())
            self._restore_jobs.clear()
        for timer, (snapshot, sequence) in jobs:
            timer.cancel()
            _restore_clipboard(self._clipboard_owner, snapshot, sequence)
        if self._clipboard_owner:
            _user32.DestroyWindow(ctypes.c_void_p(self._clipboard_owner))
            self._clipboard_owner = 0

    def set_suppressed(self, flag: bool):
        """暂停/恢复取词：OCR 框选期间拖拽不是划词，不能触发 Ctrl+C 捕获。"""
        with self._lock:
            self._suppressed = flag

    # ---------- 钩子回调（钩子线程，必须快速返回） ----------

    def _on_move(self, x, y):
        if self._press_pos is not None:
            dx = x - self._press_pos[0]
            dy = y - self._press_pos[1]
            if dx * dx + dy * dy > DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX:
                self._dragged = True

    def _on_click(self, x, y, button, pressed):
        if button != mouse.Button.left:
            return
        with self._lock:
            if self._stopping:
                return
            if pressed:
                now = time.time()
                near = (abs(x - self._last_click_pos[0]) <= DOUBLE_CLICK_DIST
                        and abs(y - self._last_click_pos[1]) <= DOUBLE_CLICK_DIST)
                self._is_double = near and (now - self._last_click_time) * 1000 < DOUBLE_CLICK_MS
                self._last_click_time = now
                self._last_click_pos = (x, y)
                self._press_pos = (x, y)
                self._dragged = False
                debug_log(f"click press ({x},{y}) double={self._is_double}")
                return
            # 释放
            press = self._press_pos
            self._press_pos = None
            should_capture = (
                (press is not None) and (self._dragged or self._is_double)
                and not self._suppressed
            )
        debug_log(f"click release ({x},{y}) capture={should_capture}")
        if should_capture:
            self._start_capture(x, y, False)

    # ---------- 取词（工作线程，可以慢慢等） ----------

    def capture_current_selection(self):
        """供热键调用：直接取词并直翻。"""
        with self._lock:
            if self._stopping or self._suppressed:
                debug_log("suppressed or stopping, hotkey capture skipped")
                return
        self._start_capture(*self._mouse.position, True)

    def _start_capture(self, x, y, direct):
        def run():
            try:
                self._capture(x, y, direct)
            finally:
                with self._lock:
                    self._capture_threads.discard(threading.current_thread())

        thread = threading.Thread(target=run, daemon=True, name="picktrans-capture")
        with self._lock:
            if self._stopping:
                return
            self._capture_threads.add(thread)
        thread.start()

    def _capture(self, x, y, direct):
        debug_log(f"capture begin at ({x},{y}) direct={direct}")
        cfg = self.config
        if not cfg.get("selection_enabled") and not direct:
            return
        now = time.time()
        if now < self._debounce_until:
            debug_log("debounced, skip")
            return
        with self._lock:
            if self._stopping or self._suppressed:
                debug_log("suppressed or stopping, skip")
                return
        self._debounce_until = now + DEBOUNCE_S

        if not direct:
            proc = foreground_process_name()
            debug_log(f"foreground proc: {proc!r}")
            blacklist = {b.lower().strip() for b in (cfg.get("blacklist") or [])}
            if proc and proc.lower() in blacklist:
                debug_log("blacklisted, skip")
                return

        original = _snapshot_and_clear_clipboard(self._clipboard_owner)
        if original is None:
            debug_log("clipboard backup failed, capture skipped")
            return
        debug_log(f"clipboard cleared (saved formats={len(original)})")

        captured_sequence = _clipboard_sequence()

        # Ctrl+C 复制当前选区
        try:
            with self.kb.pressed(Key.ctrl):
                self.kb.tap("c")
            debug_log("ctrl+c sent")
        except Exception as e:
            debug_log(f"ctrl+c failed: {e!r}")
            self._schedule_restore(original, captured_sequence)
            return

        text = ""
        deadline = time.time() + COPY_POLL_S
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_S)
            cur = self._paste()
            if cur and cur.strip():
                text = cur
                captured_sequence = _clipboard_sequence()
                break
        debug_log(f"poll done, text len={len(text)}")
        self._schedule_restore(original, captured_sequence)

        text = text.strip()
        max_len = int(cfg.get("max_selection_len", 5000))
        debug_log(f"captured text len={len(text)}")
        if not text or len(text) > max_len:
            return
        self.bus.textCaptured.emit(int(x), int(y), text, bool(direct))

    # ---------- 剪贴板工具（pyperclip 每次独立开关剪贴板，线程内串行使用） ----------

    def _paste(self) -> str | None:
        """读取剪贴板；读不到（被其他程序占用等）返回 None，与「空」区分开。"""
        for _ in range(2):
            try:
                return pyperclip.paste() or ""
            except Exception:
                time.sleep(0.05)
        return None

    def _schedule_restore(self, snapshot: list[tuple[int, bytes]], sequence: int):
        def restore():
            try:
                if not _restore_clipboard(self._clipboard_owner, snapshot, sequence):
                    debug_log("restore skipped: newer clipboard content")
            finally:
                with self._lock:
                    self._restore_jobs.pop(timer, None)

        timer = threading.Timer(RESTORE_DELAY_S, restore)
        timer.daemon = True
        with self._lock:
            self._restore_jobs[timer] = (snapshot, sequence)
        timer.start()
