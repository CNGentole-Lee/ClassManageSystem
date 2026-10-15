"""backup_store —— 系统级隐蔽备份（基于 QSettings，一套代码三平台通用）。

存的是加密后的 config.dat 内容，位置由 QSettings 自动选择，学生既找不到也
不容易删：

    Windows : HKEY_CURRENT_USER\\Software\\YourOrg\\ClassManageSystem   （注册表）
    macOS   : ~/Library/Preferences/com.YourOrg.ClassManageSystem.plist
    Linux   : ~/.config/YourOrg/ClassManageSystem.conf

为什么不直接用 winreg：winreg 只在 Windows 上存在，直接 import 会让 macOS
抛 ModuleNotFoundError。QSettings 是 PyQt5 自带的跨平台封装，Windows 下落成
注册表、macOS 下落成 plist，因此这里不需要写 import winreg，也不需要平台判断。

所有函数都静默失败：没装 PyQt5、没有 Qt 应用、注册表只读、plist 损坏……
一律返回 None / False，绝不抛异常，绝不影响主流程。

命名空间说明：QSettings 只有一张「表」，而本项目的配置可能来自不同目录
（源码目录、打包后的安装目录、冒烟测试的临时目录）。为了让 A 目录的数据
不会被 B 目录误读，备份值按配置目录指纹分开存放（键名后缀 = 目录路径哈希）。
不传 tag 的调用方仍然使用默认键 "sys_cache"，行为与最简实现一致。
"""

import hashlib
import os

ORG_NAME = "YourOrg"
APP_NAME = "ClassManageSystem"
VALUE_KEY = "sys_cache"

try:  # PyQt5 缺失时（例如纯逻辑测试）本模块退化为「无隐蔽备份」
    from PyQt5.QtCore import QSettings
except Exception:  # pragma: no cover - 取决于运行环境
    QSettings = None

_settings = None
_settings_failed = False


def _get_settings():
    """惰性创建 QSettings：任何异常都退化成 None（静默）。"""
    global _settings, _settings_failed
    if _settings is not None:
        return _settings
    if _settings_failed or QSettings is None:
        return None
    try:
        settings = QSettings(ORG_NAME, APP_NAME)
        # 不要读系统级 fallback，避免读到别的用户/别的安装留下的值。
        settings.setFallbacksEnabled(False)
        _settings = settings
        return settings
    except Exception:
        _settings_failed = True
        return None


def _key(tag: str = "", prefix: str = VALUE_KEY) -> str:
    """默认键 sys_cache；带 tag 时按配置目录哈希分桶；prefix 用于区分不同用途
    （积分为 sys_cache，操作日志为 sys_log，互不覆盖）。"""
    if not tag:
        return prefix
    try:
        raw = os.path.abspath(str(tag)).encode("utf-8", "surrogatepass")
    except Exception:
        raw = str(tag).encode("utf-8", "replace")
    return prefix + "_" + hashlib.sha256(raw).hexdigest()[:16]


def save_backup(blob: bytes, tag: str = "", prefix: str = VALUE_KEY) -> bool:
    """写隐蔽备份。失败静默返回 False。"""
    settings = _get_settings()
    if settings is None or not blob:
        return False
    try:
        settings.setValue(_key(tag, prefix), bytes(blob).hex())
        settings.sync()  # macOS 上确保写进 plist
        return True
    except Exception:
        return False


def load_backup(tag: str = "", prefix: str = VALUE_KEY):
    """读隐蔽备份。没有 / 读不出 / 格式不对都返回 None。"""
    settings = _get_settings()
    if settings is None:
        return None
    try:
        raw = settings.value(_key(tag, prefix), None)
        if not raw:
            return None
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        return bytes.fromhex(str(raw).strip())
    except Exception:
        return None
