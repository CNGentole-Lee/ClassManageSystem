"""Prepare a clean folder for a one-shot upload through the GitHub web UI.

Why: this machine has no remote configured, so the GitHub repository has been
kept up to date by dragging individual files into the web uploader. That is how
files get skipped (`namepicker/integrity.py` went missing once) and how the
remote ends up as a mix of versions.

This script copies **exactly the tracked files** of the current commit into
`upload/`, preserving paths, and prints a checklist:

    python tools/prepare_upload.py
    # then drag the *contents* of upload/ onto GitHub (Chrome supports folders)

It does not delete anything; files that were removed from the project must be
deleted in the GitHub UI by hand (the script lists them).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

UPLOAD_DIR = os.path.join(_ROOT, "upload")

#: 这些路径即使被 git 跟踪也不该出现在上传目录里
EXCLUDE_PREFIXES = (".git/", "upload/", "dist/", "build/", "Data/")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_ROOT,
        capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def removed_files() -> list[str]:
    """本分支相对 master 删除过的文件（GitHub 网页不会自动删）。"""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-status", "master..HEAD"], cwd=_ROOT,
            capture_output=True, check=True).stdout.decode("utf-8")
    except subprocess.CalledProcessError:
        return []
    gone = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("D"):
            gone.append(parts[1])
    return gone


def main() -> int:
    files = [f for f in tracked_files()
             if not f.startswith(EXCLUDE_PREFIXES)]
    if not files:
        print("[FAIL] no tracked files found; run this inside the repository")
        return 1

    if os.path.isdir(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    total = 0
    for rel in files:
        src = os.path.join(_ROOT, rel)
        dst = os.path.join(UPLOAD_DIR, rel)
        if not os.path.isfile(src):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        total += os.path.getsize(src)

    print(f"[OK  ] copied {len(files)} files ({total / 1024 / 1024:.1f} MB) -> upload/")
    print()
    print("下一步：把 upload/ 里的**内容**整体拖进 GitHub 的 Upload files 页面。")
    print("       （不要只挑几个文件——上次就是这样漏了 integrity.py）")
    print()

    gone = removed_files()
    if gone:
        print("另外，这些文件已从项目中删除，需要在 GitHub 上手工删除：")
        for rel in gone:
            print(f"  - {rel}")
        print()

    # 关键文件自检
    important = [
        "namepicker/integrity.py",
        "namepicker/guard.py",
        "namepicker/sntp.py",
        "namepicker/native_manifest.py",
        "native/cmd_sign",
        "native/cmd_verify",
        "native/cmd_sign.exe",
        "native/cmd_verify.exe",
        "namepicker/native_backup/cmd_sign.gz",
        "namepicker/native_backup/cmd_verify.gz",
    ]
    missing = [rel for rel in important if not os.path.isfile(os.path.join(UPLOAD_DIR, rel))]
    if missing:
        print("[!] 上传目录里缺少关键文件：", ", ".join(missing))
    else:
        print("[OK  ] 关键文件齐全（安全模块、两个二进制、还原副本）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
