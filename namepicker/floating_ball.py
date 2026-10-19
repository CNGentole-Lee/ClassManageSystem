"""FloatingBall —— 屏幕边缘可拖动的小圆球，用于随机抽名字。"""

import ctypes
import sys

from PyQt5.QtCore import (
    Qt, QPoint, QTimer, pyqtSignal
)
from PyQt5.QtGui import (
    QPainter, QBrush, QColor, QFont, QPen, QMouseEvent
)
from PyQt5.QtWidgets import QWidget, QApplication, QMenu, QAction

from . import theme


# --- 强制置顶（跨平台）-------------------------------------------------
#
# Qt 的 WindowStaysOnTopHint 只保证「同一桌面内高于普通窗口」，两个平台都还有
# 各自的一道坎，所以要分别补刀；置顶只是增强，任何一步失败都静默跳过。
#
#   Windows：全屏应用会把普通置顶窗口压住，需要 SetWindowPos(HWND_TOPMOST)
#            把窗口钉进 topmost 层。
#   macOS  ：Qt.Tool 会变成 NSPanel，默认 hidesOnDeactivate=YES，程序一失焦
#            （老师切到 PPT）整个球会被系统隐藏；全屏应用还各自占一个 Space，
#            普通浮动窗口不会跟过去。前者在 _init_ui 里用
#            Qt.WA_MacAlwaysShowToolWindow 关掉，后者在这里设置
#            NSWindowCollectionBehavior。

# --- Windows ---
_HWND_TOPMOST = -1
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010

# 历史坑：原来这里写的是 ctypes.windll... 然后 _HWND = ctypes.wintypes.HWND。
# `import ctypes` 并不会带出 wintypes 子模块，于是第 20 行抛 AttributeError，
# 被下面那个宽松的 except 吞掉 → _SetWindowPos = None → Windows 上的强制置顶
# 一直是空操作（除非某个库碰巧先 import 了 ctypes.wintypes）。
# 现在直接用 ctypes.c_void_p 传 HWND，彻底不依赖 wintypes。
_SetWindowPos = None
if sys.platform == "win32":
    try:
        _SetWindowPos = ctypes.windll.user32.SetWindowPos
        _SetWindowPos.restype = ctypes.c_bool
        _SetWindowPos.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint,
        ]
    except Exception:
        _SetWindowPos = None

# --- macOS ---
# NSWindowCollectionBehavior 位值（AppKit 定义）
_NS_CAN_JOIN_ALL_SPACES = 1 << 0      # 出现在所有 Space（含其它 App 的全屏空间）
_NS_STATIONARY = 1 << 4               # 切换 Space 时保持不动（不参与空间动画）
_NS_FULL_SCREEN_AUXILIARY = 1 << 8    # 允许与全屏窗口同屏显示
_MACOS_OVERLAY_LEVEL = 25             # NSStatusWindowLevel，高于普通窗口与全屏窗口
_macos_objc = None


