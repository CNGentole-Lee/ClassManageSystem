"""theme —— 深/浅色自适应配色 + 跨平台中文字体。

为什么需要它
------------
界面样式原先全是硬编码的浅色（`#f5f5f5`、`#fbfcfd`、`#888`…）和
`font-family: "Microsoft YaHei"`。在 macOS / Windows 的**深色模式**下会出现：

  * 系统 `QPalette.ButtonText` 是纯黑、`WindowText` 是纯白，而样式表只设了
    背景没设前景 —— 日志查看器就变成了「近白底 + 白字」，几乎看不见；
  * 浅色卡片配系统浅灰提示文字，对比度低，观感发灰；
  * macOS 没有 Microsoft YaHei，Qt 回退到系统字体并打印告警，字号与字宽不一致。

做法
----
  * 启动时用 `QApplication.palette().color(QPalette.Window)` 的亮度判断深色；
    也可用环境变量 `CLASSMANAGE_THEME=dark|light` 强制（截图与测试用）；
  * 所有颜色收敛到一套 token，样式表由 token 生成，不再出现散落的硬编码色；
  * 字体按平台选：macOS → PingFang SC，Windows → Microsoft YaHei，
    Linux → Noto Sans CJK SC；都不可用时回退系统 UI 字体。

注意：这里**不改 QPalette**。系统本身已经给了正确的深色调色板，我们只需要
保证自己画的样式表与它一致；覆盖调色板会让原生对话框（QMessageBox 等）反过来变花。
"""

import sys

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QPalette

from .i18n import tr

ENV_NAME = "CLASSMANAGE_THEME"

#: 深浅两套 token。命名按用途，不按颜色 —— 换主题只换值。
_LIGHT = {
    "window": "#f4f5f7",
    "panel": "#ffffff",
    "card": "#fbfcfd",
    "card_selected": "#eef4fa",
    "card_border": "#dfe3e8",
    "card_border_selected": "#4682b4",
    "text": "#2c3e50",
    "text_strong": "#1f2d3d",
    "muted": "#6b7480",
    "hint": "#8a929c",
    "faint": "#aab1ba",
    "accent": "#4682b4",
    "accent_text": "#ffffff",
    "success": "#2e8b57",
    "danger": "#c0392b",
    "warning": "#cd853f",
    "button_bg": "#f5f6f7",
    "button_hover": "#e8eaec",
    "button_pressed": "#d9dcdf",
    "button_border": "#c4c9ce",
    "view_bg": "#ffffff",
    "view_border": "#d7dbe0",
    "view_alt": "#f7f8fa",
    "minus_bg": "#fdecea",
    "minus_fg": "#c0392b",
    "minus_border": "#f0b4ae",
    "minus_hover": "#f8d3ce",
    "plus_bg": "#eaf6ee",
    "plus_fg": "#2e8b57",
    "plus_border": "#a9d5b9",
    "plus_hover": "#d5ecdf",
    "pressed_bg": "#c8c8c8",
    "pressed_fg": "#333333",
    "log_bg": "#fbfcfd",
}

_DARK = {
    "window": "#1f2125",
    "panel": "#26282c",
    "card": "#2b2e33",
    "card_selected": "#2f3c4d",
    "card_border": "#3a3e45",
    "card_border_selected": "#5b9bd5",
    "text": "#e6e8eb",
    "text_strong": "#f2f4f6",
    "muted": "#a8b0ba",
    "hint": "#9aa3ad",
    "faint": "#7e8791",
    "accent": "#5b9bd5",
    "accent_text": "#0f1115",
    "success": "#58c98a",
    "danger": "#ef7b6f",
    "warning": "#e0a76a",
    "button_bg": "#33363c",
    "button_hover": "#3d4148",
    "button_pressed": "#2a2d32",
    "button_border": "#4a4f57",
    "view_bg": "#1b1d21",
    "view_border": "#3a3e45",
    "view_alt": "#23262b",
    "minus_bg": "#3a2624",
    "minus_fg": "#ef8b80",
    "minus_border": "#6b3b36",
    "minus_hover": "#472d2a",
    "plus_bg": "#23362b",
    "plus_fg": "#6ed09a",
    "plus_border": "#3d5c49",
    "plus_hover": "#2b4434",
    "pressed_bg": "#22252a",
    "pressed_fg": "#cfd3d8",
    "log_bg": "#1b1d21",
}

