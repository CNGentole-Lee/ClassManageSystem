"""Static check with pyflakes: undefined names crash at runtime.

Usage:
    python tools/lint_check.py

Exit code: 0 = clean, 1 = findings, 77 = pyflakes not installed (skipped).

Why: a rename once left `DEPENDENCIES_ZH` referenced after the constant was
deleted; the About dialog crashed only when THIRD-PARTY-NOTICES.md was missing,
so no test ever hit it. pyflakes catches this class in a second.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

try:
    from pyflakes.api import checkPath as _pyflakes_check
    from pyflakes.reporter import Reporter
except ImportError:
    print("[SKIP] pyflakes is not installed (pip install pyflakes)")
    sys.exit(77)


class _Collector:
    def __init__(self):
        self.messages = []

    def unexpectedError(self, filename, msg):
        self.messages.append((filename, 0, "E", msg))

    def syntaxError(self, filename, msg, lineno, offset, text):
        self.messages.append((filename, lineno or 0, "E", msg))

    def flake(self, message):
        # pyflakes 的消息对象没有统一的 message_class 属性；
        # 用异常类型名区分“未定义名字”这类致命问题。
        self.messages.append((message.filename, message.lineno,
                              type(message).__name__,
                              message.message % message.message_args))


def main() -> int:
    targets = [os.path.join(_ROOT, "main.py")]
    for folder in ("namepicker", "tools"):
        base = os.path.join(_ROOT, folder)
        for name in sorted(os.listdir(base)):
            if name.endswith(".py"):
                targets.append(os.path.join(base, name))

    collector = _Collector()
    for path in targets:
        _pyflakes_check(path, collector)

    # 只把“未定义名字/语法错误”视为失败；未使用导入等先作为提示
    fatal = [m for m in collector.messages
             if "undefined name" in m[3] or m[2] in ("E", "UndefinedName", "SyntaxError")]
    style = [m for m in collector.messages if m not in fatal]

    for filename, lineno, _kind, msg in fatal:
        rel = os.path.relpath(filename, _ROOT)
        print(f"[FAIL] {rel}:{lineno}: {msg}")
        # GitHub Actions 注解：直接显示在 PR/运行摘要里，不用翻日志
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error file={rel},line={max(lineno, 1)}::{msg}")
    for filename, lineno, _kind, msg in style:
        print(f"[warn] {os.path.relpath(filename, _ROOT)}:{lineno}: {msg}")

    print(f"\n{len(targets)} files, {len(fatal)} fatal, {len(style)} warnings")
    if fatal:
        print("FAILED")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
