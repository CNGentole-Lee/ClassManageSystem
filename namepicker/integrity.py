"""integrity —— 原生模块完整性、恢复、ctime 见证与篡改归档。

职责边界（重要）：
    这里**不含业务规则**，只做“文件是否被换过 / 数据是否被还原过”的判定。
    业务规则与验签仍由闭源的 cmd_native 负责。

分层：
    1. native 二进制 SHA-256 与 native_manifest.py 固定值比对
    2. 不一致 → 可从 namepicker/native_backup/*.gz 一键还原
    3. ctime 见证：文件 inode 变更时间不可能被普通用户回拨
    4. 异常分级归档到 tamper.log（不打断上课）
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import time

from . import native_manifest

#: 备份文件所在目录（随包分发）
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "native_backup")

#: ctime 与最后事件时间相差多少秒视为“文件被整体替换”
CTIME_TOLERANCE_S = 600

#: 异常等级
LEVEL_INFO = "info"
LEVEL_WARN = "warn"
LEVEL_CRITICAL = "critical"


def _platform_key() -> str:
    return "win32" if sys.platform == "win32" else "darwin"


def expected(role: str = "sign") -> tuple[str, str, int, str] | None:
    """(binary_name, sha256, size, backup_name)；不支持的平台返回 None。"""
    return native_manifest.NATIVE.get(_platform_key(), {}).get(role)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_native(path: str, role: str = "sign") -> dict:
    """检查原生模块是否与固定值一致。

    返回 {"ok": bool, "reason": str, "expected": str, "actual": str,
          "restorable": bool}
    """
    info = expected(role)
    if info is None:
        return {"ok": True, "reason": "unsupported-platform"}
    _name, want_hash, want_size, backup = info
    result = {"ok": False, "reason": "", "expected": want_hash, "actual": "",
              "restorable": os.path.isfile(os.path.join(BACKUP_DIR, backup))}
    if not os.path.isfile(path):
        result["reason"] = "MISSING"
        return result
    try:
        actual = sha256_file(path)
        size = os.path.getsize(path)
    except OSError as exc:
        result["reason"] = f"UNREADABLE {exc}"
        return result
    result["actual"] = actual
    if size != want_size:
        result["reason"] = f"SIZE {size}!={want_size}"
        return result
    if actual != want_hash:
        result["reason"] = "HASH_MISMATCH"
        return result
    result["ok"] = True
    result["reason"] = "OK"
    return result


def restore_native(path: str, role: str = "sign") -> dict:
    """用随包的原始副本覆盖原生模块，然后复验。

    返回 {"ok": bool, "reason": str}
    """
    info = expected(role)
    if info is None:
        return {"ok": False, "reason": "unsupported-platform"}
    _name, want_hash, _size, backup = info
    backup_path = os.path.join(BACKUP_DIR, backup)
    if not os.path.isfile(backup_path):
        return {"ok": False, "reason": "NO_BACKUP"}
    try:
        with gzip.open(backup_path, "rb") as fh:
            payload = fh.read()
        if hashlib.sha256(payload).hexdigest() != want_hash:
            return {"ok": False, "reason": "BACKUP_CORRUPT"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".restore"
        with open(tmp, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        if sys.platform != "win32":
            os.chmod(tmp, 0o755)
        os.replace(tmp, path)
        if sys.platform != "win32":
            # 还原后的二进制保留原签名；这里只确保没有隔离属性
            os.system(f'xattr -d com.apple.quarantine "{path}" 2>/dev/null')
    except OSError as exc:
        return {"ok": False, "reason": f"RESTORE_FAILED {exc}"}
    again = check_native(path, role)
    return {"ok": again["ok"], "reason": "RESTORED" if again["ok"] else again["reason"]}


def ctime_gap(path: str, last_event_ts: float) -> float | None:
    """文件 ctime 与最后一条事件时间之差（秒）。

    用法：拷贝旧文件会新建 inode，ctime 变成“现在”，与最后事件时间拉开差距。
    返回 None 表示无法判定（文件不存在 / 文件系统无 ctime 语义）。
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    ctime = getattr(st, "st_birthtime", None)
    # macOS 用 st_ctime（inode 变更时间）；Windows 的 st_ctime 是创建时间，
    # 都不可被普通用户回拨，方向一致。
    ctime = st.st_ctime
    if not ctime or ctime <= 0:
        return None
    return float(ctime) - float(last_event_ts)


def check_ctime(path: str, last_event_ts: float, tolerance: float = CTIME_TOLERANCE_S) -> dict:
    """判定文件是否被整体替换过。"""
    gap = ctime_gap(path, last_event_ts)
    if gap is None:
        return {"ok": True, "reason": "UNKNOWN", "gap": None}
    # ctime 早于最后事件时间是不可能的（写入必然更新 ctime），说明时钟/文件异常
    if gap < -tolerance:
        return {"ok": False, "reason": "CTIME_BEFORE_EVENT", "gap": gap}
    # ctime 明显晚于最后事件时间：文件被重新创建过（拷贝旧数据）
    if gap > tolerance:
        return {"ok": False, "reason": f"CTIME_AHEAD {gap:.0f}s", "gap": gap}
    return {"ok": True, "reason": "OK", "gap": gap}


def classify_anomaly(result: dict) -> tuple[str, str]:
    """把检查结果分级：(level, code)。"""
    if result.get("ok"):
        return LEVEL_INFO, "OK"
    reason = str(result.get("reason", ""))
    if reason in ("MISSING", "HASH_MISMATCH", "SIZE") or reason.startswith("SIZE "):
        return LEVEL_CRITICAL, "NATIVE_REPLACED"
    if reason.startswith("CTIME_AHEAD"):
        return LEVEL_CRITICAL, "SNAPSHOT_RESTORED"
    if reason.startswith("CTIME_BEFORE_EVENT"):
        return LEVEL_WARN, "CLOCK_ANOMALY"
    return LEVEL_WARN, reason.split()[0] if reason else "UNKNOWN"


def append_tamper_log(log_dir: str, level: str, code: str, detail: str = "") -> None:
    """把异常追加到 tamper.log（独立文件，不进链，不影响业务）。"""
    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "tamper.log")
        line = json.dumps({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "code": code,
            "detail": detail,
        }, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def read_tamper_log(log_dir: str, limit: int = 20) -> list[dict]:
    path = os.path.join(log_dir, "tamper.log")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
