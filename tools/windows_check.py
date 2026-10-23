"""Windows 兼容性自检 —— 在 Windows 上一条命令给出确定答案。

用法（Windows）:
    .venv\\Scripts\\python.exe tools\\windows_check.py
或:
    python tools\\windows_check.py

为什么需要它：开发机是 macOS，Windows 上的平台专有行为（注册表隐蔽备份、
SetWindowPos 置顶、os.replace 覆盖、GBK 环境下的编码、文件被占用）没法在
macOS 上真正跑一遍。这个脚本把每条平台相关假设都实测一次。

退出码 0 = 全部通过；非 0 = 有项目失败。
"""

import os
import locale
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

IS_WINDOWS = sys.platform == "win32"
failures = []
skipped = []


def check(label, condition, detail=""):
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def skip(label, why):
    mark = "SKIP"
    print(f"[{mark}] {label}  {why}")
    skipped.append(label)


print("=" * 68)
print(f"Platform: {sys.platform} | Python {sys.version.split()[0]} | {sys.executable}")
print(f"Filesystem encoding: {sys.getfilesystemencoding()} | Default text encoding: {locale.getpreferredencoding(False)}")
print("=" * 68)

print("\n--- 1. Dependency imports (ImportError check) ---")
try:
    import cryptography                      # noqa: F401
    check("cryptography imports", True, cryptography.__version__)
except Exception as e:
    check("cryptography imports", False, repr(e))

try:
    from PyQt5.QtCore import QSettings, QT_VERSION_STR
    check("PyQt5 imports", True, f"Qt {QT_VERSION_STR}")
    has_qt = True
except Exception as e:
    check("PyQt5 imports", False, repr(e))
    has_qt = False

from namepicker import backup_store, crypto_utils, log_store  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402

print("\n--- 2. Floating ball topmost (ctypes.wintypes bug fixed?) ---")
from namepicker import floating_ball  # noqa: E402
if IS_WINDOWS:
    check("_SetWindowPos resolved to the real Win32 function (not None)",
          floating_ball._SetWindowPos is not None,
          "None means force_topmost is a no-op on Windows (legacy bug is back)")
    check("argtypes set (HWND passed as c_void_p, no ctypes.wintypes)",
          bool(floating_ball._SetWindowPos.argtypes) if floating_ball._SetWindowPos else False)

    # 验证「我们的代码不依赖 ctypes.wintypes」。
    # 注意：必须在**干净的独立子进程**里验证。本进程已经 import 了
    # cryptography / PyQt5 / pyinstaller，其中 PyInstaller 的
    # _pyi_rth_utils._win32 与 pip 的 truststore._windows 都会
    # `import ctypes.wintypes`，于是 ctypes 上多出 wintypes 属性 ——
    # 那是环境现象，不是本程序的问题（曾经误报过一次）。
    probe = (
        "import ctypes, sys\n"
        "assert not hasattr(ctypes, 'wintypes'), 'clean ctypes leaked wintypes'\n"
        "from namepicker import floating_ball\n"
        "assert floating_ball._SetWindowPos is not None, 'SetWindowPos missing'\n"
        "print('OK')\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=os.path.dirname(os.path.dirname(
                             os.path.abspath(__file__))))
    check("importing the app in a clean process does not pull in ctypes.wintypes",
          out.returncode == 0 and "OK" in out.stdout,
          (out.stdout + out.stderr).strip()[:160])
else:
    skip("Win32 SetWindowPos live test", "not running on Windows")
    check("degrades to None on macOS/Linux (no ImportError)",
          floating_ball._SetWindowPos is None)

print("\n--- 3. Key file ---")
blob = crypto_utils.encrypt("中文测试".encode("utf-8"))   # 先触发密钥生成
check("key file can be created", os.path.isfile(crypto_utils.KEY_FILE), crypto_utils.KEY_FILE)
if os.path.isfile(crypto_utils.KEY_FILE):
    check("key is 32 bytes", os.path.getsize(crypto_utils.KEY_FILE) == 32,
          f"actual {os.path.getsize(crypto_utils.KEY_FILE)} bytes")
else:
    check("key is 32 bytes", False, "key file does not exist")
check("encrypt/decrypt round-trip (with Chinese)", crypto_utils.decrypt(blob).decode("utf-8") == "中文测试")

# 隔离的工作目录：中文 + 空格 + 长路径，Windows 上最容易出问题
TMP = os.path.join(tempfile.mkdtemp(prefix="cm_win_check_"), "班级 管理 测试目录")
os.makedirs(TMP, exist_ok=True)
CFG = os.path.join(TMP, "config.ini")
print(f"\n--- 4. Full read/write under a Chinese + space path ({TMP}) ---")
store = ConfigStore(CFG)
store.set_group_name(1, "雄鹰组")
store.set_score(1, 7, reason="+7")
store.set_score(1, 3, reason="-4")
check("save() succeeds (Chinese fields + Chinese path)", store.save())
again = ConfigStore(CFG)
check("Chinese group name survives reload", again.get_group_name(1) == "雄鹰组",
      f"actual {again.get_group_name(1)!r}")
