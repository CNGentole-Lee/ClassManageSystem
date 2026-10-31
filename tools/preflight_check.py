"""Preflight: the checkout must contain every file the app needs.

Why this exists: the project is often updated by dragging files into the GitHub
web UI. If one file is skipped, the failure shows up much later and looks
unrelated (e.g. `ImportError: cannot import name 'integrity'`, or a stale
`about_dialog.py` raising `NameError`). This check names the missing files
immediately.

Usage:
    python tools/preflight_check.py
Exit code: 0 = complete, 1 = missing files.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

#: 运行与测试都需要的文件（相对仓库根）
REQUIRED = [
    "main.py",
    "requirements.txt",
    "LICENSE",
    "NOTICE",
    "THIRD-PARTY-NOTICES.md",
    # 事件链与安全
    "namepicker/ledger.py",
    "namepicker/native_bridge.py",
    "namepicker/native_manifest.py",
    "namepicker/integrity.py",
    "namepicker/guard.py",
    "namepicker/sntp.py",
    # 原生程序与还原副本
    "native/cmd_sign",
    "native/cmd_verify",
    "native/cmd_sign.exe",
    "native/cmd_verify.exe",
    "native/LICENSE",
    "namepicker/native_backup/cmd_sign.gz",
    "namepicker/native_backup/cmd_verify.gz",
    "namepicker/native_backup/cmd_sign.exe.gz",
    "namepicker/native_backup/cmd_verify.exe.gz",
    # 测试
    "tools/run_all_tests.py",
    "tools/tamper_check.py",
    "tools/ledger_check.py",
    "tools/native_check.py",
    "tools/lint_check.py",
    "tools/packaging_check.py",
    "tools/make_native_manifest.py",
]


def main() -> int:
    missing = [rel for rel in REQUIRED if not os.path.isfile(os.path.join(_ROOT, rel))]
    if missing:
        for rel in missing:
            print(f"[FAIL] missing: {rel}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::error file={rel}::required file is missing from the checkout")
        print(f"\n{len(missing)} required file(s) missing - the upload is incomplete.")
        return 1
    print(f"[OK  ] all {len(REQUIRED)} required files are present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
