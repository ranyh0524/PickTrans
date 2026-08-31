"""设置对话框：API 配置（含测试连接）、翻译方向、划词与热键、OCR、开机自启。"""
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import autostart
from ..config import PRESETS, APP_VERSION
from ..detector import LANG_NAMES
from ..translator import fetch_models, test_connection
from .card import THEME_LABELS

MODEL_SUGGESTIONS = [
    "glm-4-flash",
    "glm-4.5-flash",
    "deepseek-chat",
    "gpt-4o-mini",
    "moonshot-v1-8k",
    "qwen-turbo",
]

STYLE = """
QDialog, QScrollArea, #scrollContent { background: #F3F5FA; }
QScrollArea { border: none; }
#section {
    background: #FFFFFF;
    border: 1px solid #E9ECF4;
    border-radius: 12px;
}
#sectionTitle { color: #1F2430; font-weight: bold; font-size: 13px; }
#sectionDot {
    background: #3D56E0; border-radius: 2px; max-width: 4px; min-width: 4px;
}
QLabel { color: #4B5563; }
QLineEdit, QComboBox, QPlainTextEdit {
    background: #F8F9FC; border: 1px solid #DFE3EF; border-radius: 8px;
    padding: 5px 10px; color: #1F2937; selection-background-color: #3D56E0;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #7D93FF; background: #FFFFFF; }
QCheckBox, QRadioButton { color: #374151; spacing: 6px; }
QCheckBox:hover, QRadioButton:hover { color: #1F2430; }
#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #6A8DFF, stop:1 #3D56E0);
    color: white; border: none;
    border-radius: 9px; padding: 7px 26px; font-weight: bold;
}
#primaryBtn:hover { background: #5B7CFA; }
#primaryBtn:pressed { background: #3448C8; }
#ghostBtn {
    background: #FFFFFF; border: 1px solid #DFE3EF; border-radius: 9px;
    padding: 6px 18px; color: #414856;
}
#ghostBtn:hover { background: #F3F5FB; color: #3D56E0; border-color: #B9C4FF; }
#testResult { color: #6B7280; }
#saveResult { color: #6B7280; }
"""


class Section(QFrame):
    """圆角白底设置分区。"""

    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("section")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        dot = QFrame()
        dot.setObjectName("sectionDot")
        dot.setFixedHeight(14)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        head.addWidget(dot)
        head.addSpacing(6)
        head.addWidget(label)
        head.addStretch(1)
        root.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        root.addLayout(self.body)


