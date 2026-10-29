"""macos_window —— macOS 窗口层：激活策略与「全屏也压不住」的浮层。

为什么需要单独一个模块
----------------------
要让悬浮球盖在**别的 App 的原生全屏 Space** 上，需要同时满足两件事：

1. **应用必须是 accessory 激活策略**（`NSApplicationActivationPolicyAccessory`，
   即打包时的 `LSUIElement=True`）。regular 应用自己占着一个桌面 Space，
   切到别人的全屏 Space 后它的窗口不在那儿；accessory 应用不占 Space，
   窗口才能加入当前（全屏）Space。这一点用
   `CGWindowListCopyWindowInfo(onScreenOnly)` 实测过：
   regular 时全屏 App 根本不在当前 Space 列表里，浮层留在桌面；
   accessory 时全屏 App 与浮层同时出现在列表里。

2. **窗口属性**：`CanJoinAllSpaces | Stationary | FullScreenAuxiliary`、
   `level = NSStatusWindowLevel(25)`、`hidesOnDeactivate = NO`、`canHide = NO`，
   并在显示后 `orderFrontRegardless`。

代价：accessory 应用**没有 Dock 图标**（Alfred / Raycast 就是这样）。
本程序的入口是悬浮球与菜单栏图标，因此不受影响；若想要 Dock 图标，
就只能退回 regular 策略，同时放弃全屏覆盖能力。

全部实现都包在 try/except 里：任何一步失败都只是「没有增强」，不影响程序运行。
"""

import ctypes
import ctypes.util
import sys

# --- NSWindowCollectionBehavior ---
NS_CAN_JOIN_ALL_SPACES = 1 << 0
NS_STATIONARY = 1 << 4
NS_FULL_SCREEN_AUXILIARY = 1 << 8

# --- NSScreen 层级 ---
NS_STATUS_WINDOW_LEVEL = 25      # 状态栏层级：高于普通窗口与全屏窗口
NS_SCREEN_SAVER_LEVEL = 1000     # 屏保层级：更高，代价是会盖住菜单栏

#: 浮层默认层级。25 已实测可进入全屏 Space；如需更强可改 1000。
DEFAULT_LEVEL = NS_STATUS_WINDOW_LEVEL

#: 对话框层级：必须高于积分面板/弹窗的 25，否则会被面板盖住（表现为「假死」）
DIALOG_LEVEL = NS_STATUS_WINDOW_LEVEL + 1

#: NSApplicationActivationPolicy
POLICY_REGULAR = 0
POLICY_ACCESSORY = 1

_objc = None


def _is_cocoa() -> bool:
    """当前 Qt 平台插件是不是 cocoa。

    必须是 cocoa 才有真实的 NSView/NSWindow；offscreen（CI、截图脚本）下
    winId() 不是 NSView，拿它去发 objc 消息会直接段错误。
    """
    try:
        from PySide6.QtGui import QGuiApplication
        return str(QGuiApplication.platformName()).startswith("cocoa")
    except Exception:
        return False

#: 事件过滤器必须有人持有，否则会被 Python GC 掉（Qt 的 parent 只管 C++ 侧）
_dialog_raiser = None


def _objc_lib():
    """惰性加载 libobjc 并缓存常用函数。"""
    global _objc
    if _objc is not None:
        return _objc
    if sys.platform != "darwin":
        return None
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        _objc = objc
        return objc
    except Exception:
        return None


def ffi_sel(name: bytes):
    objc = _objc_lib()
    return objc.sel_registerName(name) if objc else None


def _class(name: bytes):
    objc = _objc_lib()
    return objc.objc_getClass(name) if objc else None


def _msg(obj, name: bytes, restype=ctypes.c_void_p, argtypes=None, *args):
    objc = _objc_lib()
    if objc is None:
        return None
    msg = objc.objc_msgSend
    msg.restype = restype
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + (argtypes or [])
    return msg(ctypes.c_void_p(obj), ffi_sel(name), *args)


def ns_app():
    """`[NSApplication sharedApplication]`（Qt 子类 QNSApplication 同样适用）。

    注意：`sharedApplication` 是**类方法**，接收者必须是 NSApplication 类对象，
    对 nil 发这个消息会返回 nil —— 之前就是这里写错，导致策略设置静默失效。
    """
    return _msg(_class(b"NSApplication"), b"sharedApplication")


def set_accessory_policy() -> bool:
    """把应用切到 accessory 策略：不占 Space、没有 Dock 图标。

    返回是否设置成功。非 macOS 直接返回 False。
    """
    if sys.platform != "darwin":
        return False
    try:
        app = ns_app()
        if not app:
            return False
        _msg(app, b"setActivationPolicy:", ctypes.c_bool,
             [ctypes.c_long], ctypes.c_long(POLICY_ACCESSORY))
        return activation_policy() == POLICY_ACCESSORY
    except Exception:
        return False


def activation_policy() -> int:
    """当前激活策略：0=regular，1=accessory。非 macOS 返回 -1。"""
    try:
        app = ns_app()
        if not app:
            return -1
        value = _msg(app, b"activationPolicy", ctypes.c_long)
        return int(value) if value is not None else -1
    except Exception:
        return -1


