"""旧数据升级提示弹窗 —— 检测到 3.x 链时告诉老师要手动重录。

为什么单独做：
    旧链格式与 4.0 不兼容，程序不会改写它，只是把组名/分数留在 config.ini
    让老师重录。以前只有状态栏一行字，太容易错过 —— 老师会以为"数据丢了"。
    这里用一个必须停留 10 秒的弹窗，确保说明被看到。

三条硬要求：
    1. 中英文双语同时显示（不是切换语言只显示一种）；
    2. 关闭按钮至少 10 秒后才可用，倒计时可见；
    3. 只弹一次 —— 用 QSettings 记住，重启也不再弹。
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
)

#: QSettings 里记住"已提示过"的键。与语言设置同一个命名空间。
_SETTINGS_ORG = "NamePicker"
_SETTINGS_APP = "Config"
SEEN_KEY = "legacy_notice_shown"

#: 关闭按钮多少秒后可用
WAIT_SECONDS = 10


def _settings() -> QSettings:
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


def has_shown(settings: QSettings | None = None) -> bool:
    """是否已经弹过（持久化，重启也记得）。"""
    store = settings if settings is not None else _settings()
    try:
        return bool(store.value(SEEN_KEY, False))
    except Exception:                                  # noqa: BLE001
        return False


def mark_shown(settings: QSettings | None = None) -> None:
    """标记已弹过，之后不再打扰。"""
    store = settings if settings is not None else _settings()
    try:
        store.setValue(SEEN_KEY, True)
        store.sync()
    except Exception:                                  # noqa: BLE001
        pass


class LegacyDataDialog(QDialog):
    """双语、10 秒倒计时、只弹一次的升级提示。"""

    def __init__(self, parent=None, wait_seconds: int = WAIT_SECONDS):
        super().__init__(parent)
        self._wait = max(0, int(wait_seconds))
        self._left = self._wait
        self.setWindowTitle("数据升级提示 / Data upgrade notice")
        self.setModal(True)

        layout = QVBoxLayout(self)
        zh = QLabel(
            "⚠ 检测到旧版本（3.x）的数据\n\n"
            "4.0 的数据结构变了，为了不破坏原始数据，程序没有改写旧文件，"
            "因此暂时读不到小组名称与分数。\n"
            "请在「预设」里按旧的 config.ini 手动重新录入一次组名与分数。"
            "名单会正常保留，只需要重录组名和分数。\n"
            "原文件已保留在 Data/ledger.esc。"
        )
        zh.setWordWrap(True)
        en = QLabel(
            "⚠ Data from an older version (3.x) was found\n\n"
            "The 4.0 data format changed. To avoid damaging the original data, the app "
            "did not rewrite the old chain, so group names and scores cannot be read "
            "for now.\n"
            "Please re-enter the group names and scores once under Profiles, using the "
            "values from your old config.ini. The name list is preserved — only names "
            "and scores need re-entering.\n"
            "The original file is kept at Data/ledger.esc."
        )
        en.setWordWrap(True)
        layout.addWidget(zh)
        layout.addWidget(en)

        row = QHBoxLayout()
        row.addStretch()
        self._button = QPushButton()
        self._button.setEnabled(self._wait <= 0)
        self._button.clicked.connect(self.accept)
        row.addWidget(self._button)
        layout.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._update_label()
        if self._wait > 0:
            self._timer.start()

    def _update_label(self) -> None:
        """按钮文案同时给中英倒计时，符合双语要求。"""
        if self._left <= 0:
            self._button.setText("我知道了 / OK")
        else:
            self._button.setText(
                f"请阅读 {self._left}s / Please read ({self._left}s)")

    def _tick(self) -> None:
        self._left -= 1
        if self._left <= 0:
            self._timer.stop()
            self._button.setEnabled(True)
        self._update_label()

    def seconds_left(self) -> int:
        """供测试查询剩余秒数。"""
        return self._left

    def can_close(self) -> bool:
        """供测试查询当前是否允许关闭。"""
        return self._button.isEnabled()
