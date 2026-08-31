"""OCR 框选遮罩：全屏半透明蒙层，按住拖拽框选要识别的区域。"""
import os

from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QGuiApplication
from PyQt6.QtWidgets import QLabel, QRubberBand, QWidget

DEBUG = os.environ.get("PICKTRANS_DEBUG") == "1"

MIN_REGION = 8  # 小于该尺寸视为误操作，直接取消

HINT = "按住左键拖拽，框选要翻译的文字区域；按 Esc 或右键取消"


def _virtual_geometry() -> QRect:
    """所有屏幕的并集（虚拟桌面），多显示器时蒙层需覆盖副屏。"""
    screens = QGuiApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    geo = QRect(screens[0].geometry())
    for s in screens[1:]:
        geo = geo.united(s.geometry())
    return geo


class OcrSelector(QWidget):
    # 全局屏幕坐标下的选区（物理像素）
    regionSelected = pyqtSignal(int, int, int, int)
    # 用户取消（Esc/右键/失焦/超时），外部据此恢复被暂停的功能
    cancelled = pyqtSignal()

    TIMEOUT_MS = 60_000

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.setGeometry(_virtual_geometry())

        self._origin = None
        self._pending_rect = None
        self._capture_delay = QTimer(self)
        self._capture_delay.setSingleShot(True)
        self._capture_delay.setInterval(160)
        self._capture_delay.timeout.connect(self._emit_pending)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(self.TIMEOUT_MS)
        self._timeout.timeout.connect(lambda: self._finish(None))
        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._rubber.setStyleSheet(
            "QRubberBand { border: 1px solid #4059E8; background: rgba(64, 89, 232, 24); }"
        )

        self._hint = QLabel(HINT, self)
        self._hint.setStyleSheet(
            "QLabel {"
            " background: rgba(30, 33, 46, 190); color: #FFFFFF; font-size: 13px;"
            " border-radius: 8px; padding: 7px 18px; border: 1px solid rgba(255,255,255,50);"
            "}"
        )
        self._hint.adjustSize()
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._place_hint()

    # ---------- 生命周期 ----------

    def start(self):
        self._capture_delay.stop()
        self._pending_rect = None
        self._origin = None
        self._rubber.hide()
        self.setGeometry(_virtual_geometry())
        self._place_hint()
        self.show()
        self.raise_()
        self.activateWindow()
        self._timeout.start()

    def _place_hint(self):
        """提示放在主屏顶部中央（蒙层可能横跨多个屏幕，并集中心可能落在屏缝上）。"""
        screen = QGuiApplication.primaryScreen()
        geo = screen.geometry() if screen else QRect(self.rect())
        x = geo.center().x() - self._hint.width() // 2 - self.x()
        self._hint.move(x, geo.top() + 36 - self.y())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        # 焦点被别的窗口抢走时 Esc 就收不到了，直接取消，避免蒙层卡死屏幕
        if self.isVisible():
            self._finish(None)
        super().focusOutEvent(event)

    # ---------- 框选交互 ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._finish(None)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._rubber.setGeometry(QRect(self._origin, self._origin))
            self._rubber.show()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._rubber.setGeometry(QRect(self._origin, event.position().toPoint()).normalized())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
            rect = self._rubber.geometry()
            self._origin = None
            self._rubber.hide()
            if rect.width() < MIN_REGION or rect.height() < MIN_REGION:
                self._finish(None)
                return
            # 先隐藏蒙层，稍等一帧再截图；成员定时器可被下一轮框选取消。
            self.hide()
            self._pending_rect = QRect(rect)
            self._capture_delay.start()
        super().mouseReleaseEvent(event)

    def _emit_pending(self):
        rect = self._pending_rect
        self._pending_rect = None
        if rect is not None:
            self._finish(rect)

    def _finish(self, rect):
        self._capture_delay.stop()
        self._pending_rect = None
        self._timeout.stop()
        self.hide()
        if rect is None:
            self.cancelled.emit()
            return
        gx = self.x() + rect.x()
        gy = self.y() + rect.y()
        self.regionSelected.emit(gx, gy, rect.width(), rect.height())

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 12, 20, 70))
        super().paintEvent(event)
