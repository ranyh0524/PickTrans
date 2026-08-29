"""全局热键：基于 Win32 RegisterHotKey（可靠、不受输入法影响）。

pynput 的 GlobalHotKeys 依赖按键字符匹配，在中文输入法等场景下
Ctrl+组合键拿不到字符导致失效，这里直接用系统级热键注册。
"""
import ctypes
import ctypes.wintypes
import threading

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_MAP = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
VK_SPECIAL = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "page_up": 0x21, "page_down": 0x22, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27,
}


def _parse_combo(combo: str):
    """'ctrl+alt+t' -> (modifiers, vk)；无法解析返回 None。"""
    mods = 0
    vk = None
    for token in combo.lower().replace(" ", "").split("+"):
        if not token:
            continue
        if token in MOD_MAP:
            mods |= MOD_MAP[token]
        elif token in VK_SPECIAL:
            vk = VK_SPECIAL[token]
        elif len(token) == 1 and token.isalnum():
            vk = ord(token.upper())
        elif token.startswith("f") and token[1:].isdigit():
            n = int(token[1:])
            if 1 <= n <= 24:
                vk = 0x6F + n  # VK_F1 = 0x70
        elif token == "insert":
            vk = 0x2D
    if vk is None or not mods:
        return None
    return mods, vk


class HotkeyManager:
    """可重启的全局热键：注册/注销都在专用消息线程里完成。"""

    def __init__(self, config, action):
        self.config = config
        self.action = action  # 在热键线程回调
        self._thread = None
        self._thread_id = 0
        self._stop_flag = False
        self._lock = threading.Lock()

    def start(self):
        self.restart()

    def restart(self):
        with self._lock:
            self._stop_locked()
            if not self.config.get("hotkey_enabled"):
                return
            parsed = _parse_combo(self.config.get("hotkey", "ctrl+alt+y"))
            if not parsed:
                return
            self._stop_flag = False
            self._thread = threading.Thread(
                target=self._run, args=parsed, daemon=True, name="picktrans-hotkey"
            )
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        self._stop_flag = True
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        thread = self._thread
        self._thread = None
        self._thread_id = 0
        if thread and thread.is_alive():
            thread.join(timeout=1.0)

    def _run(self, mods, vk):
        self._thread_id = kernel32.GetCurrentThreadId()
        hotkey_id = 1  # 本进程只注册一个热键，直接用整数 id
        if not user32.RegisterHotKey(None, hotkey_id, mods, vk):
            return  # 组合键被占用，静默降级
        try:
            msg = ctypes.wintypes.MSG()
            while not self._stop_flag:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                if msg.message == WM_HOTKEY and not self._stop_flag:
                    self.action()
                elif msg.message == WM_QUIT:
                    break
        finally:
            user32.UnregisterHotKey(None, hotkey_id)
