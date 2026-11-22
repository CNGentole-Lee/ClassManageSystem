"""ProfileDialog —— 课堂预设（分组制）的管理窗口。

预设就是「一套分组规则」：哪个学生在哪一组。课前在悬浮球右键里点一下
就切换，不用重启、不用改任何文件。

几个刻意的取舍
    * **保存才写链**：界面上点来点去只是改内存，点「保存」时一次性提交
      真正变化的那些下标。误点几十下也不会把事件链撑大。
    * **均分是初值**：40 人 4 组默认每组 10 人，老师只需要把个别学生挪一下。
    * **只在名单变了之后才可能提示**：组员按名单下标存，名单变短时多出来的
      下标由 C++ 回放丢弃，这里如实标出「未分配」，而不是假装还记着。
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from . import dialogs, theme
from .i18n import tr
from .profiles import ProfileError

#: 组数上限（与 C++ 侧的 MAX_GROUPS 一致）
MAX_GROUPS = 24


class ProfileDialog(QDialog):
    """新建 / 改名 / 设置组数 / 指派组员 / 删除预设。"""

    saved = Signal()      # 保存成功后发出，让主程序重新映射组员

    def __init__(self, store, name_supplier=None, parent=None):
        super().__init__(parent)
        self._store = store
        self._names_supplier = name_supplier or (lambda: [])
        self._current_id = 0
        self._pending: dict[int, int] = {}      # 下标 -> 组号（未保存的改动）
        self._group_buttons: list[QPushButton] = []

        self.setWindowTitle(tr("预设（分组）", "Profiles (groups)"))
        self.setMinimumSize(520, 520)
        self._build_ui()
        self._load_current()

    # --- 构建 ---

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("预设：", "Profile:")))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(200)
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        top.addWidget(self._combo, 1)

        self._new_btn = QPushButton(tr("新建", "New"))
        self._new_btn.clicked.connect(self._on_new)
        top.addWidget(self._new_btn)

        self._del_btn = QPushButton(tr("删除", "Delete"))
        self._del_btn.clicked.connect(self._on_delete)
        top.addWidget(self._del_btn)
        layout.addLayout(top)

        self._name_label = QLabel("")
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet(f"color: {theme.c('faint')}; font-size: 12px;")
        layout.addWidget(self._name_label)

        rule = QHBoxLayout()
        rule.addWidget(QLabel(tr("组数：", "Groups:")))
        self._group_spin = QSpinBox()
        self._group_spin.setRange(1, MAX_GROUPS)
        self._group_spin.setValue(4)
        rule.addWidget(self._group_spin)

        self._split_btn = QPushButton(tr("均分", "Split evenly"))
        self._split_btn.setToolTip(tr("按当前人数平均分配到各组，之后可再微调",
                                      "Spread the current names evenly across the groups"))
        self._split_btn.clicked.connect(self._on_split)
        rule.addWidget(self._split_btn)
        rule.addStretch(1)
        self._sizes_label = QLabel("")
        rule.addWidget(self._sizes_label)
        layout.addLayout(rule)

        hint = QLabel(tr("点组号按钮给该学生分组；数字 = 组号，0 = 不分。",
                         "Click a number to put that student in a group; 0 = unassigned."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.c('faint')}; font-size: 12px;")
        layout.addWidget(hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(4, 4, 4, 4)
        self._rows_layout.setSpacing(2)
        self._scroll.setWidget(self._rows_host)
        layout.addWidget(self._scroll, 1)

        self._empty_label = QLabel("")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        buttons = QDialogButtonBox()
        self._save_btn = buttons.addButton(tr("保存", "Save"), QDialogButtonBox.AcceptRole)
        self._close_btn = buttons.addButton(tr("关闭", "Close"), QDialogButtonBox.RejectRole)
        self._save_btn.clicked.connect(self._on_save)
        self._close_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    # --- 显示 ---

    def showEvent(self, event) -> None:
        super().showEvent(event)
        dialogs.center_on_screen(self)
        self._refresh_combo()
        self._load_current()

    def show_and_activate(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # --- 列表 ---

    def _refresh_combo(self) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        for profile in self._store.list():
            label = profile["name"]
            if profile["active"]:
                label = tr("{n}（使用中）", "{n} (in use)", n=label)
            self._combo.addItem(label, profile["id"])
        if self._current_id and self._combo.findData(self._current_id) < 0:
            self._current_id = 0
        index = self._combo.findData(self._current_id)
        self._combo.setCurrentIndex(index if index >= 0 else 0)
        self._combo.blockSignals(False)

    def _on_combo_changed(self, _index: int) -> None:
        pid = self._combo.currentData()
        if pid is None:
            return
        self._current_id = int(pid)
        self._load_current()

    def _load_current(self) -> None:
        profile = self._store.get(self._current_id) if self._current_id else None
        self._pending = {}
        if profile:
            self._group_spin.setValue(max(1, profile["group_count"] or 1))
            self._pending = {i: g for i, g in enumerate(profile["members"]) if g > 0}
        self._name_label.setText(
            tr("名称：{n}", "Name: {n}", n=profile["name"]) if profile
            else tr("还没有预设。点「新建」建一个，再按「均分」一键铺平。",
                    "No profiles yet. Create one, then use \"Split evenly\"."))
        self._del_btn.setEnabled(bool(profile))
        self._save_btn.setEnabled(bool(profile))
        self._rebuild_rows()

    # --- 名单 ---

    def _rebuild_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._group_buttons = []

        names = list(self._names_supplier())
        self._empty_label.setText(
            "" if names else tr("还没有加载名单。先在主面板导入名单，再回来分组。",
                                "No names loaded yet. Import a name list first."))
        self._split_btn.setEnabled(bool(names) and bool(self._current_id))

        group_count = self._group_spin.value()
        for index, name in enumerate(names):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 0, 2, 0)
            row_layout.setSpacing(4)

            label = QLabel(f"{index + 1}. {name}")
            label.setMinimumWidth(180)
            row_layout.addWidget(label, 1)

            current = self._pending.get(index, 0)
            for group in range(0, group_count + 1):
                button = QPushButton("—" if group == 0 else str(group))
                button.setCheckable(True)
                button.setChecked(group == current)
                button.setFixedWidth(34)
                button.clicked.connect(
                    lambda _checked=False, i=index, g=group: self._assign(i, g))
                row_layout.addWidget(button)
                if group > 0:
                    self._group_buttons.append(button)

            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch(1)
        self._update_sizes()

    def _assign(self, index: int, group: int) -> None:
        if group <= 0:
            self._pending.pop(index, None)
        else:
            self._pending[index] = group
        self._rebuild_rows()

    def _update_sizes(self) -> None:
        names = self._names_supplier()
        if not names:
            self._sizes_label.setText("")
            return
        counts = {}
        for index in range(len(names)):
            g = self._pending.get(index, 0)
            counts[g] = counts.get(g, 0) + 1
        parts = [tr("{g}组 {n}人", "G{g}: {n}", g=g, n=counts.get(g, 0))
                 for g in range(1, self._group_spin.value() + 1)]
        unassigned = counts.get(0, 0)
        text = " / ".join(parts)
        if unassigned:
            text += tr("  ·  未分配 {n} 人", "  ·  unassigned {n}", n=unassigned)
        self._sizes_label.setText(text)

    # --- 动作 ---

    def _on_split(self) -> None:
        names = list(self._names_supplier())
        if not names:
            return
        group_count = self._group_spin.value()
        self._pending = self._store.balanced_assignment(group_count, len(names))
        self._rebuild_rows()

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(
            self, tr("新建预设", "New profile"),
            tr("预设名称（例如：化学课）:", "Profile name (e.g. Chemistry):"))
        if not ok or not name.strip():
            return
        try:
            pid = self._store.create(name.strip())
        except ProfileError as exc:
            QMessageBox.warning(self, tr("新建失败", "Could not create"), str(exc))
            return
        self._current_id = pid
        self._refresh_combo()
        self._load_current()

    def _on_delete(self) -> None:
        if not self._current_id:
            return
        profile = self._store.get(self._current_id) or {}
        reply = QMessageBox.warning(
            self,
            tr("删除预设", "Delete profile"),
            tr("删除「{n}」？\n\n这个分组规则会从记录中移除（不可撤销），"
               "但分数和抽取次数不受影响。",
               "Delete \"{n}\"?\n\nThe grouping rule is removed (cannot be undone); "
               "scores and draw counts are untouched.", n=profile.get("name", "")),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            self._store.delete(self._current_id)
        except ProfileError as exc:
            QMessageBox.warning(self, tr("删除失败", "Could not delete"), str(exc))
            return
        self._current_id = 0
        self._refresh_combo()
        self._load_current()
        self.saved.emit()

    def _on_save(self) -> None:
        if not self._current_id:
            return
        names = list(self._names_supplier())
        group_count = self._group_spin.value()
        try:
            profile = self._store.get(self._current_id) or {}
            if profile.get("group_count") != group_count or \
                    len(profile.get("members", [])) != len(names):
                self._store.set_rule(self._current_id, group_count, len(names))
            # 只提交真正变化的下标
            mapping = {index: self._pending.get(index, 0) for index in range(len(names))}
            self._store.assign_bulk(self._current_id, mapping)
        except ProfileError as exc:
            QMessageBox.warning(self, tr("保存失败", "Could not save"), str(exc))
            return
        self.saved.emit()
        self._refresh_combo()
        self._load_current()
        QMessageBox.information(
            self, tr("已保存", "Saved"),
            tr("分组已保存。用悬浮球右键 → 预设 切换过去即可生效。",
               "Saved. Switch to it from the ball's right-click menu → Profiles."))
