"""翻译卡片：显示原文、流式渲染大模型译文，支持复制/重试/关闭/拖动。

圆角通过 WA_TranslucentBackground + 样式表实现（顶层窗口不能用
QGraphicsDropShadowEffect，会原生崩溃）。
"""
import os
import sys
import threading

from PyQt6.QtCore import Qt, QTimer, QPoint, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor, QFont, QGuiApplication, QImage, QTextCursor, QTextDocument
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..detector import detect, target_for, LANG_NAMES
from ..formula import build_rich_html
from ..translator import TranslateWorker

DEBUG = os.environ.get("PICKTRANS_DEBUG") == "1"


def _dlog(msg: str):
    if DEBUG:
        print(f"[card] {msg}", file=sys.stderr, flush=True)


def _lang_display(code: str) -> str:
    return LANG_NAMES.get(code, code)

STATUS_COLORS = {"idle": "#B4B9C6", "running": "#F5A623", "done": "#22C55E", "error": "#EF4444"}

THEMES = {
    "light": {
        "card_bg": "#FFFFFF", "card_border": "#E6E9F2",
        "badge_bg": "#EEF1FF", "badge_fg": "#3D56E0",
        "status": "#9CA3AF",
        "source_bg": "#F6F7FB", "source_fg": "#5B6472",
        "target_fg": "#171C26",
        "btn_fg": "#414856", "btn_border": "#DFE3EF",
        "btn_hover_bg": "#F3F5FB", "btn_hover_fg": "#3D56E0", "btn_hover_border": "#B9C4FF",
        "btn_disabled": "#B9BFCB",
        "close_fg": "#A8AEBD", "close_hover_bg": "#F0F2F8", "close_hover_fg": "#374151",
        "formula": "#171C26",
    },
    "dark": {
        "card_bg": "#1F2430", "card_border": "#343B4A",
        "badge_bg": "#2A3350", "badge_fg": "#9DB0FF",
        "status": "#8A93A6",
        "source_bg": "#262C3A", "source_fg": "#A7B0C0",
        "target_fg": "#E8ECF5",
        "btn_fg": "#C6CDDB", "btn_border": "#3A4254",
        "btn_hover_bg": "#2E3646", "btn_hover_fg": "#9DB0FF", "btn_hover_border": "#4A5578",
        "btn_disabled": "#5A6272",
        "close_fg": "#7A8296", "close_hover_bg": "#2E3646", "close_hover_fg": "#D5DAE6",
        "formula": "#E8ECF5",
    },
    "sepia": {
        "card_bg": "#F7F1E3", "card_border": "#E3D9C2",
        "badge_bg": "#EFE5CD", "badge_fg": "#8A6D3B",
        "status": "#9A8F7C",
        "source_bg": "#EFE7D4", "source_fg": "#6B5F4B",
        "target_fg": "#43382A",
        "btn_fg": "#5C5140", "btn_border": "#DCD2B8",
        "btn_hover_bg": "#EFE7D4", "btn_hover_fg": "#8A6D3B", "btn_hover_border": "#C9B98D",
        "btn_disabled": "#B3A88F",
        "close_fg": "#A2977F", "close_hover_bg": "#EDE4CF", "close_hover_fg": "#4A4030",
        "formula": "#43382A",
    },
    "green": {
        "card_bg": "#C7EDCC", "card_border": "#A8D5AE",
        "badge_bg": "#B2E0B8", "badge_fg": "#2F7D3B",
        "status": "#7FA986",
        "source_bg": "#BCE3C1", "source_fg": "#4A7A52",
        "target_fg": "#24452B",
        "btn_fg": "#35603D", "btn_border": "#A8D5AE",
        "btn_hover_bg": "#BCE3C1", "btn_hover_fg": "#2F7D3B", "btn_hover_border": "#7FBF88",
        "btn_disabled": "#93B89A",
        "close_fg": "#7FA986", "close_hover_bg": "#BCE3C1", "close_hover_fg": "#24452B",
        "formula": "#24452B",
    },
    "highcontrast": {
        "card_bg": "#000000", "card_border": "#E0E0E0",
        "badge_bg": "#000000", "badge_fg": "#FFFF00",
        "status": "#FFFFFF",
        "source_bg": "#1A1A1A", "source_fg": "#FFFFFF",
        "target_fg": "#FFFFFF",
        "btn_fg": "#FFFFFF", "btn_border": "#FFFFFF",
        "btn_hover_bg": "#333333", "btn_hover_fg": "#FFFF00", "btn_hover_border": "#FFFF00",
        "btn_disabled": "#808080",
        "close_fg": "#C0C0C0", "close_hover_bg": "#333333", "close_hover_fg": "#FFFFFF",
        "formula": "#FFFFFF",
    },
}

