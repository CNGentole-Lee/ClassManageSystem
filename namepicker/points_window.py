"""PointsWindow —— 小组积分管理面板.

六张小组卡片排成网格。先点卡片把它展开，露出 -1 / +1 / +2 / +3 四个按钮，
点按钮即应用对应增减。同一时刻只展开一张卡片，老师始终知道下一击落在哪组。

每次改动防抖写入加密的 config.dat（明文 config.ini 只是查看副本），关窗时再
补一次落盘，分数跨重启保留。每次分数变动还会自动追加一条加密的操作日志，
唯一入口是底栏「小组数量...」旁边的「操作日志」按钮（见 _LogViewerDialog）。
"""

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QGridLayout, QVBoxLayout,
    QHBoxLayout, QMessageBox, QInputDialog, QSizePolicy, QMenu, QAction,
    QScrollArea, QLayout, QDialog, QPlainTextEdit,
)

from . import i18n, log_store, macos_window, theme
from .i18n import tr
from .widgets import ElidedLabel
from .config_store import MAX_GROUP_COUNT, MIN_GROUP_COUNT

# 每个操作按钮对应的增减量，按显示顺序。
DELTAS = (-1, 1, 2, 3)
# 键盘快捷键到增减量的映射（讲台上用键盘，不用鼠标找按钮）。
DELTA_KEYS = {Qt.Key_1: -1, Qt.Key_2: 1, Qt.Key_3: 2, Qt.Key_4: 3}

COLUMNS = 3
CARD_HEIGHT = 200

_CARD_QSS = """
QFrame#card {
    background: %(bg)s;
    border: 2px solid %(border)s;
    border-radius: 14px;
}
QFrame#card QLabel { background: transparent; }
QFrame#card QLabel#groupName {
    color: %(name)s;
    font-family: "%(family)s";
    font-size: 17px;
    font-weight: bold;
}
QFrame#card QLabel#score {
    color: %(score)s;
    font-family: "%(family)s";
    font-size: 44px;
    font-weight: bold;
}
QFrame#card QLabel#deltaBadge {
    color: %(badge)s;
    font-family: "%(family)s";
    font-size: 18px;
    font-weight: bold;
}
QFrame#card QLabel#hint {
    color: %(hint)s;
    font-family: "%(family)s";
    font-size: 12px;
}
QFrame#card QPushButton {
    font-family: "%(family)s";
    font-size: 15px;
    font-weight: bold;
    border-radius: 8px;
    padding: 6px 0;
}
QFrame#card QPushButton#minus {
    background: %(minus_bg)s;
    color: %(minus_fg)s;
    border: 1px solid %(minus_border)s;
}
QFrame#card QPushButton#minus:hover { background: %(minus_hover)s; }
QFrame#card QPushButton#plus {
    background: %(plus_bg)s;
    color: %(plus_fg)s;
    border: 1px solid %(plus_border)s;
}
QFrame#card QPushButton#plus:hover { background: %(plus_hover)s; }
QFrame#card QPushButton:pressed {
    background: %(pressed_bg)s;
    color: %(pressed_fg)s;
}
"""


def _score_color(score: int) -> str:
    """分数颜色：正/负/零，跟随主题（深色下用更亮的绿/红保证对比度）。"""
    if score > 0:
        return theme.c("success")
    if score < 0:
        return theme.c("danger")
    return theme.c("text")


