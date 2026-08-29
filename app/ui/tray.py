"""托盘图标与菜单：划词开关、OCR 取词、检查更新、设置、退出。"""
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from ..config import APP_VERSION


class TrayIcon(QSystemTrayIcon):
    def __init__(self, config, icon: QIcon, open_settings, on_ocr, on_update=None, parent=None):
        super().__init__(icon, parent)
        self.config = config
        self.open_settings = open_settings
        self.setToolTip(f"PickTrans 划词翻译 v{APP_VERSION}")

        menu = QMenu()
        self.toggle_action = menu.addAction("划词翻译：已开启")
        self.toggle_action.setCheckable(True)
        self.toggle_action.setChecked(bool(config.get("selection_enabled")))
        self.toggle_action.toggled.connect(self._on_toggle)

        ocr_label = f"OCR 取词 ({config.get('ocr_hotkey', 'ctrl+alt+o')})"
        self.ocr_action = menu.addAction(ocr_label)
        self.ocr_action.triggered.connect(on_ocr)

        menu.addSeparator()
        update_action = menu.addAction("检查更新…")
        if on_update is not None:
            update_action.triggered.connect(on_update)
        else:
            update_action.setEnabled(False)
        settings_action = menu.addAction("设置…")
        settings_action.triggered.connect(open_settings)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._on_quit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_toggle(self, checked: bool):
        self.config.set("selection_enabled", checked)
        self.config.save()
        self._sync_text()

    def _sync_text(self):
        enabled = bool(self.config.get("selection_enabled"))
        self.toggle_action.setChecked(enabled)
        self.toggle_action.setText("划词翻译：已开启" if enabled else "划词翻译：已关闭")
        self.ocr_action.setText(f"OCR 取词 ({self.config.get('ocr_hotkey', 'ctrl+alt+o')})")

    def refresh(self):
        self._sync_text()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_settings()

    def _on_quit(self):
        self.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
