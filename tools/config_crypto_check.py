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
    print("[INFO] 未安装 PyQt5：隐蔽备份使用内存假实现")
else:
    # 有 PyQt5 时也把数据写进隔离的 org/app，避免污染真实备份槽位
    # 有 PyQt5 时用共享的隔离工具：测试数据不写进真实注册表 / plist，退出时自动清空
    from _settings_isolation import isolate_settings  # noqa: E402
    isolate_settings('YourOrgCryptoCheck', 'ClassManageSystemCheck')
    print("[INFO] 检测到 PyQt5：隐蔽备份使用真实 QSettings（隔离命名空间）")


def hidden_bytes(tag):
    return backup_store.load_backup(tag=tag)


def new_dir(name):
    path = os.path.join(_TMP_HOME, name)
    os.makedirs(path, exist_ok=True)
    return path


# ======================================================================
print("\n--- 1. 密钥文件 ---")
data = crypto_utils.encrypt(b"hello")
check("加密结果长度 = nonce(12) + 密文 + tag(16)", len(data) == 12 + 5 + 16,
      f"实际 {len(data)}")
check("解密还原", crypto_utils.decrypt(data) == b"hello")
check("往返：空明文也能解回", crypto_utils.decrypt(crypto_utils.encrypt(b"")) == b"")

key_stat = os.stat(crypto_utils.KEY_FILE)
check("密钥文件 32 字节", key_stat.st_size == 32, f"实际 {key_stat.st_size}")
if os.name == "posix":
    check("密钥权限 600",
          stat.S_IMODE(key_stat.st_mode) == 0o600,
          f"实际 {oct(stat.S_IMODE(key_stat.st_mode))}")
else:
    print("[SKIP] Windows 没有 POSIX 权限位，chmod 600 不是有效约束")

print("\n--- 2. 篡改一定解密失败 ---")
tampered = bytearray(data)
tampered[-1] ^= 0x01
try:
    crypto_utils.decrypt(bytes(tampered))
    check("改 tag 字节 → 抛异常", False)
except Exception as e:
    check("改 tag 字节 → 抛异常", True, type(e).__name__)
for label, blob in (("空文件", b""), ("截断到 5 字节", data[:5]),
                    ("只有 nonce", data[:12])):
    try:
        crypto_utils.decrypt(blob)
        check(f"{label} → 抛异常", False)
    except Exception as e:
        check(f"{label} → 抛异常", True, type(e).__name__)

# ======================================================================
print("\n--- 3. 首次运行：默认值 + 加密主文件 ---")
d1 = new_dir("d1")
ini1 = os.path.join(d1, "config.ini")
dat1 = os.path.join(d1, "config.dat")
bak1 = dat1 + ".bak"

store = ConfigStore(ini1)
check("默认 6 组", store.group_count == 6, f"实际 {store.group_count}")
check("默认全 0 分", store.all_scores() == [0] * 6, f"实际 {store.all_scores()}")
check("生成了 config.dat", os.path.isfile(dat1))
check("生成了 config.dat.bak", os.path.isfile(bak1))
check("生成了明文 config.ini", os.path.isfile(ini1))

with open(dat1, "rb") as f:
    raw = f.read()
check("config.dat 是二进制（不是可读文本）", is_binary(raw))
check("config.dat 里找不到明文段名", b"[points]" not in raw and b"score_1" not in raw)

with open(ini1, encoding="utf-8") as f:
    ini_text = f.read()
check("config.ini 是明文且带查看标记",
      config_store.VIEW_MARKER in ini_text and "[points]" in ini_text)
check("config.ini 里没有真实密钥/密文", "nonce" not in ini_text.lower())

# ======================================================================
print("\n--- 4. 分数持久化 ---")
store.set_score(1, 12)
store.set_score(3, -2)
store.set_group_name(2, "雄鹰组")
check("save() 成功", store.save())
again = ConfigStore(ini1)
check("重新加载分数一致", again.all_scores() == [12, 0, -2, 0, 0, 0],
      f"实际 {again.all_scores()}")
