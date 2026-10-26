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

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    # 程序运行时不读取包内资源：名单文件由老师自己选；配置/日志写在 EXE 旁边，
    # 只读目录则回退到 %APPDATA%\ClassTerminal2411。
    # 唯一要随包走的资源是 LICENSE —— GPL-3.0 要求分发时附带许可证全文，
    # 「关于」窗口会读取它显示。
    datas=[(os.path.join(ROOT, "LICENSE"), ".")],
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


# ============================================================
#  GPL-3.0：把 LICENSE 放到分发包里
# ============================================================
# 1) a.datas 已经把 LICENSE 打进 EXE（单文件）/ 程序目录（目录模式），
#    程序内「关于」窗口能读到；
# 2) GPL 还要求随分发的副本能看到许可证文本，所以在构建结束时再往
#    dist 目录放一份明文，用户直接打开 dist 就能看到。
# 复制失败不影响出包（程序内仍有内置回退文本）。
def _ship_license() -> None:
    import shutil
    src = os.path.join(ROOT, "LICENSE")
    if not os.path.isfile(src):
        print("[w] LICENSE not found in the project root")
        return
    dist_dir = os.path.join(ROOT, "dist")
    try:
        os.makedirs(dist_dir, exist_ok=True)
        shutil.copy2(src, os.path.join(dist_dir, "LICENSE"))
        print("[i] shipped LICENSE ->", os.path.join(dist_dir, "LICENSE"))
    except OSError as exc:
        print("[w] could not copy LICENSE:", exc)


_ship_license()
