"""sntp —— 极简 NTP 客户端（RFC 5905 的子集），用于可信时间校验。

为什么自己写而不是加依赖：只需要“现在几点”和一个误差估计，
标准库的 socket/struct 足够；而且断网时必须在 1.5 秒内失败，不能拖住启动。

精度：offset 的误差约为 RTT/2（对称路径假设）。局域网/正常家宽下
通常 < 5 ms；报告里使用的是 offset 与 rtt 两个值，不用绝对精度做断言。
"""

from __future__ import annotations

import socket
import struct
import time

#: 公共 NTP 服务器（按地理与运营商分散，避免单点被污染）
DEFAULT_SERVERS = (
    "ntp.aliyun.com",
    "time.apple.com",
    "time.windows.com",
    "pool.ntp.org",
)

#: NTP 纪元（1900-01-01）到 Unix 纪元（1970-01-01）的秒数
_NTP_DELTA = 2_208_988_800


def _to_ntp_timestamp(seconds: float) -> bytes:
    whole = int(seconds) + _NTP_DELTA
    frac = int((seconds - int(seconds)) * (1 << 32))
    return struct.pack("!II", whole & 0xFFFFFFFF, frac & 0xFFFFFFFF)


def _from_ntp_timestamp(data: bytes) -> float:
    whole, frac = struct.unpack("!II", data)
    return whole - _NTP_DELTA + frac / (1 << 32)


def query(server: str, timeout: float = 0.6) -> dict:
    """向一个服务器查询，返回 {offset, rtt, server}；失败抛异常。"""
    packet = b"\x1b" + 47 * b"\0"          # LI=0, VN=3, Mode=3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        # t1/t4 用 perf_counter 计算间隔，避免查询期间系统时间被改动
        t1 = time.time()
        p1 = time.perf_counter()
        sock.sendto(packet, (server, 123))
        data, _addr = sock.recvfrom(48)
        p4 = time.perf_counter()
        t4 = t1 + (p4 - p1)

    if len(data) < 48:
        raise ValueError("short NTP reply")
    t2 = _from_ntp_timestamp(data[32:40])   # receive timestamp
    t3 = _from_ntp_timestamp(data[40:48])   # transmit timestamp

    # 标准公式：offset = ((t2 - t1) + (t3 - t4)) / 2
    offset = ((t2 - t1) + (t3 - t4)) / 2.0
    rtt = (t4 - t1) - (t3 - t2)
    return {"offset": offset, "rtt": max(rtt, 0.0), "server": server}


def sync(servers: tuple[str, ...] = DEFAULT_SERVERS, timeout: float = 0.6) -> dict:
    """查询多个服务器，返回最可信的结果。

    返回：
        {"ok": bool, "offset": float, "rtt": float, "server": str,
         "samples": int, "error": str}
    """
    results = []
    errors = []
    for server in servers:
        try:
            results.append(query(server, timeout))
        except (OSError, ValueError) as exc:
            errors.append(f"{server}:{type(exc).__name__}")
        if len(results) >= 3:
            break

    if not results:
        return {"ok": False, "offset": 0.0, "rtt": 0.0, "server": "",
                "samples": 0, "error": "offline " + ",".join(errors)}

    # 取 RTT 最小的一份：路径最短，offset 误差最小
    best = min(results, key=lambda r: r["rtt"])
    # 如果有多个样本，检查它们的 offset 是否一致（防单点污染）
    if len(results) >= 2:
        offsets = sorted(r["offset"] for r in results)
        spread = offsets[-1] - offsets[0]
    else:
        spread = 0.0

    return {
        "ok": True,
        "offset": best["offset"],
        "rtt": best["rtt"],
        "server": best["server"],
        "samples": len(results),
        "spread": spread,
        "error": "",
    }
