"""导出 / 导入：把当前分数与组名存成一个人类可读的 JSON 快照。

设计取舍
    导出的是**明文快照**（组名 + 分数 + 抽取次数），不是链的密文：
    * 密文只有原机器能解开，换机等于废纸；
    * 老师需要"看得到、改得动"，出问题时能手工核对。

    导入是**用户确认信任**的操作：数据来自别的密钥体系，无法用签名证明，
    只能靠人。所以导入必须由用户显式点“我信任这份数据”，
    程序不会自己悄悄替换。

    Inno 更新不经过这里：安装包只替换 _internal / native，
    Data/ 原地保留，密钥不变，链照常验过。
"""

from __future__ import annotations

import json
import os
import time

EXPORT_VERSION = 1


def export_payload(store, chain=None, draws: dict | None = None,
                   profiles: list | None = None,
                   active_profile: int = 0) -> dict:
    """组装要导出的快照。"""
    count = int(store.group_count)
    names = [store.get_group_name(i) for i in range(1, count + 1)]
    scores = [int(x) for x in store.all_scores()][:count]
    payload = {
        "format": "classmanage-snapshot",
        "version": EXPORT_VERSION,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "group_count": count,
        "names": names,
        "scores": scores,
    }
    if draws:
        payload["draws"] = {str(k): int(v) for k, v in draws.items()}
    if profiles:
        # 预设（分组制）跟着一起走：换电脑后分组不用重录
        payload["profiles"] = [
            {
                "id": int(p.get("id", 0)),
                "name": str(p.get("name", "")),
                "group_count": int(p.get("group_count", 0)),
                "members": [int(g) for g in p.get("members", [])],
            }
            for p in profiles
        ]
        payload["active_profile"] = int(active_profile or 0)
    return payload


def save(payload: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load(path: str) -> dict:
    """读取并校验快照；格式不对抛 ValueError。"""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or data.get("format") != "classmanage-snapshot":
        raise ValueError("not a snapshot file")
    count = int(data.get("group_count", 0))
    names = data.get("names") or []
    scores = data.get("scores") or []
    if not (1 <= count <= 24):
        raise ValueError(f"bad group_count: {count}")
    if len(scores) < count:
        raise ValueError("scores shorter than group_count")
    profiles = []
    for index, raw in enumerate(data.get("profiles") or []):
        if not isinstance(raw, dict):
            continue
        try:
            pid = int(raw.get("id", index + 1))
            groups = int(raw.get("group_count", 0))
            members = [int(g) for g in (raw.get("members") or [])]
        except (TypeError, ValueError):
            continue
        if pid <= 0 or not (1 <= groups <= 24):
            continue
        profiles.append({
            "id": pid,
            "name": str(raw.get("name", "")),
            "group_count": groups,
            # 组号超出组数的一律归 0：宁可少分，也不要带入不一致的组号
            "members": [g if 1 <= g <= groups else 0 for g in members],
        })
    return {
        "count": count,
        "names": [str(x) for x in names[:count]],
        "scores": [int(x) for x in scores[:count]],
        "draws": {str(k): int(v) for k, v in (data.get("draws") or {}).items()},
        "profiles": profiles,
        "active_profile": int(data.get("active_profile", 0) or 0),
        "exported_at": str(data.get("exported_at", "")),
    }


def default_name(directory: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(directory, f"classmanage-backup-{stamp}.json")
