"""native_bridge —— 调用原生模块（cmd_native / cmd_native.exe）的 Python 侧封装。

设计约定：
    * 原生模块是**独立进程**，通过命令行参数与 stdin/stdout 通信；
    * Python 只传明文事件与链头，**不接触任何密钥**；
    * 所有命令输出单行 JSON，失败时返回错误类别码；
    * Windows 上必须带 CREATE_NO_WINDOW，否则每加一分都会闪一个黑框。

找不到原生模块时不抛到界面：调用方用 available() 判断，
并降级为“只读 + 状态栏提示”，避免课上打不开。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys

#: 与 native 侧的 PROTOCOL 对应；不一致时只警告，不阻断
EXPECTED_PROTOCOL = 1

#: Windows: 不弹出控制台窗口
_CREATE_NO_WINDOW = 0x08000000


class NativeError(Exception):
    """调用原生模块失败。"""


class NativeMissing(NativeError):
    """找不到可执行文件，或不可执行。"""


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def native_path() -> str:
    """按优先级定位原生模块；找不到抛 NativeMissing。"""
    name = "cmd_native.exe" if sys.platform == "win32" else "cmd_native"
    candidates = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(os.path.join(meipass, "native", name))
        candidates.append(os.path.join(meipass, name))
    candidates.append(os.path.join(_root(), "native", name))
    candidates.append(os.path.join(os.path.dirname(sys.executable), "native", name))
    for path in candidates:
        if path and os.path.isfile(path):
            if sys.platform != "win32" and not os.access(path, os.X_OK):
                raise NativeMissing(f"not executable: {path}")
            return path
    raise NativeMissing("cmd_native not found; looked in: " + ", ".join(candidates))


def available() -> bool:
    """原生模块是否可用（不抛异常）。"""
    try:
        native_path()
        return True
    except NativeMissing:
        return False


def _run(args: list[str], stdin_text: str | None = None, timeout: float = 20.0) -> dict:
    exe = native_path()
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            [exe] + args,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        raise NativeError(f"timeout after {timeout}s") from exc
    except OSError as exc:
        raise NativeError(str(exc)) from exc

    out = (proc.stdout or "").strip()
    try:
        data = json.loads(out.splitlines()[-1]) if out else {}
    except (ValueError, IndexError) as exc:
        raise NativeError(f"bad json: {out[:200]!r}") from exc
    if not isinstance(data, dict):
        raise NativeError("bad json shape")
    if data.get("ok") is True:
        proto = data.get("protocol")
        if proto is not None and int(proto) != EXPECTED_PROTOCOL:
            raise NativeError(f"protocol mismatch: native={proto} app={EXPECTED_PROTOCOL}")
        return data
    code = data.get("error", "UNKNOWN")
    if code in ("BAD_FP", "BAD_USAGE"):
        raise NativeError(f"native rejected arguments: {code}")
    return data


_fp_cache: str | None = None


def fingerprint(refresh: bool = False) -> str:
    """取环境指纹（hex）。带缓存，避免每次加分都起进程。"""
    global _fp_cache
    if _fp_cache is not None and not refresh:
        return _fp_cache
    data = _run(["fingerprint"], timeout=5)
    fp = data.get("fp")
    if not fp:
        raise NativeError("missing fp")
    _fp_cache = str(fp)
    return _fp_cache


def reset_cache() -> None:
    global _fp_cache
    _fp_cache = None


def state(records: list[bytes]) -> dict:
    """重放整条链，返回业务状态（C++ 计算，Python 不解析事件）。"""
    lines = "\n".join(base64.b64encode(r).decode("ascii") for r in records)
    return _run(["state", "--fp", fingerprint()], stdin_text=lines, timeout=30)


def apply(records: list[bytes], op: str, **kwargs) -> dict:
    """执行一个业务操作；规则校验与事件生成都在 C++ 里。

    kwargs 会按 --key value 的形式传下去（下划线会转成短横线）。
    业务规则拒绝时抛 NativeError。
    """
    args = ["apply", "--fp", fingerprint(), "--op", op]
    for key, value in kwargs.items():
        args += ["--" + key.replace("_", "-"), str(value)]
    lines = "\n".join(base64.b64encode(r).decode("ascii") for r in records)
    data = _run(args, stdin_text=lines, timeout=30)
    if data.get("ok") is not True:
        raise NativeError(str(data.get("error", "APPLY_FAILED")))
    return data


def verify(records: list[bytes], expect_seq: int | None = None,
           expect_head: bytes | None = None) -> tuple[bool, bytes, str]:
    """校验整条链，返回 (ok, head, error_code)。

    records 为按顺序排列的完整记录字节；空链返回 (False, b"", "EMPTY")。
    """
    if not records:
        return False, b"", "EMPTY"
    lines = "\n".join(base64.b64encode(r).decode("ascii") for r in records)
    args = ["verify", "--fp", fingerprint()]
    if expect_seq is not None:
        args += ["--expect-seq", str(int(expect_seq))]
    if expect_head is not None:
        args += ["--expect-head", base64.b64encode(expect_head).decode("ascii")]
    data = _run(args, stdin_text=lines, timeout=30)
    if data.get("ok") is True:
        return True, base64.b64decode(data.get("head", "")), ""
    return False, b"", str(data.get("error", "UNKNOWN"))


def selftest() -> bool:
    """原生模块内置自检（同进程内 append→verify）。"""
    data = _run(["selftest"], timeout=10)
    return data.get("ok") is True
