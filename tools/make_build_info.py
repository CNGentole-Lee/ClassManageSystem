"""把 version.json 里的版本与构建时间写进 build-info.txt。

打包前运行（spec 只负责把它放进包内）。程序启动时读它判断
"本机是哪个构建"，从而与远端 version.json 比较。
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()


def main() -> int:
    """版本取自 about_dialog.VERSION，构建时间取自当前时刻或 CI 环境变量。

    不再依赖仓库里的 version.json —— 那个文件现在只作为发布资产生成，
    避免两处版本号漂移。
    """
    import datetime

    target = os.path.join(_ROOT, "build-info.txt")
    try:
        from _version import app_version

        build = (os.environ.get("CLASSMANAGE_BUILD")
                 or datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
        info = {"version": app_version(), "build": build}
    except Exception as exc:                              # noqa: BLE001
        print(f"[FAIL] cannot determine version: {exc}")
        return 1
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False)
        fh.write("\n")
    print(f"[OK  ] build-info.txt -> {info['version']} ({info['build']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
