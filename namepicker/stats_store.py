"""StatsStore —— 长期抽取次数，单独存在 stats.ini 里。

为什么不用 config.ini 里的一个 [stats] 段：
    「清空历史」是老师每节课前的习惯动作。长期次数若和配置放在同一个文件里，
    任何一次重置都会一并把它抹掉，加权就退化成"每节课各自独立随机"—— 一学期
    下来同几个人反复被抽，加权失去作用。

    stats.ini 只被抽取本身写入，清空历史不碰它。要真正从零开始（新学期、
    换班级），走托盘菜单的「彻底重置」。

格式（键就是名字，所以关掉插值、保留大小写）:
    [counts]
    张三 = 5
    李四 = 3
"""

import configparser
import os

from .config_store import resolve_config_path

STATS_FILENAME = "stats.ini"


def resolve_stats_path() -> str:
    """stats.ini 与 config.ini 同目录（同样的只读目录回退规则）。"""
    return os.path.join(os.path.dirname(resolve_config_path()), STATS_FILENAME)


class StatsStore:
    """长期抽取次数。save 是合并而非覆盖，中途换花名册不会清掉上一个班的记录。"""

    def __init__(self, path: str = ""):
        self.path = path or resolve_stats_path()
        self._cp = configparser.ConfigParser(interpolation=None)
        self._cp.optionxform = str  # 保留键名大小写（人名）
        self._last_error = ""
        self.reload()

    # --- 加载 ---

    def reload(self) -> None:
        self._cp.clear()
        if os.path.isfile(self.path):
            try:
                self._cp.read(self.path, encoding="utf-8")
            except (OSError, configparser.Error) as e:
                self._last_error = str(e)
        if not self._cp.has_section("counts"):
            self._cp.add_section("counts")

    def load(self) -> dict[str, int]:
        """{name: lifetime draws}，无法解析的条目跳过。"""
        counts: dict[str, int] = {}
        if not self._cp.has_section("counts"):
            return counts
        for key, raw in self._cp.items("counts"):
            try:
                counts[key] = int(raw)
            except (TypeError, ValueError):
                continue
        return counts

    # --- 保存 ---

    def save(self, counts: dict[str, int]) -> bool:
        """把 {name: count} 合并进去。

        次数为 0 时删掉该行而不是写 `name = 0`，避免 99 人的名单多出 99 行
        无用条目。未提及的名字保持原样，所以换一个班的花名册不会清掉上一个班
        的记录。
        """
        if not self._cp.has_section("counts"):
            self._cp.add_section("counts")
        for name, count in counts.items():
            try:
                count = int(count)
            except (TypeError, ValueError):
                continue
            if count > 0:
                self._cp.set("counts", name, str(count))
            elif self._cp.has_option("counts", name):
                self._cp.remove_option("counts", name)
        return self._write()

    def clear(self) -> bool:
        """清空所有已记录的抽取次数（彻底重置 / 新学期）。"""
        if self._cp.has_section("counts"):
            self._cp.remove_section("counts")
        self._cp.add_section("counts")
        return self._write()

    def _write(self) -> bool:
        """原子写入（tmp + os.replace），与 config.ini 一致。"""
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