def set_regular_policy() -> bool:
    """切回 regular（有 Dock 图标；会失去全屏覆盖能力）。"""
    try:
        app = ns_app()
        if not app:
            return False
        _msg(app, b"setActivationPolicy:", ctypes.c_bool,
             [ctypes.c_long], ctypes.c_long(POLICY_REGULAR))
        return activation_policy() == POLICY_REGULAR
    except Exception:
        return False


def ns_window(widget):
    """拿到 QWidget 底层的 NSWindow 指针（没有则为 0）。"""
    try:
        view = int(widget.winId())
        return _msg(view, b"window")
    except Exception:
        return 0


def make_overlay(widget, level: int = DEFAULT_LEVEL) -> bool:
    """把窗口配成「全屏也压不住」的浮层。返回是否成功。"""
    if sys.platform != "darwin" or not _is_cocoa():
        return False
    try:
        window = ns_window(widget)
        if not window:
            return False

        # 1) 加入所有 Space + 全屏共存 + 切 Space 不跟动画
        _msg(window, b"setCollectionBehavior:", None,
             [ctypes.c_ulong],
             ctypes.c_ulong(NS_CAN_JOIN_ALL_SPACES
                            | NS_STATIONARY
                            | NS_FULL_SCREEN_AUXILIARY))
        # 2) 层级
        _msg(window, b"setLevel:", None, [ctypes.c_long], ctypes.c_long(level))
        # 3) 切到别的 App 时不被收起/隐藏
        _msg(window, b"setHidesOnDeactivate:", None, [ctypes.c_bool], ctypes.c_bool(False))
        _msg(window, b"setCanHide:", None, [ctypes.c_bool], ctypes.c_bool(False))
        # 4) 不抢焦点也显示到最前
        _msg(window, b"orderFrontRegardless")
        return True
    except Exception:
        return False


def bring_to_front(widget, level: int = DEFAULT_LEVEL) -> bool:
    if sys.platform != "darwin" or not _is_cocoa():
        return False
    """重新应用浮层属性并置前（窗口显示/隐藏后调用）。

    不用 `NSApp.activate`：那会抢走 PPT 的焦点，反而把全屏 App 切走。
    """
    if not make_overlay(widget, level):
        return False
    try:
        window = ns_window(widget)
        _msg(window, b"orderFrontRegardless")
        return True
    except Exception:
        return False


class _DialogRaiser:
    """把所有 QDialog 抬到浮层之上（macOS）。

    背景：积分面板/结果弹窗被设成 level 25（NSStatusWindowLevel）才能盖住全屏
    PPT，但 QInputDialog / QMessageBox 这些普通对话框是 level 0 —— 于是被面板
    盖在下面，而模态框还在等点击，用户看到的就是「点了没反应 / 假死」。

    这里装一个应用级事件过滤器：任何 QDialog 显示时，把它也配成浮层（level 26，
    高于面板）并置前。集中一处，改名、改组数、确认框、日志查看器全覆盖。
    """

    def __init__(self):
        self._filter = None

    def install(self, app) -> bool:
        global _dialog_raiser
        if sys.platform != "darwin":
            return False
        try:
            from PySide6.QtCore import QObject, QEvent

            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QDialog

            def raise_dialog(obj) -> None:
                try:
                    if not isinstance(obj, QDialog) or not obj.isVisible():
                        return
                    # 关于窗口自己要低于抽选弹窗，这里跳过
                    if obj.property("cmd_skip_raise"):
                        return
                    make_overlay(obj, DIALOG_LEVEL)
                    obj.raise_()
                except (RuntimeError, AttributeError):
                    pass          # 对话框已经销毁

            class _Filter(QObject):
                def eventFilter(inner, obj, event):      # noqa: N805
                    try:
                        kind = event.type()
                        if kind == QEvent.Show:
                            # Qt 在 Show 之后还会把父窗口的 level 传播给子窗口，
                            # 所以必须等这一轮事件处理完再抬一次。
                            #
                            # 不要在 WindowActivate 时再抬：对话框弹出**自己的
                            # 二次确认框**时会收到 WindowActivate，此时 raise()
                            # 会把父对话框盖到确认框上面，看起来就是「点了重置
                            # 没反应」（确认框被挡住，父框还在等）。
                            QTimer.singleShot(0, lambda o=obj: raise_dialog(o))
                    except Exception:
                        pass
                    return False

            self._filter = _Filter(app)
            app.installEventFilter(self._filter)
            _dialog_raiser = self              # 模块级引用，防止被 GC 回收
            return True
        except Exception:
            return False


def install_dialog_raiser(app) -> bool:
    """让所有对话框都显示在积分面板/结果弹窗之上（仅 macOS 生效）。"""
    raiser = _DialogRaiser()
    return raiser.install(app)


def window_attrs(widget) -> dict | None:
    """读取 NSWindow 的关键属性（自检工具用）。"""
    if sys.platform != "darwin" or not _is_cocoa():
        return None
    try:
        window = ns_window(widget)
        if not window:
            return None
        return {
            "level": int(_msg(window, b"level", ctypes.c_long)),
            "behavior": int(_msg(window, b"collectionBehavior", ctypes.c_ulong)),
            "hides_on_deactivate": bool(_msg(window, b"hidesOnDeactivate", ctypes.c_bool)),
            "can_hide": bool(_msg(window, b"canHide", ctypes.c_bool)),
            "on_active_space": bool(_msg(window, b"isOnActiveSpace", ctypes.c_bool)),
        }
    except Exception:
        return None
