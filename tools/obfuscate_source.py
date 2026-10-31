"""Build-time source obfuscation for the native module.

Copies the C++ sources to a build directory and wraps most string literals in
OBF("...") so that `strings` no longer reveals the protocol, error codes or JSON
keys. It is a cost increase, not a cryptographic guarantee: the key is derived
from the line number and lives in the binary.

Usage:
    python tools/obfuscate_source.py --src native/src --out <build dir>

Rules:
    * skip #include / #define / #if lines
    * skip single-character and very short literals ("rb", "/")
    * skip format strings containing '%'
    * skip any line mentioning CROSS_TOKEN (the peer check searches raw bytes)
    * keep comments and char literals untouched
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

SKIP_LINE_PREFIXES = ("#include", "#define", "#if", "#endif", "#else", "#pragma", "#error")
SKIP_LINE_TOKENS = ("CROSS_TOKEN",)


def wrap_literals(source: str) -> str:
    out: list[str] = []
    i = 0
    n = len(source)
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = source[i]

        # 注释：原样输出
        if in_line_comment:
            out.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            out.append(ch)
            if source.startswith("*/", i):
                out.append("/")
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue
        if source.startswith("//", i):
            in_line_comment = True
            out.append("//")
            i += 2
            continue
        if source.startswith("/*", i):
            in_block_comment = True
            out.append("/*")
            i += 2
            continue

        # 字符字面量：原样输出（含转义）
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                out.append(source[i])
                if source[i] == "\\":
                    i += 1
                    if i < n:
                        out.append(source[i])
                        i += 1
                    continue
                if source[i] == "'":
                    i += 1
                    break
                i += 1
            continue

        # 普通字符串字面量
        if ch == '"':
            start = i
            i += 1
            while i < n:
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == '"':
                    i += 1
                    break
                i += 1
            literal = source[start:i]

            line_start = source.rfind("\n", 0, start) + 1
            line_prefix = source[line_start:start]

            skip = (
                any(line_prefix.lstrip().startswith(p) for p in SKIP_LINE_PREFIXES)
                or any(tok in line_prefix for tok in SKIP_LINE_TOKENS)
                or len(literal) <= 4          # ""、"rb"、"/" 这类
                or "%" in literal             # printf 格式串
                or line_prefix.rstrip().endswith("#include")
            )
            if skip:
                out.append(literal)
            else:
                out.append("OBF(" + literal + ")")
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    changed = 0
    for name in sorted(os.listdir(args.src)):
        if not name.endswith((".cpp", ".hpp")):
            continue
        data = open(os.path.join(args.src, name), encoding="utf-8").read()
        if name.endswith(".hpp"):
            result = data
        else:
            result = wrap_literals(data)
            if '#include "obf.hpp"' not in result:
                # 插在第一个 #include 之后
                idx = result.find("\n", result.find("#include"))
                result = result[: idx + 1] + '#include "obf.hpp"\n' + result[idx + 1 :]
        if result != data:
            changed += 1
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            fh.write(result)
    print(f"[i] obfuscated {changed} translation units -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