def _macos_overlay(widget: QWidget) -> None:
    """macOS：把窗口做成「全屏也压不住」的浮层（纯 ctypes 调 libobjc）。

    要真正盖住 PPT 全屏，光靠 Qt 的 WindowStaysOnTopHint 不够，需要同时满足：

      1. collectionBehavior 含 CanJoinAllSpaces —— 否则窗口只待在自己那个 Space，
         切到 PPT 的全屏 Space 时它根本不在这块屏幕上；
      2. FullScreenAuxiliary —— 允许与全屏窗口共存；
      3. Stationary —— Space 切换动画期间不跟着跑，避免闪一下；
      4. level 高于全屏窗口（这里用 NSStatusWindowLevel = 25）；
      5. canHide = NO / hidesOnDeactivate = NO —— 否则切到别的 App（PPT）时
         系统会把窗口收起来；
      6. orderFrontRegardless —— 不抢焦点也要显示到最前。

    这些属性都只在窗口完成创建后才有意义，所以调用点放在 show 之后/拖动时。
    任何一步失败都静默（置顶是增强，不该影响主流程）。
    """
    global _macos_objc
    try:
        import ctypes.util
        if _macos_objc is None:
            objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            _macos_objc = objc
        objc = _macos_objc
        msg = objc.objc_msgSend
        sel = objc.sel_registerName

        # [nsView window] → NSWindow
        msg.restype = ctypes.c_void_p
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        window = msg(ctypes.c_void_p(int(widget.winId())), sel(b"window"))
        if not window:
            return

        # 1) Space / 全屏行为
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        msg(window, sel(b"setCollectionBehavior:"),
            _NS_CAN_JOIN_ALL_SPACES | _NS_STATIONARY | _NS_FULL_SCREEN_AUXILIARY)

        # 2) 层级
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        msg(window, sel(b"setLevel:"), _MACOS_OVERLAY_LEVEL)

        # 3) 切到别的 App 时不要被收起/隐藏（BOOL 参数用 c_bool 传）
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        msg(window, sel(b"setHidesOnDeactivate:"), False)
        msg(window, sel(b"setCanHide:"), False)

        # 4) 不抢焦点也显示到最前
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        msg(window, sel(b"orderFrontRegardless"))
    except Exception:
        pass


def force_topmost(widget: QWidget) -> None:
    """把控件钉在最上层：Windows 用 SetWindowPos，macOS 用 NSWindow 层级/Space。"""
    if sys.platform == "darwin":
        _macos_overlay(widget)
        return

    if _SetWindowPos is None:
        return
    try:
        _SetWindowPos(
            ctypes.c_void_p(int(widget.winId())),
            ctypes.c_void_p(_HWND_TOPMOST),
            0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
        )
    except Exception:
        pass