THEME_LABELS = {
    "light": "浅色",
    "dark": "深色",
    "sepia": "米色",
    "green": "护眼绿",
    "highcontrast": "高对比",
}


def build_style(theme: str, font_size: int) -> str:
    t = THEMES.get(theme, THEMES["light"])
    return f"""
#card {{
    background: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: 14px;
}}
#accent {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #6A8DFF, stop:0.55 #3D56E0, stop:1 #8B5CF6);
    border-top-left-radius: 13px;
    border-top-right-radius: 13px;
}}
#langBadge {{
    background: {t['badge_bg']};
    color: {t['badge_fg']};
    font-size: 12px;
    font-weight: bold;
    border-radius: 9px;
    padding: 3px 12px;
}}
#statusLabel {{ color: {t['status']}; font-size: 12px; }}
#closeBtn {{
    border: none; background: transparent; color: {t['close_fg']};
    font-size: 13px; border-radius: 7px; padding: 1px 7px;
}}
#closeBtn:hover {{ background: {t['close_hover_bg']}; color: {t['close_hover_fg']}; }}
#sourceBox {{
    background: {t['source_bg']}; border: none; border-radius: 10px;
    color: {t['source_fg']}; font-size: 12.5px; padding: 6px;
}}
#targetBox {{
    background: transparent; border: none; color: {t['target_fg']};
    font-size: {font_size}px; padding: 0px;
}}
#copyBtn, #retryBtn {{
    border: 1px solid {t['btn_border']}; border-radius: 8px; background: {t['card_bg']};
    color: {t['btn_fg']}; font-size: 12px; padding: 4px 14px;
}}
#copyBtn:hover, #retryBtn:hover {{ background: {t['btn_hover_bg']}; color: {t['btn_hover_fg']}; border-color: {t['btn_hover_border']}; }}
#copyBtn:disabled, #retryBtn:disabled {{ color: {t['btn_disabled']}; }}
"""


class _ResizeGrip(QSizeGrip):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(14, 14)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        parent = self.parent()
        if parent is not None:
            parent._auto_height = False


