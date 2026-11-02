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
    source = os.path.join(_ROOT, "version.json")
    target = os.path.join(_ROOT, "build-info.txt")
    try:
        with open(source, encoding="utf-8") as fh:
            data = json.load(fh)
        info = {"version": data["version"], "build": data.get("build", "")}
    except (OSError, ValueError, KeyError) as exc:
        print(f"[FAIL] cannot read version.json: {exc}")
        return 1
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False)
        fh.write("\n")
    print(f"[OK  ] build-info.txt -> {info['version']} ({info['build']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
