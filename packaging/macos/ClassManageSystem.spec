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

_NATIVE_BINS = ("cmd_sign", "cmd_verify")
NATIVE_PAIRS = []
for _name in _NATIVE_BINS:
    _path = os.path.join(ROOT, "native", _name)
    if not os.path.isfile(_path):
        raise SystemExit(
            f"[x] native/{_name} is missing.\n    Build both: native/build_macos.sh")
    NATIVE_PAIRS.append((_path, "native"))

# 一键还原用的原始副本：BUNDLE 的 resources 不复制目录，
# 必须作为 data 文件逐个加入（落在 Resources/native，与二进制同名的 .gz）。
_BACKUP_DIR = os.path.join(ROOT, "namepicker", "native_backup")
_BACKUP_DATAS = []
if os.path.isdir(_BACKUP_DIR):
    for _name in sorted(os.listdir(_BACKUP_DIR)):
        if _name.endswith(".gz"):
            _BACKUP_DATAS.append((os.path.join(_BACKUP_DIR, _name), "native"))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=NATIVE_PAIRS,
    # 运行时不读取包内资源：名单由老师自选；配置/日志写在程序旁边，
    # 只读目录则回退到 ~/ClassTerminal2411。
    # 随包资源：LICENSE（Apache-2.0 全文）、NOTICE、第三方声明。
    # Apache-2.0 第 4(d) 条要求再分发时附带许可证与 NOTICE。
    datas=[
        (os.path.join(ROOT, "LICENSE"), "."),
        (os.path.join(ROOT, "NOTICE"), "."),
        (os.path.join(ROOT, "THIRD-PARTY-NOTICES.md"), "."),
    ] + _BACKUP_DATAS,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc_data", "test", "lib2to3",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
        "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
        "PySide6.QtXml", "PySide6.QtXmlPatterns", "PySide6.QtDBus",
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
_BUNDLED_DOCS = ("LICENSE", "NOTICE", "THIRD-PARTY-NOTICES.md")
LICENSE_LIST = [
    (f"Resources/{name}", os.path.join(ROOT, name), "DATA")
    for name in _BUNDLED_DOCS
    if os.path.isfile(os.path.join(ROOT, name))
]
# 原生模块的专有许可（关于窗口的「原生模块」分页读取）
_NATIVE_LICENSE = os.path.join(ROOT, "native", "LICENSE")
if os.path.isfile(_NATIVE_LICENSE):
    LICENSE_LIST.append(("Resources/native/LICENSE", _NATIVE_LICENSE, "DATA"))

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
