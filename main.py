"""PickTrans 划词翻译入口。"""
import ctypes
import faulthandler
import os
import sys
import threading

# 原生崩溃时把线程栈打印到 stderr，便于定位。
# --noconsole 打包后 sys.stderr 为 None，faulthandler.enable() 会直接抛
# RuntimeError，此时改为把崩溃栈落盘到 %APPDATA%/PickTrans/crash.log
if sys.stderr is not None:
    faulthandler.enable()
else:
    try:
        from app.config import config_dir
        os.makedirs(config_dir(), exist_ok=True)
        _crash_log_hold = open(os.path.join(config_dir(), "crash.log"), "a", encoding="utf-8")
        faulthandler.enable(_crash_log_hold)
    except Exception:
        pass

DEBUG = os.environ.get("PICKTRANS_DEBUG") == "1"


def _dlog(msg: str):
    if DEBUG:
        print(f"[app] {msg}", file=sys.stderr, flush=True)


def _fix_windows_console():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                # line_buffering：qFatal abort 前也能把 traceback 落盘
                stream.reconfigure(encoding="utf-8", errors="ignore", line_buffering=True)
            except Exception:
                pass


_fix_windows_console()

from PyQt6.QtCore import QObject, QTimer, QPoint, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor, QGuiApplication, QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.config import Config, APP_NAME, APP_DISPLAY, APP_VERSION, config_dir
from app.cache import TranslationCache
from app.hotkey import HotkeyManager
from app.listener import CaptureBus, SelectionListener
from app.ocr import image_to_png_bytes, recognize_png, warmup
from app.formula import warmup as formula_warmup
from app.resources import app_icon
from app.updater import check_update
from app.ui.card import TranslationCard
from app.ui.mini_button import MiniButton
from app.ui.ocr_selector import OcrSelector
from app.ui.settings_dialog import SettingsDialog
from app.ui.tray import TrayIcon

MUTEX_NAME = "PickTrans.SingleInstance.Mutex"


def _another_instance_running() -> bool:
    """用命名互斥体检测单实例：进程死亡时系统自动释放，不会留僵尸锁。"""
    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    # ERROR_ALREADY_EXISTS = 183；互斥体一旦创建成功会随进程存活
    return ctypes.windll.kernel32.GetLastError() == 183


class _ConfigView:
    """让 HotkeyManager 复用配置键：它固定读 hotkey_enabled/hotkey，
    这里把这两个键重定向到实际配置键（划词热键: hotkey_*；OCR: ocr_*）。"""

    def __init__(self, config, enabled_key: str = "hotkey_enabled", hotkey_key: str = "hotkey"):
        self._config = config
        self._enabled_key = enabled_key
        self._hotkey_key = hotkey_key

    def get(self, key, default=None):
        if key == "hotkey_enabled":
            return self._config.get(self._enabled_key, default)
        if key == "hotkey":
            return self._config.get(self._hotkey_key, default)
        return self._config.get(key, default)


class OcrBridge(QObject):
    """OCR 工作线程 -> 主线程的结果桥。"""

    finishedOk = pyqtSignal(str, int, int)   # text, 中心点 x/y
    finishedErr = pyqtSignal(str, int, int)

    def recognize(self, png_bytes: bytes, cx: int, cy: int):
        def work():
            try:
                text = recognize_png(png_bytes)
                if text:
                    self.finishedOk.emit(text, cx, cy)
                else:
                    self.finishedErr.emit("未识别到文字，请框选包含清晰文字的区域。", cx, cy)
            except Exception as e:
                self.finishedErr.emit(str(e), cx, cy)

        threading.Thread(target=work, daemon=True).start()


class UpdateBridge(QObject):
    """更新检查线程 -> 主线程的结果桥。"""

    found = pyqtSignal(str, str, str)   # version, url, notes
    no_update = pyqtSignal()
    failed = pyqtSignal(str)


