"""stats_check —— 长期抽取次数现在存在事件链里（不再是明文 stats.ini）。

这条测试盯住三件事：
    1. 抽取次数确实进了链，重启后能重放出来
    2. 磁盘上不再产生明文文件（学生姓名不得以可读形式落盘）
    3. 清空长期次数会追加 wipe 事件，重放后归零；旧 stats.ini 只迁移一次

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
from namepicker.stats_store import StatsStore  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def fresh(tmp):
    chain = Ledger(os.path.join(tmp, "config.ini"))
    chain.migrate_from(3, ["甲组", "乙组", "丙组"], [0, 0, 0])
    return chain


def main() -> int:
    if not nb.available():
        print("[SKIP] native module not available")
        return 77

    tmp = tempfile.mkdtemp(prefix="cm_stats_")
    chain = fresh(tmp)

    check("chain starts with no draw counts", chain.state().get("draws") == {})

    # ---- 1. 写入与重放 ------------------------------------------------
    stats = StatsStore(os.path.join(tmp, "stats.ini"), chain=chain)
    check("store is backed by the chain", stats.usable)
    ok = stats.save({"张三": 3, "李四": 1})
    check("save() reports success", ok, stats.last_error())
    check("counts are visible in memory", stats.load() == {"张三": 3, "李四": 1}, str(stats.load()))
    check("counts reached the chain state",
          chain.state().get("draws") == {"张三": 3, "李四": 1}, str(chain.state().get("draws")))

    # 重新打开链：模拟重启
    reopened = Ledger(os.path.join(tmp, "config.ini"))
    check("reopened chain verifies", reopened.verify(), reopened.verify_error())
    again = StatsStore(os.path.join(tmp, "stats.ini"), chain=reopened)
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
    check("the new total is replayed", StatsStore(os.path.join(tmp, "stats.ini"),
                                                  chain=Ledger(os.path.join(tmp, "config.ini"))
                                                  ).load()["张三"] == 4)

    # ---- 4. 清空 ------------------------------------------------------
    check("clear() reports success", stats.clear(), stats.last_error())
    check("counts are empty in memory", stats.load() == {}, str(stats.load()))
    cleared = StatsStore(os.path.join(tmp, "stats.ini"),
                         chain=Ledger(os.path.join(tmp, "config.ini")))
    check("counts stay cleared after a restart", cleared.load() == {}, str(cleared.load()))

    # 清空之后还能继续记
    cleared.save({"王五": 2})
    check("counting works again after a clear", cleared.load() == {"王五": 2}, str(cleared.load()))

    # ---- 5. 旧 stats.ini 只迁移一次 -----------------------------------
    tmp2 = tempfile.mkdtemp(prefix="cm_stats_legacy_")
    legacy_path = os.path.join(tmp2, "stats.ini")
    with open(legacy_path, "w", encoding="utf-8") as fh:
        fh.write("[counts]\n老张 = 7\n老李 = 2\n")
    chain2 = fresh(tmp2)
    migrated = StatsStore(legacy_path, chain=chain2)
    check("legacy stats.ini is imported into the chain",
          migrated.load() == {"老张": 7, "老李": 2}, str(migrated.load()))
    check("legacy stats.ini is removed after the import", not os.path.isfile(legacy_path))

    # 再建一个同名明文文件，程序不应再读它
    with open(legacy_path, "w", encoding="utf-8") as fh:
        fh.write("[counts]\n老张 = 999\n")
    reopened2 = StatsStore(legacy_path, chain=Ledger(os.path.join(tmp2, "config.ini")))
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