class FloatingBall(QWidget):
    """50×50 的圆形悬浮按钮，始终置顶，显示「抽」，抽中时短暂闪烁。"""

    ball_clicked = pyqtSignal()
    open_panel_requested = pyqtSignal()  # 右键 → 打开管理面板
    points_panel_requested = pyqtSignal()  # 右键 → 打开小组积分窗口
    multi_draw_requested = pyqtSignal(int)  # 右键 → 连抽 N 人

    # 连抽人数（右键菜单里竖排展开的选项）
    MULTI_DRAW_CHOICES = tuple(range(2, 11))

    BALL_SIZE = 50

    COLOR_NORMAL = QColor(70, 130, 180, 200)    # 钢蓝，约 78% 不透明
    COLOR_FLASH = QColor(255, 215, 0, 230)       # 金色
    COLOR_BORDER = QColor(255, 255, 255, 80)

    DOUBLE_CLICK_MS = 400  # 两次点击之间判定双击的最大间隔

    @staticmethod
    def menu_stylesheet() -> str:
        """右键菜单样式：跟随深/浅色，避免深色模式下白底黑字或反过来的惨案。"""
        return f"""
            QMenu {{
                background: {theme.c("panel")};
                color: {theme.c("text")};
                border: 1px solid {theme.c("card_border")};
                border-radius: 4px;
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 6px 24px;
                font-family: "{theme.font_family()}";
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: {theme.c("accent")};
                color: {theme.c("accent_text")};
            }}
            QMenu::separator {{
                height: 1px;
                background: {theme.c("card_border")};
                margin: 4px 8px;
            }}
            QMenu::right-arrow {{
                width: 12px;
                height: 12px;
            }}
        """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_flashing = False
        self._drag_pos: QPoint | None = None
        self._drag_active = False
        self._click_count = 0
        self._click_timer: QTimer | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if sys.platform == "darwin":
            # Qt.Tool 在 macOS 上就是 NSPanel，默认 hidesOnDeactivate=YES：
            # 一旦本程序失焦（老师切到 PPT 放映），系统会把整个球隐藏，
            # 看起来就像「置顶失效」。这个属性让它保持可见。
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)

        self.setFixedSize(self.BALL_SIZE, self.BALL_SIZE)
        self._position_at_right_edge()

        QTimer.singleShot(100, lambda: force_topmost(self))

    # --- 事件 ---

    def showEvent(self, event) -> None:
        """每次显示都重新确认浮层属性。

        「隐藏悬浮球」按钮会 hide()/show() 这个窗口；Qt 在隐藏/显示之间可能重建
        平台窗口，NSWindow 上的 level / collectionBehavior 就丢了。这里补一次，
        顺便保证重新显示后仍然盖在全屏应用之上。
        """
        super().showEvent(event)
        force_topmost(self)

    def _position_at_right_edge(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        x = geom.right() - self.BALL_SIZE - 10
        y = geom.center().y() - self.BALL_SIZE // 2
        self.move(x, y)

    # --- 公共接口 ---

    def flash_drawing(self) -> None:
        """短暂闪金色，然后恢复正常。"""
        self._is_flashing = True
        self.update()
        QTimer.singleShot(400, self._end_flash)

    def _end_flash(self) -> None:
        self._is_flashing = False
        self.update()

    # --- 拖拽处理 ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._drag_active = False
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            delta = event.globalPos() - (self.frameGeometry().topLeft() + self._drag_pos)
            if delta.manhattanLength() > 3:
                self._drag_active = True
            if self._drag_active:
                new_pos = event.globalPos() - self._drag_pos
                self._clamp_to_screen(new_pos)
                force_topmost(self)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            was_drag = self._drag_active
            self._drag_pos = None
            self._drag_active = False

            if not was_drag:
                # 用定时器判定双击
                self._click_count += 1
                if self._click_count == 1:
                    # 第一次点击 —— 启动定时器
                    if self._click_timer is None:
                        self._click_timer = QTimer(self)
                        self._click_timer.setSingleShot(True)
                        self._click_timer.timeout.connect(self._on_click_timeout)
                    self._click_timer.start(self.DOUBLE_CLICK_MS)
                elif self._click_count >= 2:
                    # 双击触发
                    if self._click_timer is not None:
                        self._click_timer.stop()
                    self._click_count = 0
                    self.ball_clicked.emit()
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())
            event.accept()

    def _on_click_timeout(self) -> None:
        """单击超时 —— 重置计数，不触发动作。"""
        self._click_count = 0

    def build_context_menu(self) -> QMenu:
        """构建右键菜单（与 exec_ 分开，便于测试）。"""
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_stylesheet())

        # 连抽 —— 悬停后竖排展开 2~10 人（左键双击本来就能抽一个，不重复放）
        multi_menu = menu.addMenu("连抽")
        multi_menu.setStyleSheet(self.menu_stylesheet())
        for count in self.MULTI_DRAW_CHOICES:
            action = QAction(f"{count} 人", self)
            action.triggered.connect(
                lambda _checked=False, n=count: self.multi_draw_requested.emit(n)
            )
            multi_menu.addAction(action)

        points_action = QAction("积分管理", self)
        points_action.triggered.connect(self.points_panel_requested.emit)
        menu.addAction(points_action)

        menu.addSeparator()

        open_action = QAction("打开管理面板", self)
        open_action.triggered.connect(self.open_panel_requested.emit)
        menu.addAction(open_action)

        return menu

    def _show_context_menu(self, pos: QPoint) -> None:
        """弹出右键菜单。"""
        self.build_context_menu().exec_(pos)

    # --- 辅助 ---

    def _clamp_to_screen(self, pos: QPoint) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(pos)
            return
        geom = screen.availableGeometry()
        x = max(geom.left(), min(pos.x(), geom.right() - self.BALL_SIZE))
        y = max(geom.top(), min(pos.y(), geom.bottom() - self.BALL_SIZE))
        self.move(x, y)

    # --- 绘制 ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color = self.COLOR_FLASH if self._is_flashing else self.COLOR_NORMAL

        margin = 2
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)

        pen = QPen(self.COLOR_BORDER, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # 始终显示「抽」
        painter.setPen(QColor(255, 255, 255, 240))
        painter.setFont(theme.font(20, bold=True))
        painter.drawText(self.rect(), Qt.AlignCenter, "抽")

        painter.end()
