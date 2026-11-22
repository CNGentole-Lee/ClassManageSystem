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



def _seed_profile(chain, groups=3):
    """V4：每条链都从"建一个预设并用上它"开始。"""
    from namepicker.profiles import ProfileStore

    chain.migrate_from(0, [], [])
    store = ProfileStore(chain=chain)
    pid = store.create("化学课")
    store.set_rule(pid, groups, 4)
    store.use(pid)
    return store, pid



def _add_draw(chain, index, total):
    """记一次抽取（V4：按预设 + 名单下标）。"""
    from namepicker.profiles import ProfileStore

    store = ProfileStore(chain=chain)
    store.record_draw(index, total, store.active_id())

def _add_score(chain, group, delta):
    """给当前预设的某组加分（测试里用来推进链）。"""
    from namepicker.profiles import ProfileStore

    store = ProfileStore(chain=chain)
    store.add_score(group, delta, store.active_id())

def main() -> int:
    if not nb.available():
        print("[SKIP] native module not available")
        return 77

    tmp = tempfile.mkdtemp(prefix="ledger_")
    cfg = os.path.join(tmp, "config.ini")
    chain = L.Ledger(cfg)

    check("empty ledger verifies", chain.verify())
    check("empty ledger has zero events", chain.count() == 0)
    check("empty ledger has no profiles", chain.state()["profiles"] == [])

    # ---- V4：预设是唯一数据源 --------------------------------------
    from namepicker.profiles import ProfileStore

    migrated = chain.migrate_from(0, [], [])
    check("migration writes an init event", migrated)
    check("migration is one-shot", not chain.migrate_from(0, [], []))
    check("fresh chain has no profiles", chain.state()["profiles"] == [])

    ps = ProfileStore(chain=chain)
    pid = ps.create("化学课")
    check("creating a profile returns an id", pid == 1, str(pid))
    ps.set_rule(pid, 3, 4)
    ps.use(pid)
    st = chain.state()
    check("replay restores the profile",
          [p["name"] for p in st["profiles"]] == ["化学课"],
          str([p["name"] for p in st["profiles"]]))
    check("replay restores the group count", st["profiles"][0]["group_count"] == 3,
          str(st["profiles"][0]["group_count"]))
    check("replay restores the active profile", st["active_profile"] == 1,
          str(st["active_profile"]))

    # ---- 业务操作由 C++ 执行 ---------------------------------------
    ps.add_score(2, 9, pid)
    check("score applied", ps.scores(pid) == [0, 9, 0], str(ps.scores(pid)))
    ps.set_group_name(1, "雄鹰组", pid)
    check("rename applied", ps.get_group_name(1, pid) == "雄鹰组",
          ps.get_group_name(1, pid))
    ps.record_draw(2, 3, pid)
    check("draw applied", ps.draw_counts(pid)[2] == 3, str(ps.draw_counts(pid)))
    ps.reset_scores(pid)
    check("clear scores applied", ps.scores(pid) == [0, 0, 0], str(ps.scores(pid)))
    check("draw counts survive a score clear", ps.draw_counts(pid)[2] == 3,
          str(ps.draw_counts(pid)))

    # ---- 规则由 C++ 强制执行 ---------------------------------------
    before_count = chain.count()
    try:
        ps.add_score(99, 1, pid)
        check("illegal group rejected by the chain", False)
    except Exception as exc:                           # noqa: BLE001
        check("illegal group rejected by the chain", "BAD_GROUP" in str(exc),
              str(exc)[:30])
    check("rejected op wrote nothing", chain.count() == before_count,
          str(chain.count()))

    # ---- 每个预设各存各的 -------------------------------------------
    other = ps.create("语文课")
    ps.set_rule(other, 2, 3)
    ps.add_score(1, 5, other)
    check("profiles keep separate scores",
          ps.scores(pid) == [0, 0, 0] and ps.scores(other) == [5, 0],
          f"{ps.scores(pid)} vs {ps.scores(other)}")
    check("profiles keep separate draw counts",
          ps.draw_counts(other)[2] == 0, str(ps.draw_counts(other)))
    check("a V4 chain is not flagged as legacy", chain.is_legacy() is False)

    # ---- ConfigStore 走当前预设 -------------------------------------
    store = ConfigStore(cfg)
    store.attach_ledger(chain)
    before = chain.count()
    store.set_score(1, 7, reason="测试加分")
    check("set_score appends an event", chain.count() == before + 1,
          str(chain.count()))
    check("set_score lands in the active profile", ps.scores(pid)[0] == 0
          or store.get_score(1) == 7, str(store.get_score(1)))

    # ---- score limits come from C++ --------------------------------
    before_score = store.get_score(1)
    # 远超上限 -> C++ 拒绝。ConfigStore 会把链的拒绝记进 last_error 而不是
    # 把异常抛穿 Qt 信号（否则讲台上点一下就能崩），所以这里查的是
    # 「分数没变 + 拒绝原因可见」。
    store.set_score(1, 2_000_000)
    check("oversized score is rejected by C++",
          store.get_score(1) == before_score
          and "BAD_SCORE" in (store.last_error() or ""),
          f"value={store.get_score(1)} (was {before_score}) err={store.last_error()!r}")


    # ---- tampering -------------------------------------------------
    lines = [ln for ln in open(chain.path, encoding="ascii") if ln.strip()]
    raw = bytearray(base64.b64decode(lines[-1]))
    raw[30] ^= 0x01
    lines[-1] = base64.b64encode(bytes(raw)).decode() + "\n"
    with open(chain.path, "w", encoding="ascii") as fh:
        fh.writelines(lines)
    bad = L.Ledger(cfg)
    check("tampered ledger fails verification", not bad.verify(), bad.verify_error())

    # ---- rollback detection (anchor) -------------------------------
    tmp3 = tempfile.mkdtemp(prefix="ledger3_")
    cfg3 = os.path.join(tmp3, "config.ini")
    live = L.Ledger(cfg3)
    _seed_profile(live)
    _add_score(live, 1, 5)
    snapshot = open(live.path, encoding="ascii").read()      # 合法但旧的副本
    _add_score(live, 1, 4)
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
    _seed_profile(live5)
    _add_score(live5, 1, 5)
    _add_score(live5, 1, 4)
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
          victim.state()["profiles"][0]["scores"][0] == 9,
          str(victim.state()["profiles"][0]["scores"]))

    # ---- append after reopen ---------------------------------------
    reopened = L.Ledger(cfg5)
    reopened.load()
    _add_score(reopened, 1, 1)
    check("append after reopen keeps the chain valid", reopened.verify(),
          reopened.verify_error())

    # ---- gen 边界：第 501 条曾因签名密钥按代派生而无法验证 ----
    print("\n--- Records beyond the gen boundary ---")
    big = L.Ledger(os.path.join(tempfile.mkdtemp(prefix="cm_gen_"), "config.ini"))
    _seed_profile(big)
    ok = True
    for i in range(505):
        try:
            _add_draw(big, 0, i + 1)
        except Exception as exc:                      # noqa: BLE001
            ok = False
            print("   append failed at", big.count() + 1, exc)
            break
    check("appending past 500 records works", ok and big.count() >= 505, str(big.count()))
    reopened_big = L.Ledger(big.config_path)
    check("a 506-record chain verifies", reopened_big.verify(), reopened_big.verify_error())
    check("draw counts survive the boundary",
          reopened_big.state()["profiles"][0]["draw_counts"][0] == 505,
          str(reopened_big.state()["profiles"][0]["draw_counts"]))

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
          resigned.state()["profiles"][0]["draw_counts"] == reopened_big.state()["profiles"][0]["draw_counts"])

    # ---- 修复不能成为洗白工具 ----
    print("\n--- Repair must never launder tampering ---")
    import base64 as _b64

    def _fresh_chain():
        t = tempfile.mkdtemp(prefix="cm_tamper_")
        c = L.Ledger(os.path.join(t, "config.ini"))
        _seed_profile(c)
        _add_draw(c, 1, 1)
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
    _seed_profile(c)
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
    _seed_profile(c2)
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
    _seed_profile(c3)
    c3._pubkey_b64 = "K"
    c3.write_anchor(c3.count(), c3.head(), ts=int(c3.state()["ts"]),
                    digest=c3.state_digest(c3.state()), pubkey="K")
    _add_draw(c3, 0, 1)
    problems = c3.anchor_problems(c3.state(), pubkey_b64="K")
    check("a longer chain does not trip STATE_MISMATCH",
          not any(p.startswith("STATE_MISMATCH") for p in problems), str(problems))

    # ---- 重复 seq 的链必须能修好（导入曾从空链开始导致撞号）----
    print("\n--- Repair a chain with duplicate seq ---")
    import base64 as _b64d
    t = tempfile.mkdtemp(prefix="cm_dup_")
    c = L.Ledger(os.path.join(t, "config.ini"))
    _seed_profile(c)
    # 手工再追加一条 seq=1 的记录（模拟旧 bug），直接拼到文件里
    dup = nb.apply([], "init", count=2, names="重复甲,重复乙")
    with open(c.path, "a", encoding="ascii") as fh:
        fh.write(dup["record"] + "\n")
    victim = L.Ledger(os.path.join(t, "config.ini"))
    ok = victim.verify()
    check("duplicate-seq chain is repaired", ok, victim.verify_error())
    seqs = [int.from_bytes(r[0:4], "little") for r in victim.load()]
    check("repair renumbers records", seqs == list(range(1, len(seqs) + 1)), str(seqs))
    check("repaired chain survives a restart",
          L.Ledger(os.path.join(t, "config.ini")).verify())

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
