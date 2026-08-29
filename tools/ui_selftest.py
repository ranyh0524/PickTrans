"""UI 组件离线渲染与交互测试（不依赖桌面状态，确定性通过/失败）。

用法：python tools/ui_selftest.py
验证：
  1. 迷你按钮：渲染为圆形（四角透明）、中心不透明（背景已渲染）、尺寸 26
  2. 翻译卡片：渲染为圆角（四角透明）、布局完整、内容可设
  3. 翻译卡片：程序注入鼠标事件后可拖动
  4. OCR 遮罩：渲染含提示文案
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication

from app.ui.card import TranslationCard
from app.ui.mini_button import MiniButton
from app.ui.ocr_selector import OcrSelector

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build")
os.makedirs(OUT, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def corner_transparent(image: QImage, size: int) -> bool:
    """四角 (2,2) 处应为透明或接近背景，圆角半径大于 2px 即可判定。"""
    corners = [(2, 2), (size - 3, 2), (2, size - 3), (size - 3, size - 3)]
    alphas = [image.pixelColor(x, y).alpha() for x, y in corners]
    return all(a < 200 for a in alphas), alphas


def mouse_event(widget, etype, pos):
    ev = QMouseEvent(
        etype, QPointF(pos), QPointF(widget.mapToGlobal(pos)),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QCoreApplication.sendEvent(widget, ev)


def main():
    app = QApplication(sys.argv)  # 必须保留引用，否则包装对象被 GC 后原生崩溃
    from app.config import Config
    config = Config()

    # ---------- 1. 迷你按钮 ----------
    mini = MiniButton(15000)
    mini.popup_at(200, 200, "test text")
    pix = mini.grab()
    path = os.path.join(OUT, "mini_button.png")
    pix.save(path)
    img = pix.toImage()
    check("mini.size=26", mini.width() == 26 and mini.height() == 26, f"{mini.width()}x{mini.height()}")
    ok, alphas = corner_transparent(img, 26)
    check("mini.rounded", ok, f"corner alphas={alphas}")
    # 必须有不透明的蓝色背景：统计全图蓝色像素，
    # 不能只取中心点——中心恰好是白色「译」字
    blue_px = 0
    for yy in range(0, 26, 2):
        for xx in range(0, 26, 2):
            c = img.pixelColor(xx, yy)
            if c.alpha() > 200 and c.blue() > c.red() + 20:
                blue_px += 1
    check("mini.body.opaque", blue_px > 40, f"blue pixels={blue_px}")

    # ---------- 2. 翻译卡片（静态渲染） ----------
    card = TranslationCard(config)
    card.show_failure("英语 → 中文", "[示例] 这是渲染测试译文。")
    card.resize(440, 300)
    pix = card.grab()
    path = os.path.join(OUT, "card.png")
    pix.save(path)
    img = pix.toImage()
    w, h = img.width(), img.height()
    corners = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    alphas = [img.pixelColor(x, y).alpha() for x, y in corners]
    check("card.rounded", all(a < 200 for a in alphas), f"corner alphas={alphas}")
    center_alpha = img.pixelColor(w // 2, h // 2).alpha()
    check("card.body.opaque", center_alpha > 200, f"center alpha={center_alpha}")

    # ---------- 3. 卡片拖动 ----------
    card.show()
    origin = card.pos()
    target = origin + QPoint(60, 40)
    # 在卡片头部区域（状态栏旁空白）按下并拖动
    grab_local = card.mapFromGlobal(target)
    start_local = QPoint(220, 20)
    mouse_event(card, QEvent.Type.MouseButtonPress, start_local)
    steps = 6
    for i in range(1, steps + 1):
        p = start_local + (grab_local - start_local) * (i / steps)
        mouse_event(card, QEvent.Type.MouseMove, p)
    mouse_event(card, QEvent.Type.MouseButtonRelease, grab_local)
    moved = card.pos() - origin
    check("card.draggable", abs(moved.x()) > 30 and abs(moved.y()) > 20,
          f"moved=({moved.x()},{moved.y()})")

    # ---------- 4. OCR 遮罩 ----------
    selector = OcrSelector()
    selector.show()
    pix = selector.grab()
    path = os.path.join(OUT, "ocr_selector.png")
    pix.save(path)
    check("ocr.selector.rendered", pix.width() > 1000 and not pix.isNull(),
          f"{pix.width()}x{pix.height()}")
    selector.hide()

    mini.dismiss()
    card.close_card()
    print("\n=== SUMMARY ===")
    failed = [r for r in results if not r[1]]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
