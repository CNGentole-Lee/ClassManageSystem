"""macOS 平台自检 —— 验证全屏覆盖 / 菜单栏图标 / 深色模式。

用法:
    python tools/macos_check.py                # 只做静态检查
    python tools/macos_check.py --fullscreen   # 额外跑一次真实全屏覆盖测试

检查项：
    1. 深色/浅色识别、主题色、平台字体；
    2. 菜单栏图标：模板图、尺寸、是否已创建状态栏窗口；并检测「自动隐藏菜单栏」；
    3. 应用激活策略（必须 accessory，否则全屏时窗口会被挡在桌面 Space）；
    4. 悬浮球 NSWindow 属性：level / collectionBehavior / hidesOnDeactivate / canHide，
       以及 hide()+show() 后是否保持；
    5. [--fullscreen] 启动一个真·原生全屏的辅助进程，检查悬浮球是否仍在
       当前 Space（用 CGWindowList onScreenOnly + 窗口尺寸判定）。

退出码 0 = 全部通过；非 0 = 有失败项。
"""

import ctypes
import ctypes.util
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)
from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from namepicker import macos_window, theme  # noqa: E402
from namepicker.floating_ball import FloatingBall, force_topmost  # noqa: E402

failures = []
is_macos = sys.platform == "darwin"
FULLSCREEN_TEST = "--fullscreen" in sys.argv


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def skip(label, why):
    print(f"[SKIP] {label}  {why}")


# --- 极简 CoreGraphics 封装：当前 Space 里有哪些窗口（含尺寸）---------------

def _cg_api():
    cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    return cg, cf


def _cfstr(cf, text: str):
    return cf.CFStringCreateWithCString(None, text.encode(), 0x08000100)  # UTF-8


def _cfnum(cf, d, key):
    num = cf.CFDictionaryGetValue(d, key)
    if not num:
        return None
    value = ctypes.c_double(0)
    if cf.CFNumberGetValue(num, 6, ctypes.byref(value)):   # kCFNumberFloat64Type
        return value.value
    return None


def on_screen_windows():
    """当前活跃 Space 里的窗口（按前后顺序）：[(pid, number, width, height), ...]。"""
    try:
        cg, cf = _cg_api()
    except Exception:
        return []
    k_pid = _cfstr(cf, "kCGWindowOwnerPID")
    k_num = _cfstr(cf, "kCGWindowNumber")
    k_bounds = _cfstr(cf, "kCGWindowBounds")
    k_w = _cfstr(cf, "Width")
    k_h = _cfstr(cf, "Height")
    arr = cg.CGWindowListCopyWindowInfo(1, 0)             # kCGWindowListOptionOnScreenOnly
    out = []
    if not arr:
        return out
    try:
        for i in range(cf.CFArrayGetCount(arr)):
            d = cf.CFArrayGetValueAtIndex(arr, i)
            pid = _cfnum(cf, d, k_pid)
            number = _cfnum(cf, d, k_num)
            bounds = cf.CFDictionaryGetValue(d, k_bounds)
            if pid is None or number is None or not bounds:
                continue
            out.append((int(pid), int(number), _cfnum(cf, bounds, k_w) or 0.0,
                        _cfnum(cf, bounds, k_h) or 0.0))
    finally:
        cf.CFRelease(arr)
    return out


def status_bar_window_count() -> int:
    """NSApp 里状态栏窗口的数量（Qt 建出 NSStatusItem 才会有）。"""
    try:
        app = macos_window.ns_app()
        arr = macos_window._msg(app, b"windows")
        n = int(macos_window._msg(arr, b"count", ctypes.c_ulong) or 0)
        count = 0
        for i in range(n):
            win = macos_window._msg(arr, b"objectAtIndex:", ctypes.c_void_p,
                                    [ctypes.c_void_p], ctypes.c_void_p(i))
            cls_ptr = macos_window._msg(win, b"className")
            name = macos_window._msg(cls_ptr, b"UTF8String", ctypes.c_char_p)
            if name == b"NSStatusBarWindow":
                count += 1
        return count
    except Exception:
        return 0


