import os, sys, tempfile
sys.path.insert(0, ".")

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
assert not s3._cp.has_section("stats"), "旧的 [stats] 残留没清掉"
print("CONFIG RESET_OK")
print("-" * 50)

# --- StatsStore: survives a config reset ---
stats_path = os.path.join(tmp_dir, "stats.ini")
st = StatsStore(stats_path)
print("stats path:", st.path, "| exists:", os.path.isfile(st.path))
assert st.load() == {}, st.load()
assert st.save({"张三": 3, "李四": 1}), "stats save failed"

st2 = StatsStore(stats_path)
print("reload stats:", st2.load())
assert st2.load() == {"张三": 3, "李四": 1}

# merge, not replace: a new class list must not wipe the previous one
assert st2.save({"王五": 2}), "merge save failed"
assert st2.load() == {"张三": 3, "李四": 1, "王五": 2}, st2.load()
print("merge keeps other names:", StatsStore(stats_path).load())

# count 0 removes the entry instead of writing `name = 0`
assert st2.save({"张三": 0}), "zero save failed"
loaded = StatsStore(stats_path).load()
assert "张三" not in loaded and loaded.get("王五") == 2, loaded
print("zero removes the line:", loaded)

# clear() drops everything
assert st2.clear(), "clear failed"
assert StatsStore(stats_path).load() == {}
print("cleared:", StatsStore(stats_path).load())
print("STATS ROUND-TRIP OK")
print("-" * 50)
print(open(stats_path, encoding="utf-8").read())
print("ALL OK")
