"""Check the encrypted event ledger (business logic lives in C++).

Usage:
    python tools/ledger_check.py

Covers:
    1. empty ledger verifies;
    2. migration writes one init event that replays back the same state;
    3. score / rename / wipe are applied by C++ and replayed;
    4. ConfigStore drives the chain through C++;
    5. tampering breaks verification;
    6. a rolled-back copy is detected via the anchor;
    7. deleting the ledger is detected and recovered from the shadow copy.

Exit code 0 = all passed, 1 = failure, 77 = native module missing.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()
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
    check("empty ledger has zero events", chain.count() == 0)
    check("empty ledger state is empty", chain.state()["count"] == 0)

    # ---- migration -------------------------------------------------
    migrated = chain.migrate_from(3, ["甲组", "乙组", "丙组"], [0, 5, -2])
    check("migration writes an init event", migrated)
    check("migration is one-shot", not chain.migrate_from(3, [], []))
    st = chain.state()
    check("replay restores group count", st["count"] == 3, str(st["count"]))
    check("replay restores names", st["names"] == ["甲组", "乙组", "丙组"], str(st["names"]))
    check("replay restores scores", st["scores"] == [0, 5, -2], str(st["scores"]))

    # ---- business ops driven by C++ --------------------------------
    st = chain.apply("score", group=2, delta=4)
    check("score event applied", st["scores"] == [0, 9, -2], str(st["scores"]))
    st = chain.apply("rename", group=1, name="雄鹰组")
    check("rename event applied", st["names"][0] == "雄鹰组", st["names"][0])
    st = chain.apply("wipe", parts="scores")
    check("wipe scores applied", st["scores"] == [0, 0, 0], str(st["scores"]))
    check("event count matches", chain.count() == 4, str(chain.count()))

    # ---- rule enforcement comes from C++ ---------------------------
    try:
        chain.apply("score", group=99, delta=1)
        check("illegal group rejected by the chain", False)
    except L.LedgerError as exc:
        check("illegal group rejected by the chain", "BAD_GROUP" in str(exc), str(exc)[:30])
    check("rejected op wrote nothing", chain.count() == 4, str(chain.count()))

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
    check("appended score replays", chain2.state()["scores"][0] == 7,
          str(chain2.state()["scores"]))
    store.set_group_name(2, "闪电组")
    check("set_group_name replays", chain2.state()["names"][1] == "闪电组",
          str(chain2.state()["names"]))
    store.set_score(1, 7)                     # 值没变：不应新增事件
    check("no-op score does not append", chain2.count() == before + 2,
          str(chain2.count()))

    # ---- score limits come from C++ --------------------------------
    before_score = store.get_score(1)
    store.set_score(1, 2_000_000)             # 远超上限 -> C++ 拒绝
    check("oversized score is rejected by C++", store.get_score(1) == before_score,
          f"{store.get_score(1)} vs {before_score}")

    # ---- tampering -------------------------------------------------
    lines = [ln for ln in open(chain2.path, encoding="ascii") if ln.strip()]
    raw = bytearray(base64.b64decode(lines[-1]))
    raw[30] ^= 0x01
    lines[-1] = base64.b64encode(bytes(raw)).decode() + "\n"
    with open(chain2.path, "w", encoding="ascii") as fh:
        fh.writelines(lines)
    bad = L.Ledger(cfg)
    check("tampered ledger fails verification", not bad.verify(), bad.verify_error())

    # ---- rollback detection (anchor) -------------------------------
    tmp3 = tempfile.mkdtemp(prefix="ledger3_")
    cfg3 = os.path.join(tmp3, "config.ini")
    live = L.Ledger(cfg3)
    live.migrate_from(1, ["A"], [0])
    live.apply("score", group=1, delta=5)
    snapshot = open(live.path, encoding="ascii").read()      # 合法但旧的副本
    live.apply("score", group=1, delta=4)
    check("anchor records the newest seq", live.read_anchor()[0] == live.count(),
          f"{live.read_anchor()[0]} vs {live.count()}")
    with open(live.path, "w", encoding="ascii") as fh:
        fh.write(snapshot)
    rolled = L.Ledger(cfg3)
    check("old copy still self-verifies", rolled.verify())
    check("old copy is detected via anchor", rolled.rollback_reason().startswith("SHORTER"),
          rolled.rollback_reason())

    # ---- restore from shadow ---------------------------------------
    tmp5 = tempfile.mkdtemp(prefix="ledger5_")
    cfg5 = os.path.join(tmp5, "config.ini")
    live5 = L.Ledger(cfg5)
    live5.migrate_from(1, ["A"], [0])
    live5.apply("score", group=1, delta=5)
    live5.apply("score", group=1, delta=4)
    good = live5.read_anchor()
    os.remove(live5.path)                     # 模拟“删掉 Data 里的链”
    victim = L.Ledger(cfg5)
    check("deleted chain is detected", victim.rollback_reason() == "DELETED",
          victim.rollback_reason())
    check("restore from shadow succeeds", victim.restore_from_shadow())
    check("restored chain verifies", victim.verify())
    check("restored chain has the newest seq", victim.count() == good[0],
          f"{victim.count()} vs {good[0]}")
    check("restored chain replays the newest score",
          victim.state()["scores"][0] == 9, str(victim.state()["scores"]))

    # ---- append after reopen ---------------------------------------
    reopened = L.Ledger(cfg5)
    reopened.load()
    reopened.apply("score", group=1, delta=1)
    check("append after reopen keeps the chain valid", reopened.verify(),
          reopened.verify_error())

    # ---- gen 边界：第 501 条曾因签名密钥按代派生而无法验证 ----
    print("\n--- Records beyond the gen boundary ---")
    big = L.Ledger(os.path.join(tempfile.mkdtemp(prefix="cm_gen_"), "config.ini"))
    big.migrate_from(3, ["A", "B", "C"], [0, 0, 0])
    ok = True
    for i in range(505):
        try:
            big.apply("draw", name="A", total=i + 1)
        except Exception as exc:                      # noqa: BLE001
            ok = False
            print("   append failed at", big.count() + 1, exc)
            break
    check("appending past 500 records works", ok and big.count() == 506, str(big.count()))
    reopened_big = L.Ledger(big.config_path)
    check("a 506-record chain verifies", reopened_big.verify(), reopened_big.verify_error())
    check("draw counts survive the boundary",
          reopened_big.state().get("draws", {}).get("A") == 505,
          str(reopened_big.state().get("draws")))

    # ---- 重签：内容不变，链仍可验证 ----
    print("\n--- Re-signing an existing chain ---")
    import base64 as _b64
    data = nb.repair(big.load())
    new_records = [_b64.b64decode(x) for x in data["records"]]
    check("repair keeps the record count", len(new_records) == big.count(), str(len(new_records)))
    with open(big.path, "w", encoding="ascii") as fh:
        for rec in new_records:
            fh.write(_b64.b64encode(rec).decode("ascii") + "\n")
    resigned = L.Ledger(big.config_path)
    check("re-signed chain verifies", resigned.verify(), resigned.verify_error())
    check("re-signing keeps the draw counts",
          resigned.state().get("draws") == reopened_big.state().get("draws"))

    # ---- 修复不能成为洗白工具 ----
    print("\n--- Repair must never launder tampering ---")
    import base64 as _b64

    def _fresh_chain():
        t = tempfile.mkdtemp(prefix="cm_tamper_")
        c = L.Ledger(os.path.join(t, "config.ini"))
        c.migrate_from(3, ["A", "B", "C"], [0, 0, 0])
        c.apply("draw", name="B", total=1)
        return t, c

    # 1) 改签名
    t, c = _fresh_chain()
    lines = open(c.path, encoding="ascii").read().splitlines()
    raw = bytearray(_b64.b64decode(lines[-1]))
    raw[-1] ^= 0xFF
    open(c.path, "w", encoding="ascii").write(
        "\n".join(lines[:-1] + [_b64.b64encode(bytes(raw)).decode()]) + "\n")
    victim = L.Ledger(os.path.join(t, "config.ini"))
    check("flipped signature is rejected and not repaired",
          not victim.verify() and not victim._resigned, victim.verify_error())

    # 2) 改密文
    t, c = _fresh_chain()
    lines = open(c.path, encoding="ascii").read().splitlines()
    raw = bytearray(_b64.b64decode(lines[-1]))
    raw[len(raw) // 2] ^= 0x01
    open(c.path, "w", encoding="ascii").write(
        "\n".join(lines[:-1] + [_b64.b64encode(bytes(raw)).decode()]) + "\n")
    victim = L.Ledger(os.path.join(t, "config.ini"))
    check("flipped ciphertext is rejected and not repaired",
          not victim.verify() and not victim._resigned, victim.verify_error())

    # 3) 正常链仍能重签（修复能力不能被误伤）
    t, c = _fresh_chain()
    data = nb.repair(c.load())
    check("a genuine chain can still be re-signed", data["count"] == c.count())

    # ---- 锚点：公钥只写一次、digest 按 seq gate、旧格式兼容 ----
    print("\n--- Anchor: public key pinning ---")
    t = tempfile.mkdtemp(prefix="cm_anchor_")
    c = L.Ledger(os.path.join(t, "config.ini"))
    c.migrate_from(3, ["A", "B", "C"], [0, 0, 0])
    c.write_anchor(c.count(), c.head(), ts=int(c.state()["ts"]),
                   digest=c.state_digest(c.state()), pubkey="PUBKEY_ONE")
    c.write_anchor(c.count(), c.head(), ts=int(c.state()["ts"]),
                   digest=c.state_digest(c.state()), pubkey="PUBKEY_TWO")
    anchor = c.read_anchor_full()
    check("public key is pinned to the first value",
          anchor["pubkey"] == "PUBKEY_ONE", anchor["pubkey"])
    check("a different key is reported",
          "PUBKEY_MISMATCH" in c.anchor_problems(c.state(), pubkey_b64="PUBKEY_THREE"))

    import json as _json
    import base64 as _b64mod
    t2 = tempfile.mkdtemp(prefix="cm_anchor_old_")
    c2 = L.Ledger(os.path.join(t2, "config.ini"))
    c2.migrate_from(3, ["A", "B", "C"], [0, 0, 0])
    legacy = _json.dumps({"seq": c2.count(),
                          "head": _b64mod.b64encode(c2.head()).decode()})
    for path in c2.anchor_paths():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(legacy)
    problems = c2.anchor_problems(c2.state(), pubkey_b64="ANY_KEY")
    check("legacy anchor without a pubkey does not report a mismatch",
          "PUBKEY_MISMATCH" not in problems, str(problems))

    t3 = tempfile.mkdtemp(prefix="cm_anchor_grow_")
    c3 = L.Ledger(os.path.join(t3, "config.ini"))
    c3.migrate_from(3, ["A", "B", "C"], [0, 0, 0])
    c3._pubkey_b64 = "K"
    c3.write_anchor(c3.count(), c3.head(), ts=int(c3.state()["ts"]),
                    digest=c3.state_digest(c3.state()), pubkey="K")
    c3.apply("draw", name="A", total=1)
    problems = c3.anchor_problems(c3.state(), pubkey_b64="K")
    check("a longer chain does not trip STATE_MISMATCH",
          not any(p.startswith("STATE_MISMATCH") for p in problems), str(problems))

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
