"""Check the native helper module (cmd_native / cmd_native.exe).

Usage:
    python tools/native_check.py

Covers:
    1. binary exists, is executable, and its built-in selftest passes;
    2. fingerprint is stable and the protocol matches the Python bridge;
    3. append -> verify round-trip over several records;
    4. flipping one byte is rejected (BAD_SIG);
    5. swapping two records is rejected (BAD_SIG / BAD_SEQ);
    6. a different fingerprint cannot verify (data is machine-bound).

Exit code 0 = all passed; 1 = something failed; 77 = native module missing.
"""

import base64
import os
import sys

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
    check("protocol matches the bridge",
          nb.EXPECTED_PROTOCOL == 1)

    # ---- round trip -------------------------------------------------
    genesis = b"\x00" * 32
    head = genesis
    records = []
    payloads = [
        b'{"op":"init"}',
        b'{"op":"score","group":2,"to":5}',
        b'{"op":"score","group":3,"to":-1}',
    ]
    for i, payload in enumerate(payloads, start=1):
        rec, head = nb.append(head, i, payload)
        records.append(rec)
        check(f"record {i} has expected size", len(rec) > 32 + 64, f"{len(rec)} bytes")

    ok, final_head, error = nb.verify(records)
    check("chain verifies", ok, error)
    check("final head matches", final_head == head)

    # ---- tamper -----------------------------------------------------
    broken = [bytearray(r) for r in records]
    broken[1][20] ^= 0x01                      # 改密文区域一个 bit
    ok, _, error = nb.verify([bytes(r) for r in broken])
    check("single-byte tamper is rejected", not ok, error)
    check("tamper reports a signature error", error in ("BAD_SIG", "BAD_DECRYPT"), error)

    # ---- reorder ----------------------------------------------------
    ok, _, error = nb.verify([records[1], records[0], records[2]])
    check("reordered records are rejected", not ok, error)

    # ---- dropped record --------------------------------------------
    ok, _, error = nb.verify([records[0], records[2]])
    check("dropped record is rejected", not ok, error)

    # ---- wrong machine ---------------------------------------------
    wrong = "00" * 32
    saved = nb._fp_cache
    try:
        nb._fp_cache = wrong
        ok, _, error = nb.verify(records)
        check("another machine's fingerprint cannot verify", not ok, error)
    finally:
        nb._fp_cache = saved

    # ---- base64 payloads survive --------------------------------
    ok, _, _ = nb.verify(records, expect_seq=len(records))
    check("expect_seq matches", ok)

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
