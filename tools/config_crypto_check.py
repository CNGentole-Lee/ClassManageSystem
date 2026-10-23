"""加密配置存储自检 —— 覆盖「积分防篡改」的验收标准。

用法:
    python tools/config_crypto_check.py

检查项（对应任务验收标准）：
    1. config.dat 是加密二进制，用文本打开是乱码；
    2. config.ini 仍是明文，但手工修改后程序里的分数不变（程序永不读它）；
    3. 篡改 config.dat 任意字节 → 自动从 config.dat.bak 回档并修复；
    4. 删除 config.dat + config.dat.bak → 从 QSettings 隐蔽备份回档；
    5. 全部删除 → 用默认值初始化，不崩溃；
    6. 旧版明文 config.ini → 一次性迁移成加密存储；
    7. 密钥文件 ~/.classmanage_key 为 32 字节、权限 600；
    8. 原子写入：落盘后不留 .tmp 残留文件。

脚本会在临时 HOME 里运行（不碰真实的 ~/.classmanage_key 和真实备份），
没有装 PyQt5 时隐蔽备份退化成内存假实现，仍然覆盖回档链路。
"""

import os
import shutil
import stat
import sys
import tempfile

# --- 隔离：在临时 HOME 下运行，避免动到真实密钥/真实备份 ---
_TMP_HOME = tempfile.mkdtemp(prefix="cm_crypto_home_")
os.environ["HOME"] = _TMP_HOME            # macOS / Linux
os.environ["USERPROFILE"] = _TMP_HOME     # Windows（expanduser 走这里）
os.environ.pop("APPDATA", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from namepicker import backup_store, config_store, crypto_utils  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402

failures = []


def check(label, condition, detail=""):
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def is_binary(raw: bytes) -> bool:
    """粗判二进制：不能按 UTF-8 解码即视为乱码。"""
    try:
        raw.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


# --- 隐蔽备份：没有 PyQt5 时用内存假实现，链路照样能测 ---
if backup_store.QSettings is None:
    _fake_store = {}

    def _fake_save(blob, tag=""):
        _fake_store[tag] = blob
        return True

    def _fake_load(tag=""):
        return _fake_store.get(tag)

    backup_store.save_backup = _fake_save
    backup_store.load_backup = _fake_load
    backup_store._fake = _fake_store
    print("[INFO] PyQt5 is not installed: hidden backup uses an in-memory fake")
else:
    # 有 PyQt5 时也把数据写进隔离的 org/app，避免污染真实备份槽位
    # 有 PyQt5 时用共享的隔离工具：测试数据不写进真实注册表 / plist，退出时自动清空
    from _settings_isolation import isolate_settings  # noqa: E402
    isolate_settings('YourOrgCryptoCheck', 'ClassManageSystemCheck')
    print("[INFO] PyQt5 detected: hidden backup uses real QSettings (isolated namespace)")


def hidden_bytes(tag):
    return backup_store.load_backup(tag=tag)


def new_dir(name):
    path = os.path.join(_TMP_HOME, name)
    os.makedirs(path, exist_ok=True)
    return path


# ======================================================================
print("\n--- 1. Key file ---")
data = crypto_utils.encrypt(b"hello")
check("encrypted length = nonce(12) + ciphertext + tag(16)", len(data) == 12 + 5 + 16,
      f"actual {len(data)}")
check("decrypts back", crypto_utils.decrypt(data) == b"hello")
check("round-trip: empty plaintext also decrypts back", crypto_utils.decrypt(crypto_utils.encrypt(b"")) == b"")

key_stat = os.stat(crypto_utils.KEY_FILE)
check("key file is 32 bytes", key_stat.st_size == 32, f"actual {key_stat.st_size}")
if os.name == "posix":
    check("key permissions are 600",
          stat.S_IMODE(key_stat.st_mode) == 0o600,
          f"actual {oct(stat.S_IMODE(key_stat.st_mode))}")
else:
    print("[SKIP] Windows has no POSIX permission bits; chmod 600 is not a valid constraint")

print("\n--- 2. Tampering always fails decryption ---")
tampered = bytearray(data)
tampered[-1] ^= 0x01
try:
    crypto_utils.decrypt(bytes(tampered))
    check("flipping a tag byte raises an exception", False)
except Exception as e:
    check("flipping a tag byte raises an exception", True, type(e).__name__)
for label, blob in (("empty file", b""), ("truncated to 5 bytes", data[:5]),
                    ("nonce only", data[:12])):
    try:
        crypto_utils.decrypt(blob)
        check(f"{label} raises an exception", False)
    except Exception as e:
        check(f"{label} raises an exception", True, type(e).__name__)

# ======================================================================
print("\n--- 3. First run: defaults + encrypted main file ---")
d1 = new_dir("d1")
ini1 = os.path.join(d1, "config.ini")
dat1 = os.path.join(d1, "config.dat")
bak1 = dat1 + ".bak"

store = ConfigStore(ini1)
check("6 groups by default", store.group_count == 6, f"actual {store.group_count}")
check("all scores 0 by default", store.all_scores() == [0] * 6, f"actual {store.all_scores()}")
check("config.dat created", os.path.isfile(dat1))
check("config.dat.bak created", os.path.isfile(bak1))
check("plaintext config.ini created", os.path.isfile(ini1))

with open(dat1, "rb") as f:
    raw = f.read()
check("config.dat is binary (not readable text)", is_binary(raw))
check("no plaintext section names inside config.dat", b"[points]" not in raw and b"score_1" not in raw)

with open(ini1, encoding="utf-8") as f:
    ini_text = f.read()
check("config.ini is plaintext and carries the view marker",
      config_store.VIEW_MARKER in ini_text and "[points]" in ini_text)
check("no real key/ciphertext in config.ini", "nonce" not in ini_text.lower())

# ======================================================================
print("\n--- 4. Score persistence ---")
store.set_score(1, 12)
store.set_score(3, -2)
store.set_group_name(2, "雄鹰组")
check("save() succeeds", store.save())
again = ConfigStore(ini1)
check("reloaded scores match", again.all_scores() == [12, 0, -2, 0, 0, 0],
      f"actual {again.all_scores()}")
check("reloaded group name matches", again.get_group_name(2) == "雄鹰组")

print("\n--- 5. Editing plaintext config.ini has no effect (never read) ---")
with open(ini1, "r", encoding="utf-8") as f:
    text = f.read()
with open(ini1, "w", encoding="utf-8") as f:
    f.write(text.replace("score_1 = 12", "score_1 = 9999"))
after_edit = ConfigStore(ini1)
check("score unchanged after hand-editing config.ini", after_edit.get_score(1) == 12,
      f"actual {after_edit.get_score(1)}")

# ======================================================================
print("\n--- 6. Corrupt config.dat -> restore from .bak ---")
with open(dat1, "rb") as f:
    blob = bytearray(f.read())
blob[len(blob) // 2] ^= 0xFF
with open(dat1, "wb") as f:
    f.write(bytes(blob))
recovered = ConfigStore(ini1)
check("scores recovered from .bak", recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"actual {recovered.all_scores()}")
with open(dat1, "rb") as f:
    repaired = f.read()
check("main file repaired (tampered content is gone)", bytes(blob) != repaired)
check("loads normally again after repair",
      ConfigStore(ini1).all_scores() == [12, 0, -2, 0, 0, 0])

print("\n--- 7. Empty config.dat (0 bytes) -> restore from .bak ---")
with open(dat1, "wb"):
    pass
recovered = ConfigStore(ini1)
check("empty file also restores", recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"actual {recovered.all_scores()}")

print("\n--- 8. Delete config.dat -> restore from .bak ---")
os.remove(dat1)
check("restores from .bak alone", ConfigStore(ini1).all_scores() == [12, 0, -2, 0, 0, 0])
check("config.dat recreated", os.path.isfile(dat1))

print("\n--- 8b. Corrupt both config.dat and .bak -> restore from hidden backup ---")
for bad in (dat1, bak1):
    with open(bad, "rb") as f:
        raw = bytearray(f.read())
    raw[-2] ^= 0x5A
    with open(bad, "wb") as f:
        f.write(bytes(raw))
recovered = ConfigStore(ini1)
check("both files corrupted -> hidden backup restores",
      recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"actual {recovered.all_scores()}")

print("\n--- 8c. Delete config.dat + .bak -> restore from hidden backup ---")
os.remove(dat1)
os.remove(bak1)
check("hidden backup really holds data", hidden_bytes(d1) is not None)
recovered = ConfigStore(ini1)
check("scores recovered from hidden backup", recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"actual {recovered.all_scores()}")
check("both files recreated", os.path.isfile(dat1) and os.path.isfile(bak1))

print("\n--- 9. Delete everything -> defaults, no crash ---")
os.remove(dat1)
os.remove(bak1)
if backup_store.QSettings is None:
    backup_store._fake.pop(d1, None)
else:
    # 注意：删的是 backup_store 的分桶键，不是目录 tag 本身
    backup_store._settings.remove(backup_store._key(config_store._backup_tag(ini1)))
    backup_store._settings.sync()
check("hidden backup is cleared", hidden_bytes(d1) is None)
fresh = ConfigStore(ini1)
check("falls back to defaults", fresh.all_scores() == [0] * 6, f"actual {fresh.all_scores()}")
check("config.dat recreated", os.path.isfile(dat1))

# ======================================================================
print("\n--- 10. Legacy plaintext migration (one time) ---")
d2 = new_dir("d2")
ini2 = os.path.join(d2, "config.ini")
dat2 = os.path.join(d2, "config.dat")
legacy = (
    "[meta]\napp = 班级多用教学辅助终端\nupdated = 2026-09-27 10:30:00\n\n"
    "[points]\ngroup_count = 6\ngroup_1 = 第一组\nscore_1 = 42\n"
    + "".join(f"group_{i} = 第{i}组\nscore_{i} = 1\n" for i in range(2, 7))
)
with open(ini2, "w", encoding="utf-8") as f:
    f.write(legacy)
check("migration function reports success", config_store.migrate_legacy_plaintext(ini2))
check("encrypted main file created", os.path.isfile(dat2))
migrated = ConfigStore(ini2)
check("old scores preserved", migrated.get_score(1) == 42, f"actual {migrated.get_score(1)}")
check("plaintext copy marked as view-only",
      open(ini2, encoding="utf-8").read().startswith(config_store.VIEW_MARKER))

print("\n--- 11. View copy is never used as a data source ---")
os.remove(dat2)
os.remove(dat2 + ".bak")
if backup_store.QSettings is None:
    backup_store._fake.pop(d2, None)
else:
    backup_store._settings.remove(backup_store._key(config_store._backup_tag(ini2)))
    backup_store._settings.sync()
with open(ini2, "a", encoding="utf-8") as f:
    f.write("\n# 学生偷偷加的一行\n")
rebuilt = ConfigStore(ini2)
check("view copy is not read back (falls back to defaults)", rebuilt.get_score(1) == 0,
      f"actual {rebuilt.get_score(1)}")

# ======================================================================
print("\n--- 12. Atomic writes: no leftover .tmp files ---")
leftovers = [n for n in os.listdir(d1) if n.endswith(".tmp")]
check("no .tmp leftovers in the directory", leftovers == [], f"actual {leftovers}")

print("\n--- 12b. Failed write does not damage old data (atomic replace) ---")
d_ro = new_dir("ro")
ini_ro = os.path.join(d_ro, "config.ini")
dat_ro = os.path.join(d_ro, "config.dat")
s_ro = ConfigStore(ini_ro)
s_ro.set_score(1, 5)
check("save once normally first", s_ro.save())
if os.name == "nt":
    print("[SKIP] chmod cannot make a directory read-only on Windows; skipping the write-failure case")
else:
    with open(dat_ro, "rb") as f:
        before_bytes = f.read()
    os.chmod(d_ro, 0o500)  # 目录只读：无法创建 .tmp
    try:
        s_ro.set_score(1, 999)
        check("save() returns False in a read-only directory", s_ro.save() is False)
        check("last_error() explains why", bool(s_ro.last_error()), s_ro.last_error()[:60])
        with open(dat_ro, "rb") as f:
            after_bytes = f.read()
        check("old config.dat untouched", before_bytes == after_bytes)
        check("reload still shows old scores", ConfigStore(ini_ro).get_score(1) == 5)
    finally:
        os.chmod(d_ro, 0o700)

print("\n--- 12c. Unwritable key file: no crash, still diagnosable ---")
_orig_key_file = crypto_utils.KEY_FILE
try:
    # 把密钥路径指向一个目录：读写都必然失败，与文件权限无关
    crypto_utils.KEY_FILE = d_ro
    crypto_utils.reset_cipher_cache()
    blob = crypto_utils.encrypt(b"still works")
    check("encrypt/decrypt still works with a temporary key", crypto_utils.decrypt(blob) == b"still works")
    check("key persistence failure is diagnosable",
          (not crypto_utils.key_persisted()) and bool(crypto_utils.key_error()),
          crypto_utils.key_error()[:70])
    d_key = new_dir("dkey")
    s_key = ConfigStore(os.path.join(d_key, "config.ini"))
    s_key.set_score(1, 3)
    check("saving still succeeds (no crash)", s_key.save())
    check("last_error() surfaces the key warning", bool(s_key.last_error()),
          s_key.last_error()[:70])
finally:
    crypto_utils.KEY_FILE = _orig_key_file
    crypto_utils.reset_cipher_cache()
crypto_utils.encrypt(b"probe")  # 触发重新读密钥
check("key persists normally after recovery", crypto_utils.key_persisted(),
      crypto_utils.key_error()[:70])

print("\n--- 13. Real QSettings hidden backup (only with PyQt5) ---")
if backup_store.QSettings is None:
    print("[SKIP] PyQt5 is not installed")
else:
    d3 = new_dir("d3")
    ini3 = os.path.join(d3, "config.ini")
    s3 = ConfigStore(ini3)
    s3.set_score(5, 7)
    s3.save()
    tag3 = config_store._backup_tag(ini3)
    fn = backup_store._get_settings().fileName()
    check("QSettings has an on-disk file name", bool(fn), fn)
    check("hidden backup can be read back", hidden_bytes(d3) is not None)
    os.remove(os.path.join(d3, "config.dat"))
    os.remove(os.path.join(d3, "config.dat.bak"))
    check("still restores after deleting both files", ConfigStore(ini3).get_score(5) == 7)

    # 清理隔离命名空间，别在系统里留下测试数据
    try:
        settings = backup_store._get_settings()
        settings.clear()
        settings.sync()
        if fn and os.path.isfile(fn):
            os.remove(fn)
    except Exception:
        pass

print("\n" + "=" * 60)
if failures:
    print(f"failed {len(failures)}: {failures}")
    shutil.rmtree(_TMP_HOME, ignore_errors=True)
    sys.exit(1)
print("ALL PASSED")
shutil.rmtree(_TMP_HOME, ignore_errors=True)
