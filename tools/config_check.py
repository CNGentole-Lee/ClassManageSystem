"""配置与长期计数的往返测试（V4）。

V4 起组名/分数/抽取次数都在事件链的「预设」里，config.ini 只是副本。
所以这里的「往返」指的是：写入 → 重新打开程序 → 数据还在；
而不是「config.ini 里那几行还在」。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()
sys.path.insert(0, ".")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()  # 测试数据不写进真实的隐蔽备份（Windows 注册表 / macOS plist）

from _v4_fixture import open_store, reopen_store, sync_roster  # noqa: E402
from namepicker.ledger import Ledger  # noqa: E402
from namepicker.stats_store import StatsStore  # noqa: E402

tmp_dir = tempfile.mkdtemp()
cfg = os.path.join(tmp_dir, "config.ini")

# --- 积分往返：写进去，重启后还在 ---
s = open_store(cfg)
print("config path:", s.path, "| exists:", os.path.isfile(s.path))
print("groups:", [s.get_group_name(i) for i in range(1, s.group_count + 1)])
assert s.group_count == 6, s.group_count
s.set_score(1, 5)
s.set_score(3, -2)
s.set_group_name(2, "雄鹰组")
assert s.save(), "save failed"

s2 = reopen_store(cfg)
print("reload scores:", s2.all_scores())
print("reload name2:", s2.get_group_name(2))
assert s2.all_scores() == [5, 0, -2, 0, 0, 0], s2.all_scores()
assert s2.get_group_name(2) == "雄鹰组", s2.get_group_name(2)
print("CONFIG ROUND-TRIP OK")

# --- reset_all：当前预设回到出厂状态（组数回默认、组名默认、分数 0）---
assert s2.reset_all(), "reset save failed"
s3 = reopen_store(cfg)
assert s3.all_scores() == [0] * 6, s3.all_scores()
assert s3.get_group_name(1) == "第一组" and s3.get_group_name(2) == "第二组"
assert not s3._cp.has_section("stats"), "stale [stats] section was not cleared"
print("CONFIG RESET_OK")
print("-" * 50)

# --- 手改明文副本不生效：真数据在链上 ---
raw_ini = os.path.join(tmp_dir, "config.ini")
with open(raw_ini, encoding="utf-8") as fh:
    text = fh.read()
with open(raw_ini, "w", encoding="utf-8") as fh:
    fh.write(text.replace("score_1 = 5", "score_1 = 9999"))
assert reopen_store(cfg).get_score(1) == 0, "plaintext copy must never be a data source"
print("hand-edited config.ini has no effect: OK")
print("-" * 50)

# --- StatsStore：长期次数进链（没有明文 stats.ini）---
stats_path = os.path.join(tmp_dir, "stats.ini")
chain = Ledger(cfg)
names = ["张三", "李四", "王五"]
sync_roster(cfg, len(names))             # 名单加载后对齐（main.py 也这么做）
chain = Ledger(cfg)
st = StatsStore(stats_path, chain=chain)
st.set_names(names)                      # V4：链按下标存次数，先给名单
print("stats backend:", "event chain" if st.usable else "NONE")
assert st.load() == {}, st.load()
assert st.save({"张三": 3, "李四": 1}), "stats save failed"

st2 = StatsStore(stats_path, chain=Ledger(cfg))
st2.set_names(names)
print("reload stats:", st2.load())
assert st2.load() == {"张三": 3, "李四": 1}, st2.load()

# 合并而非覆盖：再抽一次只让那一个人 +1
assert st2.save({"张三": 4}), "merge save failed"
assert st2.load() == {"张三": 4, "李四": 1}, st2.load()
print("merge keeps other names:", st2.load())

# 名字不在名单里：跳过，不猜下标、不写错位置
assert st2.save({"陌生人": 2}), "unknown name must not fail the save"
assert st2.load() == {"张三": 4, "李四": 1}, st2.load()
print("unknown name skipped:", st2.load())

# 明文文件不应生成，学生姓名不应以可读形式落盘
assert not os.path.isfile(stats_path), "plaintext stats.ini must not be created"
raw = open(os.path.join(tmp_dir, "Data", "ledger.esc"), "rb").read()
assert "张三".encode("utf-8") not in raw
print("no plaintext on disk: OK")

# 次数不会倒退：写成更小的值不产生事件
before = Ledger(cfg).count()
assert st2.save({"张三": 1}), "shrinking save should be a no-op"
assert Ledger(cfg).count() == before, "a shrinking count must not append"
print("counts never go backwards: OK")

# clear() 清空当前预设的次数（追加 wipe 事件）
assert st2.clear(), "clear failed"
st3 = StatsStore(stats_path, chain=Ledger(cfg))
st3.set_names(names)
assert st3.load() == {}, st3.load()
print("cleared:", {})
print("STATS ROUND-TRIP OK")
print("-" * 50)

print("ALL OK")
