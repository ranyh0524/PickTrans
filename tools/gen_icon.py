"""生成应用图标 assets/icon.png 与 assets/icon.ico。用法：python tools/gen_icon.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")


def make_pixmap(size: int) -> QPixmap:
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


def main():
    _ = QGuiApplication(sys.argv)
    os.makedirs(ASSETS, exist_ok=True)
    pm = make_pixmap(256)
    ok_png = pm.save(os.path.join(ASSETS, "icon.png"), "PNG")
    ok_ico = pm.save(os.path.join(ASSETS, "icon.ico"), "ICO")
    print(f"icon.png: {ok_png}, icon.ico: {ok_ico}")


if __name__ == "__main__":
    main()
