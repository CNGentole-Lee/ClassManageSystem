#!/usr/bin/env python3
"""一键跑全套测试 —— 双击即可（macOS / Windows / Linux）。

它自己解决三件事：
  1. 找到能用的 Python（优先项目里的 .conda，其次当前解释器）；
  2. 给每个测试设置隔离的 HOME / QT_QPA_PLATFORM=offscreen，
     不会污染你的真实配置，也不需要在 CI 里有真实显示器；
  3. 逐项限时运行，卡住的直接杀掉并继续下一项 —— 不会整场挂死；
  4. 默认把每项测试的输出**实时**打印出来（能看见卡在哪一步）。

用法：
    双击本文件；或在终端里：
        python tools/run_all_tests.py          # 全部
        python tools/run_all_tests.py --gui    # 用真实窗口跑（本机调试用）
        python tools/run_all_tests.py -k wipe  # 只跑名字含 wipe 的
        python tools/run_all_tests.py -q       # 只看失败摘要

退出码 0 = 全绿；非 0 = 有失败/超时。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 按「快 → 慢」排序；平台专属的放在最后
TESTS = [
    ("config_check", 60),
    ("wipe_check", 60),
    ("i18n_check", 90),
    ("config_crypto_check", 60),
    ("log_crypto_check", 60),
    ("smoke_test", 120),
    ("group_count_stress", 180),
    ("native_check", 120),        # 原生模块；缺失时返回 77 -> SKIP
    ("ledger_check", 180),        # 事件链：迁移/重放/篡改/回滚
    ("packaging_check", 60),      # 打包配置：spec / 安装包 / CI 一致性
    ("windows_check", 60),      # 非 Windows 上会自动跳过 Win32 分支
    ("macos_check", 120),       # 非 macOS / offscreen 下会自动跳过
]

#: 这些测试会写配置，必须隔离 HOME，避免碰真实数据
NEEDS_HOME = {"config_crypto_check", "log_crypto_check", "smoke_test"}


def find_python() -> str:
    """优先用项目自带的 .conda，其次当前解释器。"""
    candidates = []
    if sys.platform == "win32":
        candidates.append(os.path.join(ROOT, ".conda", "python.exe"))
        candidates.append(os.path.join(ROOT, ".venv-build", "Scripts", "python.exe"))
    else:
        candidates.append(os.path.join(ROOT, ".conda", "bin", "python"))
        candidates.append(os.path.join(ROOT, ".venv-build", "bin", "python"))
    candidates.append(sys.executable)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return sys.executable


def run_one(python: str, name: str, timeout: int, gui: bool,
            stream: bool = True) -> tuple[bool | None, float, str]:
    """运行一项测试。

    stream=True 时把子进程输出**实时**转发到终端（能看见卡在哪一步），
    同时留一份全文用于最后的失败摘要；stream=False 时只收集。
    """
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if not gui:
        env["QT_QPA_PLATFORM"] = "offscreen"
    if name in NEEDS_HOME:
        env["HOME"] = tempfile.mkdtemp(prefix=f"cm_{name}_")

    script = os.path.join(HERE, f"{name}.py")
    started = time.time()
    collected: list[str] = []

    try:
        proc = subprocess.Popen(
            [python, "-u", script], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1,
        )
    except Exception as exc:                      # pragma: no cover
        return False, time.time() - started, f"[error] {exc}"

    timed_out = False
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            collected.append(line)
            if stream:
                sys.stdout.write(line)
                sys.stdout.flush()
            if time.time() - started > timeout:
                timed_out = True
                proc.kill()
                break
        proc.wait(timeout=max(1, timeout))
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    elapsed = time.time() - started
    out = "".join(collected)
    if timed_out:
        out += f"\n[timeout] 超过 {timeout}s，已终止"
        if stream:
            print(f"[timeout] 超过 {timeout}s，已终止", flush=True)
        return False, elapsed, out
    if proc.returncode == 77:          # 约定：依赖缺失 -> 跳过，不算失败
        return None, elapsed, out
    return proc.returncode == 0, elapsed, out


def highlight(output: str) -> str:
    """只打印失败行和最后几行，避免刷屏。"""
    lines = []
    for line in output.splitlines():
        if line.startswith("[FAIL]") or "[timeout]" in line or "[error]" in line:
            lines.append(line)
        elif "Traceback" in line or "Error" in line:
            lines.append(line)
    if not lines:
        tail = [l for l in output.splitlines() if l.strip()][-3:]
        lines = tail
    return "\n".join("      " + l for l in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="一键跑全套测试")
    parser.add_argument("--gui", action="store_true",
                        help="用真实窗口跑（默认 offscreen，等价 CI）")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="只打印失败摘要（默认打印每项测试的完整输出）")
    parser.add_argument("-k", "--filter", default="",
                        help="只跑名字包含该字符串的测试")
    args = parser.parse_args()

    python = find_python()
    tests = [(n, t) for n, t in TESTS if args.filter.lower() in n.lower()]
    if not tests:
        print(f"没有匹配 {args.filter!r} 的测试")
        return 1

    print("=" * 66)
    print(f"Python      : {python}")
    print(f"平台        : {sys.platform}")
    print(f"窗口模式    : {'真实 GUI' if args.gui else 'offscreen（无头）'}")
    print(f"测试数量    : {len(tests)}")
    print("=" * 66)

    failed = []
    total = time.time()
    for name, timeout in tests:
        print(f"\n>>> {name} ...", flush=True)
        ok, elapsed, output = run_one(python, name, timeout, args.gui,
                                      stream=not args.quiet)
        status = "SKIP" if ok is None else ("OK" if ok else "FAIL")
        print(f"<<< {status}  {elapsed:.1f}s")
        if ok is False:
            failed.append(name)
            if args.quiet:
                print(highlight(output))

    print("\n" + "=" * 66)
    print(f"总计 {time.time() - total:.1f}s")
    if failed:
        print(f"失败 {len(failed)} 项: {', '.join(failed)}")
        print("=" * 66)
        return 1
    print(f"全部通过（{len(tests)} 项）")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    code = main()
    # 双击运行时窗口会立刻关掉，留一个停顿方便看结果
    if sys.platform == "win32" and sys.stdin and sys.stdin.isatty():
        input("\n按回车关闭...")
    sys.exit(code)