class TranslationCard(QWidget):
    _richReady = pyqtSignal(str, str, dict)

    def __init__(self, config):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.config = config
        self.worker = None
        self.current_text = ""
        self.current_target = "zh"
        self._result_text = ""
        self._drag_offset: QPoint | None = None
        self._auto_height = True

        self.setObjectName("cardShell")
        self.apply_style()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(280, 200)
        self.resize(int(config.get("card_width", 440)), 10)

        # 顶层窗口在 WA_TranslucentBackground 下自身样式表背景不渲染，
        # 圆角白底必须放在填满窗口的子容器上
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName("card")
        outer.addWidget(shell)

        root = QVBoxLayout(shell)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        # ---- 顶部渐变饰条 ----
        accent = QFramelessAccent()
        root.addWidget(accent)

        content = QVBoxLayout()
        content.setContentsMargins(14, 10, 14, 12)
        content.setSpacing(8)
        root.addLayout(content)

        # ---- 头部（可拖动区域） ----
        header = QHBoxLayout()
        header.setSpacing(8)
        self.lang_label = QLabel("")
        self.lang_label.setObjectName("langBadge")
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(24, 22)
        close_btn.clicked.connect(self.close_card)
        header.addWidget(self.lang_label)
        header.addStretch(1)
        header.addWidget(self.status_label)
        header.addWidget(close_btn)
        content.addLayout(header)

        # ---- 原文 ----
        self.source_box = QTextEdit()
        self.source_box.setObjectName("sourceBox")
        self.source_box.setReadOnly(True)
        self.source_box.setFixedHeight(60)
        self.source_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content.addWidget(self.source_box)

        # ---- 译文 ----
        self.target_box = QTextEdit()
        self.target_box.setObjectName("targetBox")
        self.target_box.setReadOnly(True)
        self.target_box.setMinimumHeight(110)
        self.target_box.setFont(QFont("Microsoft YaHei UI", 11))
        content.addWidget(self.target_box, 1)

        # ---- 底部按钮 ----
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.copy_btn = QPushButton("复制译文")
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_result)
        self.copy_btn.setEnabled(False)
        self.retry_btn = QPushButton("重试")
        self.retry_btn.setObjectName("retryBtn")
        self.retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_btn.clicked.connect(self._retry)
        footer.addWidget(self.copy_btn)
        footer.addWidget(self.retry_btn)
        footer.addStretch(1)
        content.addLayout(footer)

        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.setInterval(250)
        self._reset_timer.timeout.connect(self._adjust_height)
        self._richReady.connect(self._apply_rich)

        self._grip = _ResizeGrip(self)
        self._grip.move(self.width() - self._grip.width(), self.height() - self._grip.height())

    # ---------- 对外接口 ----------

    def translate(self, text: str, anchor: QPoint | None = None):
        """开始一次新翻译；重复调用会取消上一次。"""
        _dlog(f"translate begin len={len(text)}")
        self.current_text = text
        self._result_text = ""
        source_lang = detect(text)
        self.current_target = target_for(text, self.config, source_lang)
        self.lang_label.setText(f"{_lang_display(source_lang)} → {_lang_display(self.current_target)}")

        self.source_box.setPlainText(text)
        self.target_box.clear()
        self.copy_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)

        self._show_at(anchor or QCursor.pos() + QPoint(18, 26))
        self._stop_worker()
        self._set_status("翻译中…", "running")
        self.worker = TranslateWorker(self.config, text, source_lang, self.current_target)
        self.worker.chunk.connect(self._on_chunk)
        self.worker.finished_ok.connect(self._on_ok)
        self.worker.failed.connect(self._on_fail)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        _dlog("worker started")

    def show_failure(self, title: str, message: str, anchor: QPoint | None = None):
        """显示一条不发起翻译的错误信息（如 OCR 失败）。"""
        _dlog(f"show_failure {title}: {message[:80]!r}")
        self.lang_label.setText(title)
        self.current_text = ""
        self._result_text = ""
        self.source_box.setPlainText("")
        self.target_box.setPlainText(message)
        self.copy_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
        self._show_at(anchor or QCursor.pos() + QPoint(18, 26))
        self._set_status("失败", "error")

    def close_card(self):
        _dlog("close_card")
        self._stop_worker()
        self._auto_height = True
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_card()
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        self._grip.move(self.width() - self._grip.width(), self.height() - self._grip.height())
        super().resizeEvent(event)

    # ---------- 显示与布局 ----------

    def apply_style(self):
        """按配置应用主题与译文字号；设置保存后对已有卡片重复调用即可换肤。"""
        theme = self.config.get("card_theme", "light")
        try:
            size = int(self.config.get("card_font_size", 14))
        except (TypeError, ValueError):
            size = 14
        self._formula_color = THEMES.get(theme, THEMES["light"])["formula"]
        self.setStyleSheet(build_style(theme, size))

    def _show_at(self, anchor: QPoint):
        self._place_near(anchor)
        self.show()
        if self._auto_height:
            self._adjust_height()
        self.raise_()
        self.activateWindow()

    def _place_near(self, corner: QPoint):
        screen = QGuiApplication.screenAt(corner) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        w = self.width()
        h = 320
        x = min(corner.x(), area.right() - w - 8)
        y = min(corner.y(), area.bottom() - h - 8)
        x = max(x, area.left() + 8)
        y = max(y, area.top() + 8)
        self.move(x, y)

    def _adjust_height(self):
        """根据文档实际高度调整卡片高度，超出屏幕则用最大值靠滚动；用户手动缩放后不再接管。"""
        if not self._auto_height:
            return
        screen = QGuiApplication.screenAt(self.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        target_h = self.sizeHint().height()
        max_h = area.height() - 40
        self.resize(self.width(), min(max(target_h, 230), max_h))
        if self.frameGeometry().bottom() > area.bottom() - 8:
            self.move(self.x(), area.bottom() - 8 - self.height())

    # ---------- 工作线程回调 ----------

    def _on_chunk(self, piece: str):
        _dlog(f"chunk {len(piece)} chars")
        self.target_box.moveCursor(QTextCursor.MoveOperation.End)
        self.target_box.insertPlainText(piece)
        self.target_box.moveCursor(QTextCursor.MoveOperation.End)
        self._reset_timer.start()

    def _on_ok(self, full: str):
        _dlog("finished ok")
        self._result_text = full
        self._set_status("完成", "done")
        self.copy_btn.setEnabled(True)
        self.retry_btn.setEnabled(True)
        if "$" in full:
            threading.Thread(target=self._render_rich, args=(full,), daemon=True).start()
        self._reset_timer.start()
        if self.config.get("auto_copy"):
            self._copy_result(quiet=True)

    def _render_rich(self, full: str):
        rich = build_rich_html(full, self._formula_color)
        if rich:
            self._richReady.emit(full, rich[0], rich[1])

    def _apply_rich(self, token: str, html_text: str, images: dict):
        if token != self._result_text:
            return  # 已发起新翻译，丢弃过期渲染
        doc = self.target_box.document()
        for name, png in images.items():
            doc.addResource(
                QTextDocument.ResourceType.ImageResource,
                QUrl(name),
                QImage.fromData(png),
            )
        self.target_box.setHtml(html_text)
        self._reset_timer.start()

    def _on_fail(self, message: str):
        _dlog(f"failed: {message!r}")
        self._set_status("失败", "error")
        self.target_box.setPlainText(f"翻译出错：{message}\n\n请检查设置中的 API 地址、密钥与模型名称。")
        self.retry_btn.setEnabled(True)

    def _on_worker_finished(self):
        worker = self.sender()
        _dlog("worker thread finished")
        if worker is self.worker:
            self.worker = None
        if worker is not None:
            worker.deleteLater()

    def _set_status(self, text: str, state: str):
        color = STATUS_COLORS.get(state, "#9CA3AF")
        self.status_label.setText(f"<span style='color:{color};font-weight:bold;'>●</span> {text}")

    # ---------- 动作 ----------

    def _copy_result(self, quiet: bool = False):
        text = (self._result_text or self.target_box.toPlainText()).strip()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        if not quiet:
            self.copy_btn.setText("已复制 ✓")
            QTimer.singleShot(1200, lambda: self.copy_btn.setText("复制译文"))

    def _retry(self):
        if self.current_text:
            self.translate(self.current_text)

    # ---------- 工作线程管理 ----------

    def _stop_worker(self):
        worker = self.worker
        self.worker = None
        if worker is None:
            return
        # 断开 UI 更新信号，但保留 finished -> deleteLater 的自清理
        try:
            worker.chunk.disconnect()
            worker.finished_ok.disconnect()
            worker.failed.disconnect()
        except TypeError:
            pass
        worker.cancel()
        worker.finished.connect(worker.deleteLater)

    # ---------- 拖动（标题栏/空白区域，文本框内不影响选择） ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class QFramelessAccent(QWidget):
    """卡片顶部渐变饰条。"""

    def __init__(self):
        super().__init__()
        self.setObjectName("accent")
        self.setFixedHeight(3)
