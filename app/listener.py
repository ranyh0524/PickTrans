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

DEBUG = os.environ.get("POPTRANS_DEBUG") == "1"


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

    # ---------- 生命周期 ----------

    def start(self):
        self._listener = mouse.Listener(on_move=self._on_move, on_click=self._on_click)
        self._listener.daemon = True
        self._listener.start()
        debug_log("mouse listener started")

    def stop(self):
        if self._listener:
            self._listener.stop()

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
            should_capture = (press is not None) and (self._dragged or self._is_double)
        debug_log(f"click release ({x},{y}) capture={should_capture}")
        if should_capture:
            threading.Thread(target=self._capture, args=(x, y, False), daemon=True).start()

    # ---------- 取词（工作线程，可以慢慢等） ----------

    def capture_current_selection(self):
        """供热键调用：直接取词并直翻。"""
        threading.Thread(target=self._capture, args=(*self._mouse.position, True), daemon=True).start()

    def _capture(self, x, y, direct):
        debug_log(f"capture begin at ({x},{y}) direct={direct}")
        cfg = self.config
        if not cfg.get("selection_enabled") and not direct:
            return
        now = time.time()
        if now < self._debounce_until:
            debug_log("debounced, skip")
            return
        self._debounce_until = now + DEBOUNCE_S

        if not direct:
            proc = foreground_process_name()
            debug_log(f"foreground proc: {proc!r}")
            blacklist = {b.lower().strip() for b in (cfg.get("blacklist") or [])}
            if proc and proc.lower() in blacklist:
                debug_log("blacklisted, skip")
                return

        original = self._paste()
        self._copy_clear()
        debug_log(f"clipboard cleared (original len={len(original)})")

        # Ctrl+C 复制当前选区
        try:
            with self.kb.pressed(Key.ctrl):
                self.kb.tap("c")
            debug_log("ctrl+c sent")
        except Exception as e:
            debug_log(f"ctrl+c failed: {e!r}")
            self._schedule_restore(original)
            return

        text = ""
        deadline = time.time() + COPY_POLL_S
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_S)
            cur = self._paste()
            if cur and cur.strip():
                text = cur
                break
        debug_log(f"poll done, text len={len(text)}")
        self._schedule_restore(original)

        text = text.strip()
        max_len = int(cfg.get("max_selection_len", 5000))
        debug_log(f"captured text len={len(text)}")
        if not text or len(text) > max_len:
            return
        self.bus.textCaptured.emit(int(x), int(y), text, bool(direct))

    # ---------- 剪贴板工具（pyperclip 每次独立开关剪贴板，线程内串行使用） ----------

    def _paste(self) -> str:
        for _ in range(2):
            try:
                return pyperclip.paste() or ""
            except Exception:
                time.sleep(0.05)
        return ""

    def _copy_clear(self):
        try:
            pyperclip.copy("")
        except Exception:
            pass

    def _schedule_restore(self, original: str):
        def restore():
            if original:
                try:
                    pyperclip.copy(original)
                except Exception:
                    pass
        threading.Timer(RESTORE_DELAY_S, restore).start()
