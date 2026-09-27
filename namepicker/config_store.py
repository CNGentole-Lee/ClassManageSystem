"""ConfigStore —— config.ini 的持久化：小组积分与抽取统计。

首次运行自动生成，是普通可读的 INI，老师可以备份、手工编辑或拷到别的机器。

结构：
    [meta]
    app = 班级多用教学辅助终端
    updated = 2026-09-27 10:30:00

    [points]
    group_count = 6
    group_1 = 第一组          ; 显示名，可自由编辑
    score_1 = 12              ; 可为负数
    ...

长期抽取次数刻意放在 stats.ini（见 stats_store.py），
这样「清空历史」不会把公平性记忆一起丢掉。
"""

import configparser
import os
import sys
from datetime import datetime

APP_NAME = "班级多用教学辅助终端"
CONFIG_FILENAME = "config.ini"

DEFAULT_GROUP_COUNT = 6
MIN_GROUP_COUNT = 1
MAX_GROUP_COUNT = 24

# 第一组 … 第六组
DEFAULT_GROUP_NAMES = ["第{}组".format(n) for n in ("一", "二", "三", "四", "五", "六")]


def default_group_name(index: int) -> str:
    """小组 index（1 起）的兜底显示名。"""
    if 1 <= index <= len(DEFAULT_GROUP_NAMES):
        return DEFAULT_GROUP_NAMES[index - 1]
    return f"第{index}组"


def _app_dir() -> str:
    """程序运行目录：打包后是 EXE 所在目录，否则是项目根目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # namepicker/config_store.py → 项目根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fallback_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ClassTerminal2411")


def _is_writable(directory: str) -> bool:
    probe = os.path.join(directory, ".~write_probe")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return True
    except OSError:
        return False


def resolve_config_path() -> str:
    """优先用程序旁的 config.ini，只读目录则退到 %APPDATA%。

    防止装在只读位置（如 C:\\Program Files）时，老师点的分全部静默写不进去。
    """
    primary = os.path.join(_app_dir(), CONFIG_FILENAME)
    if os.path.isfile(primary) or _is_writable(_app_dir()):
        return primary

    fallback = _fallback_dir()
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        pass
    return os.path.join(fallback, CONFIG_FILENAME)


class ConfigStore:
    """内存中的 config.ini，原子写入。每个进程共享一个实例。"""

    def __init__(self, path: str = ""):
        self.path = path or resolve_config_path()
        self._cp = configparser.ConfigParser(interpolation=None)
        self._cp.optionxform = str  # 保留键名大小写（人名）
        self._last_error = ""
        self.reload()

    # --- 加载 ---

    def reload(self) -> None:
        """从磁盘重读文件，丢弃内存中未保存的改动。"""
        self._cp.clear()
        if os.path.isfile(self.path):
            try:
                self._cp.read(self.path, encoding="utf-8")
            except (OSError, configparser.Error) as e:
                self._last_error = str(e)
        self._ensure_sections()

    def _ensure_sections(self) -> None:
        """补齐缺失的段和键，调用方永远不会遇到 KeyError。"""
        if not self._cp.has_section("meta"):
            self._cp.add_section("meta")
        self._cp.set("meta", "app", APP_NAME)

        if not self._cp.has_section("points"):
            self._cp.add_section("points")

        # 补齐缺失的小组名 / 分数槽位
        count = self.group_count
        for i in range(1, count + 1):
            if not self._cp.has_option("points", f"group_{i}"):
                self._cp.set("points", f"group_{i}", default_group_name(i))
            if not self._cp.has_option("points", f"score_{i}"):
                self._cp.set("points", f"score_{i}", "0")

    # --- 小组 / 分数 ---

    @property
    def group_count(self) -> int:
        raw = self._cp.get("points", "group_count", fallback="")
        try:
            count = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_GROUP_COUNT
        return max(MIN_GROUP_COUNT, min(count, MAX_GROUP_COUNT))

    def set_group_count(self, count: int) -> int:
        """改小组数量：整段重建 [points]，组名回默认、分数归零，返回实际生效值。

        换组数即换了一套分组，旧分数没有可挂靠的小组，所以一并清空。
        """
        try:
            count = int(count)
        except (TypeError, ValueError):
            return self.group_count
        count = max(MIN_GROUP_COUNT, min(count, MAX_GROUP_COUNT))
        if count == self.group_count:
            return count  # 数量没变，不做任何事，避免白清一次分数
        self._write_default_groups(count)
        return count

    def get_group_name(self, index: int) -> str:
        """小组 index（1 起）的显示名。"""
        fallback = default_group_name(index)
        name = self._cp.get("points", f"group_{index}", fallback=fallback).strip()
        return name or fallback

    def set_group_name(self, index: int, name: str) -> None:
        name = name.strip()
        if not name:
            return
        self._cp.set("points", f"group_{index}", name)

    def get_score(self, index: int) -> int:
        raw = self._cp.get("points", f"score_{index}", fallback="0")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def set_score(self, index: int, value: int) -> None:
        self._cp.set("points", f"score_{index}", str(int(value)))

    def all_scores(self) -> list[int]:
        return [self.get_score(i) for i in range(1, self.group_count + 1)]

    def reset_scores(self) -> None:
        for i in range(1, self.group_count + 1):
            self.set_score(i, 0)

    def _write_default_groups(self, count: int) -> None:
        """把 [points] 整段换成 `count` 个全新小组（默认组名、0 分）。"""
        if self._cp.has_section("points"):
            self._cp.remove_section("points")
        self._cp.add_section("points")
        self._cp.set("points", "group_count", str(count))
        for i in range(1, count + 1):
            self._cp.set("points", f"group_{i}", default_group_name(i))
            self._cp.set("points", f"score_{i}", "0")

    def reset_all(self) -> bool:
        """回到出厂状态：组名、分数、组数全部重置（彻底重置用）。

        长期抽取次数不在这里，它存在 stats.ini（见 stats_store.py）。
        """
        self._write_default_groups(DEFAULT_GROUP_COUNT)
        # 早期版本把抽取次数写在 [stats] 段里，一并删除避免留下误导性残留。
        if self._cp.has_section("stats"):
            self._cp.remove_section("stats")
        return self.save()

    # --- 保存 ---

    def save(self) -> bool:
        """原子写入整个文件（tmp + os.replace），返回是否成功。"""
        self._cp.set("meta", "updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        tmp_path = self.path + ".tmp"
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                self._cp.write(f)
            os.replace(tmp_path, self.path)
            self._last_error = ""
            return True
        except OSError as e:
            self._last_error = str(e)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False

    def last_error(self) -> str:
        return self._last_error
