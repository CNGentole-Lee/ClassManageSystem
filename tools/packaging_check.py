"""Static checks for the packaging setup (no build, no network).

Usage:
    python tools/packaging_check.py

Why: a packaging config can silently drift from the app (missing native module,
missing license, installer not shipped). These checks fail fast in CI instead of
producing an installer that runs in read-only mode.

Covers:
    1. both PyInstaller specs reference the native binary and fail fast without it;
    2. both specs bundle LICENSE, NOTICE and THIRD-PARTY-NOTICES.md;
    3. the native binaries exist for macOS and Windows;
    4. the Windows installer (Inno Setup) exists, ships the license, installs
       per-user (no admin) and points at the PyInstaller onedir output;
    5. the Windows CI workflow builds the installer and uploads it;
    6. the macOS build script produces a .dmg and checks the native module.

Exit code 0 = all passed, 1 = failure.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

failed = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failed.append(label)


def read(rel: str) -> str:
    path = os.path.join(_ROOT, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def main() -> int:
    win_spec = read("packaging/windows/ClassManageSystem.spec")
    mac_spec = read("packaging/macos/ClassManageSystem.spec")
    iss = read("packaging/windows/installer.iss")
    workflow = read(".github/workflows/build-windows.yml")
    build_cmd = read("packaging/macos/build.command")

    # ---- specs ------------------------------------------------------
    for label, spec, exe in (
        ("windows", win_spec, "cmd_native.exe"),
        ("macos", mac_spec, "cmd_native"),
    ):
        check(f"{label} spec exists", bool(spec))
        check(f"{label} spec references {exe}", exe in spec)
        check(f"{label} spec fails fast without the native module",
              "raise SystemExit" in spec and "missing" in spec)
        check(f"{label} spec bundles LICENSE", '"LICENSE"' in spec)
        check(f"{label} spec bundles NOTICE", '"NOTICE"' in spec)
        check(f"{label} spec bundles third-party notices",
              "THIRD-PARTY-NOTICES.md" in spec)
        check(f"{label} spec bundles the native module license",
              '"native"' in spec and "LICENSE" in spec)

    # ---- native binaries -------------------------------------------
    check("macOS native binary exists", os.path.isfile(os.path.join(_ROOT, "native", "cmd_native")))
    check("Windows native binary exists", os.path.isfile(os.path.join(_ROOT, "native", "cmd_native.exe")))
    check("native binaries are committed (not ignored)",
          "native/cmd_native" not in read(".gitignore").replace("# 注意：发布用的二进制", ""))

    # ---- Windows installer -----------------------------------------
    check("installer script exists", bool(iss))
    check("installer ships LICENSE", "LicenseFile=" in iss and "LICENSE" in iss)
    check("installer installs per-user (no admin)",
          "PrivilegesRequired=lowest" in iss and "localappdata" in iss)
    check("installer packages the onedir output",
          r"dist\ClassManageSystem\*" in iss)
    check("installer creates start-menu and desktop shortcuts",
          "[Icons]" in iss and "autodesktop" in iss)
    check("installer has an uninstaller",
          "{uninstallexe}" in iss)
    check("installer version is injected at build time",
          "#ifndef MyAppVersion" in iss and "MyAppVersion" in iss)

    # ---- CI ---------------------------------------------------------
    check("workflow builds the Inno Setup installer",
          "innosetup" in workflow and "ISCC" in workflow)
    # ISCC 的 /D 定义必须在脚本路径之前，否则会被当成第二个脚本文件
    iscc_line = next((l for l in workflow.splitlines() if "& $iscc" in l), "")
    check("ISCC receives /D before the script path",
          iscc_line.find('"/DMyAppVersion=') < iscc_line.find('installer.iss')
          and iscc_line.find('"/DMyAppVersion=') != -1, iscc_line.strip()[:80])
    check("workflow fails fast when ISCC fails", "LASTEXITCODE" in workflow)
    check("installer paths are derived from the script location",
          "RepoRoot" in iss and "SourcePath" in iss)
    check("workflow uploads the installer",
          "Setup.exe" in workflow and "upload-artifact" in workflow)
    check("workflow builds a portable zip", "portable.zip" in workflow)
    check("workflow verifies the native module before packaging",
          "cmd_native.exe" in workflow and "selftest" in workflow)
    check("workflow runs tests headless", "QT_QPA_PLATFORM: offscreen" in workflow)

    # ---- macOS build script ----------------------------------------
    check("macOS build produces a dmg", "hdiutil create" in build_cmd and ".dmg" in build_cmd)
    check("macOS build checks the native module", "native/cmd_native" in build_cmd)
    check("macOS build no longer depends on PyQt5", "PyQt5" not in build_cmd)

    print("\n" + "=" * 60)
    if failed:
        print(f"{len(failed)} FAILED: {failed}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
