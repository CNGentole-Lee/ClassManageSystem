"""stats_check —— 每节课的抽取次数存在事件链里（不再是明文 stats.ini）。

这条测试盯住四件事：
    1. 抽取次数确实进了链，重启后能重放出来
    2. 磁盘上不再产生明文文件（学生姓名不得以可读形式落盘）
    3. 次数按「预设」独立：化学课抽过的次数不会跑到语文课去（SOP v2 第 3 条）
    4. 清空只清当前预设；清空后还能继续记

用法：
    python tools/stats_check.py
"""

import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

from _settings_isolation import isolate_settings

isolate_settings()
os.environ.setdefault("CLASSMANAGE_STATE_DIR", tempfile.mkdtemp(prefix="cm_stats_"))

from namepicker import native_bridge as nb   # noqa: E402
from namepicker.ledger import Ledger          # noqa: E402
from namepicker.profiles import ProfileStore  # noqa: E402
from namepicker.stats_store import StatsStore  # noqa: E402

failures = []
NAMES = ["张三", "李四", "王五"]


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def fresh(tmp, groups=3, names=None):
    """建一条链 + 一个预设，并把「名单长度」对齐（main.py 也这么做）。"""
    roster = NAMES if names is None else names
    chain = Ledger(os.path.join(tmp, "config.ini"))
    if chain.count() == 0:
        chain.migrate_from(0, [], [])
    store = ProfileStore(chain=chain)
    pid = store.create("化学课")
    store.set_rule(pid, groups, len(roster))
    store.use(pid)
    return chain


def counts_of(chain, pid=None):
    state = chain.state()
    active = int(pid or state.get("active_profile", 0) or 0)
    for profile in state.get("profiles", []):
        if int(profile["id"]) == active:
            return list(profile.get("draw_counts", []))
    return []


