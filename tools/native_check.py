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
        exe = nb.native_path()
    except nb.NativeMissing as exc:
        print(f"[SKIP] native module not found: {exc}")
        return 77

    print(f"native: {exe}")
    check("native binary exists", os.path.isfile(exe))
    check("selftest passes", nb.selftest())

    fp = nb.fingerprint()
    check("fingerprint is 64 hex chars",
          len(fp) == 64 and all(c in "0123456789abcdef" for c in fp), fp[:16] + "...")
    check("fingerprint is stable", nb.fingerprint() == fp)

    # ---- 业务状态机（数据由 C++ 计算） ----------------------------
    r = nb.apply([], "init", count=3, names="甲,乙,丙", scores="0,0,0")
    check("init returns a record", bool(r.get("record")))
    rec1 = base64.b64decode(r["record"])
    check("init state", r["count"] == 3 and r["names"] == ["甲", "乙", "丙"]
          and r["scores"] == [0, 0, 0], str(r["scores"]))

    r = nb.apply([rec1], "score", group=2, delta=5)
    rec2 = base64.b64decode(r["record"])
    check("score applied by C++", r["scores"] == [0, 5, 0], str(r["scores"]))
    check("score returns new seq", r["seq"] == 2, str(r["seq"]))

    r = nb.apply([rec1, rec2], "rename", group=1, name="雄鹰组")
    rec3 = base64.b64decode(r["record"])
    check("rename applied by C++", r["names"][0] == "雄鹰组", r["names"][0])

    st = nb.state([rec1, rec2, rec3])
    check("state replays to the same result",
          st["names"][0] == "雄鹰组" and st["scores"] == [0, 5, 0], str(st["scores"]))
    check("state reports the head", len(base64.b64decode(st["head"])) == 32)

    # ---- 规则在 C++ 侧 --------------------------------------------
    try:
        nb.apply([rec1, rec2, rec3], "score", group=99, delta=1)
        check("out-of-range group is rejected", False)
    except nb.NativeError as exc:
        check("out-of-range group is rejected", "BAD_GROUP" in str(exc), str(exc)[:40])
    try:
        nb.apply([rec1, rec2, rec3], "score", group=1, delta=10 ** 9)
        check("absurd score delta is rejected", False)
    except nb.NativeError as exc:
        check("absurd score delta is rejected", "BAD_SCORE" in str(exc), str(exc)[:40])
    try:
        nb.apply([rec1, rec2, rec3], "count", count=999)
        check("absurd group count is rejected", False)
    except nb.NativeError as exc:
        check("absurd group count is rejected", "BAD_COUNT" in str(exc), str(exc)[:40])

    # ---- 链完整性 -------------------------------------------------
    records = [rec1, rec2, rec3]
    ok, head, error = nb.verify(records)
    check("chain verifies", ok, error)

    broken = [bytearray(r) for r in records]
    broken[1][20] ^= 0x01
    ok, _, error = nb.verify([bytes(r) for r in broken])
    check("single-byte tamper is rejected", not ok, error)

    ok, _, error = nb.verify([records[1], records[0], records[2]])
    check("reordered records are rejected", not ok, error)

    ok, _, error = nb.verify([records[0], records[2]])
    check("dropped record is rejected", not ok, error)

    saved = nb._fp_cache
    try:
        nb._fp_cache = "00" * 32
        ok, _, error = nb.verify(records)
        check("another machine's fingerprint cannot verify", not ok, error)
    finally:
        nb._fp_cache = saved

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
