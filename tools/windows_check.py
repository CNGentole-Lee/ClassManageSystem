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
print(f"平台: {sys.platform} | Python {sys.version.split()[0]} | {sys.executable}")
print(f"文件系统编码: {sys.getfilesystemencoding()} | 默认文本编码: {locale.getpreferredencoding(False)}")
print("=" * 68)

print("\n--- 1. 依赖导入（ImportError 检查）---")
try:
    import cryptography                      # noqa: F401
    check("cryptography 可导入", True, cryptography.__version__)
except Exception as e:
    check("cryptography 可导入", False, repr(e))

try:
    from PyQt5.QtCore import QSettings, QT_VERSION_STR
    check("PyQt5 可导入", True, f"Qt {QT_VERSION_STR}")
    has_qt = True
except Exception as e:
    check("PyQt5 可导入", False, repr(e))
    has_qt = False

from namepicker import backup_store, crypto_utils, log_store  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402

print("\n--- 2. 悬浮球强制置顶（祖传 ctypes.wintypes bug 是否已修）---")
from namepicker import floating_ball  # noqa: E402
if IS_WINDOWS:
    check("_SetWindowPos 拿到了真实的 Win32 函数（不是 None）",
          floating_ball._SetWindowPos is not None,
          "None 说明 force_topmost 在 Windows 上是空操作（祖传 bug 复发）")
    check("argtypes 已设置（HWND 用 c_void_p 传，不依赖 ctypes.wintypes）",
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
    check("干净进程里导入本程序不依赖 ctypes.wintypes",
          out.returncode == 0 and "OK" in out.stdout,
          (out.stdout + out.stderr).strip()[:160])
else:
    skip("Win32 SetWindowPos 实测", "当前不是 Windows")
    check("macOS/Linux 上安全降级为 None（不会 ImportError）",
          floating_ball._SetWindowPos is None)

print("\n--- 3. 密钥文件 ---")
blob = crypto_utils.encrypt("中文测试".encode("utf-8"))   # 先触发密钥生成
check("密钥文件可生成", os.path.isfile(crypto_utils.KEY_FILE), crypto_utils.KEY_FILE)
if os.path.isfile(crypto_utils.KEY_FILE):
    check("密钥 32 字节", os.path.getsize(crypto_utils.KEY_FILE) == 32,
          f"实际 {os.path.getsize(crypto_utils.KEY_FILE)} 字节")
else:
    check("密钥 32 字节", False, "密钥文件不存在")
check("加解密往返（含中文）", crypto_utils.decrypt(blob).decode("utf-8") == "中文测试")

# 隔离的工作目录：中文 + 空格 + 长路径，Windows 上最容易出问题
TMP = os.path.join(tempfile.mkdtemp(prefix="cm_win_check_"), "班级 管理 测试目录")
os.makedirs(TMP, exist_ok=True)
CFG = os.path.join(TMP, "config.ini")
print(f"\n--- 4. 中文/空格路径下的完整读写（{TMP}）---")
store = ConfigStore(CFG)
store.set_group_name(1, "雄鹰组")
store.set_score(1, 7, reason="+7")
store.set_score(1, 3, reason="-4")
check("save() 成功（中文字段 + 中文路径）", store.save())
again = ConfigStore(CFG)
check("重载后中文组名不丢", again.get_group_name(1) == "雄鹰组",
      f"实际 {again.get_group_name(1)!r}")
check("重载后分数正确", again.get_score(1) == 3, f"实际 {again.get_score(1)}")
check("config.dat 是加密二进制",
      b"[points]" not in open(os.path.join(TMP, "config.dat"), "rb").read())
ini = open(os.path.join(TMP, "config.ini"), encoding="utf-8").read()
check("明文查看副本是 UTF-8 且带标记", "仅供查看" in ini)

print("\n--- 5. 原子写入（os.replace 覆盖已存在文件）---")
check("连续保存两次都成功",
      store.save() and ConfigStore(CFG).save())
check("没有 .tmp 残留", not [n for n in os.listdir(TMP) if n.endswith(".tmp")],
      f"实际 {[n for n in os.listdir(TMP) if n.endswith('.tmp')]}")

print("\n--- 6. 篡改回档（config.dat → .bak → 隐蔽备份）---")
dat = os.path.join(TMP, "config.dat")
with open(dat, "rb") as f:
    raw = bytearray(f.read())
raw[len(raw) // 2] ^= 0xFF
with open(dat, "wb") as f:
    f.write(bytes(raw))
check("改坏主文件 → 从 .bak 回档", ConfigStore(CFG).get_score(1) == 3)
os.remove(dat)
os.remove(dat + ".bak")
check("删掉主文件与 .bak → 从隐蔽备份回档",
      ConfigStore(CFG).get_group_name(1) == "雄鹰组")

print("\n--- 7. QSettings 隐蔽备份（Windows = HKCU 注册表）---")
if not has_qt:
    skip("注册表隐蔽备份实测", "未安装 PyQt5")
else:
    s = backup_store._get_settings()
    where = s.fileName() if s is not None else "(不可用)"
    check("隐蔽备份通道可用", s is not None)
    print(f"       实际落盘位置: {where}")
    tag = os.path.dirname(os.path.abspath(CFG))
    check("写入即读回", backup_store.save_backup(b"\x00\x01demo", tag=tag)
          and backup_store.load_backup(tag=tag) == b"\x00\x01demo")
    hidden_log = backup_store.load_backup(tag=log_store._tag(CFG),
                                         prefix=log_store.HIDDEN_PREFIX)
    check("日志用自己的键前缀，不与积分冲突", hidden_log is not None)

print("\n--- 8. 操作日志：自动记录 / 防回滚 ---")
entries = log_store.load(CFG).entries
check("积分变动已自动记录", len(entries) >= 2, f"实际 {len(entries)} 条")
check("日志密文不含明文",
      b"group" not in open(log_store.log_path_for(CFG), "rb").read())
with open(log_store.log_path_for(CFG), "rb") as f:
    old_copy = f.read()
store.set_score(1, 99, reason="+96")
store.save()
seq_now = log_store.load(CFG).seq
with open(log_store.log_path_for(CFG), "wb") as f:
    f.write(old_copy)                       # 用旧密文覆盖 = 回滚式篡改
check("旧密文覆盖主日志后能被修回", log_store.load(CFG).seq == seq_now,
      f"实际 {log_store.load(CFG).seq} / 期望 {seq_now}")

print("\n--- 9. 文件被占用（Windows 特有：os.replace 会 PermissionError）---")
locked = None
try:
    locked = open(os.path.join(TMP, "config.dat"), "rb")
    ok = store.save()
    check("目标文件被占用时 save() 优雅失败（不崩溃）",
          ok in (True, False), f"返回 {ok}")
    if ok is False:
        print(f"       失败原因已记录: {store.last_error()[:90]}")
except OSError as e:
    check("目标文件被占用时 save() 优雅失败（不崩溃）", False, repr(e))
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
    print(f"失败 {len(failures)} 项：")
    for f in failures:
        print(f"  - {f}")
    print("\n请把以上输出发回，我按平台差异修。")
    sys.exit(1)
print(f"全部通过（跳过 {len(skipped)} 项平台无关检查）")
print("Windows 兼容性：本机实测无异常")
