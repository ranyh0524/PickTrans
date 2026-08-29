"""划词后的迷你触发按钮。

关键点：
- WA_ShowWithoutActivating + Tool 窗口，弹出不抢焦点，否则目标应用的选区会立刻消失；
- WA_TranslucentBackground 让圆角样式呈现真正的圆形按钮而非方形窗口；
- 顶层窗口在 WA_TranslucentBackground 下自身样式表背景不渲染（与翻译卡片同理），
  蓝色圆底必须画在填满窗口的子控件上，否则按钮只剩文字、近乎不可见。
"""
import os
import sys
import threading

from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QLabel, QWidget

DEBUG = os.environ.get("POPTRANS_DEBUG") == "1"

STYLE = """
QLabel#face {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4C6FFF, stop:1 #2A3FB8);
    color: white;
    font-size: 13px;
    font-weight: bold;
    border: 2px solid rgba(255, 255, 255, 235);
    border-radius: 13px;
}
QLabel#face:hover { background: #5B7CFA; }
"""


class _Face(QLabel):
    pressed = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit()
        super().mouseReleaseEvent(event)


class MiniButton(QWidget):
    clicked = pyqtSignal()

    SIZE = 26

    def __init__(self, timeout_ms: int = 4000):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.text = ""

        self._face = _Face("译", self)
        self._face.setObjectName("face")
        self._face.setStyleSheet(STYLE)
        self._face.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._face.setGeometry(0, 0, self.SIZE, self.SIZE)
        self._face.setCursor(Qt.CursorShape.PointingHandCursor)
        self._face.pressed.connect(self._on_pressed)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(timeout_ms)
        self._hide_timer.timeout.connect(self.hide)

    def popup_at(self, x: int, y: int, text: str):
        """在捕获选词时的坐标（屏幕物理像素）附近显示按钮。"""
        self.text = text
        self._place(QPoint(int(x) + 12, int(y) + 14))
        self.show()
        self.raise_()
        self._hide_timer.start()
        if DEBUG:
            import ctypes
            os_visible = bool(ctypes.windll.user32.IsWindowVisible(int(self.winId())))
            print(
                f"[mini] popup_at thread={threading.current_thread().name} "
                f"qt_visible={self.isVisible()} os_visible={os_visible} pos=({self.x()},{self.y()})",
                file=sys.stderr,
                flush=True,
            )

    def _place(self, corner: QPoint):
        screen = QGuiApplication.screenAt(corner) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(corner.x(), area.right() - self.width() - 4)
        y = min(corner.y(), area.bottom() - self.height() - 4)
        x = max(x, area.left() + 4)
        y = max(y, area.top() + 4)
        self.move(x, y)

    def _on_pressed(self):
        self._hide_timer.stop()
        self.hide()
        self.clicked.emit()

    def dismiss(self):
        self._hide_timer.stop()
        self.hide()
