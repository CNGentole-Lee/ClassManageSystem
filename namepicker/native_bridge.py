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


def _exe_name(role: str) -> str:
    """role: "sign" | "verify"。"""
    if sys.platform == "win32":
        return f"cmd_{role}.exe"
    return f"cmd_{role}"


def native_path(role: str = "sign") -> str:
    """定位某个原生模块（sign/verify）；找不到抛 NativeMissing。"""
    name = _exe_name(role)
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
    raise NativeMissing(f"{name} not found; looked in: " + ", ".join(candidates))


def available() -> bool:
    """两个原生模块是否都可用（不抛异常）。"""
    try:
        native_path("sign")
        native_path("verify")
        return True
    except NativeMissing:
        return False


def _peer_args(role: str) -> list[str]:
    """显式告诉原生程序“另一个程序在哪”。

    C++ 侧虽然能从 argv[0] 推断，但 Windows 上要补 .exe、打包后路径也可能
    不同；由 Python 传绝对路径最稳。
    """
    other = "verify" if role == "sign" else "sign"
    try:
        return ["--peer", native_path(other)]
    except NativeMissing:
        return []


def _run(args: list[str], stdin_text: str | None = None, timeout: float = 20.0,
         role: str = "sign") -> dict:
    exe = native_path(role)
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


def identity() -> bytes:
    """原生模块的 Ed25519 公钥（32 字节）。首启时钉进锚点。"""
    data = _run(["identity", "--fp", fingerprint()] + _peer_args("sign"), timeout=5)
    pub = base64.b64decode(data.get("pubkey", ""))
    if len(pub) != 32:
        raise NativeError("bad pubkey length")
    return pub


def state(records: list[bytes], plains: list[bytes]) -> dict:
    """让【验证器】用公钥验签并重放（不解密）。"""
    pairs = "\n".join(
        base64.b64encode(r).decode("ascii") + "," + base64.b64encode(p).decode("ascii")
        for r, p in zip(records, plains))
    pub = base64.b64encode(identity()).decode("ascii")
    return _run(["state", "--pubkey", pub] + _peer_args("verify"),
                stdin_text=pairs, timeout=30, role="verify")


def apply(records: list[bytes], op: str, **kwargs) -> dict:
    """让【签名器】执行操作；返回 record/plain/state。

    签名器只负责产生签名数据；是否采纳由验证器复核（见 ledger）。
    """
    args = ["apply", "--fp", fingerprint(), "--op", op] + _peer_args("sign")
    for key, value in kwargs.items():
        args += ["--" + key.replace("_", "-"), str(value)]
    lines = "\n".join(base64.b64encode(r).decode("ascii") for r in records)
    data = _run(args, stdin_text=lines, timeout=30, role="sign")
    if data.get("ok") is not True:
        raise NativeError(str(data.get("error", "APPLY_FAILED")))
    return data


def dump(records: list[bytes]) -> dict:
    """让签名器解密整条链，返回 plains/state/ts/head（供验证器使用）。"""
    lines = "\n".join(base64.b64encode(r).decode("ascii") for r in records)
    data = _run(["dump", "--fp", fingerprint()] + _peer_args("sign"),
                stdin_text=lines, timeout=30, role="sign")
    if data.get("ok") is not True:
        raise NativeError(str(data.get("error", "DUMP_FAILED")))
    return data


def migrate(records: list[bytes]) -> dict:
    """把 v1 链重签成 v2（迁移方案 A）。"""
    lines = "\n".join(base64.b64encode(r).decode("ascii") for r in records)
    data = _run(["migrate", "--fp", fingerprint()] + _peer_args("sign"),
                stdin_text=lines, timeout=60, role="sign")
    if data.get("ok") is not True:
        raise NativeError(str(data.get("error", "MIGRATE_FAILED")))
    return data


def verify(records: list[bytes], plains: list[bytes],
           expect_seq: int | None = None) -> tuple[bool, bytes, str]:
    """只验签不重放；用于测试与快速检查。"""
    if not records:
        return False, b"", "EMPTY"
    pairs = "\n".join(
        base64.b64encode(r).decode("ascii") + "," + base64.b64encode(p).decode("ascii")
        for r, p in zip(records, plains))
    pub = base64.b64encode(identity()).decode("ascii")
    data = _run(["verify", "--pubkey", pub] + _peer_args("verify"),
                stdin_text=pairs, timeout=30, role="verify")
    if data.get("ok") is True:
        return True, base64.b64decode(data.get("head", "")), ""
    return False, b"", str(data.get("error", "UNKNOWN"))


def selftest() -> bool:
    for role in ("sign", "verify"):
        data = _run(["selftest"], timeout=10, role=role)
        if data.get("ok") is not True:
            return False
    return True
