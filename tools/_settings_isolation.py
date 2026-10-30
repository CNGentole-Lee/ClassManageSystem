"""测试用的 QSettings 隔离 —— 别让测试数据写进用户的真实隐蔽备份。

Windows 上 QSettings 落在 HKCU 注册表，macOS 上是
~/Library/Preferences/*.plist，$HOME 隔离对注册表无效，所以测试必须切换
QSettings 的 org/app 命名空间，并在退出时清空该命名空间。

用法（放在所有 ConfigStore/save 之前）：

    from _settings_isolation import isolate_settings
    isolate_settings()
"""

import atexit

ORG = "YourOrgTestCase"
APP = "ClassManageSystemTestCase"


def isolate_settings(org: str = ORG, app: str = APP) -> None:
    """把 backup_store 指向一个测试专用命名空间，并注册退出时清理。"""
    from namepicker import backup_store

    backup_store.ORG_NAME = org
    backup_store.APP_NAME = app
    backup_store._settings = None

    def _cleanup() -> None:
        # 注意：这里必须**新建**一个 QSettings，不能复用 backup_store 里缓存的那个。
        # Qt 拆除发生在 atexit 之前，缓存实例的 C++ 对象可能已被 delete，复用它只会
        # 抛 "wrapped C/C++ object ... has been deleted"；若被静默吞掉，测试数据就
        # 留在用户真实的注册表 / plist 里了。
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(org, app)
            settings.setFallbacksEnabled(False)
            settings.clear()
            settings.sync()
        except Exception:
            pass

    atexit.register(_cleanup)