def window_number(widget) -> int:
    """NSWindow.windowNumber（用于在 CGWindowList 里定位窗口）。"""
    try:
        window = macos_window.ns_window(widget)
        return int(macos_window._msg(window, b"windowNumber", ctypes.c_long) or 0)
    except Exception:
        return 0


def menu_bar_auto_hidden() -> bool | None:
    try:
        out = subprocess.run(["defaults", "read", "-g", "_HIHideMenuBar"],
                             capture_output=True, text=True, timeout=3)
        value = out.stdout.strip()
        return value == "1" if value else False
    except Exception:
        return None


# --- 全屏覆盖测试 -------------------------------------------------------

def fullscreen_test():
    """启动一个进入原生全屏的辅助进程，验证悬浮球仍在当前 Space。"""
    print("\n--- 6. Real full-screen overlap test ---")
    helper = subprocess.Popen(
        [sys.executable, os.path.join(_HERE, "_fullscreen_helper.py")],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    ball = None
    try:
        line = helper.stdout.readline().strip()
        print(f"  helper process: {line}")
        if line != "FULLSCREEN":
            check("helper process enters native full screen", False, line or "no output")
            return

        ball = FloatingBall()
        ball.show()
        force_topmost(ball)
        process(0.4)

        # 激活辅助进程 → 系统切到它的全屏 Space。
        # 切换 Space 是异步动画，CI/负载高时会慢半拍，所以重试几次再判定。
        def activate_helper():
            try:
                running = macos_window._msg(
                    macos_window._class(b"NSRunningApplication"),
                    b"runningApplicationWithProcessIdentifier:",
                    ctypes.c_void_p, [ctypes.c_int32], ctypes.c_int32(helper.pid))
                macos_window._msg(running, b"activateWithOptions:", ctypes.c_bool,
                                  [ctypes.c_ulong], ctypes.c_ulong(1 << 1))
            except Exception:
                pass

        windows = []
        helper_visible = False
        for attempt in range(4):
            activate_helper()
            process(1.2 if attempt == 0 else 0.9)
            windows = on_screen_windows()
            helper_visible = any(pid == helper.pid for pid, _n, _w, _h in windows)
            if helper_visible:
                break

        mine = [(w, h) for pid, _n, w, h in windows if pid == os.getpid()]
        small = [(w, h) for w, h in mine if w <= 90 and h <= 90]

        check("helper full-screen window is on screen (switched to its full-screen Space)", helper_visible,
              f"{len(windows)} windows on screen")
        check("floating ball (50x50) appears in the same Space", bool(small),
              f"this process windows: {[f'{w:.0f}x{h:.0f}' for w, h in mine]}")
        if helper_visible and small:
            print("  -> Conclusion: the floating ball can sit above native full-screen apps ✅")
        else:
            print("  -> Conclusion: could not enter the full-screen Space; please send the output above to the developer")
    finally:
        if ball is not None:
            ball.hide()
            ball.deleteLater()
        helper.terminate()
        try:
            helper.wait(timeout=3)
        except Exception:
            helper.kill()


def process(seconds: float):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


# --- 主流程 -------------------------------------------------------------

app = QApplication(sys.argv)
theme.apply(app)

# offscreen（CI / 无头）下没有真实的 NSWindow/NSStatusBar，继续跑只会对
# 假的 winId 发 objc 消息（段错误），所以这里直接跳过。
if is_macos and not macos_window._is_cocoa():
    print(f"平台插件: {app.platformName()}（无真实窗口系统）")
    print("SKIP: macOS 自检需要 cocoa 平台插件，offscreen 下不适用")
    sys.exit(0)
# 与 main.py 一致：macOS 必须切到 accessory 策略，窗口才能加入别的 App 的全屏 Space
if is_macos:
    macos_window.set_accessory_policy()
    macos_window.install_dialog_raiser(app)

print("=" * 66)
print(f"Platform: {sys.platform} | Python {sys.version.split()[0]}")
print("=" * 66)

print("\n--- 1. Dark mode and fonts ---")
lightness = app.palette().color(QPalette.Window).lightness()
print(f"  palette Window lightness: {lightness} (<128 counts as dark)")
check("dark-mode detection matches the palette", theme.is_dark() == (lightness < 128),
      f"theme.is_dark()={theme.is_dark()}")
family = theme.font_family()
check("font resolves to a platform CJK font", bool(family), family)
if is_macos:
    check("macOS uses PingFang SC (not a missing Microsoft YaHei)",
          "PingFang" in family, family)
for token in ("text", "muted", "card", "view_bg", "log_bg",
              "success", "danger", "accent", "button_bg"):
    check(f"theme colour {token} is available", theme.c(token).startswith("#"), theme.c(token))
check("log area foreground/background contrast is sufficient",
      abs(QColor(theme.c("text")).lightness() - QColor(theme.c("log_bg")).lightness()) > 80,
      f"{theme.c('text')} on {theme.c('log_bg')}")

print("\n--- 2. Menu bar / tray icon ---")
check("system tray is available", QSystemTrayIcon.isSystemTrayAvailable())
icon = theme.tray_icon()
print(f"  icon sizes: {[f'{s.width()}x{s.height()}' for s in icon.availableSizes()]}")
check("icon has multiple sizes", len(icon.availableSizes()) >= 2)
if is_macos:
    check("macOS icon is a template image (system inverts it automatically)", icon.isMask())
for size in (22, 44):
    pixmap = icon.pixmap(size, size)
    image = pixmap.toImage()
    opaque = sum(1 for y in range(image.height()) for x in range(image.width())
                 if image.pixelColor(x, y).alpha() > 20)
    check(f"{size}px icon has real content", opaque > 50, f"{opaque} opaque pixels")
tray = QSystemTrayIcon(icon)
tray.setToolTip("macOS self-check")
tray.show()
process(0.3)
check("isVisible() after tray.show()", tray.isVisible())
if is_macos:
    bars = status_bar_window_count()
    check("NSStatusBarWindow created (status item really exists)", bars >= 1, f"{bars} found")
    hidden = menu_bar_auto_hidden()
    if hidden:
        print("  ⚠ System \"automatically hide the menu bar\" is on (_HIHideMenuBar=1): while the menu bar is collapsed the status item")
        print("    is simply not shown (not an app bug). Turn it off in System Settings -> Appearance/Desktop & Dock,")
        print("    or just use the same feature in the floating ball context menu.")
    else:
        check("system menu bar is not auto-hidden", True)

print("\n--- 3. App activation policy ---")
policy = macos_window.activation_policy()
print(f"  current activationPolicy: {policy} (0=regular, 1=accessory)")
if is_macos:
    check("app switched to the accessory policy (required for full-screen overlay)",
          policy == macos_window.POLICY_ACCESSORY,
          f"policy={policy}")
else:
    skip("activation policy check", "only needed on macOS")

print("\n--- 4. Floating ball layer attributes ---")
ball = FloatingBall()
ball.show()
force_topmost(ball)
attrs = macos_window.window_attrs(ball)
check("underlying NSWindow retrieved", attrs is not None)
if attrs:
    print(f"  level={attrs['level']} behavior=0x{attrs['behavior']:x} "
          f"hidesOnDeactivate={attrs['hides_on_deactivate']} canHide={attrs['can_hide']}")
    check("level reaches NSStatusWindowLevel",
          attrs["level"] >= macos_window.NS_STATUS_WINDOW_LEVEL, f"level={attrs['level']}")
    check("CanJoinAllSpaces (follows into full-screen Spaces)",
          bool(attrs["behavior"] & macos_window.NS_CAN_JOIN_ALL_SPACES))
    check("FullScreenAuxiliary (can coexist with full-screen windows)",
          bool(attrs["behavior"] & macos_window.NS_FULL_SCREEN_AUXILIARY))
    check("Stationary (does not move when switching Spaces)",
          bool(attrs["behavior"] & macos_window.NS_STATIONARY))
    check("hidesOnDeactivate = False", not attrs["hides_on_deactivate"])
    check("canHide = False", not attrs["can_hide"])
    ball.hide()
    ball.show()
    force_topmost(ball)
    again = macos_window.window_attrs(ball)
    check("attributes survive hide + show",
          again is not None and again["level"] == attrs["level"]
          and again["behavior"] == attrs["behavior"])
ball.hide()
ball.deleteLater()

print("\n--- 5. Modal dialogs above the overlay panel ---")
if is_macos:
    from PySide6.QtWidgets import QInputDialog
    from namepicker.config_store import ConfigStore
    from namepicker.points_window import PointsWindow

    store = ConfigStore(os.path.join(tempfile.mkdtemp(prefix="cm_modal_"), "config.ini"))
    panel = PointsWindow(store)
    panel.show()
    force_topmost(panel)
    process(0.3)

    dialog = QInputDialog(panel)
    dialog.setWindowTitle("Rename")
    dialog.setLabelText("New name:")
    result = {}

    def inspect():
        panel_level = (macos_window.window_attrs(panel) or {}).get("level", 0)
        dialog_level = (macos_window.window_attrs(dialog) or {}).get("level", 0)
        order = [number for _pid, number, _w, _h in on_screen_windows()]
        panel_num, dialog_num = window_number(panel), window_number(dialog)
        above = (panel_num in order and dialog_num in order
                 and order.index(dialog_num) < order.index(panel_num))
        result.update(panel_level=panel_level, dialog_level=dialog_level, above=above)
        dialog.reject()

    QTimer.singleShot(600, inspect)
    dialog.exec()          # 模态打开；inspect() 在模态循环里执行并关掉它
    process(0.2)

    check("panel really is an overlay (level 25)", result.get("panel_level") == 25,
          f"level={result.get('panel_level')}")
    check("modal dialog is raised above the panel",
          result.get("dialog_level", 0) > result.get("panel_level", 0),
          f"dialog level={result.get('dialog_level')}")
    check("dialog is frontmost in the window list", bool(result.get("above")),
          f"above={result.get('above')}")
    panel.close()
    panel.hide()
    panel.deleteLater()
    process(0.4)
else:
    skip("modal dialog layering", "macOS only")

print("\n--- 5b. About window does not block drawing ---")
if is_macos:
    from PySide6.QtWidgets import QApplication
    from namepicker.about_dialog import AboutDialog, show_about
    from namepicker.draw_popup import DrawResultPopup

    show_about(None)                 # 非模态
    process(0.4)
    about = None
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, AboutDialog) and widget.isVisible():
            about = widget
            break
    check("About window is shown", about is not None)
    if about is not None:
        attrs = macos_window.window_attrs(about) or {}
        check("About is NOT raised to the dialog level (26)",
              attrs.get("level") == macos_window.NS_STATUS_WINDOW_LEVEL,
              f"level={attrs.get('level')}")
        from PySide6.QtCore import Qt as _Qt
        check("About is non-modal",
              about.windowModality() == _Qt.WindowModality.NonModal,
              str(about.windowModality()))

        popup = DrawResultPopup()
        popup.set_name_pool(["A", "B"])
        popup.show_results(["A"])
        process(0.5)
        order = [number for _pid, number, _w, _h in on_screen_windows()]
        about_num = window_number(about)
        popup_num = window_number(popup)
        above = (about_num in order and popup_num in order
                 and order.index(popup_num) < order.index(about_num))
        check("draw popup is above the About window", above,
              f"about={order.index(about_num) if about_num in order else 'off'}"
              f" popup={order.index(popup_num) if popup_num in order else 'off'}")
        popup._stop_timers()
        popup.close()
        about.close()
        process(0.2)
else:
    skip("About window layering", "macOS only")

if FULLSCREEN_TEST and is_macos:
    fullscreen_test()
elif FULLSCREEN_TEST:
    skip("real full-screen test", "only supported on macOS")
else:
    print("\nTip: to verify overlay behaviour under a real native full screen, run")
    print("      python tools/macos_check.py --fullscreen")

print("\n" + "=" * 66)
if failures:
    print(f"failed {len(failures)}:")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)
print("ALL PASSED")
QTimer.singleShot(0, app.quit)
app.exec()