def main() -> int:
    if not nb.available():
        print("[SKIP] native module not available")
        return 77

    tmp = tempfile.mkdtemp(prefix="cm_stats_")
    chain = fresh(tmp)

    check("chain starts with no draw counts", counts_of(chain) == [0, 0, 0], str(counts_of(chain)))

    # ---- 1. 写入与重放 ------------------------------------------------
    stats = StatsStore(os.path.join(tmp, "stats.ini"), chain=chain)
    stats.set_names(NAMES)
    check("store is backed by the chain", stats.usable)
    ok = stats.save({"张三": 3, "李四": 1})
    check("save() reports success", ok, stats.last_error())
    check("counts are visible in memory",
          stats.load() == {"张三": 3, "李四": 1}, str(stats.load()))
    check("counts reached the chain state", counts_of(chain) == [3, 1, 0], str(counts_of(chain)))

    # 重新打开链：模拟重启
    reopened = Ledger(os.path.join(tmp, "config.ini"))
    check("reopened chain verifies", reopened.verify(), reopened.verify_error())
    again = StatsStore(os.path.join(tmp, "stats.ini"), chain=reopened)
    again.set_names(NAMES)
    check("counts survive a restart", again.load() == {"张三": 3, "李四": 1}, str(again.load()))

    # ---- 2. 磁盘上没有明文 --------------------------------------------
    on_disk = sorted(os.listdir(tmp))
    check("no plaintext stats.ini is created", "stats.ini" not in on_disk, str(on_disk))
    ledger_path = os.path.join(tmp, "Data", "ledger.esc")
    raw = open(ledger_path, "rb").read()
    check("student names are not readable in the chain file",
          "张三".encode("utf-8") not in raw)

    # ---- 3. 只增不重复 ------------------------------------------------
    before = len(open(ledger_path, "rb").read().splitlines())
    stats.save({"张三": 3, "李四": 1})
    after = len(open(ledger_path, "rb").read().splitlines())
    check("saving unchanged counts adds no events", before == after, f"{before} -> {after}")

    stats.save({"张三": 4})
    check("a real change appends exactly one event",
          len(open(ledger_path, "rb").read().splitlines()) == after + 1)
    replay = StatsStore(os.path.join(tmp, "stats.ini"),
                        chain=Ledger(os.path.join(tmp, "config.ini")))
    replay.set_names(NAMES)
    check("the new total is replayed", replay.load()["张三"] == 4, str(replay.load()))

    # ---- 4. 每个预设各算各的 ------------------------------------------
    chain2 = Ledger(os.path.join(tmp, "config.ini"))
    ps = ProfileStore(chain=chain2)
    other = ps.create("语文课")
    ps.set_rule(other, 3, len(NAMES))
    ps.use(other)
    other_stats = StatsStore(os.path.join(tmp, "stats.ini"), chain=chain2)
    other_stats.set_names(NAMES)
    check("a new profile starts from zero", other_stats.load() == {}, str(other_stats.load()))
    check("the first profile's counts are untouched",
          counts_of(chain2, pid=1) == [4, 1, 0], str(counts_of(chain2, pid=1)))

    other_stats.save({"李四": 2})
    check("the second profile keeps its own counts",
          other_stats.load() == {"李四": 2}, str(other_stats.load()))
    check("writing in one profile does not touch the other",
          counts_of(chain2, pid=1) == [4, 1, 0], str(counts_of(chain2, pid=1)))

    # ---- 5. 清空只清当前预设 ------------------------------------------
    # 此刻当前预设是「语文课」，清空必须只影响它。
    check("clear() reports success", other_stats.clear(), other_stats.last_error())
    check("counts are empty in memory", other_stats.load() == {}, str(other_stats.load()))
    cleared = StatsStore(os.path.join(tmp, "stats.ini"),
                         chain=Ledger(os.path.join(tmp, "config.ini")))
    cleared.set_names(NAMES)
    check("counts stay cleared after a restart", cleared.load() == {}, str(cleared.load()))
    check("clearing one profile leaves the other alone",
          counts_of(Ledger(os.path.join(tmp, "config.ini")), pid=1) == [4, 1, 0],
          str(counts_of(Ledger(os.path.join(tmp, "config.ini")), pid=1)))

    # 清空之后还能继续记
    cleared.save({"王五": 2})
    check("counting works again after a clear", cleared.load() == {"王五": 2}, str(cleared.load()))

    # ---- 6. 名单没对齐时绝不谎报成功 ----------------------------------
    tmp3 = tempfile.mkdtemp(prefix="cm_stats_noroster_")
    chain3 = fresh(tmp3, names=[])
    nobody = StatsStore(os.path.join(tmp3, "stats.ini"), chain=chain3)
    nobody.set_names(["张三"])
    check("a draw beyond the roster is reported, not silently dropped",
          nobody.save({"张三": 1}) is False, nobody.last_error())

    # ---- 7. 旧 stats.ini 只迁移一次 -----------------------------------
    tmp2 = tempfile.mkdtemp(prefix="cm_stats_legacy_")
    legacy_path = os.path.join(tmp2, "stats.ini")
    with open(legacy_path, "w", encoding="utf-8") as fh:
        fh.write("[counts]\n老张 = 7\n老李 = 2\n")
    chain4 = fresh(tmp2, names=["老张", "老李", "老王"])
    migrated = StatsStore(legacy_path, chain=chain4)
    migrated.set_names(["老张", "老李", "老王"])
    check("legacy stats.ini is imported into the chain",
          migrated.load() == {"老张": 7, "老李": 2}, str(migrated.load()))
    check("legacy stats.ini is removed after the import", not os.path.isfile(legacy_path))

    # 再建一个同名明文文件，程序不应再读它
    with open(legacy_path, "w", encoding="utf-8") as fh:
        fh.write("[counts]\n老张 = 999\n")
    reopened2 = StatsStore(legacy_path, chain=Ledger(os.path.join(tmp2, "config.ini")))
    reopened2.set_names(["老张", "老李", "老王"])
    check("a hand-written stats.ini is ignored afterwards",
          reopened2.load() == {"老张": 7, "老李": 2}, str(reopened2.load()))

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
