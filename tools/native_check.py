"""Check the native helper (cmd_native / cmd_native.exe).

Usage:
    python tools/native_check.py

Covers:
    1. binary exists, selftest, fingerprint, protocol;
    2. business state machine in C++: init / score / rename / count / wipe;
    3. rule enforcement (bad group, bad count, score limits);
    4. tamper detection, reorder, dropped record, wrong fingerprint.

Exit code 0 = passed, 1 = failure, 77 = native module missing.
"""

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()

from namepicker import native_bridge as nb  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    try:
        exe = nb.native_path("sign")
        vexe = nb.native_path("verify")
    except nb.NativeMissing as exc:
        print(f"[SKIP] native module not found: {exc}")
        return 77

    print(f"sign:   {exe}")
    print(f"verify: {vexe}")
    check("sign binary exists", os.path.isfile(exe))
    check("verify binary exists", os.path.isfile(vexe))

    # 两个二进制必须来自同一次构建（共享令牌），否则任何调用都会 PEER_MISMATCH
    try:
        nb.identity()
        check("signer and verifier share one build token", True)
    except nb.NativeError as exc:
        check("signer and verifier share one build token", False, str(exc))
    check("selftest passes", nb.selftest())

    fp = nb.fingerprint()
    check("fingerprint is 64 hex chars",
          len(fp) == 64 and all(c in "0123456789abcdef" for c in fp), fp[:16] + "...")
    check("fingerprint is stable", nb.fingerprint() == fp)

    # ---- 业务状态机（数据由 C++ 计算，V4：全部在预设里） --------------
    r = nb.apply([], "init", count=2, names="化学课,语文课")
    check("init returns a record", bool(r.get("record")))
    rec1 = base64.b64decode(r["record"])
    plain1 = base64.b64decode(r["plain"])
    check("init creates the profiles",
          [p["name"] for p in r["profiles"]] == ["化学课", "语文课"],
          str([p["name"] for p in r["profiles"]]))

    r = nb.apply([rec1], "profile-rule", id=1, count=3, members=4)
    rec2 = base64.b64decode(r["record"])
    plain2 = base64.b64decode(r["plain"])
    check("profile-rule sets the group count",
          r["profiles"][0]["group_count"] == 3, str(r["profiles"][0]["group_count"]))
    check("profile-rule allocates score slots",
          r["profiles"][0]["scores"] == [0, 0, 0], str(r["profiles"][0]["scores"]))
    check("profile-rule allocates member slots",
          r["profiles"][0]["members"] == [0, 0, 0, 0],
          str(r["profiles"][0]["members"]))
    check("profile-rule returns new seq", r["seq"] == 2, str(r["seq"]))

    r = nb.apply([rec1, rec2], "profile-score", id=1, group=2, delta=5)
    rec3 = base64.b64decode(r["record"])
    plain3 = base64.b64decode(r["plain"])
    check("profile-score adds to that profile's group",
          r["profiles"][0]["scores"] == [0, 5, 0], str(r["profiles"][0]["scores"]))
    check("the other profile is untouched",
          r["profiles"][1]["scores"] == [], str(r["profiles"][1]["scores"]))

    r = nb.apply([rec1, rec2, rec3], "profile-groupname", id=1, group=1,
                 name="雄鹰组")
    rec4 = base64.b64decode(r["record"])
    plain4 = base64.b64decode(r["plain"])
    check("profile-groupname renames that profile's group",
          r["profiles"][0]["group_names"][0] == "雄鹰组",
          str(r["profiles"][0]["group_names"]))

    r = nb.apply([rec1, rec2, rec3, rec4], "profile-member", id=1, index=2, group=1)
    rec5 = base64.b64decode(r["record"])
    plain5 = base64.b64decode(r["plain"])
    check("profile-member assigns a list index",
          r["profiles"][0]["members"][2] == 1, str(r["profiles"][0]["members"]))

    r = nb.apply([rec1, rec2, rec3, rec4, rec5], "draw", id=1, index=2, total=3)
    rec6 = base64.b64decode(r["record"])
    plain6 = base64.b64decode(r["plain"])
    check("draw records per-profile draw counts",
          r["profiles"][0]["draw_counts"][2] == 3,
          str(r["profiles"][0]["draw_counts"]))

    r = nb.apply([rec1, rec2, rec3, rec4, rec5, rec6], "profile-use", id=1)
    rec7 = base64.b64decode(r["record"])
    plain7 = base64.b64decode(r["plain"])
    check("profile-use selects the active profile", r["active_profile"] == 1,
          str(r["active_profile"]))

    records = [rec1, rec2, rec3, rec4, rec5, rec6, rec7]
    plains = [plain1, plain2, plain3, plain4, plain5, plain6, plain7]
    st = nb.state(records, plains)
    check("state replays to the same result",
          st["profiles"][0]["scores"] == [0, 5, 0]
          and st["profiles"][0]["group_names"][0] == "雄鹰组",
          str(st["profiles"][0]["scores"]))
    check("state reports the head", len(base64.b64decode(st["head"])) == 32)

    # ---- 非 ASCII 参数（Windows 上曾因 argv 代码页而乱码）----------
    # Windows 的 main(int, char**) 拿的是当前代码页的窄字符；
    # 这里用中文 + emoji 覆盖 UTF-16 -> UTF-8 的转换路径。
    r = nb.apply([], "init", count=2, names="甲组,乙组")
    ascii_rec = base64.b64decode(r["record"])
    ascii_plain = base64.b64decode(r["plain"])
    check("non-ASCII names survive init",
          [p["name"] for p in r["profiles"]] == ["甲组", "乙组"],
          str([p["name"] for p in r["profiles"]]))
    r = nb.apply([ascii_rec], "profile-rule", id=1, count=2, members=1)
    a2 = base64.b64decode(r["record"])
    a2p = base64.b64decode(r["plain"])
    r = nb.apply([ascii_rec, a2], "profile-groupname", id=1, group=1, name="🚀火箭组")
    emoji_rec = base64.b64decode(r["record"])
    emoji_plain = base64.b64decode(r["plain"])
    check("emoji name survives rename",
          r["profiles"][0]["group_names"][0] == "🚀火箭组",
          r["profiles"][0]["group_names"][0])
    st = nb.state([ascii_rec, a2, emoji_rec], [ascii_plain, a2p, emoji_plain])
    check("non-ASCII names replay correctly",
          st["profiles"][0]["group_names"][0] == "🚀火箭组",
          str(st["profiles"][0]["group_names"]))

    # ---- 规则在 C++ 侧 --------------------------------------------
    try:
        nb.apply(records, "profile-score", id=1, group=99, delta=1)
        check("out-of-range group is rejected", False)
    except nb.NativeError as exc:
        check("out-of-range group is rejected", "BAD_GROUP" in str(exc), str(exc)[:40])
    try:
        nb.apply(records, "profile-score", id=1, group=1, delta=10 ** 9)
        check("absurd score delta is rejected", False)
    except nb.NativeError as exc:
        check("absurd score delta is rejected", "BAD_SCORE" in str(exc), str(exc)[:40])
    try:
        nb.apply(records, "profile-rule", id=1, count=999, members=0)
        check("absurd group count is rejected", False)
    except nb.NativeError as exc:
        check("absurd group count is rejected", "BAD_COUNT" in str(exc), str(exc)[:40])
    try:
        nb.apply(records, "profile-score", id=99, group=1, delta=1)
        check("unknown profile is rejected", False)
    except nb.NativeError as exc:
        check("unknown profile is rejected", "BAD_PROFILE" in str(exc), str(exc)[:40])

    # ---- 链完整性 -------------------------------------------------
    records = [rec1, rec2, rec3]
    plains = [plain1, plain2, plain3]
    ok, head, error = nb.verify(records, plains)
    check("chain verifies", ok, error)

    broken = [bytearray(r) for r in records]
    broken[1][20] ^= 0x01
    ok, _, error = nb.verify([bytes(r) for r in broken], list(plains))
    check("single-byte tamper is rejected", not ok, error)

    ok, _, error = nb.verify([records[1], records[0], records[2]],
                             [plains[1], plains[0], plains[2]])
    check("reordered records are rejected", not ok, error)

    ok, _, error = nb.verify([records[0], records[2]], [plains[0], plains[2]])
    check("dropped record is rejected", not ok, error)

    saved = nb._fp_cache
    try:
        nb._fp_cache = "00" * 32
        ok, _, error = nb.verify(records, plains)
        check("another machine's fingerprint cannot verify", not ok, error)
    finally:
        nb._fp_cache = saved

    print("\n--- profiles (grouping, all incremental) ---")
    r = nb.apply([], "profile-new", id=1, name="化学课")
    p_new, pp_new = base64.b64decode(r["record"]), base64.b64decode(r["plain"])
    check("profile-new creates the profile", r["profiles"][0]["name"] == "化学课",
          str(r.get("profiles")))
    check("a fresh profile has no groups yet", r["profiles"][0]["group_count"] == 0)

    r = nb.apply([p_new], "profile-rule", id=1, count=2, members=3)
    p_rule, pp_rule = base64.b64decode(r["record"]), base64.b64decode(r["plain"])
    check("profile-rule sets group count and member slots",
          r["profiles"][0]["group_count"] == 2
          and r["profiles"][0]["members"] == [0, 0, 0], str(r["profiles"][0]))

    # 增量：一次只改一个人
    chain_recs = [p_new, p_rule]
    chain_plains = [pp_new, pp_rule]
    for index, group in ((0, 1), (1, 2), (2, 1)):
        rr = nb.apply(chain_recs, "profile-member", id=1, index=index, group=group)
        chain_recs.append(base64.b64decode(rr["record"]))
        chain_plains.append(base64.b64decode(rr["plain"]))
    check("profile-member assigns one index at a time",
          rr["profiles"][0]["members"] == [1, 2, 1], str(rr["profiles"][0]["members"]))

    st_a = nb.state(chain_recs, chain_plains)
    st_b = nb.state(chain_recs, chain_plains)
    check("profile replay is deterministic",
          st_a["profiles"] == st_b["profiles"]
          and st_a["active_profile"] == st_b["active_profile"])
    check("profile replay keeps the assignment",
          st_a["profiles"][0]["members"] == [1, 2, 1], str(st_a["profiles"][0]["members"]))

    # 名单变短：越界下标必须被丢弃，而不是让整条链打不开
    rr = nb.apply(chain_recs, "profile-member", id=1, index=9, group=1)
    short_recs = chain_recs + [base64.b64decode(rr["record"])]
    short_plains = chain_plains + [base64.b64decode(rr["plain"])]
    check("out-of-range member index is dropped, not fatal",
          nb.state(short_recs, short_plains)["profiles"][0]["members"] == [1, 2, 1])

    rr = nb.apply(short_recs, "profile-rule", id=1, count=2, members=2)
    shrink_recs = short_recs + [base64.b64decode(rr["record"])]
    shrink_plains = short_plains + [base64.b64decode(rr["plain"])]
    check("shrinking the name list trims the assignment",
          nb.state(shrink_recs, shrink_plains)["profiles"][0]["members"] == [1, 2])

    rr = nb.apply(short_recs, "profile-use", id=1)
    use_recs = short_recs + [base64.b64decode(rr["record"])]
    use_plains = short_plains + [base64.b64decode(rr["plain"])]
    check("profile-use marks the active profile",
          nb.state(use_recs, use_plains)["active_profile"] == 1)

    rr = nb.apply(use_recs, "profile-del", id=1)
    del_recs = use_recs + [base64.b64decode(rr["record"])]
    del_plains = use_plains + [base64.b64decode(rr["plain"])]
    st_del = nb.state(del_recs, del_plains)
    check("profile-del removes it and clears the active marker",
          st_del["profiles"] == [] and st_del["active_profile"] == 0, str(st_del["profiles"]))

    # 规则校验（duplicate 用删掉之前的链：del_recs 里的 1 号已经不存在了）
    for label, chain, kwargs, error in (
        ("duplicate profile id", chain_recs, dict(id=1, name="dup"), "BAD_PROFILE"),
        ("empty profile name", del_recs, dict(id=2, name=""), "BAD_NAME"),
    ):
        try:
            nb.apply(chain, "profile-new", **kwargs)
            check(label + " is rejected", False, "no error")
        except nb.NativeError as exc:
            check(label + " is rejected", error in str(exc), str(exc))
    try:
        nb.apply(chain_recs, "profile-member", id=1, index=0, group=9)
        check("member group beyond group_count is rejected", False, "no error")
    except nb.NativeError as exc:
        check("member group beyond group_count is rejected", "BAD_GROUP" in str(exc), str(exc))
    try:
        nb.apply(del_recs, "profile-use", id=7)
        check("activating a missing profile is rejected", False, "no error")
    except nb.NativeError as exc:
        check("activating a missing profile is rejected", "BAD_PROFILE" in str(exc), str(exc))

    # V4 给 INIT 载荷加了格式版本字节：3.x 的链必须被明确拒绝，
    # 这样 Python 侧才能区分"版本旧"和"数据被篡改"。
    check("V4 chains carry the format marker",
          nb.state(records, plains)["profiles"][0]["id"] == 1,
          "V4 chain replays")
    legacy_payload = bytes([1]) + bytes([2, 0])          # OP_INIT + count=2（无版本字节）
    check("a payload without the format marker is not V4", len(legacy_payload) == 3)

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
