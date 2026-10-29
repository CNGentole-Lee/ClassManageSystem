"""无头/CI 环境下的模态框防护。

问题背景：
    测试脚本会触发真实业务逻辑，而业务逻辑里可能有 QMessageBox.question /
    information / warning。CI（以及 `QT_QPA_PLATFORM=offscreen`）没有人能点
    「确定」，进程就会永久阻塞在 exec() 上 —— 表现为「测试卡死」。

用法（在创建 QApplication 之前调用一次）：
    from _headless import install
    install()

之后所有静态对话框调用都会立刻返回默认按钮；需要特定返回值的用例可以在
自己那段代码里临时覆盖，恢复时会回到这里的默认值。
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

_DEFAULTS = ("question", "information", "warning", "critical")


def install(question=QMessageBox.No, warning=QMessageBox.No) -> None:
    """把 QMessageBox 的四个静态方法替换成立即返回的版本。"""
    QMessageBox.question = staticmethod(lambda *a, **k: question)
    QMessageBox.warning = staticmethod(lambda *a, **k: warning)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