class AppController(QObject):
    """主线程事件接收者。

    关键：pynput/热键线程发出的信号必须由主线程的 QObject 接收，
    普通函数槽会在发射线程里直连执行，QWidget 调用会出问题。
    槽内异常在 PyQt6 下会直接终止进程，这里统一兜底。

    卡片池：每次翻译独立成卡，可同时存在多张；关闭后的卡片被复用。
    """

    MAX_CARDS = 6

    def __init__(self, config, mini: MiniButton, cache: TranslationCache | None = None,
                 listener=None):
        super().__init__()
        self.config = config
        self.mini = mini
        self.cache = cache
        self.listener = listener
        self.cards: list[TranslationCard] = []
        self._ocr_card: TranslationCard | None = None
        self.selector = OcrSelector()
        self.ocr_bridge = OcrBridge()
        self.selector.regionSelected.connect(self.on_ocr_region)
        self.selector.cancelled.connect(self.on_ocr_cancelled)
        self.ocr_bridge.finishedOk.connect(self.on_ocr_ok)
        self.ocr_bridge.finishedErr.connect(self.on_ocr_err)

    def _acquire_card(self) -> TranslationCard:
        for card in self.cards:
            if not card.isVisible():
                return card
        if len(self.cards) < self.MAX_CARDS:
            card = TranslationCard(self.config, self.cache)
            self.cards.append(card)
            return card
        return self.cards[0]

    def _cascade(self, anchor: QPoint | None) -> QPoint:
        n = sum(1 for c in self.cards if c.isVisible())
        base = anchor if anchor is not None else QCursor.pos() + QPoint(18, 26)
        return base + QPoint(24 * n, 24 * n)

    def restyle(self):
        for card in self.cards:
            card.apply_style()

    def on_captured(self, x: int, y: int, text: str, direct: bool):
        try:
            if direct:
                self.mini.dismiss()
                self._acquire_card().translate(
                    text, anchor=self._cascade(QPoint(x + 18, y + 26))
                )
            else:
                self.mini.popup_at(x, y, text)
        except Exception:
            import traceback
            traceback.print_exc()

    def on_mini_clicked(self):
        try:
            # 点击按钮时光标就在按钮上，以其为锚点
            self._acquire_card().translate(self.mini.text, anchor=self._cascade(None))
        except Exception:
            import traceback
            traceback.print_exc()

    # ---------- OCR ----------

    def on_ocr_requested(self):
        try:
            _dlog("ocr requested")
            self.mini.dismiss()
            self._ocr_card = self._acquire_card()
            if self.listener is not None:
                self.listener.set_suppressed(True)
            self.selector.start()
        except Exception:
            import traceback
            traceback.print_exc()
            if self.listener is not None:
                self.listener.set_suppressed(False)

    def on_ocr_cancelled(self):
        _dlog("ocr cancelled")
        if self.listener is not None:
            self.listener.set_suppressed(False)

    def on_ocr_region(self, x: int, y: int, w: int, h: int):
        # 蒙层已隐藏，恢复划词捕获；识别本身不再干扰用户操作
        if self.listener is not None:
            self.listener.set_suppressed(False)
        try:
            _dlog(f"ocr region ({x},{y}) {w}x{h}")
            # 必须用主屏对象抓图：Windows 下它走虚拟桌面 DC，全局坐标对副屏同样有效；
            # 用副屏对象传全局坐标会偏移加倍，抓出纯黑图（副屏 OCR 必然失败）。
            pixmap = QGuiApplication.primaryScreen().grabWindow(0, x, y, w, h)
            png = image_to_png_bytes(pixmap.toImage())
            self.ocr_bridge.recognize(png, x + w // 2, y + h // 2)
        except Exception as e:
            import traceback
            traceback.print_exc()
            card = self._ocr_card or self._acquire_card()
            self._ocr_card = None
            card.show_failure("OCR", f"截屏失败：{e}", anchor=self._cascade(QPoint(x + 12, y + 12)))

    def on_ocr_ok(self, text: str, cx: int, cy: int):
        try:
            _dlog(f"ocr ok len={len(text)}")
            card = self._ocr_card or self._acquire_card()
            self._ocr_card = None
            card.translate(text, anchor=self._cascade(QPoint(cx + 12, cy + 12)))
        except Exception:
            import traceback
            traceback.print_exc()

    def on_ocr_err(self, message: str, cx: int, cy: int):
        try:
            _dlog(f"ocr err: {message!r}")
            card = self._ocr_card or self._acquire_card()
            self._ocr_card = None
            card.show_failure("OCR", message, anchor=self._cascade(QPoint(cx + 12, cy + 12)))
        except Exception:
            import traceback
            traceback.print_exc()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    if _another_instance_running():
        QMessageBox.information(None, APP_DISPLAY, "PickTrans 已经在运行（请查看系统托盘）。")
        return 0

    config = Config()
    cache = TranslationCache(os.path.join(config_dir(), "cache.json"))

    # ---- 组件 ----
    bus = CaptureBus()
    listener = SelectionListener(config, bus)
    mini = MiniButton(int(config.get("button_timeout_ms", 4000)))
    hotkey = HotkeyManager(_ConfigView(config), lambda: listener.capture_current_selection())
    ocr_hotkey = HotkeyManager(
        _ConfigView(config, enabled_key="ocr_enabled", hotkey_key="ocr_hotkey"),
        lambda: bus.ocrRequested.emit(),
    )
    controller = AppController(config, mini, cache, listener)
    dialog_holder = {}

    def on_settings_changed():
        hotkey.restart()
        ocr_hotkey.restart()
        tray.refresh()
        controller.restyle()

    update_bridge = UpdateBridge()

    def _show_update(version: str, url: str, notes: str):
        box = QMessageBox(QMessageBox.Icon.Information, APP_DISPLAY,
                          f"发现新版本 v{version}" + (f"\n\n{notes}" if notes else ""))
        dl = box.addButton("打开下载页", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("稍后", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is dl and url:
            QDesktopServices.openUrl(QUrl(url))

    def _check_update(manual: bool = False):
        def work():
            url = (config.get("update_url") or "").strip()
            if not url:
                if manual:
                    update_bridge.failed.emit("未配置更新地址（设置 → 其他 → 更新地址）")
                return
            try:
                manifest = check_update(url)
            except Exception as e:
                if manual:
                    update_bridge.failed.emit(f"检查更新失败：{e}")
                else:
                    _dlog(f"update check failed: {e!r}")
                return
            if manifest:
                update_bridge.found.emit(
                    str(manifest.get("version", "")),
                    str(manifest.get("url") or ""),
                    str(manifest.get("notes") or ""),
                )
            elif manual:
                update_bridge.no_update.emit()
        threading.Thread(target=work, daemon=True, name="picktrans-update").start()

    update_bridge.found.connect(_show_update)
    update_bridge.no_update.connect(
        lambda: QMessageBox.information(None, APP_DISPLAY, f"当前 v{APP_VERSION} 已是最新版本。")
    )
    update_bridge.failed.connect(
        lambda msg: QMessageBox.warning(None, APP_DISPLAY, msg)
    )

    tray = TrayIcon(
        config,
        app_icon(),
        lambda: _open_settings(config, cache, dialog_holder, app_icon(), on_settings_changed),
        on_ocr=controller.on_ocr_requested,
        on_update=lambda: _check_update(manual=True),
    )

    # ---- 事件接线（controller 在主线程 -> 自动排队连接，跨线程安全） ----
    bus.textCaptured.connect(controller.on_captured)
    bus.ocrRequested.connect(controller.on_ocr_requested)
    mini.clicked.connect(controller.on_mini_clicked)

    # ---- 启动 ----
    listener.start()
    hotkey.start()
    ocr_hotkey.start()
    tray.show()
    def _warmup():
        warmup()
        formula_warmup()

    threading.Thread(target=_warmup, daemon=True, name="picktrans-warmup").start()
    _check_update()

    if not config.get("api_key"):
        QTimer.singleShot(
            400,
            lambda: _open_settings(config, cache, dialog_holder, app_icon(), on_settings_changed),
        )

    exit_code = app.exec()

    cache.save()
    listener.stop()
    hotkey.stop()
    ocr_hotkey.stop()
    return exit_code


def _open_settings(config, cache, dialog_holder, icon, on_changed):
    dialog = dialog_holder.get("dlg")
    if dialog is not None and dialog.isVisible():
        dialog.raise_()
        dialog.activateWindow()
        return
    dialog = SettingsDialog(config, cache)
    dialog.setWindowIcon(icon)
    dialog.settingsChanged.connect(on_changed)
    dialog_holder["dlg"] = dialog
    dialog.exec()
    dialog_holder["dlg"] = None


if __name__ == "__main__":
    sys.exit(main())
