"""widgets —— 共用的小控件。

ElidedLabel
-----------
小组名、抽中结果都可能是很长的外国人名（"Bartholomew Montgomery-Fitzgerald"）。
固定宽度的卡片/弹窗格子里直接 `setText` 会把文字顶出边界或被硬裁一半，
所以统一用这个 Label：按当前宽度做省略（"…"），完整文本放进 tooltip，
鼠标悬停还能看到全名。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """按宽度自动省略的 QLabel（完整文本见 tooltip）。"""

    def __init__(self, text: str = "", parent=None, mode=Qt.ElideRight):
        super().__init__(parent)
        self._full_text = ""
        self._mode = mode
        self.setAlignment(Qt.AlignCenter)
        self.setText(text)

    # --- 公共接口 ---

    def full_text(self) -> str:
        """未省略的原始文本。"""
        return self._full_text

    def setText(self, text: str) -> None:  # noqa: N802 (Qt 命名)
        self._full_text = "" if text is None else str(text)
        self.setToolTip(self._full_text if self._is_long() else "")
        self._update_elided()

    # --- 内部 ---

    def _is_long(self) -> bool:
        return len(self._full_text) > 6

    def _update_elided(self) -> None:
        width = self.width()
        if width <= 0:                       # 还没布局，先原样显示
            super().setText(self._full_text)
            return
        self.ensurePolished()
        metrics = self.fontMetrics()
        available = max(0, width - 4)
        if metrics.horizontalAdvance(self._full_text) <= available:
            super().setText(self._full_text)
            return
        super().setText(metrics.elidedText(self._full_text, self._mode, available))
        self.setToolTip(self._full_text)

    def resizeEvent(self, event) -> None:   # noqa: N802
        super().resizeEvent(event)
        self._update_elided()

    def changeEvent(self, event) -> None:   # noqa: N802
        """字体/样式变化后重新计算省略。"""
        super().changeEvent(event)
        self._update_elided()
