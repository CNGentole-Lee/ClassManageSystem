"""读取程序版本号，不导入 PySide6。

release 工作流跑在 ubuntu 上，那里没有 PySide6；
直接 `import namepicker.about_dialog` 会连带拉起 Qt，导致发布失败。
这里只用正则读源码里的 VERSION 常量。
"""

import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ABOUT = os.path.join(_ROOT, "namepicker", "about_dialog.py")


def app_version() -> str:
    import re

    text = open(_ABOUT, encoding="utf-8").read()
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise RuntimeError("VERSION not found in about_dialog.py")
    return match.group(1)


if __name__ == "__main__":
    print(app_version())
