"""macOS 平台自检 —— 一条命令验证置顶 / 菜单栏图标 / 深色模式三项修复。

用法:
    python tools/macos_check.py

检查项：
    1. 深色/浅色模式识别、主题色、平台字体是否解析到 PingFang SC；
    2. 托盘（菜单栏）图标：是否为模板图、各尺寸是否有内容、是否已显示；
    3. 悬浮球 NSWindow：level / collectionBehavior / hidesOnDeactivate / canHide，
       并验证 hide() + show() 之后属性仍然保留。

退出码 0 = 全部通过；非 0 = 有失败项。
"""

import ctypes
import ctypes.util
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)
from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()

from PyQt5.QtCore import QTimer, Qt  # noqa: E402
from PyQt5.QtGui import QPalette  # noqa: E402
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from namepicker import theme  # noqa: E402
from namepicker.floating_ball import (  # noqa: E402
    FloatingBall, force_topmost, _MACOS_OVERLAY_LEVEL,
)

failures = []
is_macos = sys.platform == "darwin"


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def skip(label, why):
    print(f"[SKIP] {label}  {why}")


def objc_sel(objc, name: bytes):
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    return objc.sel_registerName(name)


def window_attrs(widget):
    """读取 QWidget 底层 NSWindow 的关键属性。"""
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    msg = objc.objc_msgSend
    msg.restype = ctypes.c_void_p
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    window = msg(ctypes.c_void_p(int(widget.winId())), objc_sel(objc, b"window"))
    if not window:
        return None

    def call(name, restype):
        msg.restype = restype
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        return msg(window, objc_sel(objc, name))

    return {
        "level": call(b"level", ctypes.c_long),
        "behavior": call(b"collectionBehavior", ctypes.c_ulong),
        "hides_on_deactivate": call(b"hidesOnDeactivate", ctypes.c_bool),
        "can_hide": call(b"canHide", ctypes.c_bool),
    }


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply(app)

    print("=" * 66)
    print(f"平台: {sys.platform} | Python {sys.version.split()[0]} | Qt {app.applicationVersion() or '5.15'}")
    print("=" * 66)

    # ---------------- 1. 深色模式 ----------------
    print("\n--- 1. 深色模式与字体 ---")
    window_lightness = app.palette().color(QPalette.Window).lightness()
    print(f"  palette Window 亮度: {window_lightness}（<128 视为深色）")
    check("深色识别与调色板一致", theme.is_dark() == (window_lightness < 128),
          f"theme.is_dark()={theme.is_dark()}")
    family = theme.font_family()
    check("字体解析到本平台中文字体", family not in ("", None), family)
    if is_macos:
        check("macOS 使用 PingFang SC（而不是缺失的 Microsoft YaHei）",
              "PingFang" in family, family)
    for token in ("text", "muted", "card", "view_bg", "log_bg",
                  "success", "danger", "accent", "button_bg"):
        value = theme.c(token)
        check(f"主题色 {token} 可用", value.startswith("#") and len(value) == 7, value)
    # 日志区前景/背景不能同色（深色模式白字白底的老 bug）
    from PyQt5.QtGui import QColor
    check("日志区前景与背景有足够对比度",
          abs(QColor(theme.c("text")).lightness() - QColor(theme.c("log_bg")).lightness()) > 80,
          f"{theme.c('text')} on {theme.c('log_bg')}")

    # ---------------- 2. 菜单栏图标 ----------------
    print("\n--- 2. 菜单栏 / 托盘图标 ---")
    available = QSystemTrayIcon.isSystemTrayAvailable()
    check("系统托盘可用", available)
    if available:
        icon = theme.tray_icon()
        sizes = [f"{s.width()}x{s.height()}" for s in icon.availableSizes()]
        print(f"  图标尺寸: {sizes}")
        check("图标有多档尺寸", len(icon.availableSizes()) >= 2)
        if is_macos:
            check("macOS 图标是模板图（系统会自动反色）", icon.isMask())
        else:
            skip("模板图检查", "仅 macOS 需要")
        for size in (22, 44):
            pm = icon.pixmap(size, size)
            img = pm.toImage()
            opaque = sum(1 for y in range(img.height()) for x in range(img.width())
                         if img.pixelColor(x, y).alpha() > 20)
            check(f"{size}px 图标有实际内容", opaque > 50, f"{opaque} 个不透明像素")
        tray = QSystemTrayIcon(icon)
        tray.setToolTip("macOS 自检")
        tray.show()
        check("tray.show() 后 isVisible()", tray.isVisible())
        tray.hide()
    else:
        skip("托盘图标检查", "系统托盘不可用")

    # ---------------- 3. 悬浮球浮层 ----------------
    print("\n--- 3. 悬浮球置顶 / 全屏覆盖 ---")
    if not is_macos:
        skip("NSWindow 属性检查", "仅 macOS 需要")
    else:
        ball = FloatingBall()
        ball.show()
        force_topmost(ball)
        attrs = window_attrs(ball)
        check("能取到底层 NSWindow", attrs is not None)
        if attrs:
            print(f"  level={attrs['level']} behavior=0x{attrs['behavior']:x} "
                  f"hidesOnDeactivate={attrs['hides_on_deactivate']} canHide={attrs['can_hide']}")
            check("层级达到 NSStatusWindowLevel",
                  attrs["level"] >= _MACOS_OVERLAY_LEVEL, f"level={attrs['level']}")
            check("CanJoinAllSpaces 已设置（跟随到 PPT 全屏 Space）",
                  bool(attrs["behavior"] & (1 << 0)))
            check("FullScreenAuxiliary 已设置（可与全屏窗口共存）",
                  bool(attrs["behavior"] & (1 << 8)))
            check("Stationary 已设置（切 Space 不跟着跑）",
                  bool(attrs["behavior"] & (1 << 4)))
            check("hidesOnDeactivate = False（切到 PPT 不被收起）",
                  not attrs["hides_on_deactivate"])
            check("canHide = False", not attrs["can_hide"])

            # 隐藏再显示后属性是否还在（「隐藏悬浮球」按钮会走这条路径）
            ball.hide()
            ball.show()
            force_topmost(ball)
            again = window_attrs(ball)
            check("hide + show 之后属性仍然保留",
                  again is not None and again["level"] == attrs["level"]
                  and again["behavior"] == attrs["behavior"],
                  f"level={again['level'] if again else '?'} "
                  f"behavior=0x{again['behavior']:x}" if again else "")
        ball.hide()
        ball.deleteLater()

    print("\n提示：全屏覆盖的最终效果取决于 PPT 的放映方式（是否占用独立 Space）。")
    print("      本脚本只能验证 NSWindow 属性是否正确；若 PPT 仍盖不住，")
    print("      可把 floating_ball.py 里的 _MACOS_OVERLAY_LEVEL 提到 1000 再试。")

    print("\n" + "=" * 66)
    if failures:
        print(f"失败 {len(failures)} 项：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("全部通过")
    QTimer.singleShot(0, app.quit)
    app.exec_()
    return 0


if __name__ == "__main__":
    sys.exit(main())
