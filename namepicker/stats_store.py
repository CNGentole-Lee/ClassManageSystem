"""StatsStore —— 长期抽取次数（公平加权的依据）。

它存在哪里
    在事件链里（op=draw 的事件），与分数同一套签名、加密、单调时间戳。
    这里不再有任何明文文件：学生姓名 + 被抽中次数不再以可读形式躺在磁盘上。

为什么单独读
    抽取计数必须在重启后保留，「清空历史」也不能碰它——否则加权退化成
    每节课独立随机，一学期下来同几个人反复被抽。

    事件链天然满足这一点：清空历史只是追加一条 wipe 事件，
    不会动已有的 draw 事件。

兼容旧数据
    老版本把计数写在 stats.ini 明文里。这里只在「链里一条 draw 都没有」
    时读一次 stats.ini 作为种子，然后立刻把它删掉。之后再也不会读它，
    老师手写改它也不会影响程序。
"""

import os

from .config_store import resolve_config_path

STATS_FILENAME = "stats.ini"


def resolve_stats_path() -> str:
    """旧版 stats.ini 的位置（与 config.ini 同目录）。"""
    return os.path.join(os.path.dirname(resolve_config_path()), STATS_FILENAME)


class StatsStore:
    """长期抽取次数：从事件链读，新记录追加为 draw 事件。

    chain 为 None 时退化为“无持久化”（链不可用时的只读场景），
    此时 load() 返回空、save() 静默失败，绝不抛异常。
    """

    def __init__(self, path: str = "", chain=None):
        self.legacy_path = path or resolve_stats_path()
        self.chain = chain
        self._counts: dict[str, int] = {}
        self._last_error = ""
        self.reload()

    # --- 加载 ---

    def reload(self) -> None:
        """从链上重放当前计数；链为空时才用旧 stats.ini 做一次性种子。"""
        self._counts = {}
        if self.chain is not None:
            try:
                state = self.chain.state()
                self._counts = {str(k): int(v) for k, v in state.get("draws", {}).items()}
            except Exception as exc:                       # noqa: BLE001
                self._last_error = str(exc)
                return
        if not self._counts:
            self._migrate_legacy_once()

    def _migrate_legacy_once(self) -> None:
        """把旧 stats.ini 里的计数一次性写进链，然后删除该文件。"""
        legacy = self._read_legacy()
        if not legacy:
            return
        seeded = False
        for name, count in legacy.items():
            if count <= 0:
                continue
            if self._append_draw(name, count):
                seeded = True
        if not seeded:
            return
        try:
            self.reload_from_chain()
        except Exception:                                  # noqa: BLE001
            pass
        try:
            os.remove(self.legacy_path)
        except OSError:
            pass

    def _read_legacy(self) -> dict[str, int]:
        import configparser

        if not os.path.isfile(self.legacy_path):
            return {}
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
        try:
            cp.read(self.legacy_path, encoding="utf-8")
        except (OSError, configparser.Error):
            return {}
        if not cp.has_section("counts"):
            return {}
        out: dict[str, int] = {}
        for key, raw in cp.items("counts"):
            try:
                out[key] = int(raw)
            except (TypeError, ValueError):
                continue
        return out

    def reload_from_chain(self) -> None:
        if self.chain is None:
            return
        state = self.chain.state()
        self._counts = {str(k): int(v) for k, v in state.get("draws", {}).items()}

    # --- 查询 ---

    def load(self) -> dict[str, int]:
        """{name: 累计被抽中次数}。"""
        return dict(self._counts)

    def last_error(self) -> str:
        return self._last_error

    @property
    def usable(self) -> bool:
        """是否真的会持久化（链可用时为 True）。"""
        return self.chain is not None

    # --- 写入 ---

    def _append_draw(self, name: str, total: int) -> bool:
        if self.chain is None:
            self._last_error = "no chain: draw counts are not persisted"
            return False
        try:
            self.chain.apply("draw", name=name, total=int(total))
        except Exception as exc:                           # noqa: BLE001
            self._last_error = str(exc)
            return False
        self._counts[name] = int(total)
        self._last_error = ""
        return True

    def save(self, counts: dict[str, int]) -> bool:
        """把 {name: count} 的**变化**追加为 draw 事件。

        只写真正变大的项：次数没变、变小或为 0 都不产生事件，
        因此反复保存不会把链撑大。
        """
        changed = False
        for name, count in counts.items():
            try:
                count = int(count)
            except (TypeError, ValueError):
                continue
            current = self._counts.get(name, 0)
            if count > current:
                if not self._append_draw(name, count):
                    return False
                changed = True
            # 归零不进链：C++ 侧拒绝次数倒退，且“把某个名字清零”由
            # 「彻底重置」统一处理，避免产生互相矛盾的记录。
        return True if changed else True

    def record_draw(self, name: str, total: int) -> bool:
        """一次抽取：写入该名字的新累计次数。"""
        return self._append_draw(name, int(total))

    def clear(self) -> bool:
        """彻底重置：追加一条 wipe(draws) 事件。"""
        if self.chain is None:
            self._last_error = "no chain: cannot clear draw counts"
            return False
        try:
            self.chain.apply("wipe", parts="draws")
        except Exception as exc:                           # noqa: BLE001
            self._last_error = str(exc)
            return False
        self._counts = {}
        self._last_error = ""
        return True
