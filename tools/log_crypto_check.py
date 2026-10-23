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

from namepicker import backup_store, i18n, log_store  # noqa: E402
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
    print("[INFO] PyQt5 is not installed: hidden backup uses an in-memory fake")
else:
    # 有 PyQt5 时用共享的隔离工具：测试数据不写进真实注册表 / plist，退出时自动清空
    from _settings_isolation import isolate_settings  # noqa: E402
    isolate_settings('YourOrgLogCheck', 'ClassManageSystemLogCheck')
    print("[INFO] PyQt5 detected: hidden backup uses real QSettings (isolated namespace)")

TMP = os.path.join(_TMP_HOME, "app")
os.makedirs(TMP)
CFG = os.path.join(TMP, "config.ini")
LOG = log_store.log_path_for(CFG)
BAK = log_store.log_backup_path_for(CFG)
TAG = log_store._tag(CFG)

print("\n--- 1. Every score change is logged automatically ---")
store = ConfigStore(CFG)
check("log starts empty", log_store.load(CFG).entries == [])
store.set_score(1, 3, reason="+3")
store.set_score(1, 1, reason="-2")
store.set_score(2, 0)                     # 值没变（本来就是 0）→ 不记
store.set_score(2, 5, reason="+3")
before = len(log_store.load(CFG).entries)
store.set_score(2, 5)                     # 再次赋同一个值 → 不记
check("unchanged value produces no entry", len(log_store.load(CFG).entries) == before == 3,
      f"actual {before} -> {len(log_store.load(CFG).entries)}")

# 撤销 / 清零此组（复刻界面的调用方式）
store.set_score(2, 5 - 3, reason=i18n.both("撤销 +3", "undo +3"))
store.set_score(1, 0, reason=i18n.both("清零此组", "clear group"))
store.reset_scores(reason=i18n.both("全部清零", "clear all"))
store.set_group_count(3)
store.reset_all()
entries = log_store.load(CFG).entries
bodies = [zh for _s, zh, _en in entries]
bodies_en = [en for _s, _zh, en in entries]
print("  logged entries:")
for stamp, zh, en in entries:
    print(f"    [{stamp}] {zh}")
    if en and en != zh:
        print(f"               {en}")
check("undo is logged", any("撤销" in b for b in bodies) and any("undo" in b for b in bodies_en))
check("clear-group is logged", any("清零此组" in b for b in bodies))
check("clear-all is logged", any("全部清零" in b for b in bodies))
check("group count change is logged", any("修改小组数量" in b for b in bodies))
check("full reset is logged", any("彻底重置" in b for b in bodies))
check("add/subtract points are logged", any("+3" in b for b in bodies) and any("-2" in b for b in bodies))
check("log entries are bilingual (English side present)", any(b for b in bodies_en), f"actual {bodies_en[:2]}")

print("\n--- 2. Encrypted at rest, no plaintext copy ---")
with open(LOG, "rb") as f:
    main_blob = f.read()
check("points_log.dat exists", os.path.isfile(LOG))
check(".bak sits in the same directory", os.path.isfile(BAK))
try:
    main_blob.decode("utf-8")
    readable = True
except UnicodeDecodeError:
    readable = False
check("ciphertext is not readable text", not readable)
check("no plaintext traces in the ciphertext",
      b"score" not in main_blob and b"group" not in main_blob and "第1组".encode() not in main_blob)
others = sorted(n for n in os.listdir(TMP) if "log" in n)
check("directory holds only .dat and .dat.bak (no plaintext .ini/.txt)",
      others == ["points_log.dat", "points_log.dat.bak"], f"actual {others}")

