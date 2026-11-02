"""递增版本号（默认 patch），写回 namepicker/about_dialog.py。

用法：
    python tools/bump_version.py          # 3.0.1 -> 3.0.2
    python tools/bump_version.py minor    # 3.0.2 -> 3.1.0
    python tools/bump_version.py major    # 3.1.0 -> 4.0.0

发布流程用 V{版本号} 当 tag，所以发版前先跑一次这个脚本，
再 commit + push，tag 就不会重复。
"""

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

ABOUT = os.path.join(_ROOT, "namepicker", "about_dialog.py")
PATTERN = re.compile(r'^(VERSION\s*=\s*")(\d+)\.(\d+)\.(\d+)(")$', re.M)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("part", nargs="?", default="patch",
                        choices=("patch", "minor", "major"))
    args = parser.parse_args()

    text = open(ABOUT, encoding="utf-8").read()
    match = PATTERN.search(text)
    if not match:
        print("[FAIL] VERSION not found in about_dialog.py")
        return 1

    major, minor, patch = (int(match.group(2)), int(match.group(3)), int(match.group(4)))
    old = f"{major}.{minor}.{patch}"
    if args.part == "major":
        major, minor, patch = major + 1, 0, 0
    elif args.part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new = f"{major}.{minor}.{patch}"

    text = text[:match.start()] + f'{match.group(1)}{new}"' + text[match.end():]
    open(ABOUT, "w", encoding="utf-8").write(text)
    print(f"[OK  ] {old} -> {new}  (tag V{new})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
