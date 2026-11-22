"""预设（分组制）的检查：全部走事件链，不产生任何文件。

用法:
    TMPDIR=$PWD/.tmptest python tools/profile_check.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def _write_json(directory: str, payload: dict) -> str:
    import json

    path = os.path.join(directory, "tmp-snapshot.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return path


def main() -> int:
    from namepicker import native_bridge as nb

    try:
        nb.native_path("sign")
    except nb.NativeMissing as exc:
        print(f"[SKIP] native module not found: {exc}")
        return 77

    from namepicker.ledger import Ledger
    from namepicker.profiles import ProfileStore, ProfileError

    tmp = tempfile.mkdtemp(prefix="cm_profile_")
    ledger = Ledger(os.path.join(tmp, "ledger.esc"))
    ledger.apply("init", count=3, names="甲组,乙组,丙组", scores="0,0,0")
    store = ProfileStore(chain=ledger)

    print("\n--- 1. Create / rename ---")
    check("no profiles at first", store.list() == [])
    check("grouping is off without a profile", store.grouping_enabled() is False)
    pid = store.create("化学课")
    check("create returns id 1", pid == 1, str(pid))
    check("profile shows up in the list", [p["name"] for p in store.list()] == ["化学课"])
    store.rename(pid, "化学 · 实验组")
    check("rename is applied", store.get(pid)["name"] == "化学 · 实验组")
    second = store.create("语文课")
    check("second profile gets id 2", second == 2, str(second))

    print("\n--- 2. Rules and members (incremental) ---")
    before = len(ledger.load())
    store.set_rule(pid, group_count=2, member_count=3)
    after_rule = len(ledger.load())
    check("set_rule writes exactly one event", after_rule == before + 1,
          f"{after_rule - before}")
    check("group_count is stored", store.get(pid)["group_count"] == 2)

    written = store.assign_bulk(pid, {0: 1, 1: 2, 2: 1})
    after_bulk = len(ledger.load())
    check("assign_bulk writes one event per changed index", after_bulk == after_rule + 3,
          f"{after_bulk - after_rule} for {written} changes")
    check("members are stored in index order", store.get(pid)["members"] == [1, 2, 1],
          str(store.get(pid)["members"]))

    written = store.assign_bulk(pid, {0: 1, 1: 2, 2: 1})
    check("re-assigning the same mapping writes nothing", written == 0, str(written))
    check("...and the chain does not grow", len(ledger.load()) == after_bulk)

    written = store.assign_bulk(pid, {0: 1, 1: 1, 2: 1})
    check("only the actually changed index is written", written == 1, str(written))
    check("members follow the incremental write", store.get(pid)["members"] == [1, 1, 1],
          str(store.get(pid)["members"]))

    print("\n--- 3. Activation ---")
    store.use(pid)
    check("active_id is the chosen profile", store.active_id() == pid)
    check("grouping is now enabled", store.grouping_enabled() is True)
    check("exactly one profile is marked active",
          sum(1 for p in store.list() if p["active"]) == 1)
    store.use(0)
    check("use(0) turns grouping off", store.grouping_enabled() is False)
    check("group_of returns 0 without an active profile",
          [store.group_of(i) for i in range(3)] == [0, 0, 0])
    store.use(pid)
    check("group_of follows the assignment",
          [store.group_of(i) for i in range(3)] == [1, 1, 1],
          str([store.group_of(i) for i in range(3)]))

    print("\n--- 4. Shrinking the name list ---")
    store.set_rule(pid, group_count=2, member_count=2)
    check("shrinking trims the assignment", store.get(pid)["members"] == [1, 1],
          str(store.get(pid)["members"]))
    store.assign(pid, 9, 1)          # 越界下标：不该炸
    check("out-of-range index is ignored, not fatal", len(store.get(pid)["members"]) == 2)

    print("\n--- 5. Deleting ---")
    store.delete(pid)
    check("profile is gone", store.get(pid) is None)
    check("active marker falls back to 0", store.active_id() == 0)
    check("the other profile survives", store.get(second)["name"] == "语文课")
    try:
        store.delete(999)
        check("deleting a missing profile is rejected", False, "no error")
    except ProfileError as exc:
        check("deleting a missing profile is rejected", "BAD_PROFILE" in str(exc), str(exc))

    print("\n--- 6. No files are produced ---")
    # Ledger 会把路径规范化到 <dir>/Data/ 下，就按它实际用的目录检查
    ledger_dir = os.path.dirname(ledger.path)
    produced = sorted(os.listdir(ledger_dir))
    check("presets add no files of their own (only ledger + anchor)",
          set(produced) <= {"ledger.esc", "anchor.json"}, str(produced))

    print("\n--- 7. Helpers ---")
    bal = store.balanced_assignment(4, 40)
    sizes = ProfileStore.group_sizes([bal[i] for i in range(40)], 4)
    check("balanced_assignment fills every slot", len(bal) == 40)
    check("balanced_assignment is even", all(sizes[g] == 10 for g in range(1, 5)),
          str(sizes))
    check("balanced_assignment starts at group 1", bal[0] == 1 and bal[39] == 4,
          f"{bal[0]}..{bal[39]}")

    print("\n--- 8. Export / import round trip ---")
    from namepicker import export_import

    src = Ledger(os.path.join(tmp, "src", "ledger.esc"))
    src.apply("init", count=3, names="甲组,乙组,丙组", scores="0,0,0")
    src_store = ProfileStore(chain=src)
    spid = src_store.create("化学课")
    src_store.set_rule(spid, 2, 3)
    src_store.assign_bulk(spid, {0: 1, 1: 2, 2: 1})
    src_store.use(spid)

    class _FakeConfig:
        group_count = 3

        def get_group_name(self, i):
            return ["甲组", "乙组", "丙组"][i - 1]

        def all_scores(self):
            return [0, 0, 0]

    payload = export_import.export_payload(
        _FakeConfig(), draws={"张三": 2},
        profiles=src_store.list(), active_profile=src_store.active_id())
    check("export carries the profiles",
          payload["profiles"][0]["name"] == "化学课", str(payload.get("profiles")))
    snap = os.path.join(tmp, "snap.json")
    export_import.save(payload, snap)
    loaded = export_import.load(snap)
    check("snapshot round-trips through JSON",
          loaded["profiles"] == payload["profiles"]
          and loaded["active_profile"] == payload["active_profile"])

    dst = Ledger(os.path.join(tmp, "dst", "ledger.esc"))
    dst.apply("init", count=3, names="甲组,乙组,丙组", scores="0,0,0")
    dst.import_snapshot(loaded)
    dst_store = ProfileStore(chain=dst)
    check("import restores the preset",
          [p["name"] for p in dst_store.list()] == ["化学课"],
          str(dst_store.list()))
    check("import restores the group assignment",
          dst_store.get(dst_store.active_id())["members"] == [1, 2, 1],
          str(dst_store.get(dst_store.active_id())))
    check("import restores the active marker", dst_store.active_id() == 1)
    check("grouping works after the import", dst_store.grouping_enabled() is True)

    bogus = dict(payload)          # 原始 payload 带 format 字段
    bogus["profiles"] = [{"id": 5, "name": "坏组", "group_count": 99,
                          "members": [1]}]
    check("malformed profiles are dropped on load",
          export_import.load(_write_json(tmp, bogus))["profiles"] == [])

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
