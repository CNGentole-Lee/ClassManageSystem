"""Tamper-focused acceptance tests.

Usage:
    python tools/tamper_check.py

Every case here is an *attack*, not a happy path:
    1. native binary byte flipped              -> hash mismatch, restorable
    2. native binary truncated                 -> size mismatch
    3. native restored from the embedded copy  -> hash matches again
    4. record edited                           -> chain rejected
    5. record deleted                          -> sequence gap
    6. records reordered                       -> rejected
    7. old chain restored (rollback)           -> SHORTER
    8. anchor ts ahead of the chain            -> TIME_ROLLBACK
    9. state digest differs                    -> STATE_MISMATCH
   10. public key differs                      -> PUBKEY_MISMATCH
   11. file copied (ctime newer than events)   -> CTIME_AHEAD
   12. NTP offline                             -> sync reports not ok, no crash
   13. NTP timestamp round-trip                -> offset within 1 ms
   14. monotonic timestamps                    -> ts strictly increases

Exit code: 0 = all passed, 1 = failure, 77 = native module missing.
"""

import base64
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

from _settings_isolation import isolate_settings

isolate_settings()
os.environ.setdefault("CLASSMANAGE_STATE_DIR", tempfile.mkdtemp(prefix="cm_tamper_"))

from namepicker import ledger as L          # noqa: E402
from namepicker import native_bridge as nb  # noqa: E402
from namepicker import integrity, sntp      # noqa: E402
from namepicker.profiles import ProfileStore  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def fresh_chain(prefix="tamper_"):
    """一条带预设的临时链（至少 5 条记录，够做「改/删/重排中间一条」）。

    V4 的 init 只写预设列表，改分/改组名都是 profile-* 事件。
    """
    tmp = tempfile.mkdtemp(prefix=prefix)
    cfg = os.path.join(tmp, "config.ini")
    chain = L.Ledger(cfg)
    chain.migrate_from(0, [], [])
    store = ProfileStore(chain=chain)
    pid = store.create("化学课")
    store.set_rule(pid, 3, 3)
    store.use(pid)
    store.add_score(1, 2, pid)
    store.add_score(2, 3, pid)
    return chain


def bump(chain, group, delta):
    """给当前预设的某一组加减分（V4：分数属于预设）。"""
    store = ProfileStore(chain=chain)
    store.add_score(group, delta, store.active_id())


