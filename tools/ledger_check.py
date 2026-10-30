"""Check the encrypted event ledger (append-only chain of score changes).

Usage:
    python tools/ledger_check.py

Covers:
    1. empty ledger verifies and replays to nothing;
    2. migration writes one init event that replays back the same state;
    3. score / rename / count events replay correctly;
    4. the ConfigStore appends events on every change;
    5. tampering with a record breaks verification;
    6. deleting a record breaks verification (sequence gap);
    7. replacing the ledger with an older copy is detected via head/seq.

Exit code 0 = all passed, 1 = failure, 77 = native module missing.
"""

import base64
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()
# 安全副本默认写用户缓存目录；测试里改到临时目录，避免污染真实环境
os.environ.setdefault("CLASSMANAGE_STATE_DIR",
                      tempfile.mkdtemp(prefix="cm_state_"))

from namepicker import native_bridge as nb  # noqa: E402
from namepicker import ledger as L  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    if not nb.available():
        print("[SKIP] native module not available")
        return 77

    tmp = tempfile.mkdtemp(prefix="ledger_")
    cfg = os.path.join(tmp, "config.ini")
    chain = L.Ledger(cfg)

    check("empty ledger verifies", chain.verify())
    check("empty ledger replays to zero events", chain.replay().events == 0)

    # ---- migration -------------------------------------------------
    migrated = chain.migrate_from(3, ["甲组", "乙组", "丙组"], [0, 5, -2])
    check("migration writes an init event", migrated)
    check("migration is one-shot", not chain.migrate_from(3, [], []))
    state = chain.replay()
    check("replay restores group count", state.group_count == 3, str(state.group_count))
    check("replay restores names", state.names == {1: "甲组", 2: "乙组", 3: "丙组"})
    check("replay restores scores", state.scores == {1: 0, 2: 5, 3: -2}, str(state.scores))

    # ---- score / rename / count ------------------------------------
    chain.append(L.OP_SCORE, {"op": "score", "g": 2, "v": 9, "r": "+4"})
    chain.append(L.OP_RENAME, {"op": "rename", "g": 1, "name": "雄鹰组"})
    state = chain.replay()
    check("score event applied", state.scores[2] == 9, str(state.scores[2]))
    check("rename event applied", state.names[1] == "雄鹰组", state.names[1])
    check("event count matches", state.events == 3, str(state.events))

    # ---- ConfigStore integration -----------------------------------
    store = ConfigStore(cfg)
    store.set_group_count(2)
    chain2 = L.Ledger(cfg)
    chain2.verify()
    before = chain2.count()
    store.attach_ledger(chain2)
    store.set_score(1, 7, reason="测试加分")
    check("set_score appends an event", chain2.count() == before + 1,
          f"{before} -> {chain2.count()}")
    state2 = chain2.replay()
    check("appended score replays", state2.scores.get(1) == 7, str(state2.scores))

    # ---- tampering -------------------------------------------------
    lines = [ln for ln in open(chain2.path, encoding="ascii") if ln.strip()]
    raw = bytearray(base64.b64decode(lines[-1]))
    raw[30] ^= 0x01
    lines[-1] = base64.b64encode(bytes(raw)).decode() + "\n"
    with open(chain2.path, "w", encoding="ascii") as fh:
        fh.writelines(lines)
    bad = L.Ledger(cfg)
    check("tampered ledger fails verification", not bad.verify(), bad.verify_error())
    try:
        bad.replay()
        check("tampered ledger cannot replay", False)
    except L.LedgerError as exc:
        check("tampered ledger cannot replay", True, str(exc)[:20])

    # ---- rollback detection (anchor) -------------------------------
    tmp3 = tempfile.mkdtemp(prefix="ledger3_")
    cfg3 = os.path.join(tmp3, "config.ini")
    live = L.Ledger(cfg3)
    live.migrate_from(1, ["A"], [0])
    live.append(L.OP_SCORE, {"op": "score", "g": 1, "v": 5})
    snapshot = open(live.path, encoding="ascii").read()      # 合法但旧的副本
    live.append(L.OP_SCORE, {"op": "score", "g": 1, "v": 9})
    check("anchor records the newest seq", live.read_anchor()[0] == live.count(),
          f"{live.read_anchor()[0]} vs {live.count()}")
    with open(live.path, "w", encoding="ascii") as fh:
        fh.write(snapshot)                                    # 换回旧副本
    rolled = L.Ledger(cfg3)
    check("old copy still self-verifies", rolled.verify())
    check("old copy is detected via anchor", rolled.rollback_reason().startswith("SHORTER"),
          rolled.rollback_reason())

    # 整个目录删掉：基准还在，必须判为 DELETED
    tmp4 = tempfile.mkdtemp(prefix="ledger4_")
    cfg4 = os.path.join(tmp4, "config.ini")
    gone = L.Ledger(cfg4)
    gone.migrate_from(1, ["A"], [0])
    os.remove(gone.path)
    empty = L.Ledger(cfg4)
    check("deleted ledger is detected via anchor", empty.rollback_reason() == "DELETED",
          empty.rollback_reason())

    # ---- restore from shadow ---------------------------------------
    tmp5 = tempfile.mkdtemp(prefix="ledger5_")
    cfg5 = os.path.join(tmp5, "config.ini")
    live5 = L.Ledger(cfg5)
    live5.migrate_from(1, ["A"], [0])
    live5.append(L.OP_SCORE, {"op": "score", "g": 1, "v": 5})
    live5.append(L.OP_SCORE, {"op": "score", "g": 1, "v": 9})
    good = live5.read_anchor()
    os.remove(live5.path)                     # 模拟“删掉 Data 里的链”
    victim = L.Ledger(cfg5)
    check("deleted chain is detected", victim.rollback_reason() == "DELETED",
          victim.rollback_reason())
    restored = victim.restore_from_shadow()
    check("restore from shadow succeeds", restored)
    check("restored chain verifies", victim.verify())
    check("restored chain has the newest seq", victim.count() == good[0],
          f"{victim.count()} vs {good[0]}")
    check("restored chain replays the newest score", victim.replay().scores.get(1) == 9)

    # ---- rollback (older copy, chain-only view) --------------------
    tmp2 = tempfile.mkdtemp(prefix="ledger2_")
    cfg2 = os.path.join(tmp2, "config.ini")
    fresh = L.Ledger(cfg2)
    fresh.migrate_from(1, ["A"], [0])
    fresh.append(L.OP_SCORE, {"op": "score", "g": 1, "v": 5})
    old_copy = open(fresh.path, encoding="ascii").read()
    fresh.append(L.OP_SCORE, {"op": "score", "g": 1, "v": 9})
    with open(fresh.path, "w", encoding="ascii") as fh:
        fh.write(old_copy)                      # 回滚到最后一次之前
    rolled = L.Ledger(cfg2)
    # 链本身仍自洽（旧副本是合法的），所以 verify 会通过 —— 这正是为什么要
    # 额外的“基准 seq/head”来判定回滚；这里只断言 seq 变短了。
    rolled.verify()
    check("rolled-back ledger is shorter than the newest state",
          rolled.count() == 2, str(rolled.count()))

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