#: 各平台首选的界面字体（都是各自系统里最合适的中文 UI 字体）
_FONT_PREFS = {
    "darwin": ("PingFang SC", "Hiragino Sans GB", "Heiti SC"),
    "win32": ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei"),
    "linux": ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei"),
}

_dark: bool | None = None
_family: str | None = None


def _forced() -> bool | None:
    """环境变量强制主题：dark/light，其它值视为自动。"""
    import os
    value = (os.environ.get(ENV_NAME) or "").strip().lower()
    if value in ("dark", "light"):
        return value == "dark"
    return None


def is_dark() -> bool:
    """当前是否深色模式（环境变量优先，其次看系统调色板亮度）。"""
    global _dark
    forced = _forced()
    if forced is not None:
        return forced
    if _dark is None:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            _dark = False
        else:
            _dark = app.palette().color(QPalette.Window).lightness() < 128
    return _dark


def refresh() -> None:
    """丢弃缓存（主题/字体被外部改动后调用，测试与截图脚本用）。"""
    global _dark, _family
    _dark = None
    _family = None


def c(token: str) -> str:
    """取一个颜色 token，返回 `#rrggbb`。未知 token 直接报错，避免静默出错。"""
    table = _DARK if is_dark() else _LIGHT
    try:
        return table[token]
    except KeyError:
        raise KeyError(f"未定义的主题色: {token}") from None


def font_family() -> str:
    """当前平台可用的最佳中文字体族；都不可用时回退系统 UI 字体。"""
    global _family
    if _family is not None:
        return _family

    available = set(QFontDatabase().families())
    for name in _FONT_PREFS.get(sys.platform, ()) + _FONT_PREFS["linux"]:
        if name in available:
            _family = name
            break
    else:
        _family = QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()
    return _family


def font(px: int = 13, bold: bool = False) -> QFont:
    """按像素字号取字体（样式表里也用 px，两边保持一致）。"""
    f = QFont(font_family())
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def global_stylesheet() -> str:
    """全局样式表：按钮、分组框、列表/表格、输入框、表头。

    显式写 `color` 是关键 —— 深色模式下 Qt 的 ButtonText 是黑色，
    只设背景不设前景会在浅色按钮上碰巧正常、在深色按钮上彻底看不见。
    """
    t = {k: c(k) for k in _LIGHT}
    family = font_family()
    # 注意：这里不要写 `QWidget { font-family: ... }`。全局样式表会让
    # QStyleSheetStyle 接管所有控件的绘制，QSpinBox 的原生上下箭头会因此消失
    # （截图里只剩一条小横杠）。字体统一由 app.setFont() 设置即可。
    return f"""
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {t["card_border"]};
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            color: {t["text"]};
        }}
        QPushButton {{
            padding: 6px 16px;
            border: 1px solid {t["button_border"]};
            border-radius: 4px;
            background: {t["button_bg"]};
            color: {t["text"]};
        }}
        QPushButton:hover {{ background: {t["button_hover"]}; }}
        QPushButton:pressed {{ background: {t["button_pressed"]}; }}
        QPushButton:disabled {{ color: {t["faint"]}; background: {t["button_bg"]}; }}
        QListWidget, QTableWidget, QPlainTextEdit, QTextEdit {{
            border: 1px solid {t["view_border"]};
            border-radius: 4px;
            background: {t["view_bg"]};
            color: {t["text"]};
        }}
        QListWidget::item:selected, QTableWidget::item:selected {{
            background: {t["accent"]};
            color: {t["accent_text"]};
        }}
        QLineEdit {{
            background: {t["view_bg"]};
            color: {t["text"]};
            border: 1px solid {t["view_border"]};
            border-radius: 4px;
            padding: 3px 6px;
        }}
        QLineEdit:read-only {{ color: {t["muted"]}; }}
        /* QSpinBox 故意不套样式：macOS 上加 border/padding 会把原生的
           上下箭头子控件画没（只剩一条小横杠），交给调色板即可。 */
        QHeaderView::section {{
            background: {t["button_bg"]};
            color: {t["muted"]};
            border: none;
            border-right: 1px solid {t["view_border"]};
            border-bottom: 1px solid {t["view_border"]};
            padding: 4px 8px;
        }}
        QTableWidget {{ gridline-color: {t["view_border"]}; }}
        QToolTip {{
            background: {t["panel"]};
            color: {t["text"]};
            border: 1px solid {t["card_border"]};
        }}
    """