check("重新加载组名一致", again.get_group_name(2) == "雄鹰组")

print("\n--- 5. 明文 config.ini 改了也没用（程序永不读）---")
with open(ini1, "r", encoding="utf-8") as f:
    text = f.read()
with open(ini1, "w", encoding="utf-8") as f:
    f.write(text.replace("score_1 = 12", "score_1 = 9999"))
after_edit = ConfigStore(ini1)
check("手改 config.ini 后分数不变", after_edit.get_score(1) == 12,
      f"实际 {after_edit.get_score(1)}")

# ======================================================================
print("\n--- 6. 篡改 config.dat → 从 .bak 回档 ---")
with open(dat1, "rb") as f:
    blob = bytearray(f.read())
blob[len(blob) // 2] ^= 0xFF
with open(dat1, "wb") as f:
    f.write(bytes(blob))
recovered = ConfigStore(ini1)
check("从 .bak 恢复了分数", recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"实际 {recovered.all_scores()}")
with open(dat1, "rb") as f:
    repaired = f.read()
check("主文件已被修复（不再是篡改内容）", bytes(blob) != repaired)
check("修复后能再次正常加载",
      ConfigStore(ini1).all_scores() == [12, 0, -2, 0, 0, 0])

print("\n--- 7. 清空 config.dat（0 字节）→ 从 .bak 回档 ---")
with open(dat1, "wb"):
    pass
recovered = ConfigStore(ini1)
check("空文件也能回档", recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"实际 {recovered.all_scores()}")

print("\n--- 8. 删除 config.dat → 从 .bak 回档 ---")
os.remove(dat1)
check("只剩 .bak 也能回档", ConfigStore(ini1).all_scores() == [12, 0, -2, 0, 0, 0])
check("config.dat 被重建", os.path.isfile(dat1))

print("\n--- 8b. 同时改坏 config.dat 与 .bak → 从隐蔽备份回档 ---")
for bad in (dat1, bak1):
    with open(bad, "rb") as f:
        raw = bytearray(f.read())
    raw[-2] ^= 0x5A
    with open(bad, "wb") as f:
        f.write(bytes(raw))
recovered = ConfigStore(ini1)
check("两个文件都被改坏 → 隐蔽备份回档",
      recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"实际 {recovered.all_scores()}")

print("\n--- 8c. 删除 config.dat + .bak → 从隐蔽备份回档 ---")
os.remove(dat1)
os.remove(bak1)
check("隐蔽备份里确实有数据", hidden_bytes(d1) is not None)
recovered = ConfigStore(ini1)
check("从隐蔽备份恢复了分数", recovered.all_scores() == [12, 0, -2, 0, 0, 0],
      f"实际 {recovered.all_scores()}")
check("两个文件被重建", os.path.isfile(dat1) and os.path.isfile(bak1))

print("\n--- 9. 全部删除 → 默认值，不崩溃 ---")
os.remove(dat1)
os.remove(bak1)
if backup_store.QSettings is None:
    backup_store._fake.pop(d1, None)
else:
    # 注意：删的是 backup_store 的分桶键，不是目录 tag 本身
    backup_store._settings.remove(backup_store._key(config_store._backup_tag(ini1)))
    backup_store._settings.sync()
check("隐蔽备份已清空", hidden_bytes(d1) is None)
fresh = ConfigStore(ini1)
check("回到默认值", fresh.all_scores() == [0] * 6, f"实际 {fresh.all_scores()}")
check("重建了 config.dat", os.path.isfile(dat1))

# ======================================================================
print("\n--- 10. 旧版明文迁移（一次性）---")
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
check("迁移函数报告成功", config_store.migrate_legacy_plaintext(ini2))
check("生成了加密主文件", os.path.isfile(dat2))
migrated = ConfigStore(ini2)
check("旧分数被保留", migrated.get_score(1) == 42, f"实际 {migrated.get_score(1)}")
check("明文副本被标记为只读副本",
      open(ini2, encoding="utf-8").read().startswith(config_store.VIEW_MARKER))

print("\n--- 11. 查看副本不会被当成数据源 ---")
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
check("不会把查看副本读回来（回到默认值）", rebuilt.get_score(1) == 0,
      f"实际 {rebuilt.get_score(1)}")

# ======================================================================
print("\n--- 12. 原子写入：不留 .tmp 残留 ---")
leftovers = [n for n in os.listdir(d1) if n.endswith(".tmp")]
check("目录里没有 .tmp 残留", leftovers == [], f"实际 {leftovers}")

print("\n--- 12b. 写盘失败时不破坏旧数据（原子替换）---")
d_ro = new_dir("ro")
ini_ro = os.path.join(d_ro, "config.ini")
dat_ro = os.path.join(d_ro, "config.dat")
s_ro = ConfigStore(ini_ro)
s_ro.set_score(1, 5)
check("先正常保存一次", s_ro.save())
if os.name == "nt":
    print("[SKIP] Windows 下 chmod 不能让目录只读，跳过写失败用例")
else:
    with open(dat_ro, "rb") as f:
        before_bytes = f.read()
    os.chmod(d_ro, 0o500)  # 目录只读：无法创建 .tmp
    try:
        s_ro.set_score(1, 999)
        check("只读目录下 save() 返回 False", s_ro.save() is False)
        check("last_error() 给出原因", bool(s_ro.last_error()), s_ro.last_error()[:60])
        with open(dat_ro, "rb") as f:
            after_bytes = f.read()
        check("旧 config.dat 原封不动", before_bytes == after_bytes)
        check("重新加载仍是旧分数", ConfigStore(ini_ro).get_score(1) == 5)
    finally:
        os.chmod(d_ro, 0o700)

print("\n--- 12c. 密钥文件写不进去时：不崩、可排查 ---")
_orig_key_file = crypto_utils.KEY_FILE
try:
    # 把密钥路径指向一个目录：读写都必然失败，与文件权限无关
    crypto_utils.KEY_FILE = d_ro
    crypto_utils.reset_cipher_cache()
    blob = crypto_utils.encrypt(b"still works")
    check("临时密钥下加解密仍可用", crypto_utils.decrypt(blob) == b"still works")
    check("能查到密钥未落盘的原因",
          (not crypto_utils.key_persisted()) and bool(crypto_utils.key_error()),
          crypto_utils.key_error()[:70])
    d_key = new_dir("dkey")
    s_key = ConfigStore(os.path.join(d_key, "config.ini"))
    s_key.set_score(1, 3)
    check("此时保存仍然成功（不崩）", s_key.save())
    check("last_error() 带出密钥警告", bool(s_key.last_error()),
          s_key.last_error()[:70])
finally:
    crypto_utils.KEY_FILE = _orig_key_file
    crypto_utils.reset_cipher_cache()
crypto_utils.encrypt(b"probe")  # 触发重新读密钥
check("恢复后密钥可正常落盘", crypto_utils.key_persisted(),
      crypto_utils.key_error()[:70])

print("\n--- 13. 真实 QSettings 隐蔽备份（仅装了 PyQt5 时）---")
if backup_store.QSettings is None:
    print("[SKIP] 未安装 PyQt5")
else:
    d3 = new_dir("d3")
    ini3 = os.path.join(d3, "config.ini")
    s3 = ConfigStore(ini3)
    s3.set_score(5, 7)
    s3.save()
    tag3 = config_store._backup_tag(ini3)
    fn = backup_store._get_settings().fileName()
    check("QSettings 有落盘文件名", bool(fn), fn)
    check("隐蔽备份可读回", hidden_bytes(d3) is not None)
    os.remove(os.path.join(d3, "config.dat"))
    os.remove(os.path.join(d3, "config.dat.bak"))
    check("删掉两个文件后仍能回档", ConfigStore(ini3).get_score(5) == 7)

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
    print(f"失败 {len(failures)} 项：{failures}")
    shutil.rmtree(_TMP_HOME, ignore_errors=True)
    sys.exit(1)
print("全部通过")
shutil.rmtree(_TMP_HOME, ignore_errors=True)
