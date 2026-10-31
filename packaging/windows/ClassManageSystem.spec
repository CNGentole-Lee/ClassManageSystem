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

#: False = 单目录版本（目录 + _internal），由安装包打包成安装程序。
#: 为什么不用单文件：PySide6/Qt 是 LGPL，LGPL 要求用户**能够替换 Qt 库**。
#: 单文件 EXE 运行时把 Qt 解压到临时目录、退出即删，用户无法替换；
#: 目录模式下 Qt 的 dll 是独立文件，安装后可直接替换 —— 符合 LGPL 第 4(d) 条。
ONEFILE = False

APP_NAME = "ClassManageSystem"

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir, os.pardir))
ICON = os.path.join(SPECPATH, "app.ico")


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


def version_file() -> str:
    """把 version_info.txt 的版本号替换成当前版本，写到构建目录里。

    模板仍放在 packaging/windows/version_info.txt（便于人工查看），但 EXE 属性里
    的版本号必须和「关于」窗口一致，所以构建时生成，不靠手改。
    """
    version = app_version()
    parts = (version.split(".") + ["0", "0", "0", "0"])[:4]
    ints = ", ".join(str(int(p)) for p in parts)
    dotted = ".".join(parts)

    template_path = os.path.join(SPECPATH, "version_info.txt")
    with open(template_path, encoding="utf-8") as fh:
        text = fh.read()
    import re
    text = re.sub(r"filevers=\(\s*[\d,\s]+\)", f"filevers=({ints})", text)
    text = re.sub(r"prodvers=\(\s*[\d,\s]+\)", f"prodvers=({ints})", text)
    text = re.sub(r"StringStruct\('FileVersion',\s*'[^']*'\)",
                  f"StringStruct('FileVersion', '{dotted}')", text)
    text = re.sub(r"StringStruct\('ProductVersion',\s*'[^']*'\)",
                  f"StringStruct('ProductVersion', '{dotted}')", text)

    generated = os.path.join(SPECPATH, "version_info.generated.txt")
    with open(generated, "w", encoding="utf-8") as fh:
        fh.write(text)
    return generated


VERSION_FILE = version_file()

NATIVE_SRC = os.path.join(ROOT, "native", "cmd_native.exe")


def require_native() -> str:
    """原生模块必须随包分发，否则程序只能以只读模式运行。

    宁可让构建失败，也不要打出一个“看起来正常、实际不能记分”的安装包。
    """
    if not os.path.isfile(NATIVE_SRC):
        raise SystemExit(
            "[x] native/cmd_native.exe is missing.\n"
            "    Build it first (native/build_windows.sh on macOS, or on Windows)\n"
            "    or fetch it from the private native repository.")
    return NATIVE_SRC


a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    # 原生模块：rules + crypto + chain. Destination "native" keeps the layout
    # the Python bridge expects (_MEIPASS/native/cmd_native.exe).
    binaries=[(require_native(), "native")],
    # 程序运行时不读取包内资源：名单文件由老师自己选；配置/日志写在 EXE 旁边，
    # 只读目录则回退到 %APPDATA%\ClassTerminal2411。
    # 随包资源：LICENSE（Apache-2.0 全文）、NOTICE、第三方声明。
    # Apache-2.0 第 4(d) 条要求再分发时附带许可证与 NOTICE。
    # 目录模式下 datas 会放进 _internal/，运行时通过 sys._MEIPASS 读取，
    # 「关于」窗口从那里取许可证文本。
    datas=[
        (os.path.join(ROOT, "LICENSE"), "."),
        (os.path.join(ROOT, "NOTICE"), "."),
        (os.path.join(ROOT, "THIRD-PARTY-NOTICES.md"), "."),
        # 原生模块的专有许可：关于窗口的「原生模块」分页会读取它
        (os.path.join(ROOT, "native", "LICENSE"), "native"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 砍掉用不到的模块。注意别写 "PySide6" —— 那会把整个绑定砍没。
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


# ============================================================
#  GPL-3.0：确认许可证真的进了**单文件 EXE**
# ============================================================
# 我们的分发形态是一个 EXE，用户不会额外拿到任何文件，所以许可证必须在包内
# （由上面的 datas 保证）。这里在构建结束时做一次硬校验：
# 缺了 LICENSE / NOTICE 就**直接让构建失败**，避免打出一个「关于」窗口只能显示
# 内置摘要的包 —— 那不符合 Apache-2.0 第 4(d) 条。
def _require_license() -> None:
    src = os.path.join(ROOT, "LICENSE")
    if not os.path.isfile(src) or os.path.getsize(src) == 0:
        raise SystemExit(
            "[x] LICENSE is missing or empty: " + src +
            "\n    It must be bundled inside the single-file EXE (GPL-3.0).")
    # a.datas 的条目是 (源文件, 包内目标目录)，源文件在第 0 位。
    # 注意 PyInstaller 会把它们规范成 TOC 三元组，所以两个位置都看一眼。
    def _is_license(item) -> bool:
        for part in (item if isinstance(item, (tuple, list)) else (item,)):
            try:
                if os.path.abspath(str(part)) == os.path.abspath(src):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    for extra in ("NOTICE", "THIRD-PARTY-NOTICES.md"):
        path = os.path.join(ROOT, extra)
        if not os.path.isfile(path):
            raise SystemExit("[x] " + extra + " is missing; Apache-2.0 requires it.")

    if not any(_is_license(entry) for entry in (a.datas or [])):
        raise SystemExit(
            "[x] LICENSE is not part of datas, so it would not be inside the EXE.")
    print("[i] LICENSE bundled into the EXE:", os.path.getsize(src), "bytes")


_require_license()
