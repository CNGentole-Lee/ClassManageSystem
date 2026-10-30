"""win_window —— Windows 上让对话框不被全屏应用盖住。

背景（真实故障）：
    macOS 靠 ``macos_window.install_dialog_raiser()`` 把所有 QDialog 抬到
    NSStatusWindowLevel(26)，所以「关于」「彻底重置」能显示在全屏 PPT 之上。
    Windows 之前没有对应机制：悬浮球是 WS_EX_TOPMOST，PPT 全屏在最前，
    而 QDialog 只是普通窗口 —— 于是对话框被开在全屏应用**后面**，
    用户看到的现象就是「点了没弹出窗口」。

这里补上 Windows 版：任何 QDialog 显示时执行
    SetWindowPos(HWND_TOPMOST) + SetForegroundWindow
并在鼠标所在屏幕居中（配合 dialogs.center_on_screen）。

所有调用都包在 try/except 里：拿不到 user32 时静默跳过，不影响程序运行。
"""

from __future__ import annotations

import ctypes
import sys

HWND_TOPMOST = -1

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

_user32 = None

#: 事件过滤器必须有人持有（模块级引用），否则会被 Python GC 回收
_raiser = None


def _load_user32():
    """惰性加载 user32 并设置函数签名；非 Windows 返回 None。"""
    global _user32
    if _user32 is not None:
        return _user32
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.windll.user32
        user32.SetWindowPos.restype = ctypes.c_bool
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetForegroundWindow.restype = ctypes.c_bool
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.BringWindowToTop.restype = ctypes.c_bool
        user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _user32 = user32
        return user32
    except Exception:
        return None


def is_topmost(widget) -> bool:
    """窗口当前是否带 WS_EX_TOPMOST（自检与测试用）。"""
    user32 = _load_user32()
    if user32 is None:
        return False
    try:
        style = user32.GetWindowLongW(ctypes.c_void_p(int(widget.winId())),
                                      GWL_EXSTYLE)
        return bool(style & WS_EX_TOPMOST)
    except Exception:
        return False


def make_topmost(widget, activate: bool = True) -> bool:
    """把窗口钉到 topmost 层并（可选）拉到前台。"""
    user32 = _load_user32()
    if user32 is None:
        return False
    try:
        hwnd = ctypes.c_void_p(int(widget.winId()))
        ok = user32.SetWindowPos(
            hwnd, ctypes.c_void_p(HWND_TOPMOST),
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
        )
        if activate:
            # 前台锁可能拒绝，失败也无所谓：topmost 已经能保证可见
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        return bool(ok)
    except Exception:
        return False


class _DialogRaiser:
    """安装应用级事件过滤器，把每个显示出来的 QDialog 置顶并居中。"""

    def install(self, app) -> bool:
        global _raiser
        if sys.platform != "win32":
            return False
        try:
            from PySide6.QtCore import QEvent, QObject, QTimer
            from PySide6.QtWidgets import QDialog

            from . import dialogs

            def raise_dialog(obj, center: bool = False) -> None:
                try:
                    if not isinstance(obj, QDialog) or not obj.isVisible():
                        return
                    make_topmost(obj, activate=True)
                    if center:
                        dialogs.center_on_screen(obj)
                    obj.raise_()
                except (RuntimeError, AttributeError):
                    pass      # 对话框已经销毁

            class _Filter(QObject):
                def eventFilter(inner, obj, event):      # noqa: N805
                    try:
                        kind = event.type()
                        if kind == QEvent.Show:
                            # Qt 显示之后还会调整 z-order/几何，延后一拍再处理。
                            #
                            # 不在 WindowActivate 时再抬：对话框弹出自己的二次
                            # 确认框会触发 WindowActivate，raise() 会把父对话框
                            # 盖到确认框上，表现为「点了重置没反应」。
                            QTimer.singleShot(
                                0, lambda o=obj: raise_dialog(o, center=True))
                    except Exception:
                        pass
                    return False

            self._filter = _Filter(app)
            self._filter.setObjectName("cmd_dialog_raiser")
            app.installEventFilter(self._filter)
            _raiser = self
            return True
        except Exception:
            return False


def install_dialog_raiser(app) -> bool:
    """让 Windows 上的对话框显示在全屏应用之上（仅 Windows 生效）。"""
    inst = _DialogRaiser()
    return inst.install(app)