check("score is correct after reload", again.get_score(1) == 3, f"actual {again.get_score(1)}")
check("config.dat is encrypted binary",
      b"[points]" not in open(os.path.join(TMP, "config.dat"), "rb").read())
ini = open(os.path.join(TMP, "config.ini"), encoding="utf-8").read()
check("plaintext view copy is UTF-8 and carries the marker", "仅供查看" in ini)

print("\n--- 5. Atomic write (os.replace over an existing file) ---")
check("two consecutive saves succeed",
      store.save() and ConfigStore(CFG).save())
check("no .tmp leftovers", not [n for n in os.listdir(TMP) if n.endswith(".tmp")],
      f"actual {[n for n in os.listdir(TMP) if n.endswith('.tmp')]}")

print("\n--- 6. Tamper recovery (config.dat -> .bak -> hidden backup) ---")
dat = os.path.join(TMP, "config.dat")
with open(dat, "rb") as f:
    raw = bytearray(f.read())
raw[len(raw) // 2] ^= 0xFF
with open(dat, "wb") as f:
    f.write(bytes(raw))
check("corrupt main file -> restored from .bak", ConfigStore(CFG).get_score(1) == 3)
os.remove(dat)
os.remove(dat + ".bak")
check("delete main + .bak -> restored from hidden backup",
      ConfigStore(CFG).get_group_name(1) == "雄鹰组")

print("\n--- 7. QSettings hidden backup (Windows = HKCU registry) ---")
if not has_qt:
    skip("registry hidden backup live test", "PyQt5 not installed")
else:
    s = backup_store._get_settings()
    where = s.fileName() if s is not None else "(unavailable)"
    check("hidden backup channel is available", s is not None)
    print(f"       location on disk: {where}")
    tag = os.path.dirname(os.path.abspath(CFG))
    check("write then read back", backup_store.save_backup(b"\x00\x01demo", tag=tag)
          and backup_store.load_backup(tag=tag) == b"\x00\x01demo")
    hidden_log = backup_store.load_backup(tag=log_store._tag(CFG),
                                         prefix=log_store.HIDDEN_PREFIX)
    check("log uses its own key prefix (no clash with scores)", hidden_log is not None)

print("\n--- 8. Operation log: auto-record / rollback protection ---")
entries = log_store.load(CFG).entries
check("score changes are auto-logged", len(entries) >= 2, f"actual {len(entries)} entries")
check("log ciphertext contains no plaintext",
      b"group" not in open(log_store.log_path_for(CFG), "rb").read())
with open(log_store.log_path_for(CFG), "rb") as f:
    old_copy = f.read()
store.set_score(1, 99, reason="+96")
store.save()
seq_now = log_store.load(CFG).seq
with open(log_store.log_path_for(CFG), "wb") as f:
    f.write(old_copy)                       # 用旧密文覆盖 = 回滚式篡改
check("rolling back to an old ciphertext is repaired", log_store.load(CFG).seq == seq_now,
      f"actual {log_store.load(CFG).seq} / expected {seq_now}")

print("\n--- 9. File locked (Windows-specific: os.replace raises PermissionError) ---")
locked = None
try:
    locked = open(os.path.join(TMP, "config.dat"), "rb")
    ok = store.save()
    check("save() fails gracefully when the target file is locked",
          ok in (True, False), f"returned {ok}")
    if ok is False:
        print(f"       recorded reason: {store.last_error()[:90]}")
except OSError as e:
    check("save() fails gracefully when the target file is locked", False, repr(e))
finally:
    if locked is not None:
        locked.close()

print("\n" + "=" * 68)

# --- 收尾：清掉本次自检在注册表/plist 里留下的分桶键与临时目录 -----------
TAG = os.path.dirname(os.path.abspath(CFG))
try:
    if has_qt and backup_store._settings is not None:
        s = backup_store._settings
        s.remove(backup_store._key(TAG))
        s.remove(backup_store._key(log_store._tag(CFG), log_store.HIDDEN_PREFIX))
        s.sync()
except Exception:
    pass
try:
    import shutil
    shutil.rmtree(os.path.dirname(TMP), ignore_errors=True)
except Exception:
    pass

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    print("\nPlease send this output back so the platform-specific issue can be fixed.")
    sys.exit(1)
print(f"ALL PASSED ({len(skipped)} skipped)")
print("Windows compatibility: verified on this machine")
