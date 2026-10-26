"""dialogs —— 对话框定位与显示的统一工具。

为什么需要：
    「彻底重置」「关于」这类对话框既可能从主窗口打开，也可能从**托盘菜单**或
    **悬浮球右键菜单**打开。后两种情况下主窗口往往已经隐藏到托盘（甚至最小化），
    而 Windows 上最小化窗口的矩形是 (-32000, -32000) —— 以它为基准居中的对话框
    会被摆到屏幕外，用户看到的就是「点了没反应」。

    所以这里统一做三件事：
      1. 父窗口不可见/最小化时改用 None，不拿它的几何做参考；
      2. 按**鼠标所在屏幕**居中（多显示器时不会跑到另一块屏）；
      3. 菜单动作里弹出的对话框延后一拍，等 QMenu 的事件循环退出后再显示。
"""

from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication


def visible_parent(parent=None):
    """父窗口可见就返回它，否则返回 None（避免用屏幕外的几何定位）。"""
    if parent is None:
        return None
    try:
        if parent.isVisible() and not parent.isMinimized():
            return parent
    except (RuntimeError, AttributeError):
        pass
    return None


def screen_for_cursor():
    """鼠标所在的屏幕；取不到时退回主屏。"""
    try:
        screen = QApplication.screenAt(QCursor.pos())
    except Exception:
        screen = None
    return screen or QApplication.primaryScreen()


def center_on_screen(widget) -> None:
    """把窗口移到鼠标所在屏幕的中央。"""
    screen = screen_for_cursor()
    if screen is None:
        return
    available = screen.availableGeometry()
    size = widget.frameSize() if widget.isVisible() else widget.sizeHint()
    if size.width() <= 0 or size.height() <= 0:
        size = widget.minimumSize()
    x = available.left() + (available.width() - size.width()) // 2
    y = available.top() + (available.height() - size.height()) // 2
    widget.move(x, y)


def reveal(widget) -> None:
    """显示并置前（非模态窗口用）。"""
    center_on_screen(widget)
    widget.show()
    widget.raise_()
    widget.activateWindow()


def defer(callback) -> None:
    """延后到当前事件循环结束后再执行。

    菜单（QMenu.exec_）还在自己的嵌套事件循环里时直接开模态对话框，
    Windows 上容易出现对话框不激活、被菜单压住的情况。
    """
    QTimer.singleShot(0, callback)