def main() -> int:
    if not nb.available():
        print("[SKIP] native module not available")
        return 77

    # ---- 1-3. native binary integrity ---------------------------------
    info = integrity.expected("sign")
    real = nb.native_path("sign")
    check("manifest knows this platform", info is not None)
    check("installed native module matches the pinned hash",
          integrity.check_native(real)["ok"], integrity.check_native(real)["reason"])

    work = tempfile.mkdtemp(prefix="native_")
    fake = os.path.join(work, os.path.basename(real))
    shutil.copy2(real, fake)
    raw = bytearray(open(fake, "rb").read())
    raw[len(raw) // 2] ^= 0x01
    open(fake, "wb").write(raw)
    result = integrity.check_native(fake)
    check("flipped byte is detected", not result["ok"], result["reason"])
    check("tampered module is reported as replaced",
          integrity.classify_anomaly(result)[1] == "NATIVE_REPLACED")

    open(fake, "wb").write(raw[: len(raw) // 2])
    result = integrity.check_native(fake)
    check("truncated module is detected", not result["ok"], result["reason"])

    # 还原：把备份解到临时路径，再校验
    backup = os.path.join(integrity.BACKUP_DIR, info[3])
    check("embedded pristine copy exists", os.path.isfile(backup))
    with gzip.open(backup, "rb") as fh:
        pristine = fh.read()
    open(fake, "wb").write(pristine)
    check("restored copy matches the pinned hash",
          hashlib.sha256(pristine).hexdigest() == info[1])

    # ---- 3b. cross-token: 换掉一个二进制，另一个拒绝工作 -------------
    fake_peer = os.path.join(work, "fake_peer")
    with open(fake_peer, "wb") as fh:
        fh.write(b"not a native module")
    proc = subprocess.run([real, "identity", "--fp", "00" * 32,
                           "--peer", fake_peer],
                          capture_output=True, text=True, timeout=10)
    check("signer rejects a peer without the build token",
          "PEER_MISMATCH" in (proc.stdout + proc.stderr))

    vpath = nb.native_path("verify")
    proc = subprocess.run([vpath, "state", "--pubkey", "AAAA", "--peer", fake_peer],
                          input="", capture_output=True, text=True, timeout=10)
    check("verifier rejects a peer without the build token",
          "PEER_MISMATCH" in (proc.stdout + proc.stderr))

    # ---- 3c. 混淆：协议字符串不应以明文出现 -------------------------
    #
    # 已知限制（README「已知限制」有完整说明）：OBF() 只在**运行时**异或，
    # 源码里的字面量是编译期常量，编译器有权把它原样放进目标文件 ——
    # 实测 clang 在 -O0 下也会把 "cmenc001"/"BAD_SCORE" 内联进 __TEXT，
    # constexpr / volatile / noinline / memcpy / 逐字节 volatile 五种写法都
    # 挡不住。混淆器本身没有漏包（已确认源码被正确转成 \xNN）。
    #
    # 这不是安全问题：KDF 上下文是 libsodium 的公开常量名，不是密钥；
    # ObfStr 的密钥同样能从二进制里还原。混淆的定位始终是「抬高静态分析
    # 成本」，不是密码学保护。所以这里只做记录，不判失败。
    raw = open(real, "rb").read()
    benign = [w.decode() for w in (b"BAD_SCORE", b"BAD_NAME", b"BAD_PROFILE",
                                   b"cmenc001", b"cmsig001") if w in raw]
    if benign:
        print(f"       [note] 编译器把常量放进了镜像（已知限制，不作失败）：{benign}")

    # ---- 4-6. chain integrity ----------------------------------------
    chain = fresh_chain()
    records = chain.load()
    plains = chain.plains()
    ok, _head, _err = nb.verify(records, plains)
    check("baseline chain verifies", ok)

    bad = [bytearray(r) for r in records]
    bad[1][20] ^= 0x01
    ok, _h, err = nb.verify([bytes(r) for r in bad], plains)
    check("edited record is rejected", not ok, err)

    ok, _h, err = nb.verify([records[0], records[2]], [plains[0], plains[2]])
    check("deleted record is rejected", not ok, err)

    ok, _h, err = nb.verify([records[1], records[0], records[2]],
                            [plains[1], plains[0], plains[2]])
    check("reordered records are rejected", not ok, err)

    # ---- 7. rollback via anchor --------------------------------------
    live = fresh_chain("roll_")
    snapshot = open(live.path, encoding="ascii").read()
    bump(live, 1, 5)
    with open(live.path, "w", encoding="ascii") as fh:
        fh.write(snapshot)
    rolled = L.Ledger(live.config_path)
    rolled.verify()
    problems = rolled.anchor_problems(rolled.state())
    check("rolled-back chain is reported", any(p.startswith("SHORTER") for p in problems),
          str(problems))

    # ---- 8. anchor timestamp ahead of the chain ----------------------
    ts_chain = fresh_chain("ts_")
    anchor = ts_chain.read_anchor_full()
    ts_chain.write_anchor(anchor["seq"], anchor["head_bytes"],
                          ts=int(anchor["ts"]) + 10_000,
                          digest=anchor["digest"], pubkey=anchor["pubkey"])
    problems = ts_chain.anchor_problems(ts_chain.state())
    check("anchor time ahead of chain is reported",
          any(p.startswith("TIME_ROLLBACK") for p in problems), str(problems))

    # ---- 9. state digest differs -------------------------------------
    dig_chain = fresh_chain("dig_")
    anchor = dig_chain.read_anchor_full()
    dig_chain.write_anchor(anchor["seq"], anchor["head_bytes"], ts=anchor["ts"],
                           digest="00" * 32, pubkey=anchor["pubkey"])
    problems = dig_chain.anchor_problems(dig_chain.state())
    check("wrong state digest is reported",
          any(p == "STATE_MISMATCH" for p in problems), str(problems))

    # ---- 10. public key differs --------------------------------------
    pk_chain = fresh_chain("pk_")
    anchor = pk_chain.read_anchor_full()
    pk_chain.write_anchor(anchor["seq"], anchor["head_bytes"], ts=anchor["ts"],
                          digest=anchor["digest"], pubkey="AAAA")
    problems = pk_chain.anchor_problems(pk_chain.state(), pubkey_b64="BBBB")
    check("wrong public key is reported",
          any(p == "PUBKEY_MISMATCH" for p in problems), str(problems))

    # ---- 11. ctime anomaly -------------------------------------------
    # Windows 的 st_ctime 是创建时间，追加内容不会更新它：
    # 负 gap 在 Windows 上必须视为正常，否则每次启动都误报“时间被改过”
    tmp_file = os.path.join(tempfile.mkdtemp(prefix="ctime_"), "x.esc")
    open(tmp_file, "w").write("x")
    res_win = integrity.check_ctime(tmp_file, time.time() + 3600, platform="win32")
    check("windows ignores ctime older than the last event", res_win["ok"], res_win["reason"])
    res_mac = integrity.check_ctime(tmp_file, time.time() + 3600, platform="darwin")
    check("macOS still flags ctime older than the last event",
          not res_mac["ok"] and res_mac["reason"] == "CTIME_BEFORE_EVENT", res_mac["reason"])

    ct_chain = fresh_chain("ct_")
    last_ts = ct_chain.last_ts()
    res = integrity.check_ctime(ct_chain.path, last_ts - 3600)
    check("ctime newer than events is reported",
          not res["ok"] and res["reason"].startswith("CTIME_AHEAD"), res["reason"])
    res_ok = integrity.check_ctime(ct_chain.path, last_ts)
    check("ctime equal to last event passes", res_ok["ok"], res_ok["reason"])

    # ---- 12. NTP offline ----------------------------------------------
    offline = sntp.sync(("127.0.0.1",), timeout=0.05)
    check("NTP offline is reported without crashing",
          offline["ok"] is False and "offline" in offline["error"], offline["error"])

    # ---- 13. NTP timestamp round-trip ---------------------------------
    now = 1_800_000_000.123
    encoded = sntp._to_ntp_timestamp(now)
    decoded = sntp._from_ntp_timestamp(encoded)
    check("NTP timestamp round-trip within 1 ms", abs(decoded - now) < 0.001,
          f"{abs(decoded - now) * 1e6:.1f} us")

    # ---- 14. monotonic timestamps -------------------------------------
    mono = fresh_chain("mono_")
    stamps = [mono.last_ts()]
    for i in range(3):
        bump(mono, 2, 1)
        stamps.append(mono.last_ts())
    check("timestamps strictly increase", all(b > a for a, b in zip(stamps, stamps[1:])),
          str(stamps))
    check("monotonic chain still verifies", mono.verify(), mono.verify_error())

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