print("\n--- 3. Tamper any byte -> restore from .bak ---")
keep = len(entries)
tampered = bytearray(main_blob)
tampered[len(tampered) // 2] ^= 0xFF
with open(LOG, "wb") as f:
    f.write(bytes(tampered))
view = log_store.load(CFG)
check("auto-restores (entry count unchanged)", len(view.entries) == keep, f"actual {len(view.entries)}")
check("source marked as bak", view.source == "bak", f"actual {view.source}")
check("main file repaired", open(LOG, "rb").read() != bytes(tampered))
check("source back to main after repair", log_store.load(CFG).source == "main")

print("\n--- 4. Main file + .bak both corrupt -> restore from hidden backup ---")
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
check("restores from hidden backup", len(view.entries) == keep and view.source == "hidden",
      f"entries {len(view.entries)} / source {view.source}")
check("both files recreated", os.path.isfile(LOG) and os.path.isfile(BAK))
check("loads normally after repair", log_store.load(CFG).source == "main")

print("\n--- 5. Delete main file -> restore from .bak ---")
os.remove(LOG)
view = log_store.load(CFG)
check("all entries still readable after deletion", len(view.entries) == keep, f"actual {len(view.entries)}")
check("main file recreated", os.path.isfile(LOG))

print("\n--- 6. Rollback protection: overwrite main file with old ciphertext ---")
with open(LOG, "rb") as f:
    new_blob = f.read()                      # 当前最新（seq = 全部记录数）
store.set_score(1, 42, reason="+42")
store.save()
after_seq = log_store.load(CFG).seq
with open(LOG, "wb") as f:
    f.write(new_blob)                        # 学生拿旧副本盖回去
rolled = log_store.load(CFG)
check("entries not wiped after overwriting with old ciphertext", len(rolled.entries) == after_seq,
      f"actual {len(rolled.entries)} entries / expected {after_seq} entries")
check("rollback detected and repaired from the newer copy", rolled.seq == after_seq,
      f"actual {rolled.seq} / expected {after_seq}")

print("\n--- 7. Delete everything -> empty log, no crash ---")
os.remove(LOG)
os.remove(BAK)
if backup_store.QSettings is None:
    _fake.pop((log_store.HIDDEN_PREFIX, TAG), None)
else:
    backup_store._settings.remove(
        backup_store._key(TAG, log_store.HIDDEN_PREFIX))
    backup_store._settings.sync()
view = log_store.load(CFG)
check("all three copies gone -> empty log", view.entries == [] and view.source == "empty",
      f"actual {view.source} / {len(view.entries)} entries")
store.set_score(1, 1, reason="+1")
check("logging still works afterwards", len(log_store.load(CFG).entries) == 1)

print("\n--- 8. Append-only: full reset does not clear the log ---")
store.set_score(1, 9, reason="+9")
store.reset_all()
bodies = [zh for _s, zh, _en in log_store.load(CFG).entries]
check("old entries survive a full reset", any("+9" in b for b in bodies), f"actual {bodies}")
check("full reset leaves a marker", any("彻底重置" in b for b in bodies))

print("\n--- 9. Corrupt JSON / legacy format must still be handled ---")
if backup_store.QSettings is None:
    _fake.pop((log_store.HIDDEN_PREFIX, TAG), None)
else:
    backup_store._settings.remove(backup_store._key(TAG, log_store.HIDDEN_PREFIX))
    backup_store._settings.sync()
os.remove(BAK)
from namepicker import crypto_utils  # noqa: E402
with open(LOG, "wb") as f:
    f.write(crypto_utils.encrypt(b"this is not json"))
check("invalid content treated as corruption, falls back to an empty log", log_store.load(CFG).entries == [])
with open(LOG, "wb") as f:
    f.write(crypto_utils.encrypt(b'{"entries":[["2026-01-01 08:00:00","old"]]}'))
view = log_store.load(CFG)
check("legacy format without seq is still readable; seq falls back to entry count",
      view.entries == [["2026-01-01 08:00:00", "old", ""]] and view.seq == 1,
      f"actual {view.entries} seq={view.seq}")

print("\n" + "=" * 60)
if failures:
    print(f"failed {len(failures)}: {failures}")
    shutil.rmtree(_TMP_HOME, ignore_errors=True)
    sys.exit(1)
print("ALL PASSED")
shutil.rmtree(_TMP_HOME, ignore_errors=True)