class GroupCard(QFrame):
    """一张可选中展开的小组卡片，收起时只显名称和分数，展开后露出按钮。"""

    delta_requested = pyqtSignal(int, int)   # (group_index, delta)
    selected = pyqtSignal(int)               # (group_index)
    rename_requested = pyqtSignal(int)
    reset_requested = pyqtSignal(int)

    BADGE_MS = 1200

    def __init__(self, index: int, group_name: str, score: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._score = score
        self._selected = False
        self._buttons: list[QPushButton] = []
        self._style_key: tuple | None = None
        self._badge_color: str = ""
        self._badge_timer: QTimer | None = None

        self.setObjectName("card")
        self.setFixedHeight(CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        self._build_ui(group_name)

        # 徽标定时器只建一次、永久复用。每次点击都重建 QTimer（且带 Python
        # lambda 连接）会让旧的定时器对象在 C++ 侧和 Python 侧失配，是常见的崩溃来源。
        self._badge_timer = QTimer(self)
        self._badge_timer.setSingleShot(True)
        self._badge_timer.timeout.connect(self._clear_badge)

        self.set_score(score)
        self.set_selected(False)

    # --- 构建界面 ---

    def _build_ui(self, group_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        self._name_label = ElidedLabel(group_name)
        self._name_label.setObjectName("groupName")
        layout.addWidget(self._name_label)

        # 分数行：大数字 + 短暂闪现的 "+2" 徽标
        score_row = QHBoxLayout()
        score_row.setSpacing(4)
        score_row.addStretch()

        self._score_label = QLabel("0")
        self._score_label.setObjectName("score")
        self._score_label.setAlignment(Qt.AlignCenter)
        score_row.addWidget(self._score_label)

        self._badge_label = QLabel("")
        self._badge_label.setObjectName("deltaBadge")
        self._badge_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._badge_label.setFixedWidth(38)
        score_row.addWidget(self._badge_label)

        score_row.addStretch()
        layout.addLayout(score_row)

        layout.addStretch()

        # 操作按钮 —— 卡片展开前隐藏
        self._ops = QWidget()
        ops_layout = QGridLayout(self._ops)
        ops_layout.setContentsMargins(0, 0, 0, 0)
        ops_layout.setSpacing(6)
        for i, delta in enumerate(DELTAS):
            btn = QPushButton(f"-1" if delta < 0 else f"+{delta}")
            btn.setObjectName("minus" if delta < 0 else "plus")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(
                lambda _checked=False, d=delta: self._on_delta(d)
            )
            ops_layout.addWidget(btn, i // 2, i % 2)
            self._buttons.append(btn)
        self._ops.hide()
        layout.addWidget(self._ops)

        self._hint_label = QLabel(tr("点击展开操作", "Click to expand"))
        self._hint_label.setObjectName("hint")
        self._hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint_label)

    # --- 公共接口 ---

    def group_index(self) -> int:
        return self._index

    def set_group_name(self, name: str) -> None:
        self._name_label.setText(name)

    def set_score(self, score: int) -> None:
        self._score = score
        self._score_label.setText(str(score))
        self._apply_style()

    def score(self) -> int:
        return self._score

    def flash(self, delta: int) -> None:
        """在分数旁短暂显示刚应用的增减量。"""
        self._badge_label.setText(f"{delta:+d}")
        color = theme.c("success") if delta > 0 else theme.c("danger")
        if color != self._badge_color:
            self._badge_color = color
            self._badge_label.setStyleSheet(f"color: {color};")
        self._badge_timer.start(self.BADGE_MS)

    def _clear_badge(self) -> None:
        self._badge_label.setText("")

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._ops.setVisible(selected)
        self._hint_label.setVisible(not selected)
        self._apply_style()

    def is_selected(self) -> bool:
        return self._selected

    # --- 事件 ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._index)
            event.accept()
            return
        if event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.rename_requested.emit(self._index)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _on_delta(self, delta: int) -> None:
        # 按钮只在卡片选中时可见，所以这里重发 selected 是多余的，而且会让
        # 六张卡片在每次点击时全部重新套样式，连续加分时给样式引擎造成高频
        # 重刷。只有确实处于未选中态（键盘焦点边界情况）才补发。
        if not self._selected:
            self.selected.emit(self._index)
        self.delta_requested.emit(self._index, delta)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        rename_action = QAction(tr("重命名此组...", "Rename group..."), self)
        rename_action.triggered.connect(lambda: self.rename_requested.emit(self._index))
        menu.addAction(rename_action)

        zero_action = QAction(tr("清零此组积分", "Clear this group"), self)
        zero_action.triggered.connect(lambda: self.reset_requested.emit(self._index))
        menu.addAction(zero_action)

        menu.exec_(pos)

    # --- 样式 ---

    def _apply_style(self) -> None:
        # 只有可见状态真正变化时才重套样式。每次点击都对六张卡片各调一次
        # setStyleSheet 会造成高频重刷，连续加分时可能让 Qt 崩溃；分数数字会变，
        # 但颜色只在正负号切换时变，所以按 (选中态, 颜色) 做缓存。
        key = (self._selected, _score_color(self._score))
        if key == self._style_key:
            return
        self._style_key = key
        self.setStyleSheet(_CARD_QSS % {
            "bg": theme.c("card_selected") if self._selected else theme.c("card"),
            "border": (theme.c("card_border_selected") if self._selected
                       else theme.c("card_border")),
            "name": theme.c("text_strong"),
            "score": _score_color(self._score),
            "badge": theme.c("success"),
            "hint": theme.c("hint"),
            "family": theme.font_family(),
            "minus_bg": theme.c("minus_bg"),
            "minus_fg": theme.c("minus_fg"),
            "minus_border": theme.c("minus_border"),
            "minus_hover": theme.c("minus_hover"),
            "plus_bg": theme.c("plus_bg"),
            "plus_fg": theme.c("plus_fg"),
            "plus_border": theme.c("plus_border"),
            "plus_hover": theme.c("plus_hover"),
            "pressed_bg": theme.c("pressed_bg"),
            "pressed_fg": theme.c("pressed_fg"),
        })


class PointsWindow(QWidget):
    """独立的顶层窗口，容纳全部小组卡片。"""

    SAVE_DEBOUNCE_MS = 400
    MAX_UNDO = 200

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self._store = store
        self._cards: list[GroupCard] = []
        self._selected_index = 0
        self._undo_stack: list[tuple[int, int]] = []   # (group_index, delta)
        self._save_timer: QTimer | None = None
        self._closing = False

        self._init_ui()
        self._load_from_store()

    # --- 构建界面 ---

    def _init_ui(self) -> None:
        self.setWindowTitle(tr("积分管理 — 小组加减分", "Points — group scores"))
        self.setMinimumSize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 顶栏
        header = QHBoxLayout()
        title = QLabel(tr("小组积分", "Group points"))
        title.setFont(theme.font(15, bold=True))
        header.addWidget(title)
        header.addStretch()
        hint = QLabel(tr(
            "单击小组展开操作 · 双击组名可重命名 · 快捷键 1/2/3/4 = -1/+1/+2/+3",
            "Click a group to expand · double-click the name to rename · keys 1/2/3/4 = -1/+1/+2/+3"))
        hint.setStyleSheet(f"color: {theme.c('muted')}; font-size: 12px;")
        header.addWidget(hint)
        layout.addLayout(header)

        # 卡片网格放在滚动区域内。小组数量可配置到 MAX_GROUP_COUNT，
        # 那么多卡片（8 行 × 200px）比任何窗口都高，必须能滚动。
        grid_host = QWidget()
        self._grid = QGridLayout(grid_host)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        # SetMinimumSize 让布局把真实最小高度施加到 grid_host 上。不加的话，
        # 子控件布局不会阻止滚动区域把它压扁到视口高度，多出来的行会被直接
        # 裁掉 —— 没有滚动条，卡片看不到。
        self._grid.setSizeConstraint(QLayout.SetMinimumSize)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(grid_host)
        layout.addWidget(scroll, 1)

        # 底栏
        footer = QHBoxLayout()
        self._undo_btn = QPushButton(tr("撤销 (Ctrl+Z)", "Undo (Ctrl+Z)"))
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self.undo)
        footer.addWidget(self._undo_btn)

        reset_btn = QPushButton(tr("全部清零", "Clear all"))
        reset_btn.clicked.connect(self._on_reset_all)
        footer.addWidget(reset_btn)

        count_btn = QPushButton(tr("小组数量...", "Group count..."))
        count_btn.setToolTip(tr("修改显示的小组数量（会清空所有小组的名称和积分）",
                                "Change the number of groups (clears all names and scores)"))
        count_btn.clicked.connect(self._on_change_group_count)
        footer.addWidget(count_btn)

        # 操作日志的唯一入口：紧挨着「小组数量...」。除此之外程序里没有任何
        # 地方能读到日志（磁盘上只有密文，也没有明文副本）。
        self._log_btn = QPushButton(tr("操作日志", "Log"))
        self._log_btn.setToolTip(tr("查看小组积分变动记录（加密存储，只读，可自动回档）",
                                    "View score changes (encrypted, read-only, auto-restored)"))
        self._log_btn.clicked.connect(self.show_log_viewer)
        footer.addWidget(self._log_btn)

        footer.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {theme.c('muted')}; font-size: 12px;")
        footer.addWidget(self._status_label)

        self._config_label = QLabel("")
        self._config_label.setStyleSheet(f"color: {theme.c('faint')}; font-size: 11px;")
        self._config_label.setToolTip(tr("积分数据保存在此文件中", "Scores are stored in this file"))
        footer.addWidget(self._config_label)

        layout.addLayout(footer)

    def _load_from_store(self) -> None:
        """按当前配置值创建卡片。"""
        self._build_cards()
        self._config_label.setText(tr("配置: {p}", "Config: {p}", p=self._store.path))
        self._set_status(tr("已就绪", "Ready"), ok=True)
        self._select_card(1)

    def _build_cards(self) -> None:
        """为每个小组建一张卡片并连好信号。"""
        for i in range(1, self._store.group_count + 1):
            card = GroupCard(i, self._store.get_group_name(i), self._store.get_score(i))
            card.selected.connect(self._on_card_selected)
            card.delta_requested.connect(self.apply_delta)
            card.rename_requested.connect(self._on_rename)
            card.reset_requested.connect(self._on_reset_one)
            self._grid.addWidget(card, (i - 1) // COLUMNS, (i - 1) % COLUMNS)
            self._cards.append(card)

    def _rebuild_cards(self) -> None:
        """销毁旧卡片、重建一套（小组数量变化后调用）。

        撤销栈一并清空：它存的是 (组下标, 增量)，重建后这些下标不再指向同一批小组。
        """
        for card in self._cards:
            # 先 hide()。可见控件一旦解除父级，就会变成顶层窗口 —— 不加这句，
            # 每张旧卡片都会在新卡片构建期间在屏幕上闪成一个独立小窗。
            card.hide()
            self._grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._undo_stack.clear()
        self._undo_btn.setEnabled(False)
        self._selected_index = 0
        self._build_cards()
        self._select_card(1)

    # --- Public API ---

    def show_and_activate(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event) -> None:
        """显示时套用 macOS 浮层属性：课堂中打开面板加分时，PPT 可能还在全屏。"""
        super().showEvent(event)
        macos_window.make_overlay(self)

    def reload_from_store(self) -> None:
        """从 store 重新读取组名、分数和小组数量。

        用重建而非原地修补：彻底重置会把小组数量打回出厂默认值，卡片数可能变化。
        """
        self._rebuild_cards()
        self._set_status(tr("已重置", "Reset"), ok=True)

    def apply_delta(self, index: int, delta: int) -> None:
        """给小组 index（1 起）加分 delta 并落盘。"""
        card = self._card(index)
        if card is None:
            return

        new_score = card.score() + delta
        self._store.set_score(index, new_score, reason=f"{delta:+d}")
        card.set_score(new_score)
        card.flash(delta)

        self._undo_stack.append((index, delta))
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        self._undo_btn.setEnabled(True)

        self._schedule_save()

    def undo(self) -> None:
        """撤销最近一次操作。"""
        if not self._undo_stack:
            return
        index, delta = self._undo_stack.pop()
        card = self._card(index)
        if card is None:
            return

        new_score = card.score() - delta
        self._store.set_score(index, new_score,
                                  reason=i18n.both("撤销 {d:+d}", "undo {d:+d}", d=delta))
        card.set_score(new_score)
        card.flash(-delta)

        self._undo_btn.setEnabled(bool(self._undo_stack))
        self._schedule_save()

    def save_now(self) -> bool:
        """立即把未落盘的改动写入 config.ini。

        不碰界面：这同时也是 closeEvent 的路径，窗口正在关闭时对控件重套样式
        （setStyleSheet）在快速输入下是 Qt 的崩溃风险。
        """
        if self._save_timer is not None:
            self._save_timer.stop()
        return self._write(update_status=False)

    # --- 内部实现 ---

    def _card(self, index: int) -> GroupCard | None:
        if 1 <= index <= len(self._cards):
            return self._cards[index - 1]
        return None

    def _select_card(self, index: int) -> None:
        if self._card(index) is None:
            return
        self._selected_index = index
        for card in self._cards:
            card.set_selected(card.group_index() == index)

    def _on_card_selected(self, index: int) -> None:
        self._select_card(index)

    def _on_rename(self, index: int) -> None:
        card = self._card(index)
        if card is None:
            return
        current = self._store.get_group_name(index)
        name, ok = QInputDialog.getText(
            self, tr("重命名小组", "Rename group"), tr("新的小组名称:", "New group name:"),
            text=current
        )
        if not ok:
            return
        name = name.strip()
        if not name or name == current:
            return
        self._store.set_group_name(index, name)
        card.set_group_name(self._store.get_group_name(index))
        self._schedule_save()

    def _on_reset_one(self, index: int) -> None:
        card = self._card(index)
        if card is None:
            return
        name = self._store.get_group_name(index)
        reply = QMessageBox.question(
            self, tr("确认", "Confirm"),
            tr("确定要把「{n}」的积分清零吗？", "Clear the score of \"{n}\"?", n=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._store.set_score(index, 0,
                                  reason=i18n.both("清零此组", "clear group"))
        card.set_score(0)
        self._schedule_save()

    def _on_reset_all(self) -> None:
        reply = QMessageBox.question(
            self, tr("确认", "Confirm"),
            tr("确定要把所有小组的积分清零吗？此操作不可撤销。",
               "Clear all group scores? This cannot be undone."),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._store.reset_scores(reason=i18n.both("全部清零", "clear all"))
        for card in self._cards:
            card.set_score(0)
        self._undo_stack.clear()
        self._undo_btn.setEnabled(False)
        self._schedule_save()

    def _on_change_group_count(self) -> None:
        """修改显示的小组数量，会清空所有小组的名称和分数。

        分两步（先选数字、再确认）：小组数量一学期最多改一次，若做成紧挨
        「全部清零」的一键控件，太容易误点。分数被清掉不是附带损失：换了
        组数就是换了一套分组，旧分数没有可挂靠的小组。
        """
        current = len(self._cards)
        count, ok = QInputDialog.getInt(
            self, tr("小组数量", "Group count"), tr("显示几个小组？", "How many groups?"),
            current, MIN_GROUP_COUNT, MAX_GROUP_COUNT, 1,
        )
        if not ok or count == current:
            return

        reply = QMessageBox.question(
            self, tr("确认", "Confirm"),
            tr("改为 {n} 个小组？\n\n所有小组的名称和积分都会被清空。",
               "Switch to {n} groups?\n\nAll group names and scores will be cleared.",
               n=count),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        applied = self._store.set_group_count(count)
        self._rebuild_cards()
        self._schedule_save()
        self._set_status(tr("已改为 {n} 个小组", "Now {n} groups", n=applied), ok=True)

    def _schedule_save(self) -> None:
        """把快速连点合并成一次写入。"""
        self._set_status(tr("保存中...", "Saving..."), ok=True)
        if self._save_timer is None:
            # 只建一次、永久复用 —— 不要每次点击都重建 QTimer。
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._on_save_timeout)
        self._save_timer.start(self.SAVE_DEBOUNCE_MS)

    def _on_save_timeout(self) -> None:
        if self._closing:
            return  # 窗口正在关闭，save_now() 已经写过数据
        self._write(update_status=True)

    def _write(self, update_status: bool = True) -> bool:
        ok = self._store.save()
        if update_status and not self._closing:
            if ok:
                self._set_status(tr("已保存", "Saved"), ok=True)
            else:
                self._set_status(tr("保存失败: {e}", "Save failed: {e}", e=self._store.last_error()), ok=False)
        return ok

    def _set_status(self, text: str, ok: bool = True) -> None:
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {theme.c('muted')}; font-size: 12px;" if ok
            else f"color: {theme.c('danger')}; font-size: 12px; font-weight: bold;"
        )

    # --- 事件 ---

    def keyPressEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Z:
            self.undo()
            event.accept()
            return
        delta = DELTA_KEYS.get(event.key())
        if delta is not None and self._selected_index:
            self.apply_delta(self._selected_index, delta)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        # 落盘未保存的分数改动，不做界面操作（见 save_now）。
        self._closing = True
        self.save_now()
        event.accept()

    # --- 操作日志（唯一查看入口）---

    def show_log_viewer(self) -> None:
        """打开只读的操作日志查看器。

        这是全程序读取操作日志的唯一入口：日志只有密文落盘（没有明文副本），
        也不出现在托盘菜单或管理面板里。
        """
        dialog = _LogViewerDialog(self._store.path, self)
        dialog.exec_()


class _LogViewerDialog(QDialog):
    """操作日志查看器：只读，最新记录在最上面。"""

    def __init__(self, config_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("操作日志 — 只读", "Operation log — read-only"))
        self.setMinimumSize(660, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        view = log_store.load(config_path)
        entries = list(reversed(view.entries))   # 最新的排在最前面

        if view.entries:
            title_text = tr("共 {n} 条记录", "{n} entries", n=len(view.entries))
            if view.seq > len(view.entries):
                title_text += tr(
                    "（历史累计 {s} 条，只保留最近 {n} 条）",
                    " ({s} total, showing the latest {n})",
                    s=view.seq, n=len(view.entries))
        else:
            title_text = tr("暂无记录", "No entries yet")
        title = QLabel(title_text)
        title.setFont(theme.font(12, bold=True))
        layout.addWidget(title)

        # 数据来源与自动回档提示
        source_names = {
            "main": tr("加密主文件", "encrypted main file"),
            "bak": tr("同目录加密备份", "encrypted .bak"),
            "hidden": tr("系统级隐蔽备份", "system-level hidden backup"),
            "empty": tr("无", "none"),
        }
        info = QLabel(
            tr("加密保存于 {p}", "Encrypted at {p}",
               p=log_store.log_path_for(config_path))
            + tr("（另有同目录 .bak 与系统级隐蔽备份，可自动回档）",
                " (plus a .bak and a system-level hidden backup for auto-restore)")
            + "\n" + tr("本次读取自：{s}", "Read from: {s}",
                          s=source_names.get(view.source, view.source))
        )
        if view.source in ("bak", "hidden"):
            info.setText(info.text() + "\n" + tr(
                "⚠ 主日志被篡改、丢失或回滚过，已自动从更新的一份副本恢复。",
                "⚠ The main log was tampered with, lost or rolled back; restored from a newer copy."))
        info.setStyleSheet(f"color: {theme.c('muted')}; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        # 深色模式下必须同时设 color，否则 QPlainTextEdit 会继承系统浅色文字，
        # 落在浅色背景上几乎看不见（这就是「深色模式字体观感差」最严重的一处）。
        text.setStyleSheet(
            f"background: {theme.c('log_bg')}; color: {theme.c('text')};"
            f" border: 1px solid {theme.c('view_border')};"
        )
        if entries:
            lines = []
            for stamp, zh, en in entries:
                # 双语条目：中文一行，英文紧跟在下一行；老记录只有一段文本
                lines.append(f"[{stamp}] {zh}")
                if en and en != zh:
                    lines.append(f"           {en}")
            text.setPlainText("\n".join(lines))
        else:
            text.setPlainText(tr(
                "还没有任何积分变动记录。\n每次加分 / 减分 / 撤销 / 清零 / 改组数都会自动记一条。",
                "No score changes yet.\nEvery add / subtract / undo / clear / group-count change is logged."))
        layout.addWidget(text, 1)

        tip = QLabel(tr(
            "日志只增不减：修改或删除都会被下一份副本修回来，「彻底重置」也不会清空它。",
            "The log is append-only: edits or deletions are repaired from a copy, and even a full reset keeps it."))
        tip.setStyleSheet(f"color: {theme.c('faint')}; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_btn = QPushButton(tr("关闭", "Close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
