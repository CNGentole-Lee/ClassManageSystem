# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— macOS .app。

只能在 macOS 上执行（PyInstaller 不支持交叉编译）。用法：

    packaging/macos/build.command          # 双击即可
    # 或
    .conda/bin/python -m PyInstaller packaging/macos/ClassManageSystem.spec --noconfirm --clean

产物：dist/ClassManageSystem.app

说明：
- 打出来是**当前 CPU 架构**的原生程序（Apple Silicon 上是 arm64）。
  想同时兼容 Intel 需要 universal2 的 Python + PyQt5，本环境没有，故不做。
- 未做代码签名/公证。本机运行没问题；拷给别人时对方首次要
  右键 → 打开，或执行 xattr -dr com.apple.quarantine <app>。
- 程序是常驻托盘的工具，BUNDLE 里声明 LSUIElement=True：不占 Dock，
  只留菜单栏图标（与 Windows 版"悬浮球 + 托盘"的形态一致）。
"""

import os

APP_NAME = "ClassManageSystem"
DISPLAY_NAME = "班级多用教学辅助终端"


ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir, os.pardir))
ICON = os.path.join(SPECPATH, "app.icns")


def app_version() -> str:
    """版本号从 namepicker/about_dialog.py 读取，避免两处手工同步。"""
    import re
    source = os.path.join(ROOT, "namepicker", "about_dialog.py")
    try:
        with open(source, encoding="utf-8") as fh:
            match = re.search(r'^VERSION\s*=\s*"([^"]+)"', fh.read(), re.M)
        return match.group(1) if match else "0.0.0"
    except OSError:
        return "0.0.0"


VERSION = app_version()

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    # 运行时不读取包内资源：名单由老师自选；配置/日志写在程序旁边，
    # 只读目录则回退到 ~/ClassTerminal2411。
    # 唯一要随包走的资源是 LICENSE —— GPL-3.0 要求分发时附带许可证全文，
    # 「关于」窗口会读取它显示。
    datas=[(os.path.join(ROOT, "LICENSE"), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc_data", "test", "lib2to3",
        "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore",
        "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuickWidgets",
        "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets",
        "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtPositioning",
        "PyQt5.QtLocation", "PyQt5.QtSensors", "PyQt5.QtSerialPort",
        "PyQt5.QtSql", "PyQt5.QtTest", "PyQt5.QtDesigner", "PyQt5.QtHelp",
        "PyQt5.QtXml", "PyQt5.QtXmlPatterns", "PyQt5.QtDBus",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,              # 窗口程序；出错看 crash.log
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,           # 跟随当前解释器架构
    codesign_identity=None,     # 不做签名（本机自用/课堂内分发足够）
    entitlements_file=None,
    icon=ICON if os.path.isfile(ICON) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

# GPL-3.0 要求分发时附带许可证全文。
# 放两个位置：
#   1) Resources/LICENSE —— .app 包内部，「关于」窗口通过
#      sys._MEIPASS / Contents/Resources 都能找到，单拷贝 .app 也不缺；
#   2) .app 同级的 LICENSE —— 用户不打开包也能直接看到。
LICENSE_SRC = os.path.join(ROOT, "LICENSE")
LICENSE_IN_BUNDLE = ("Resources/LICENSE", LICENSE_SRC, "DATA") \
    if os.path.isfile(LICENSE_SRC) else None
LICENSE_LIST = [LICENSE_IN_BUNDLE] if LICENSE_IN_BUNDLE else []

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    resources=LICENSE_LIST,
    icon=ICON if os.path.isfile(ICON) else None,
    bundle_identifier="com.yourorg.classmanagesystem",
    info_plist={
        "CFBundleName": DISPLAY_NAME,
        "CFBundleDisplayName": DISPLAY_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        # 常驻托盘工具：不占 Dock，只留菜单栏图标
        "LSUIElement": True,
        # 首次启动时 macOS 会弹这几类权限询问，这里给出用途说明
        "NSAppleEventsUsageDescription": "用于在课堂中切换到本程序窗口。",
    },
)