class SettingsDialog(QDialog):
    settingsChanged = pyqtSignal()   # 保存后通知外部（重启热键等）
    _testDone = pyqtSignal(str)
    _modelsDone = pyqtSignal(str, list)   # (请求时的 api_base, 模型名列表)

    def __init__(self, config, cache=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.cache = cache
        self.setWindowTitle(f"PickTrans 设置 v{APP_VERSION}")
        self.setStyleSheet(STYLE)
        self.setMinimumSize(560, 480)
        self.resize(680, 720)
        self._testDone.connect(self._on_test_done)
        self._modelsDone.connect(self._on_models_done)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        content = QVBoxLayout(scroll_content)
        content.setContentsMargins(0, 0, 6, 0)
        content.setSpacing(12)

        # ================= 大模型 API =================
        api_section = Section("大模型 API")
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("选择服务商预设…", None)
        for name, preset in PRESETS.items():
            self.preset_combo.addItem(name, preset)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        form.addRow("服务商预设", self.preset_combo)

        self.base_edit = QLineEdit(self.config.get("api_base"))
        self.base_edit.setPlaceholderText("可直接填写任意 OpenAI 兼容地址，如 https://api.deepseek.com/v1")
        form.addRow("API 地址", self.base_edit)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit(self.config.get("api_key"))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-…")
        toggle = QPushButton("显示")
        toggle.setObjectName("ghostBtn")
        toggle.setCheckable(True)
        toggle.toggled.connect(
            lambda on: (
                self.key_edit.setEchoMode(
                    QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
                ),
                toggle.setText("隐藏" if on else "显示"),
            )
        )
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(toggle)
        form.addRow("API 密钥", key_row)

        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_combo.addItems(MODEL_SUGGESTIONS)
        self.model_combo.setCurrentText(self.config.get("model"))
        self.fetch_models_btn = QPushButton("获取模型")
        self.fetch_models_btn.setObjectName("ghostBtn")
        self.fetch_models_btn.setToolTip("从服务商拉取真实模型列表（需已填写 API 地址与密钥）")
        self.fetch_models_btn.clicked.connect(self._fetch_models)
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.fetch_models_btn)
        form.addRow("模型", model_row)
        self.models_hint = QLabel("")
        self.models_hint.setObjectName("testResult")
        form.addRow("", self.models_hint)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("ghostBtn")
        self.test_btn.clicked.connect(self._run_test)
        self.test_result = QLabel("")
        self.test_result.setObjectName("testResult")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result, 1)
        form.addRow("", test_row)
        api_section.body.addLayout(form)
        content.addWidget(api_section)

        # ================= 翻译方向 =================
        dir_section = Section("翻译方向")
        dir_row = QHBoxLayout()
        self.auto_radio = QRadioButton("自动中英互译（中文→英文，其他→中文）")
        self.fixed_radio = QRadioButton("固定翻译为")
        if self.config.get("direction_mode") == "fixed":
            self.fixed_radio.setChecked(True)
        else:
            self.auto_radio.setChecked(True)
        self.target_combo = QComboBox()
        for code, name in LANG_NAMES.items():
            self.target_combo.addItem(name, code)
        target_index = self.target_combo.findData(self.config.get("fixed_target", "zh"))
        self.target_combo.setCurrentIndex(max(0, target_index))
        self.fixed_radio.toggled.connect(self.target_combo.setEnabled)
        self.target_combo.setEnabled(self.fixed_radio.isChecked())
        dir_row.addWidget(self.auto_radio)
        dir_row.addWidget(self.fixed_radio)
        dir_row.addWidget(self.target_combo)
        dir_row.addStretch(1)
        dir_section.body.addLayout(dir_row)
        content.addWidget(dir_section)

        # ================= 划词与热键 =================
        sel_section = Section("划词与热键")
        self.selection_check = QCheckBox("启用划词翻译（选中文字后弹出「译」按钮）")
        self.selection_check.setChecked(bool(self.config.get("selection_enabled")))
        sel_section.body.addWidget(self.selection_check)

        hotkey_row = QHBoxLayout()
        self.hotkey_check = QCheckBox("全局热键")
        self.hotkey_check.setChecked(bool(self.config.get("hotkey_enabled")))
        self.hotkey_edit = QLineEdit(self.config.get("hotkey"))
        self.hotkey_edit.setFixedWidth(150)
        self.hotkey_edit.setPlaceholderText("ctrl+alt+y")
        hotkey_row.addWidget(self.hotkey_check)
        hotkey_row.addWidget(self.hotkey_edit)
        hotkey_row.addWidget(QLabel("按下后直接翻译当前选中文本（组合键被占用请换一个）"))
        hotkey_row.addStretch(1)
        sel_section.body.addLayout(hotkey_row)

        self.auto_copy_check = QCheckBox("翻译完成后自动复制译文到剪贴板")
        self.auto_copy_check.setChecked(bool(self.config.get("auto_copy")))
        sel_section.body.addWidget(self.auto_copy_check)

        sel_section.body.addWidget(QLabel("划词不触发的应用（每行一个进程名，如 cmd.exe）："))
        self.blacklist_edit = QPlainTextEdit("\n".join(self.config.get("blacklist") or []))
        self.blacklist_edit.setFixedHeight(64)
        sel_section.body.addWidget(self.blacklist_edit)
        content.addWidget(sel_section)

        # ================= OCR 取词 =================
        ocr_section = Section("OCR 取词（识别屏幕上不可复制的文字）")
        ocr_row = QHBoxLayout()
        self.ocr_check = QCheckBox("启用 OCR 取词")
        self.ocr_check.setChecked(bool(self.config.get("ocr_enabled")))
        self.ocr_hotkey_edit = QLineEdit(self.config.get("ocr_hotkey"))
        self.ocr_hotkey_edit.setFixedWidth(150)
        self.ocr_hotkey_edit.setPlaceholderText("ctrl+alt+o")
        ocr_row.addWidget(self.ocr_check)
        ocr_row.addWidget(QLabel("热键"))
        ocr_row.addWidget(self.ocr_hotkey_edit)
        ocr_row.addWidget(QLabel("按下后框选屏幕区域，识别其中文字并翻译"))
        ocr_row.addStretch(1)
        ocr_section.body.addLayout(ocr_row)
        content.addWidget(ocr_section)

        # ================= 翻译卡片 =================
        card_section = Section("翻译卡片")
        card_row = QHBoxLayout()
        card_row.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        for key, label in THEME_LABELS.items():
            self.theme_combo.addItem(label, key)
        current = self.config.get("card_theme", "light")
        idx = list(THEME_LABELS).index(current) if current in THEME_LABELS else 0
        self.theme_combo.setCurrentIndex(idx)
        card_row.addWidget(self.theme_combo)
        card_row.addSpacing(16)
        card_row.addWidget(QLabel("译文字号"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(12, 20)
        try:
            self.font_spin.setValue(int(self.config.get("card_font_size", 14)))
        except (TypeError, ValueError):
            self.font_spin.setValue(14)
        card_row.addWidget(self.font_spin)
        card_row.addWidget(QLabel("保存后对新旧卡片同时生效"))
        card_row.addStretch(1)
        card_section.body.addLayout(card_row)
        content.addWidget(card_section)

        # ================= 其他 =================
        misc_section = Section("其他")
        self.autostart_check = QCheckBox("开机自动启动 PickTrans")
        self.autostart_check.setChecked(autostart.is_enabled())
        misc_section.body.addWidget(self.autostart_check)

        update_row = QHBoxLayout()
        update_row.addWidget(QLabel("更新地址"))
        self.update_edit = QLineEdit(self.config.get("update_url"))
        self.update_edit.setPlaceholderText("HTTPS version.json 直链（本机可用 HTTP），留空不检查更新")
        update_row.addWidget(self.update_edit, 1)
        misc_section.body.addLayout(update_row)

        if self.cache is not None:
            cache_row = QHBoxLayout()
            self.cache_label = QLabel(f"已缓存 {len(self.cache)} 条译文（重复句子直接取用，不调 API）")
            clear_btn = QPushButton("清空缓存")
            clear_btn.setObjectName("ghostBtn")
            clear_btn.clicked.connect(self._clear_cache)
            cache_row.addWidget(self.cache_label)
            cache_row.addWidget(clear_btn)
            cache_row.addStretch(1)
            misc_section.body.addLayout(cache_row)
        content.addWidget(misc_section)
        content.addStretch(1)
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # ================= 底部按钮 =================
        buttons = QHBoxLayout()
        self.save_result = QLabel("")
        self.save_result.setObjectName("saveResult")
        buttons.addWidget(self.save_result)
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primaryBtn")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        # 已配置密钥时，打开对话框即自动拉取当前地址的模型列表
        if self.config.get("api_key"):
            QTimer.singleShot(0, self._fetch_models)

    # ---------- 构建辅助 ----------

    def _apply_preset(self):
        preset = self.preset_combo.currentData()
        if preset:
            self.base_edit.setText(preset["api_base"])
            self.model_combo.setCurrentText(preset["model"])
            self._fetch_models()

    # ---------- 拉取真实模型列表 ----------

    def _fetch_models(self):
        base = self.base_edit.text().strip()
        key = self.key_edit.text().strip()
        if not base or not key:
            self.models_hint.setText("先填写 API 地址与密钥，才能获取模型列表")
            return
        self.fetch_models_btn.setEnabled(False)
        self.models_hint.setText("正在获取模型列表…")
        threading.Thread(
            target=lambda: self._modelsDone.emit(base, self._safe_fetch(base, key)),
            daemon=True,
        ).start()

    @staticmethod
    def _safe_fetch(base: str, key: str) -> list[str]:
        try:
            return fetch_models(base, key)
        except Exception:
            return []

    def _on_models_done(self, base: str, models: list[str]):
        self.fetch_models_btn.setEnabled(True)
        if base != self.base_edit.text().strip():
            return  # 地址已变更，丢弃过期结果
        current = self.model_combo.currentText().strip()
        if not models:
            self.models_hint.setText("获取模型列表失败，可直接手动输入模型名")
            return
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if current:
            idx = self.model_combo.findText(current)
            if idx == -1:
                self.model_combo.addItem(current)
                idx = self.model_combo.count() - 1
            self.model_combo.setCurrentIndex(idx)
        self.models_hint.setText(f"已获取 {len(models)} 个可选模型，也可手动输入其他模型名")

    # ---------- 测试连接 ----------

    def _run_test(self):
        self.test_btn.setEnabled(False)
        self.test_result.setText("测试中…")
        args = (self.base_edit.text().strip(), self.key_edit.text().strip(),
                self.model_combo.currentText().strip())
        threading.Thread(
            target=lambda: self._testDone.emit(test_connection(*args)), daemon=True
        ).start()

    def _on_test_done(self, message: str):
        self.test_btn.setEnabled(True)
        self.test_result.setText(message)

    # ---------- 缓存 ----------

    def _clear_cache(self):
        if self.cache is None:
            return
        n = self.cache.clear()
        self.cache_label.setText(f"已清空 {n} 条缓存")

    # ---------- 保存 ----------

    def _save(self):
        blacklist = [
            line.strip() for line in self.blacklist_edit.toPlainText().splitlines()
            if line.strip()
        ]
        updates = {
            "api_base": self.base_edit.text().strip(),
            "api_key": self.key_edit.text().strip(),
            "model": self.model_combo.currentText().strip(),
            "direction_mode": "fixed" if self.fixed_radio.isChecked() else "auto",
            "fixed_target": self.target_combo.currentData() or "zh",
            "selection_enabled": self.selection_check.isChecked(),
            "hotkey_enabled": self.hotkey_check.isChecked(),
            "hotkey": self.hotkey_edit.text().strip() or "ctrl+alt+y",
            "auto_copy": self.auto_copy_check.isChecked(),
            "ocr_enabled": self.ocr_check.isChecked(),
            "ocr_hotkey": self.ocr_hotkey_edit.text().strip() or "ctrl+alt+o",
            "card_theme": self.theme_combo.currentData() or "light",
            "card_font_size": self.font_spin.value(),
            "blacklist": blacklist,
            "update_url": self.update_edit.text().strip(),
        }
        try:
            self.config.update(updates, persist=True)
        except OSError as e:
            self.save_result.setText(f"保存失败：{e}")
            return

        # 开机自启使用注册表，失败不影响已保存的其他设置。
        autostart_error = ""
        try:
            autostart.set_enabled(self.autostart_check.isChecked())
        except OSError as e:
            autostart_error = f"（开机自启设置失败：{e}）"

        self.settingsChanged.emit()
        self.save_result.setText("已保存 " + autostart_error)
        QTimer.singleShot(600, self.accept)
