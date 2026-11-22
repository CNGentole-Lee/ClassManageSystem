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

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog,
    QLabel, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from . import dialogs, theme
from .i18n import tr
from .profiles import ProfileError

#: 组数上限（与 C++ 侧的 MAX_GROUPS 一致）
MAX_GROUPS = 24

#: 「未分组」按钮宽度：四个汉字在 13px 字号下约 52px，留够内边距，
#: 否则文字会被裁成「未分」—— 用户就找不到取消分组的入口了。
CLEAR_BUTTON_WIDTH = 76


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
        # 组数最多 24，一行要塞下名字 + 状态 + 组号按钮 + 未分组，
        # 太窄会把「未分组」压成「未分」，所以默认就给足宽度。
        self.setMinimumSize(760, 560)
        self.resize(860, 720)
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
        # 0 = 这个预设不启用小组制：抽取时完全按个人加权，所有分组按钮禁用
        self._group_spin.setRange(0, MAX_GROUPS)
        self._group_spin.setValue(0)
        self._group_spin.setSpecialValueText(tr("0（不分组）", "0 (no groups)"))
        self._group_spin.setToolTip(
            tr("0 = 不启用小组制：抽取只看个人次数，分组相关的按钮全部不可用。",
               "0 = grouping off: draws use per-student weights only and all "
               "grouping controls are disabled."))
        self._group_spin.valueChanged.connect(self._on_group_count_changed)
        rule.addWidget(self._group_spin)

        # 「均分」不再是一键静默铺平：它只是把初值填进界面，
        # 真正落盘仍然要点下面的「保存」，而且会先弹一次确认。
        self._split_btn = QPushButton(tr("修改分组人数", "Change grouping"))
        self._split_btn.setToolTip(
            tr("按当前人数平均分配到各组（只填入界面，点「保存」才真正生效）",
               "Spread the current names evenly across the groups (fills the form "
               "only — nothing is saved until you click Save)"))
        self._split_btn.clicked.connect(self._on_split)
        rule.addWidget(self._split_btn)
        rule.addSpacing(12)
        # 人数汇总单独一行放，避免和按钮挤在一起把文字压扁
        rule.addWidget(QLabel(tr("人数：", "Sizes:")))
        self._sizes_label = QLabel("")
        rule.addWidget(self._sizes_label)
        rule.addStretch(1)
        layout.addLayout(rule)

        # 操作说明：讲清楚每个按钮做什么、0 组意味着什么
        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color: {theme.c('faint')}; font-size: 12px;")
        layout.addWidget(self._hint)
        self._update_hint()

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
            # 组数 0 = 这个预设不启用小组制（下面的按钮全部禁用）
            self._group_spin.setValue(max(0, profile["group_count"] or 0))
            self._pending = {i: g for i, g in enumerate(profile["members"]) if g > 0}
        else:
            # 没有预设时不要给 1 组的错觉，直接停在「0 = 不启用」
            self._group_spin.setValue(0)
        self._name_label.setText(
            tr("名称：{n}", "Name: {n}", n=profile["name"]) if profile
            else tr("还没有预设。点右上角「新建」建一个，再用「修改分组人数」"
                    "把学生分到各组。",
                    "No profiles yet. Click \"New\" at the top right, then use "
                    "\"Change grouping\" to assign students to groups."))
        self._del_btn.setEnabled(bool(profile))
        self._save_btn.setEnabled(bool(profile))
        self._rebuild_rows()

    # --- 名单 ---

    def _rebuild_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # 先脱离父对象再排队删除：只调 deleteLater() 的话，
                # findChildren 在重建过程中仍会看到旧行，反复重建会不断堆积。
                widget.setParent(None)
                widget.deleteLater()
        self._group_buttons = []

        names = list(self._names_supplier())
        self._empty_label.setText(
            "" if names else tr("还没有加载名单。先在主面板导入名单，再回来分组。",
                                "No names loaded yet. Import a name list first."))
        self._split_btn.setEnabled(bool(names) and bool(self._current_id)
                                   and self._group_spin.value() > 0)

        group_count = self._group_spin.value()
        grouping = group_count > 0
        for index, name in enumerate(names):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 0, 2, 0)
            row_layout.setSpacing(4)

            label = QLabel(f"{index + 1}. {name}")
            label.setMinimumWidth(150)
            row_layout.addWidget(label, 1)

            # 明确写出「这个人现在在第几组」，不要让人从按钮高亮去猜
            current = int(self._pending.get(index, 0))
            state = QLabel(self._group_text(current, grouping))
            state.setFixedWidth(72)
            state.setAlignment(Qt.AlignCenter)
            state.setStyleSheet(
                f"color: {theme.c('success') if current and grouping else theme.c('faint')};"
                " font-size: 12px;")
            row_layout.addWidget(state)

            group_box = QButtonGroup(row)
            group_box.setExclusive(True)
            for group in range(1, group_count + 1):
                button = QPushButton(str(group))
                button.setCheckable(True)
                button.setChecked(group == current)
                button.setFixedWidth(30)
                button.setToolTip(tr("分到第 {g} 组", "Put in group {g}", g=group))
                button.clicked.connect(
                    lambda _checked=False, i=index, g=group: self._assign(i, g))
                group_box.addButton(button)
                row_layout.addWidget(button)

            # 取消分组：单独一个「未分组」，不用再猜哪个按钮是取消。
            # 宽度必须够 —— 四个字被裁掉一半就没人认得出来。
            clear = QPushButton(tr("未分组", "Ungroup"))
            clear.setFixedWidth(CLEAR_BUTTON_WIDTH)
            clear.setCheckable(True)
            clear.setChecked(current == 0 or not grouping)
            clear.setToolTip(tr("取消分组（不参与组权重）",
                                "Remove from any group (ignored by group weighting)"))
            clear.clicked.connect(lambda _checked=False, i=index: self._assign(i, 0))
            group_box.addButton(clear)
            row_layout.addWidget(clear)

            # 组数为 0 时这些按钮全部变灰：功能不可用就要看得出来不可用
            for button in group_box.buttons():
                button.setEnabled(grouping)

            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch(1)
        self._update_sizes()

    @staticmethod
    def _group_text(group: int, grouping: bool = True) -> str:
        if not grouping:
            return tr("不启用", "Off")
        if group <= 0:
            return tr("未分组", "No group")
        return tr("第 {g} 组", "Group {g}", g=group)

    def _set_status(self, text: str, ok: bool = True) -> None:
        self._sizes_label.setText(text)
        self._sizes_label.setStyleSheet(
            f"color: {theme.c('success') if ok else theme.c('warning')}; font-size: 12px;")

    def _assign(self, index: int, group: int) -> None:
        if group <= 0:
            self._pending.pop(index, None)
        else:
            self._pending[index] = group
        self._rebuild_rows()

    def _update_sizes(self) -> None:
        group_count = self._group_spin.value()
        if group_count <= 0:
            self._set_status(tr("未启用分组", "Grouping is off"), ok=True)
            self._sizes_label.setStyleSheet(
                f"color: {theme.c('faint')}; font-size: 12px;")
            return
        names = self._names_supplier()
        if not names:
            self._sizes_label.setText("")
            return
        counts = {}
        for index in range(len(names)):
            g = self._pending.get(index, 0)
            counts[g] = counts.get(g, 0) + 1
        parts = [tr("{g}组 {n}人", "G{g}: {n}", g=g, n=counts.get(g, 0))
                 for g in range(1, group_count + 1)]
        unassigned = counts.get(0, 0)
        text = " / ".join(parts)
        if unassigned:
            text += tr("  ·  未分组 {n} 人", "  ·  ungrouped {n}", n=unassigned)
            # 有人没分组时给个提醒色：这些人不参与组权重
            self._set_status(text, ok=False)
        else:
            self._set_status(text, ok=True)

    def _update_hint(self) -> None:
        """操作说明跟着组数变：0 组时说清楚「分组功能不启用」。"""
        if self._group_spin.value() <= 0:
            self._hint.setText(tr(
                "组数填 0 表示这个预设不启用小组制：抽取只按每个人的次数算，"
                "下面的组号按钮全部不可用。改成 1 以上即启用小组制。",
                "A group count of 0 means this profile does not use groups: draws "
                "use per-student counts only, and every group button below is "
                "disabled. Set it to 1 or more to enable grouping."))
        else:
            self._hint.setText(tr(
                "点「1 2 3 …」把这个学生分到那一组；点「未分组」把他移出所有组"
                "（未分组的人不参与组间均衡）。左侧「未分组 / 第 N 组」是当前状态。"
                "「修改分组人数」只是把初值填进表格，点「保存」才真正生效。",
                "Click a number to put a student in that group; click \"Ungroup\" to "
                "remove them from every group (ungrouped students are ignored by group "
                "balancing). The label on the left shows the current state. "
                "\"Change grouping\" only fills the table — nothing is saved until "
                "you click Save."))

    def _on_group_count_changed(self, _value: int) -> None:
        """组数变化时立刻刷新：0 → 全部禁用；变大/变小 → 重排按钮。"""
        # 超出新组数的旧分配要清掉，否则会留下指向不存在组的数字
        limit = self._group_spin.value()
        if limit <= 0:
            self._pending = {}
        else:
            self._pending = {i: g for i, g in self._pending.items() if 1 <= g <= limit}
        self._update_hint()
        self._rebuild_rows()

    # --- 动作 ---

    def _on_split(self) -> None:
        """均分：先确认，再只填进界面（不动磁盘）。"""
        names = list(self._names_supplier())
        if not names:
            return
        group_count = self._group_spin.value()
        if group_count <= 0:
            return
        reply = QMessageBox.question(
            self,
            tr("修改分组人数", "Change grouping"),
            tr("将按当前 {n} 人平均分到 {g} 个组（每组约 {p} 人）。\n\n"
               "这会覆盖你在表格里已经做过的分配。\n"
               "确认后只填入界面，点「保存」才会真正生效。",
               "Spread the current {n} students across {g} groups "
               "(about {p} each).\n\nThis overwrites any assignment you already made "
               "in the table.\nAfter confirming it only fills the form — click Save "
               "to apply.",
               n=len(names), g=group_count, p=max(1, len(names) // group_count)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
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
            if group_count <= 0:
                # 0 = 不启用小组制。C++ 侧组数下限是 1（那个下限是给积分面板用的），
                # 所以这里落成「1 组 + 全员未分组」：行为上等价，且不改原生模块。
                self._store.set_rule(self._current_id, 1, 0)
                self._store.assign_bulk(self._current_id, {})
            else:
                if profile.get("group_count") != group_count or \
                        len(profile.get("members", [])) != len(names):
                    self._store.set_rule(self._current_id, group_count, len(names))
                # 只提交真正变化的下标
                mapping = {index: self._pending.get(index, 0)
                           for index in range(len(names))}
                self._store.assign_bulk(self._current_id, mapping)
        except ProfileError as exc:
            QMessageBox.warning(self, tr("保存失败", "Could not save"), str(exc))
            return
        self.saved.emit()
        self._refresh_combo()
        self._load_current()
        if group_count <= 0:
            QMessageBox.information(
                self, tr("已保存", "Saved"),
                tr("已保存：这个预设不启用小组制，抽取只按每个人的次数算。",
                   "Saved: this profile does not use groups, so draws rely on "
                   "per-student counts only."))
        else:
            QMessageBox.information(
                self, tr("已保存", "Saved"),
                tr("分组已保存。用悬浮球右键 → 预设 切换过去即可生效。",
                   "Saved. Switch to it from the ball's right-click menu → Profiles."))
