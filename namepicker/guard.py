"""guard —— 启动时的安全判定（不含业务规则）。

组成（对应设计里的 2–6 层）：
    2. 原生模块哈希        → 被换/损坏则尝试还原
    3. 锚点 seq/head/ts/digest/pubkey
    5. ctime 见证          → 文件被整体替换（拷回旧目录）
    6. NTP                 → 外部时间；发现整盘镜像/改系统时间
    7. 异常分级            → 静默 / 状态栏标记 / 弹窗

所有判定都只产出“是否异常 + 原因”，不参与算分。
"""

from __future__ import annotations

import base64

from . import integrity, sntp

#: 网络时间与本机时间相差多少秒算异常。
#: 教室电脑的系统时钟经常偏几分钟（主板电池、长期不联网），
#: 300 秒会天天误报；真正用来掩盖回滚的改时间至少是几小时/几天。
NTP_OFFSET_TOLERANCE_S = 1800.0

#: 链最后事件与本机时间的差超过多少秒算“数据陈旧”。
#: 每周重置一次，但假期可能两三周不用，7 天太容易误报。
NTP_STALE_TOLERANCE_S = 30 * 24 * 3600.0


def check_native(path: str, role: str = "sign") -> dict:
    """检查并（按需）还原一个原生模块。返回 {"ok", "restored", "reason"}。"""
    result = integrity.check_native(path, role)
    if result["ok"]:
        return {"ok": True, "restored": False, "reason": "OK"}
    if not result["restorable"]:
        return {"ok": False, "restored": False, "reason": result["reason"]}
    fixed = integrity.restore_native(path, role)
    return {"ok": bool(fixed["ok"]), "restored": bool(fixed["ok"]),
            "reason": fixed["reason"]}


def check_both() -> dict:
    """两个二进制都检查；任一损坏都尝试还原。"""
    from . import native_bridge
    out = {"ok": True, "restored": False, "reason": "OK", "roles": {}}
    for role in ("sign", "verify"):
        try:
            path = native_bridge.native_path(role)
        except Exception as exc:                       # noqa: BLE001
            out.update(ok=False, reason=f"{role}: {exc}")
            out["roles"][role] = out["reason"]
            continue
        result = check_native(path, role)
        out["roles"][role] = result["reason"]
        if result["restored"]:
            out["restored"] = True
        if not result["ok"]:
            out.update(ok=False, reason=f"{role}: {result['reason']}")
    return out


def pubkey_b64() -> str:
    """当前机器的公钥（base64），用于与锚点比对。"""
    try:
        from . import native_bridge
        return base64.b64encode(native_bridge.identity()).decode("ascii")
    except Exception:                                  # noqa: BLE001
        return ""


def network_time(timeout: float = 0.8) -> dict:
    """查询 NTP；失败返回 ok=False（绝不抛异常、绝不阻断启动）。"""
    try:
        return sntp.sync(timeout=timeout)
    except Exception as exc:                           # noqa: BLE001
        return {"ok": False, "offset": 0.0, "rtt": 0.0, "server": "",
                "samples": 0, "error": f"{type(exc).__name__}: {exc}"}


def evaluate(chain, state: dict, pubkey: str, ntp: dict | None,
             tolerance_ctime: float = integrity.CTIME_TOLERANCE_S) -> dict:
    """综合判定。

    返回：
        {"level": "info"|"warn"|"critical",
         "problems": [str, ...],
         "ctime": dict,
         "ntp": dict}
    """
    problems: list[str] = []

    problems += chain.anchor_problems(state, pubkey_b64=pubkey)

    ctime = integrity.check_ctime(chain.path, chain.last_ts(), tolerance_ctime)
    if not ctime["ok"]:
        problems.append(ctime["reason"])

    if ntp and ntp.get("ok"):
        offset_ms = abs(float(ntp.get("offset", 0.0))) * 1000.0
        if offset_ms > NTP_OFFSET_TOLERANCE_S * 1000.0:
            problems.append(f"CLOCK_OFF {offset_ms / 1000:.0f}s")
        last = chain.last_ts()
        if last:
            import time as _time
            drift = _time.time() - last
            if drift > NTP_STALE_TOLERANCE_S:
                problems.append(f"STALE_DATA {drift / 86400:.0f}d")

    if not problems:
        level = "info"
    elif any(p.startswith(("SHORTER", "DELETED", "HEAD_MISMATCH",
                           "STATE_MISMATCH", "PUBKEY_MISMATCH",
                           "CTIME_AHEAD", "TIME_ROLLBACK")) for p in problems):
        level = "critical"
    else:
        level = "warn"

    return {"level": level, "problems": problems, "ctime": ctime, "ntp": ntp or {}}


def describe(problem: str) -> str:
    """把内部错误码翻译成老师能看懂的一句话。"""
    if problem.startswith("SHORTER"):
        return "数据比上次记录的短，疑似被旧的备份覆盖"
    if problem == "DELETED":
        return "数据文件被删除"
    if problem == "HEAD_MISMATCH":
        return "数据被替换成了另一条链"
    if problem == "STATE_MISMATCH":
        return "数据内容与上次记录不一致"
    if problem == "PUBKEY_MISMATCH":
        return "原生模块的公钥变了（可能被换过）"
    if problem.startswith("CTIME_AHEAD"):
        return "文件是最近被重新创建过的（疑似拷回了旧数据）"
    if problem.startswith("CTIME_BEFORE_EVENT"):
        return "文件时间早于最后一条记录，系统时间可能被改过"
    if problem.startswith("TIME_ROLLBACK"):
        return "记录的时间比上次记录的时间还早（疑似回滚）"
    if problem.startswith("CLOCK_OFF"):
        return "本机时间与网络时间相差过大"
    if problem.startswith("STALE_DATA"):
        return "数据很久没有更新（疑似恢复到了旧快照）"
    return problem