def build_palette() -> QPalette:
    """按当前主题构造 QPalette。

    为什么必须自己设调色板：Qt 5.15 在 macOS 深色下的默认调色板有几个坑
    （`ButtonText` 是纯黑、`AlternateBase` 是浅灰），只写样式表会出现
    "浅色卡片 + 系统深色窗口底"这种半深半浅的混合效果；强制浅色截图时更明显。
    统一按 token 生成，界面元素与窗口底色才是一致的。
    """
    p = QPalette()
    role = {
        QPalette.Window: c("window"),
        QPalette.WindowText: c("text"),
        QPalette.Base: c("view_bg"),
        QPalette.AlternateBase: c("view_alt"),
        QPalette.Text: c("text"),
        QPalette.Button: c("button_bg"),
        QPalette.ButtonText: c("text"),
        QPalette.BrightText: c("danger"),
        QPalette.Highlight: c("accent"),
        QPalette.HighlightedText: c("accent_text"),
        QPalette.ToolTipBase: c("panel"),
        QPalette.ToolTipText: c("text"),
        QPalette.PlaceholderText: c("faint"),
        QPalette.Link: c("accent"),
        QPalette.LinkVisited: c("accent"),
    }
    for qrole, value in role.items():
        p.setColor(qrole, QColor(value))

    # 禁用态：文字淡一些，但背景仍与主题一致
    for qrole in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, qrole, QColor(c("faint")))
    for qrole in (QPalette.Button, QPalette.Base):
        p.setColor(QPalette.Disabled, qrole, QColor(c("button_bg")))
    return p


def apply(app) -> None:
    """把字体、调色板与全局样式表应用到 QApplication（创建窗口之前调用）。"""
    refresh()
    app.setFont(font(13))
    app.setPalette(build_palette())
    app.setStyleSheet(global_stylesheet())


def tray_icon():
    """生成托盘 / 菜单栏图标。

    macOS 的菜单栏图标必须是**模板图**（只有 alpha 有效，系统会按浅/深色自动
    反色）。这里画一个纯黑的「抽」字轮廓并 `setIsMask(True)`，系统就能正确着色；
    之前用 `QStyle.SP_ComputerIcon`（512px 彩色位图）在菜单栏里既糊又可能不显示。

    Windows 托盘是彩色图标，这里用钢蓝圆底 + 白色「抽」，与悬浮球一致。
    """
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QIcon, QPainter, QPixmap

    sizes = (22, 44, 66) if sys.platform == "darwin" else (16, 24, 32, 48, 64)
    icon = QIcon()
    dark = is_dark()
    for size in sizes:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        if sys.platform == "darwin":
            # 模板图：纯黑 + alpha，系统自动反色
            p.setPen(QColor(0, 0, 0, 255))
            p.setFont(font(int(size * 0.80), bold=True))
            p.drawText(pm.rect(), Qt.AlignCenter, tr("抽", "P"))
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(70, 130, 180, 255))
            p.drawEllipse(0, 0, size, size)
            p.setPen(QColor(255, 255, 255))
            p.setFont(font(int(size * 0.62), bold=True))
            p.drawText(pm.rect(), Qt.AlignCenter, tr("抽", "P"))
        p.end()
        icon.addPixmap(pm)

    if sys.platform == "darwin":
        # Qt 在 macOS 上把 mask 图标渲染成 NSImage 模板图（自动适配浅/深色菜单栏）
        icon.setIsMask(True)
    _ = dark  # 模板图无需区分深浅；保留变量便于将来加彩色变体
    return icon
