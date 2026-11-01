import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()
sys.path.insert(0, ".")

from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()  # 测试数据不写进真实的隐蔽备份（Windows 注册表 / macOS plist）

from namepicker.config_store import ConfigStore
from namepicker.stats_store import StatsStore

tmp_dir = tempfile.mkdtemp()

# --- ConfigStore round-trip (groups + scores) ---
tmp = os.path.join(tmp_dir, "config.ini")
s = ConfigStore(tmp)
print("config path:", s.path, "| exists:", os.path.isfile(s.path))
print("groups:", [s.get_group_name(i) for i in range(1, s.group_count + 1)])
s.set_score(1, 5); s.set_score(3, -2); s.set_group_name(2, "雄鹰组")
assert s.save(), "save failed"
s2 = ConfigStore(tmp)
print("reload scores:", s2.all_scores())
print("reload name2:", s2.get_group_name(2))
assert s2.all_scores() == [5, 0, -2, 0, 0, 0]
assert s2.get_group_name(2) == "雄鹰组"
print("CONFIG ROUND-TRIP OK")

# --- reset_all: back to factory settings ---
s2.reset_all()
s3 = ConfigStore(tmp)
assert s3.all_scores() == [0] * 6, s3.all_scores()
assert s3.get_group_name(1) == "第一组" and s3.get_group_name(2) == "第二组"
assert not s3._cp.has_section("stats"), "stale [stats] section was not cleared"
print("CONFIG RESET_OK")
print("-" * 50)

# --- StatsStore: 长期次数现在存在事件链里（没有明文 stats.ini）---
from namepicker.ledger import Ledger  # noqa: E402

stats_path = os.path.join(tmp_dir, "stats.ini")
chain = Ledger(os.path.join(tmp_dir, "config.ini"))
chain.migrate_from(3, ["甲组", "乙组", "丙组"], [0, 0, 0])

st = StatsStore(stats_path, chain=chain)
print("stats backend:", "event chain" if st.usable else "NONE")
assert st.load() == {}, st.load()
assert st.save({"张三": 3, "李四": 1}), "stats save failed"

st2 = StatsStore(stats_path, chain=Ledger(os.path.join(tmp_dir, "config.ini")))
print("reload stats:", st2.load())
assert st2.load() == {"张三": 3, "李四": 1}

# 合并而非覆盖：换一个班的花名册不能清掉上一个班
assert st2.save({"王五": 2}), "merge save failed"
assert st2.load() == {"张三": 3, "李四": 1, "王五": 2}, st2.load()
print("merge keeps other names:", st2.load())

# 明文文件不应生成，学生姓名不应以可读形式落盘
assert not os.path.isfile(stats_path), "plaintext stats.ini must not be created"
raw = open(os.path.join(tmp_dir, "Data", "ledger.esc"), "rb").read()
assert "张三".encode("utf-8") not in raw
print("no plaintext on disk: OK")

# clear() 清空全部（追加 wipe 事件）
assert st2.clear(), "clear failed"
assert StatsStore(stats_path, chain=Ledger(os.path.join(tmp_dir, "config.ini"))).load() == {}
print("cleared:", {})
print("STATS ROUND-TRIP OK")
print("-" * 50)

print("ALL OK")
