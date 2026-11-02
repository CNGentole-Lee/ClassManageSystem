"""生成发布用的 version.json（作为 Release 资产上传）。

为什么要它：同 Tag 覆盖发布时，仓库里的文件不会变，只有资产会变。
程序读 `releases/latest/download/version.json`，这个地址永远指向
最新一次发布，因此同 Tag、换 Tag 都能正确判断有没有新版。

用法：
    python tools/make_version_json.py --out dist/version.json dist/*Setup.exe dist/*.dmg
"""

import argparse
import datetime
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_name(version: str, path: str) -> str:
    """把资产名规范成 URL 安全的名字。

    hdiutil 在目标文件已存在时会生成 `“xxx”已转换.dmg` 这种带引号的名字，
    启动器的资产名校验会直接拒绝它。这里改名，保证 version.json 里的名字
    和实际上传的资产名一致。
    """
    lower = path.lower()
    if lower.endswith("setup.exe"):
        return f"ClassManageSystem-{version}-Setup.exe"
    if lower.endswith(".zip"):
        return f"ClassManageSystem-{version}-macos.zip"
    return f"ClassManageSystem-{version}-macos.dmg"


def platform_of(path: str) -> str:
    name = os.path.basename(path).lower()
    if name.endswith("setup.exe"):
        return "windows"
    if name.endswith(".dmg"):
        return "macos"
    if name.endswith(".zip") and "macos" in name:
        return "macos"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--build", default="")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    from namepicker.about_dialog import VERSION

    build = args.build or datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    assets: dict[str, str] = {}
    sums: dict[str, str] = {}
    for path in args.files:
        if not os.path.isfile(path):
            continue
        key = platform_of(path)
        if not key or key in assets:
            continue
        target = canonical_name(VERSION, path)
        if os.path.basename(path) != target:
            safe = os.path.join(os.path.dirname(os.path.abspath(path)), target)
            os.replace(path, safe)
            print(f"[i] renamed asset: {os.path.basename(path)} -> {target}")
            path = safe
        assets[key] = os.path.basename(path)
        sums[key] = sha256(path)

    if not assets:
        print("[FAIL] no installer found (expected *Setup.exe or *.dmg)")
        return 1

    body = {
        "version": VERSION,
        "build": build,
        "notes": os.environ.get("RELEASE_NOTES", ""),
        "assets": assets,
        "sha256": sums,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(body, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"[OK  ] {args.out}: version={VERSION} build={build}")
    for key in assets:
        print(f"       {key:8} {assets[key]}  {sums[key][:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
