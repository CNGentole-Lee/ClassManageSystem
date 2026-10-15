"""操作日志自检 —— 加密、防篡改、自动回档。

用法:
    python tools/log_crypto_check.py

检查项：
    1. 每次积分变动自动记录（加分/减分/撤销/清零此组/全部清零/改组数/彻底重置）；
    2. 分数没变就不记（不产生噪音）；
    3. points_log.dat 是加密二进制，磁盘上没有任何明文副本；
    4. 篡改任意字节 → 自动从 points_log.dat.bak 回档并修复；
    5. 主文件 + .bak 同时坏掉 → 从 QSettings 隐蔽备份回档；
    6. 删除主文件 / 全部删除 → 回档或空日志，都不崩；
    7. 防回滚：用旧的密文覆盖主文件（GCM 解得开，但 seq 更小）→ 自动修回；
    8. 日志只增不减：「彻底重置」只追加标记，不清空。

脚本在临时 HOME 里运行，不碰真实密钥与真实备份。
"""

import os
import shutil
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="cm_log_home_")
os.environ["HOME"] = _TMP_HOME            # macOS / Linux
os.environ["USERPROFILE"] = _TMP_HOME     # Windows（expanduser 走这里）
os.environ.pop("APPDATA", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from namepicker import backup_store, log_store  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402

failures = []


def check(label, condition, detail=""):
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(label)


if backup_store.QSettings is None:
    _fake = {}

    def _fake_save(blob, tag="", prefix="sys_cache"):
        _fake[(prefix, tag)] = blob
        return True

    def _fake_load(tag="", prefix="sys_cache"):
        return _fake.get((prefix, tag))

    backup_store.save_backup = _fake_save
    backup_store.load_backup = _fake_load
    print("[INFO] 未安装 PyQt5：隐蔽备份使用内存假实现")
else:
    # 有 PyQt5 时用共享的隔离工具：测试数据不写进真实注册表 / plist，退出时自动清空
    from _settings_isolation import isolate_settings  # noqa: E402
    isolate_settings('YourOrgLogCheck', 'ClassManageSystemLogCheck')
    print("[INFO] 检测到 PyQt5：隐蔽备份使用真实 QSettings（隔离命名空间）")

TMP = os.path.join(_TMP_HOME, "app")
os.makedirs(TMP)
CFG = os.path.join(TMP, "config.ini")
LOG = log_store.log_path_for(CFG)
BAK = log_store.log_backup_path_for(CFG)
TAG = log_store._tag(CFG)

print("\n--- 1. 每次积分变动自动记录 ---")
store = ConfigStore(CFG)
check("初始日志为空", log_store.load(CFG).entries == [])
store.set_score(1, 3, reason="+3")
store.set_score(1, 1, reason="-2")
store.set_score(2, 0)                     # 值没变（本来就是 0）→ 不记
store.set_score(2, 5, reason="+3")
before = len(log_store.load(CFG).entries)
store.set_score(2, 5)                     # 再次赋同一个值 → 不记
check("值没变不产生记录", len(log_store.load(CFG).entries) == before == 3,
      f"实际 {before} → {len(log_store.load(CFG).entries)}")

# 撤销 / 清零此组（复刻界面的调用方式）
store.set_score(2, 5 - 3, reason="撤销 +3")
store.set_score(1, 0, reason="清零此组")
store.reset_scores(reason="全部清零")
store.set_group_count(3)
store.reset_all()
entries = log_store.load(CFG).entries
bodies = [b for _s, b in entries]
print("  记录到的日志：")
for stamp, body in entries:
    print(f"    [{stamp}] {body}")
check("撤销有记录", any("撤销" in b for b in bodies))
check("清零此组有记录", any("清零此组" in b for b in bodies))
check("全部清零有记录", any("全部清零" in b for b in bodies))
check("改组数有记录", any("修改小组数量" in b for b in bodies))
check("彻底重置有记录", any("彻底重置" in b for b in bodies))
check("加减分有记录", any("+3" in b for b in bodies) and any("-2" in b for b in bodies))

print("\n--- 2. 加密落盘，且没有明文副本 ---")
with open(LOG, "rb") as f:
    main_blob = f.read()
check("points_log.dat 存在", os.path.isfile(LOG))
check("是同目录 .bak", os.path.isfile(BAK))
try:
    main_blob.decode("utf-8")
    readable = True
except UnicodeDecodeError:
    readable = False
check("密文不是可读文本", not readable)
check("密文里没有明文痕迹",
      b"score" not in main_blob and b"group" not in main_blob and "第1组".encode() not in main_blob)
others = sorted(n for n in os.listdir(TMP) if "log" in n)
check("目录里只有 .dat 与 .dat.bak（无 .ini/.txt 明文）",
      others == ["points_log.dat", "points_log.dat.bak"], f"实际 {others}")

print("\n--- 3. 篡改任意字节 → 从 .bak 回档 ---")
keep = len(entries)
tampered = bytearray(main_blob)
tampered[len(tampered) // 2] ^= 0xFF
with open(LOG, "wb") as f:
    f.write(bytes(tampered))
view = log_store.load(CFG)
check("自动回档（条数不变）", len(view.entries) == keep, f"实际 {len(view.entries)}")
check("来源标记为 bak", view.source == "bak", f"实际 {view.source}")
check("主文件已修复", open(LOG, "rb").read() != bytes(tampered))
check("修复后来源回到 main", log_store.load(CFG).source == "main")

print("\n--- 4. 主文件 + .bak 同时坏掉 → 从隐蔽备份回档 ---")
with open(BAK, "rb") as f:
    bak_blob = bytearray(f.read())
bak_blob[-1] ^= 0x01
with open(BAK, "wb") as f:
    f.write(bytes(bak_blob))
tampered = bytearray(open(LOG, "rb").read())
tampered[0] ^= 0x80
with open(LOG, "wb") as f:
    f.write(bytes(tampered))
view = log_store.load(CFG)
check("从隐蔽备份回档", len(view.entries) == keep and view.source == "hidden",
      f"条数 {len(view.entries)} / 来源 {view.source}")
check("两文件被重建", os.path.isfile(LOG) and os.path.isfile(BAK))
check("重建后可正常读取", log_store.load(CFG).source == "main")

print("\n--- 5. 删除主文件 → 从 .bak 回档 ---")
os.remove(LOG)
view = log_store.load(CFG)
check("删除后仍能读到全部记录", len(view.entries) == keep, f"实际 {len(view.entries)}")
check("主文件被重建", os.path.isfile(LOG))

print("\n--- 6. 防回滚：用旧密文覆盖主文件 ---")
with open(LOG, "rb") as f:
    new_blob = f.read()                      # 当前最新（seq = 全部记录数）
store.set_score(1, 42, reason="+42")
store.save()
after_seq = log_store.load(CFG).seq
with open(LOG, "wb") as f:
    f.write(new_blob)                        # 学生拿旧副本盖回去
rolled = log_store.load(CFG)
check("旧密文覆盖后条目没被抹掉", len(rolled.entries) == after_seq,
      f"实际 {len(rolled.entries)} 条 / 期望 {after_seq} 条")
check("检测到回滚并用更新的副本修回", rolled.seq == after_seq,
      f"实际 {rolled.seq} / 期望 {after_seq}")

print("\n--- 7. 全部删除 → 空日志，不崩溃 ---")
os.remove(LOG)
os.remove(BAK)
if backup_store.QSettings is None:
    _fake.pop((log_store.HIDDEN_PREFIX, TAG), None)
else:
    backup_store._settings.remove(
        backup_store._key(TAG, log_store.HIDDEN_PREFIX))
    backup_store._settings.sync()
view = log_store.load(CFG)
check("三份都没了 → 空日志", view.entries == [] and view.source == "empty",
      f"实际 {view.source} / {len(view.entries)} 条")
store.set_score(1, 1, reason="+1")
check("之后还能继续记录", len(log_store.load(CFG).entries) == 1)

print("\n--- 8. 只增不减：彻底重置不清空 ---")
store.set_score(1, 9, reason="+9")
store.reset_all()
bodies = [b for _s, b in log_store.load(CFG).entries]
check("彻底重置后旧记录仍在", any("+9" in b for b in bodies), f"实际 {bodies}")
check("彻底重置留下标记", any("彻底重置" in b for b in bodies))

print("\n--- 9. JSON 坏掉 / 旧格式也要能兜住 ---")
if backup_store.QSettings is None:
    _fake.pop((log_store.HIDDEN_PREFIX, TAG), None)
else:
    backup_store._settings.remove(backup_store._key(TAG, log_store.HIDDEN_PREFIX))
    backup_store._settings.sync()
os.remove(BAK)
from namepicker import crypto_utils  # noqa: E402
with open(LOG, "wb") as f:
    f.write(crypto_utils.encrypt(b"this is not json"))
check("非法内容被当作损坏并回退到空日志", log_store.load(CFG).entries == [])
with open(LOG, "wb") as f:
    f.write(crypto_utils.encrypt(b'{"entries":[["2026-01-01 08:00:00","old"]]}'))
view = log_store.load(CFG)
check("缺 seq 的老格式仍可读，seq 退回条数",
      view.entries == [["2026-01-01 08:00:00", "old"]] and view.seq == 1,
      f"实际 {view.entries} seq={view.seq}")

print("\n" + "=" * 60)
if failures:
    print(f"失败 {len(failures)} 项：{failures}")
    shutil.rmtree(_TMP_HOME, ignore_errors=True)
    sys.exit(1)
print("全部通过")
shutil.rmtree(_TMP_HOME, ignore_errors=True)
