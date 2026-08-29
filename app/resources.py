"""资源加载：兼容 PyInstaller 打包后的路径。"""
import os
import sys

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def asset_path(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "assets", name)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", name)


def _fallback_pixmap(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = size * 0.06
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.22, size * 0.22)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, QColor("#5B7CFA"))
    grad.setColorAt(1, QColor("#4059E8"))
    p.fillPath(path, grad)
    font = QFont("Microsoft YaHei UI", int(size * 0.46))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QPen(QColor("white")))
    p.drawText(rect.adjusted(0, -size * 0.03, 0, 0), Qt.AlignmentFlag.AlignCenter, "译")
    p.end()
    return pm


def app_icon() -> QIcon:
    path = asset_path("icon.png")
    if os.path.exists(path):
        icon = QIcon(path)
        if not icon.isNull():
            return icon
    return QIcon(_fallback_pixmap())
