"""WipeDialog —— 彻底重置前的「选择清空范围」对话框。

流程：勾选要清空的内容 → 点“重置” → **二次确认**列出将清空的项 → 执行。

为什么拆成两步：
    重置不可撤销，而四项数据的性质不同（组名是老师辛苦起的、积分是当堂课的成绩、
    长期公平记录影响一学期、抽取历史只影响今天）。给老师逐项选择，比一刀切安全。

操作日志**永远不清空**：审计记录不能被一个按钮抹掉，重置本身会追加一条记录。
"""


from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout,
)

from . import dialogs, theme
from .i18n import tr

#: 四个可选项 → (中文, English)
PARTS = (
    ("names", "组名", "Group names"),
    ("scores", "积分", "Scores"),
    ("fairness", "长期公平记录", "Lifetime fairness counts"),
    ("history", "抽取历史与冷却", "Draw history and cooldowns"),
)


class WipeDialog(QDialog):
    """选择要清空的内容；确认后返回选中项。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("彻底重置", "Full reset"))
        self.setMinimumWidth(420)
        self._boxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        intro = QLabel(tr("选择要清空的内容（可多选）：", "Choose what to clear (multiple allowed):"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        for key, zh, en in PARTS:
            box = QCheckBox(tr(zh, en))
            box.setChecked(True)          # 默认全选，保持原来「彻底重置」的行为
            layout.addWidget(box)
            self._boxes[key] = box

        note = QLabel(tr("操作日志不会被清空，重置本身也会记录一条日志。",
                         "The operation log is never cleared; this reset itself is logged."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.c('faint')}; font-size: 12px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox()
        self._ok = buttons.addButton(tr("重置", "Reset"), QDialogButtonBox.AcceptRole)
        self._cancel = buttons.addButton(tr("取消", "Cancel"), QDialogButtonBox.RejectRole)
        self._ok.setStyleSheet(
            f"background: {theme.c('danger')}; color: {theme.c('accent_text')};")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # --- 查询 ---

    def showEvent(self, event) -> None:
        """显示时按鼠标所在屏幕居中（父窗口可能在屏幕外）。"""
        super().showEvent(event)
        dialogs.center_on_screen(self)

    def selected(self) -> dict[str, bool]:
        """{names: bool, scores: bool, fairness: bool, history: bool}"""
        return {key: box.isChecked() for key, box in self._boxes.items()}

    def selected_labels(self) -> list[str]:
        """被勾选项的显示名（用于二次确认）。"""
        return [tr(zh, en) for key, zh, en in PARTS if self._boxes[key].isChecked()]

    # --- 二次确认 ---

    def accept(self) -> None:
        chosen = self.selected_labels()
        if not chosen:
            QMessageBox.information(
                self,
                tr("提示", "Notice"),
                tr("请至少选择一项。", "Select at least one item."),
            )
            return

        body = tr(
            "即将清空以下内容：\n\n  · {items}\n\n此操作不可撤销，确定继续吗？",
            "The following will be cleared:\n\n  · {items}\n\nThis cannot be undone. Continue?",
            items="\n  · ".join(chosen),
        )
        reply = QMessageBox.warning(
            self,
            tr("确认重置", "Confirm reset"),
            body,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            super().accept()


def ask(parent=None) -> dict[str, bool] | None:
    """弹出对话框；用户确认返回选中项，取消返回 None。

    父窗口不可见（主窗口藏在托盘 / 最小化）时改用 None —— Windows 上最小化
    窗口的矩形在屏幕外，拿它做基准会让对话框也跑到屏幕外。
    """
    dialog = WipeDialog(dialogs.visible_parent(parent))
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected()
    return None
