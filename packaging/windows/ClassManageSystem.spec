# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— Windows EXE。

只能在 Windows 上执行（PyInstaller 不支持交叉编译）。两种用法：

    # 1) GitHub Actions 的 windows-latest runner（推荐，见 .github/workflows/）
    # 2) 任意一台 Windows：packaging\\windows\\build.bat

命令行等价物：
    pyinstaller packaging/windows/ClassManageSystem.spec --noconfirm --clean

产物：dist/ClassManageSystem.exe（单文件，双击即用，无需安装 Python）
"""

import os

#: True = 单文件 EXE（分发省事；启动时解压到临时目录，首次启动约 1~3 秒）；
#: False = 单目录版本（启动更快、杀软误报更少，但要把整个文件夹一起拷）。
ONEFILE = True

APP_NAME = "ClassManageSystem"

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir, os.pardir))
ICON = os.path.join(SPECPATH, "app.ico")
VERSION_FILE = os.path.join(SPECPATH, "version_info.txt")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    # 程序运行时不读取包内资源：名单文件由老师自己选；配置/日志写在 EXE 旁边，
    # 只读目录则回退到 %APPDATA%\ClassTerminal2411。所以不需要 datas。
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 砍掉用不到的模块。注意别写 "PyQt5" —— 那会把整个绑定砍没。
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

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,              # 不启用 UPX，它最容易触发杀软误报
        runtime_tmpdir=None,
        console=False,          # 窗口程序，不弹黑框；出错写 crash.log
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON if os.path.isfile(ICON) else None,
        version=VERSION_FILE if os.path.isfile(VERSION_FILE) else None,
    )
else:
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
        console=False,
        disable_windowed_traceback=False,
        icon=ICON if os.path.isfile(ICON) else None,
        version=VERSION_FILE if os.path.isfile(VERSION_FILE) else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=APP_NAME,
    )
