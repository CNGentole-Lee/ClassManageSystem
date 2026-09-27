"""MainWindow — Configuration and management window for the name picker."""

import os
import sys
import winreg

from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QSpinBox, QGroupBox, QSplitter, QHeaderView,
    QSystemTrayIcon, QMenu, QAction, QMessageBox,
    QStyle, QApplication, QAbstractItemView, QCheckBox,
)

from .config_store import APP_NAME


class MainWindow(QMainWindow):
    """Main management window for loading names, viewing history, settings."""

    REFRESH_INTERVAL_MS = 2000  # refresh cooldown display every 2s
    REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    REG_VALUE_NAME = "RandomNamePicker"

    def __init__(self, engine, app_path: str = "", parent=None):
        super().__init__(parent)
        self._engine = engine
        self._ball = None
        self._points_window = None
        self._wipe_handler = None
        self._tray_icon: QSystemTrayIcon | None = None
        self._settings = QSettings("NamePicker", "Config")
        self._name_items: dict[str, QListWidgetItem] = {}  # name → item mapping
        self._app_path = app_path  # path to main.py for auto-start

        self._init_ui()
        self._init_tray()
        self._restore_settings()

        # Periodic refresh for per-name cooldown display
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_cooldown_display)
        self._refresh_timer.start(self.REFRESH_INTERVAL_MS)

    def set_ball(self, ball) -> None:
        self._ball = ball

    def set_points_window(self, window) -> None:
        self._points_window = window

    def set_wipe_handler(self, handler) -> None:
        """Called after the user confirms 彻底重置 (main.py owns the stores)."""
        self._wipe_handler = handler

    # --- UI Construction ---

    def _init_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} — 管理面板")
        self.setMinimumSize(700, 500)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # --- Source section ---
        source_group = QGroupBox("名单来源")
        source_layout = QVBoxLayout(source_group)
        source_layout.setSpacing(6)

        # Row 1: File browse
        file_row = QHBoxLayout()
        self._file_path_edit = QLineEdit()
        self._file_path_edit.setReadOnly(True)
        self._file_path_edit.setPlaceholderText("选择名单文件 (.txt)...")

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_file)

        file_row.addWidget(QLabel("文件:"))
        file_row.addWidget(self._file_path_edit, 1)
        file_row.addWidget(browse_btn)
        source_layout.addLayout(file_row)

        # Row 2: Number range
        range_row = QHBoxLayout()
        self._range_label_from = QLabel("人数范围: 从")
        range_row.addWidget(self._range_label_from)
        self._range_start = QSpinBox()
        self._range_start.setRange(1, 9999)
        self._range_start.setValue(1)
        self._range_start.setFixedWidth(80)
        range_row.addWidget(self._range_start)

        self._range_label_to = QLabel("到")
        range_row.addWidget(self._range_label_to)
        self._range_end = QSpinBox()
        self._range_end.setRange(1, 9999)
        self._range_end.setValue(99)
        self._range_end.setFixedWidth(80)
        range_row.addWidget(self._range_end)

        self._gen_range_btn = QPushButton("确认")
        self._gen_range_btn.setToolTip("按数字范围生成名单（覆盖当前名单）")
        self._gen_range_btn.clicked.connect(self._on_generate_range)
        range_row.addWidget(self._gen_range_btn)

        self._reset_btn = QPushButton("重置为学号")
        self._reset_btn.setToolTip("重置为默认 1-99 数字学号名单")
        self._reset_btn.clicked.connect(self._on_reset_to_numbers)
        range_row.addWidget(self._reset_btn)
        range_row.addStretch()
        source_layout.addLayout(range_row)

        main_layout.addWidget(source_group)

        # --- Status ---
        status_layout = QHBoxLayout()
        self._status_label = QLabel("未加载名单")
        self._status_label.setStyleSheet("color: #888;")
        self._cooldown_hint = QLabel("")
        self._cooldown_hint.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()
        status_layout.addWidget(self._cooldown_hint)
        main_layout.addLayout(status_layout)

        # --- Splitter: name list | history ---
        splitter = QSplitter(Qt.Horizontal)

        # Name list (with per-name cooldown shown)
        name_group = QGroupBox("名单列表（灰色=冷却中）")
        name_layout = QVBoxLayout(name_group)
        self._name_list_widget = QListWidget()
        self._name_list_widget.setFont(QFont("Microsoft YaHei", 11))
        self._name_list_widget.setAlternatingRowColors(True)
        name_layout.addWidget(self._name_list_widget)
        splitter.addWidget(name_group)

        # History
        hist_group = QGroupBox("抽取历史")
        hist_layout = QVBoxLayout(hist_group)
        self._history_table = QTableWidget()
        self._history_table.setColumnCount(2)
        self._history_table.setHorizontalHeaderLabels(["时间", "名字"])
        self._history_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self._history_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self._history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.verticalHeader().setVisible(False)
        hist_layout.addWidget(self._history_table)
        splitter.addWidget(hist_group)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter, 1)

        # --- Bottom controls ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)

        bottom_layout.addWidget(QLabel("每人冷却:"))
        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(1, 60)
        self._cooldown_spin.setValue(10)
        self._cooldown_spin.setSuffix(" 分钟")
        self._cooldown_spin.setFixedWidth(100)
        self._cooldown_spin.valueChanged.connect(self._on_cooldown_changed)
        bottom_layout.addWidget(self._cooldown_spin)

        bottom_layout.addSpacing(16)

        # Auto-start checkbox
        self._autostart_checkbox = QCheckBox("开机自启动")
        self._autostart_checkbox.setToolTip("勾选后程序将在 Windows 启动时自动运行")
        self._autostart_checkbox.toggled.connect(self._on_autostart_toggled)
        bottom_layout.addWidget(self._autostart_checkbox)

        bottom_layout.addStretch()

        self._points_btn = QPushButton("积分管理")
        self._points_btn.setToolTip("打开小组积分面板（也可右键悬浮球 → 积分管理）")
        self._points_btn.clicked.connect(self._on_open_points)
        bottom_layout.addWidget(self._points_btn)

        self._ball_toggle_btn = QPushButton("隐藏悬浮球")
        self._ball_toggle_btn.setCheckable(True)
        self._ball_toggle_btn.setChecked(True)
        self._ball_toggle_btn.toggled.connect(self._on_toggle_ball)
        bottom_layout.addWidget(self._ball_toggle_btn)

        clear_btn = QPushButton("清空历史")
        clear_btn.clicked.connect(self._on_clear_history)
        bottom_layout.addWidget(clear_btn)

        main_layout.addLayout(bottom_layout)

    def _init_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self._tray_icon.setIcon(icon)
        self._tray_icon.setToolTip(APP_NAME)

        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)

        points_action = QAction("积分管理", self)
        points_action.triggered.connect(self._on_open_points)
        menu.addAction(points_action)

        menu.addSeparator()
        draw_action = QAction("抽取名字", self)
        draw_action.triggered.connect(self._tray_draw)
        menu.addAction(draw_action)
        menu.addSeparator()
        wipe_action = QAction("彻底重置...", self)
        wipe_action.triggered.connect(self._on_wipe_all)
        menu.addAction(wipe_action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    # --- Public slots ---

    def on_name_drawn(self, name: str) -> None:
        self._refresh_history()
        self._status_label.setText(f"本次抽中: {name}")
        self._status_label.setStyleSheet("color: #2E8B57; font-weight: bold;")

    def on_names_drawn(self, names: list) -> None:
        """连抽结果 — show a short preview in the status line."""
        self._refresh_history()
        preview = "、".join(names[:8])
        if len(names) > 8:
            preview += f" … 共 {len(names)} 人"
        self._status_label.setText(f"本次抽中: {preview}")
        self._status_label.setStyleSheet("color: #2E8B57; font-weight: bold;")

    def on_partial_multi_draw(self, drawn: int, requested: int) -> None:
        """连抽时可用人数不足（其余都在冷却中）。"""
        self._status_label.setText(
            f"⚠️ 只抽到 {drawn} 人（请求 {requested} 人，其余仍在冷却中）"
        )
        self._status_label.setStyleSheet("color: #CD853F; font-weight: bold;")

    def on_cooldowns_updated(self) -> None:
        self._refresh_cooldown_display()

    def on_names_loaded(self, count: int) -> None:
        self._status_label.setText(f"已加载 {count} 个名字")
        self._status_label.setStyleSheet("color: #2E8B57; font-weight: bold;")

        self._name_list_widget.clear()
        self._name_items.clear()
        for name in self._engine.get_names():
            item = QListWidgetItem(name)
            item.setFont(QFont("Microsoft YaHei", 11))
            self._name_list_widget.addItem(item)
            self._name_items[name] = item

        self._engine.set_cooldown(self._cooldown_spin.value())

        # Update popup's name pool for rolling animation
        if self._ball is not None:
            pass  # popup pool will be set from main.py

        self._update_range_enabled()
        self._refresh_cooldown_display()

    def on_pool_refilled(self, count: int) -> None:
        self._status_label.setText(f"🔄 全员已抽过一轮（共 {count} 人），开始新一轮")
        self._status_label.setStyleSheet("color: #4682B4; font-weight: bold;")

    def on_cooldown_blocked(self, remaining: int) -> None:
        """Show brief cooldown reminder (for per-name case this is less common)."""
        m = remaining // 60
        s = remaining % 60
        self._status_label.setText(f"⏳ 冷却中: {m:02d}:{s:02d}")
        self._status_label.setStyleSheet("color: #CD853F; font-weight: bold;")

    def on_error(self, message: str) -> None:
        QMessageBox.warning(self, "提示", message)

    def on_history_cleared(self) -> None:
        self._refresh_history()
        self._refresh_cooldown_display()

    # --- Private ---

    def _refresh_cooldown_display(self) -> None:
        """Update name list items: grey out cooldowned names with remaining time."""
        cooldowns = self._engine.get_per_name_cooldowns()

        cooling_count = 0
        for name, item in self._name_items.items():
            remaining = cooldowns.get(name, 0)
            if remaining > 0:
                m = remaining // 60
                s = remaining % 60
                item.setText(f"{name}  [{m}:{s:02d}]")
                item.setForeground(QBrush(QColor(160, 160, 160)))
                cooling_count += 1
            else:
                item.setText(name)
                item.setForeground(QBrush(QColor(0, 0, 0)))

        if cooling_count > 0:
            self._cooldown_hint.setText(f"{cooling_count} 人在冷却中")
        else:
            self._cooldown_hint.setText("全部就绪")

    def _browse_file(self) -> None:
        last_dir = self._settings.value("last_dir", "")
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择名单文件", last_dir,
            "文本文件 (*.txt);;所有文件 (*)"
        )
        if filepath:
            self._file_path_edit.setText(filepath)
            self._settings.setValue("last_file", filepath)
            self._settings.setValue("last_dir", os.path.dirname(filepath))
            self._engine.load_names_from_file(filepath)

    def _on_generate_range(self) -> None:
        """Generate a numeric name list from the range spinboxes."""
        start = self._range_start.value()
        end = self._range_end.value()
        if start > end:
            QMessageBox.warning(self, "提示", "起始数字不能大于结束数字。")
            return
        self._engine.generate_number_list(start, end)
        # Clear file path display since we're using a generated list
        self._file_path_edit.clear()

    def _on_reset_to_numbers(self) -> None:
        """Reset to default 1-99 number list."""
        self._range_start.setValue(1)
        self._range_end.setValue(99)
        self._engine.generate_number_list(1, 99)
        self._file_path_edit.clear()

    def _update_range_enabled(self) -> None:
        """Enable range controls only when the current list is numeric (or empty).
        The reset button stays always enabled as an escape hatch."""
        numeric = self._engine.is_numeric_list()
        self._range_label_from.setEnabled(numeric)
        self._range_start.setEnabled(numeric)
        self._range_label_to.setEnabled(numeric)
        self._range_end.setEnabled(numeric)
        self._gen_range_btn.setEnabled(numeric)
        # _reset_btn stays always enabled

    def _on_cooldown_changed(self, value: int) -> None:
        self._engine.set_cooldown(value)
        self._settings.setValue("cooldown_minutes", value)

    def _on_open_points(self) -> None:
        if self._points_window is None:
            QMessageBox.information(self, "提示", "积分面板尚未就绪。")
            return
        self._points_window.show_and_activate()

    def _on_toggle_ball(self, checked: bool) -> None:
        if self._ball is None:
            return
        if checked:
            self._ball.show()
            self._ball_toggle_btn.setText("隐藏悬浮球")
        else:
            self._ball.hide()
            self._ball_toggle_btn.setText("显示悬浮球")

    def _on_autostart_toggled(self, checked: bool) -> None:
        """Enable or disable auto-start with Windows."""
        if checked:
            success = self._set_autostart(True)
            if not success:
                self._autostart_checkbox.blockSignals(True)
                self._autostart_checkbox.setChecked(False)
                self._autostart_checkbox.blockSignals(False)
                QMessageBox.warning(self, "错误", "设置开机自启动失败，请检查权限。")
        else:
            self._set_autostart(False)

    def _is_autostart_enabled(self) -> bool:
        """Check if auto-start registry entry exists."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.REG_RUN_KEY,
                0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, self.REG_VALUE_NAME)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except OSError:
            return False

    def _set_autostart(self, enabled: bool) -> bool:
        """Write or delete the auto-start registry entry. Returns success."""
        try:
            if enabled:
                # Detect PyInstaller bundle vs source run
                if getattr(sys, 'frozen', False):
                    # Running as bundled EXE — use the EXE directly
                    command = f'"{sys.executable}"'
                else:
                    # Running from source — use pythonw.exe to avoid console
                    pythonw = os.path.join(
                        os.path.dirname(sys.executable), 'pythonw.exe'
                    )
                    if not os.path.isfile(pythonw):
                        pythonw = sys.executable  # fallback
                    command = f'"{pythonw}" "{self._app_path}"'

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, self.REG_RUN_KEY,
                    0, winreg.KEY_SET_VALUE
                )
                winreg.SetValueEx(
                    key, self.REG_VALUE_NAME,
                    0, winreg.REG_SZ, command
                )
                winreg.CloseKey(key)
            else:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, self.REG_RUN_KEY,
                    0, winreg.KEY_SET_VALUE
                )
                try:
                    winreg.DeleteValue(key, self.REG_VALUE_NAME)
                except FileNotFoundError:
                    pass  # already deleted
                winreg.CloseKey(key)
            return True
        except OSError:
            return False

    def _on_clear_history(self) -> None:
        reply = QMessageBox.question(
            self, "确认",
            "确定要清空抽取历史与冷却状态吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._engine.clear_history()

    def _on_wipe_all(self) -> None:
        """托盘菜单 → 彻底重置：config.ini 与 stats.ini 全部清空。"""
        reply = QMessageBox.warning(
            self, "彻底重置",
            "将清空所有数据并恢复到出厂状态：\n\n"
            "  · 小组名称与积分\n"
            "  · 长期公平记录（抽取次数）\n"
            "  · 抽取历史与冷却状态\n\n"
            "此操作不可撤销，确定继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if self._wipe_handler is None:
            QMessageBox.information(self, "提示", "重置功能尚未就绪。")
            return
        self._wipe_handler()

    def on_wipe_complete(self) -> None:
        """Refresh everything the wipe just invalidated."""
        self._refresh_history()
        self._refresh_cooldown_display()
        self._status_label.setText("已彻底重置，所有数据恢复出厂状态")
        self._status_label.setStyleSheet("color: #4682B4; font-weight: bold;")

    def _refresh_history(self) -> None:
        history = self._engine.get_history()
        self._history_table.setRowCount(len(history))
        for row, (timestamp, name) in enumerate(history):
            self._history_table.setItem(row, 0, QTableWidgetItem(timestamp))
            self._history_table.setItem(row, 1, QTableWidgetItem(name))

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()

    def _tray_draw(self) -> None:
        self._engine.draw_name()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()

    def _quit_app(self) -> None:
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self._tray_icon and self._tray_icon.isVisible():
            self.hide()
            self._tray_icon.showMessage(
                APP_NAME,
                "程序已最小化到系统托盘，点击托盘图标可重新打开。",
                QSystemTrayIcon.Information,
                2000,
            )
            event.ignore()
        else:
            event.accept()

    def _restore_settings(self) -> None:
        geom = self._settings.value("window_geometry")
        if geom is not None:
            self.restoreGeometry(geom)

        cooldown = self._settings.value("cooldown_minutes", 10, type=int)
        self._cooldown_spin.setValue(cooldown)
        self._engine.set_cooldown(cooldown)

        last_file = self._settings.value("last_file", "")
        if last_file and os.path.isfile(last_file):
            self._file_path_edit.setText(last_file)
            self._engine.load_names_from_file(last_file)

        # Restore auto-start checkbox
        self._autostart_checkbox.setChecked(self._is_autostart_enabled())

    def save_settings(self) -> None:
        self._settings.setValue("window_geometry", self.saveGeometry())
        self._settings.setValue("cooldown_minutes", self._cooldown_spin.value())
