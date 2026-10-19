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
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)
from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()

from PyQt5.QtCore import QTimer  # noqa: E402
from PyQt5.QtGui import QColor, QPalette  # noqa: E402
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

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
    """当前活跃 Space 里的窗口：[(pid, width, height), ...]。"""
    try:
        cg, cf = _cg_api()
    except Exception:
        return []
    k_pid = _cfstr(cf, "kCGWindowOwnerPID")
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
            bounds = cf.CFDictionaryGetValue(d, k_bounds)
            if pid is None or not bounds:
                continue
            out.append((int(pid), _cfnum(cf, bounds, k_w) or 0.0,
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
    print("\n--- 5. 真实全屏覆盖测试 ---")
    helper = subprocess.Popen(
        [sys.executable, os.path.join(_HERE, "_fullscreen_helper.py")],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    ball = None
    try:
        line = helper.stdout.readline().strip()
        print(f"  辅助进程: {line}")
        if line != "FULLSCREEN":
            check("辅助进程进入原生全屏", False, line or "无输出")
            return

        ball = FloatingBall()
        ball.show()
        force_topmost(ball)
        process(0.4)

        # 激活辅助进程 → 系统切到它的全屏 Space
        try:
            running = macos_window._msg(
                macos_window._class(b"NSRunningApplication"),
                b"runningApplicationWithProcessIdentifier:",
                ctypes.c_void_p, [ctypes.c_int32], ctypes.c_int32(helper.pid))
            macos_window._msg(running, b"activateWithOptions:", ctypes.c_bool,
                              [ctypes.c_ulong], ctypes.c_ulong(1 << 1))
        except Exception:
            pass
        process(2.2)

        windows = on_screen_windows()
        helper_visible = any(pid == helper.pid for pid, _w, _h in windows)
        mine = [(w, h) for pid, w, h in windows if pid == os.getpid()]
        small = [(w, h) for w, h in mine if w <= 90 and h <= 90]

        check("辅助进程的全屏窗口在屏（说明已切到全屏 Space）", helper_visible,
              f"屏上窗口 {len(windows)} 个")
        check("悬浮球（50×50）出现在同一 Space", bool(small),
              f"本进程窗口: {[f'{w:.0f}x{h:.0f}' for w, h in mine]}")
        if helper_visible and small:
            print("  → 结论：悬浮球可以盖在原生全屏应用之上 ✅")
        else:
            print("  → 结论：未能进入全屏 Space，请把以上输出发给开发者")
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
# 与 main.py 一致：macOS 必须切到 accessory 策略，窗口才能加入别的 App 的全屏 Space
if is_macos:
    macos_window.set_accessory_policy()

print("=" * 66)
print(f"平台: {sys.platform} | Python {sys.version.split()[0]}")
print("=" * 66)

print("\n--- 1. 深色模式与字体 ---")
lightness = app.palette().color(QPalette.Window).lightness()
print(f"  palette Window 亮度: {lightness}（<128 视为深色）")
check("深色识别与调色板一致", theme.is_dark() == (lightness < 128),
      f"theme.is_dark()={theme.is_dark()}")
family = theme.font_family()
check("字体解析到本平台中文字体", bool(family), family)
if is_macos:
    check("macOS 使用 PingFang SC（而不是缺失的 Microsoft YaHei）",
          "PingFang" in family, family)
for token in ("text", "muted", "card", "view_bg", "log_bg",
              "success", "danger", "accent", "button_bg"):
    check(f"主题色 {token} 可用", theme.c(token).startswith("#"), theme.c(token))
check("日志区前景与背景对比度足够",
      abs(QColor(theme.c("text")).lightness() - QColor(theme.c("log_bg")).lightness()) > 80,
      f"{theme.c('text')} on {theme.c('log_bg')}")

print("\n--- 2. 菜单栏 / 托盘图标 ---")
check("系统托盘可用", QSystemTrayIcon.isSystemTrayAvailable())
icon = theme.tray_icon()
print(f"  图标尺寸: {[f'{s.width()}x{s.height()}' for s in icon.availableSizes()]}")
check("图标有多档尺寸", len(icon.availableSizes()) >= 2)
if is_macos:
    check("macOS 图标是模板图（系统自动反色）", icon.isMask())
for size in (22, 44):
    pixmap = icon.pixmap(size, size)
    image = pixmap.toImage()
    opaque = sum(1 for y in range(image.height()) for x in range(image.width())
                 if image.pixelColor(x, y).alpha() > 20)
    check(f"{size}px 图标有实际内容", opaque > 50, f"{opaque} 个不透明像素")
tray = QSystemTrayIcon(icon)
tray.setToolTip("macOS 自检")
tray.show()
process(0.3)
check("tray.show() 后 isVisible()", tray.isVisible())
if is_macos:
    bars = status_bar_window_count()
    check("已创建 NSStatusBarWindow（状态项真实存在）", bars >= 1, f"{bars} 个")
    hidden = menu_bar_auto_hidden()
    if hidden:
        print("  ⚠ 系统「自动隐藏菜单栏」已开启（_HIHideMenuBar=1）：菜单栏收起时状态项")
        print("    本来就不显示（不是程序问题）。可在 系统设置 → 外观/桌面与程序坞 关闭，")
        print("    或直接用悬浮球右键菜单里的同名功能。")
    else:
        check("系统菜单栏未自动隐藏", True)

print("\n--- 3. 应用激活策略 ---")
policy = macos_window.activation_policy()
print(f"  当前 activationPolicy: {policy}（0=regular, 1=accessory）")
if is_macos:
    check("应用已切到 accessory 策略（全屏覆盖的前提）",
          policy == macos_window.POLICY_ACCESSORY,
          f"policy={policy}")
else:
    skip("激活策略检查", "仅 macOS 需要")

print("\n--- 4. 悬浮球浮层属性 ---")
ball = FloatingBall()
ball.show()
force_topmost(ball)
attrs = macos_window.window_attrs(ball)
check("能取到底层 NSWindow", attrs is not None)
if attrs:
    print(f"  level={attrs['level']} behavior=0x{attrs['behavior']:x} "
          f"hidesOnDeactivate={attrs['hides_on_deactivate']} canHide={attrs['can_hide']}")
    check("层级达到 NSStatusWindowLevel",
          attrs["level"] >= macos_window.NS_STATUS_WINDOW_LEVEL, f"level={attrs['level']}")
    check("CanJoinAllSpaces（跟随到全屏 Space）",
          bool(attrs["behavior"] & macos_window.NS_CAN_JOIN_ALL_SPACES))
    check("FullScreenAuxiliary（可与全屏窗口共存）",
          bool(attrs["behavior"] & macos_window.NS_FULL_SCREEN_AUXILIARY))
    check("Stationary（切 Space 不跟着跑）",
          bool(attrs["behavior"] & macos_window.NS_STATIONARY))
    check("hidesOnDeactivate = False", not attrs["hides_on_deactivate"])
    check("canHide = False", not attrs["can_hide"])
    ball.hide()
    ball.show()
    force_topmost(ball)
    again = macos_window.window_attrs(ball)
    check("hide + show 后属性仍然保留",
          again is not None and again["level"] == attrs["level"]
          and again["behavior"] == attrs["behavior"])
ball.hide()
ball.deleteLater()

if FULLSCREEN_TEST and is_macos:
    fullscreen_test()
elif FULLSCREEN_TEST:
    skip("真实全屏测试", "仅 macOS 支持")
else:
    print("\n提示：想验证「真·原生全屏」下的覆盖效果，运行")
    print("      python tools/macos_check.py --fullscreen")

print("\n" + "=" * 66)
if failures:
    print(f"失败 {len(failures)} 项：")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)
print("全部通过")
QTimer.singleShot(0, app.quit)
app.exec_()
