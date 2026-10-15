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
_NS_CAN_JOIN_ALL_SPACES = 1 << 0      # 出现在所有 Space（包括全屏应用的空间）
_NS_FULL_SCREEN_AUXILIARY = 1 << 8    # 允许与全屏窗口同屏显示
_MACOS_OVERLAY_LEVEL = 25             # NSStatusWindowLevel，高于普通窗口与全屏窗口
_macos_objc = None


def _macos_overlay(widget: QWidget) -> None:
    """macOS：让窗口跟随所有 Space、可盖在全屏应用之上（纯 ctypes 调 libobjc）。"""
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

        # [nsView window] → NSWindow
        msg.restype = ctypes.c_void_p
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        window = msg(ctypes.c_void_p(int(widget.winId())),
                     objc.sel_registerName(b"window"))
        if not window:
            return

        # [window setCollectionBehavior:]
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        msg(window, objc.sel_registerName(b"setCollectionBehavior:"),
            _NS_CAN_JOIN_ALL_SPACES | _NS_FULL_SCREEN_AUXILIARY)

        # [window setLevel:]
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        msg(window, objc.sel_registerName(b"setLevel:"), _MACOS_OVERLAY_LEVEL)
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

    _MENU_QSS = """
        QMenu {
            background: #fafafa;
            border: 1px solid #ccc;
            border-radius: 4px;
            padding: 4px 0;
        }
        QMenu::item {
            padding: 6px 24px;
            font-family: "Microsoft YaHei";
            font-size: 13px;
        }
        QMenu::item:selected {
            background: #4682B4;
            color: white;
        }
        QMenu::right-arrow {
            width: 12px;
            height: 12px;
        }
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
        menu.setStyleSheet(self._MENU_QSS)

        # 连抽 —— 悬停后竖排展开 2~10 人（左键双击本来就能抽一个，不重复放）
        multi_menu = menu.addMenu("连抽")
        multi_menu.setStyleSheet(self._MENU_QSS)
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
        font = QFont("Microsoft YaHei", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "抽")

        painter.end()
