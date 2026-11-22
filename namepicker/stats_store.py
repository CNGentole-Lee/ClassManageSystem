"""StatsStore —— 每节课的抽取次数（公平加权的依据）。

它存在哪里
    在事件链里（op=draw 的事件），与分数同一套签名、加密、单调时间戳。
    这里不再有任何明文文件：学生姓名 + 被抽中次数不再以可读形式躺在磁盘上。

V4：次数属于「当前预设」
    化学课和语文课各算各的（见 SOP v2 第 3 条）。链上存的是
    ``Profile.draw_counts[名单下标]``，不带名字 —— 名单里改个错别字，
    次数仍然对得上；换班级（名单变短）时越界的项由 C++ 回放丢弃。

    因此这一层要负责「名字 ↔ 下标」的翻译：引擎按名字计数（它只认名字），
    链按下标存。名单由 ``set_names()`` 提供，换名单时同步一次即可；
    名字不在名单里就跳过（没有下标可写，绝不猜测）。

为什么必须保留
    抽取计数必须在重启后保留，「清空历史」也不能碰它——否则加权退化成
    每节课独立随机，一学期下来同几个人反复被抽。

    事件链天然满足这一点：清空历史只是追加一条 wipe 事件，
    不会动已有的 draw 事件。
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
        #: 当前名单（按顺序）。链上按下标存次数，没有它就无法翻译。
        self._names: list[str] = []
        self.reload()

    def set_names(self, names) -> None:
        """告诉这一层「现在这份名单是什么」。

        名单是次数与下标之间的唯一桥梁：名单变了（换班、增删人），
        必须重新同步，否则新名字写不进链、旧下标会错位。
        因此名单一变就立刻按新名单重算一次（否则读出来的是空表 ——
        构造时名单还没到，重算必须在这里补上）。
        """
        new_names = [str(n) for n in (names or [])]
        if new_names == self._names:
            return
        self._names = new_names
        if self.chain is None:
            return
        try:
            self.reload_from_chain()
        except Exception as exc:                           # noqa: BLE001
            self._last_error = str(exc)
            return
        if not self._counts:
            # 构造时名单还没到，旧 stats.ini 的迁移被搁置了 —— 现在名单
            # 就位，补做一次（只在链上一条 draw 都没有时才做）。
            self._migrate_legacy_once()

    def _index_of(self, name: str) -> int:
        """名字在当前名单里的下标；不在名单里返回 -1（没有下标可写）。"""
        try:
            return self._names.index(str(name))
        except ValueError:
            return -1

    # --- 加载 ---

    def reload(self) -> None:
        """从链上重放当前预设的次数；链为空时才尝试旧 stats.ini 做一次性种子。"""
        self._counts = {}
        if self.chain is not None:
            try:
                self._counts = self._counts_from_chain()
            except Exception as exc:                       # noqa: BLE001
                self._last_error = str(exc)
                return
        if not self._counts:
            self._migrate_legacy_once()

    def _counts_from_chain(self) -> dict[str, int]:
        """把当前预设的 draw_counts（按名单下标）翻回 {名字: 次数}。"""
        if self.chain is None:
            return {}
        state = self.chain.state()
        profiles = state.get("profiles", [])
        active = int(state.get("active_profile", 0) or 0)
        profile = next((p for p in profiles if int(p.get("id", 0)) == active), None)
        if profile is None:
            return {}
        counts = profile.get("draw_counts", []) or []
        out: dict[str, int] = {}
        for index, total in enumerate(counts):
            if index >= len(self._names):
                break
            total = int(total)
            if total > 0:
                out[self._names[index]] = total
        return out

    def _migrate_legacy_once(self) -> None:
        """把旧 stats.ini 里的计数一次性写进链，然后删除该文件。

        只有「名单已经就位」时才做：V4 按下标存次数，没有名单就无法
        把 ``{名字: 次数}`` 变成 ``{下标: 次数}``。名单没来时**不删**文件，
        留到下次启动再试 —— 宁可晚一点，也不能把老师唯一的旧记录丢掉。
        """
        if not self._names:
            return
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
        self._counts = self._counts_from_chain()

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
        """追加一条 draw 事件：当前预设 + 名字在名单里的下标 + 累计次数。"""
        if self.chain is None:
            self._last_error = "no chain: draw counts are not persisted"
            return False
        index = self._index_of(name)
        if index < 0:
            # 名字不在名单里就没有下标可写。这不是错误：换班后旧名字本来
            # 就不该继续计数，静默跳过比写错位置好得多。
            self._last_error = f"name not in roster: {name}"
            return False
        try:
            state = self.chain.apply("draw", id=self._pid(), index=index,
                                     total=int(total))
        except Exception as exc:                           # noqa: BLE001
            self._last_error = str(exc)
            return False
        if not self._landed(state, index, int(total)):
            # C++ 对「下标超出名单长度」的 draw 是**静默丢弃**的（为了不让
            # 旧链打不开）。这里必须自己发现它，否则界面上显示"已保存"、
            # 实际什么都没写进去 —— 公平计数就这么悄悄丢掉了。
            self._last_error = f"draw dropped: index {index} beyond roster"
            return False
        self._counts[name] = int(total)
        self._last_error = ""
        return True

    @staticmethod
    def _landed(state: dict, index: int, total: int) -> bool:
        """确认这次 draw 真的落进了状态（而不是被静默丢弃）。"""
        if not isinstance(state, dict):
            return True                     # 拿不到状态就信任 C++（旧行为）
        active = int(state.get("active_profile", 0) or 0)
        for profile in state.get("profiles", []):
            if int(profile.get("id", 0)) != active:
                continue
            counts = profile.get("draw_counts", []) or []
            return index < len(counts) and int(counts[index]) == total
        return False

    def _pid(self) -> int:
        """当前预设 id；没有预设时返回 0（C++ 会拒绝，不会写坏数据）。"""
        if self.chain is None:
            return 0
        try:
            return int(self.chain.state().get("active_profile", 0) or 0)
        except Exception:                                  # noqa: BLE001
            return 0

    def save(self, counts: dict[str, int]) -> bool:
        """把 {name: count} 的**变化**追加为 draw 事件。

        只写真正变大的项：次数没变、变小或为 0 都不产生事件，
        因此反复保存不会把链撑大。
        """
        if not counts:
            return True
        for name, count in counts.items():
            try:
                count = int(count)
            except (TypeError, ValueError):
                continue
            current = self._counts.get(name, 0)
            if count <= current:
                # 归零不进链：C++ 侧拒绝次数倒退，且“把某个名字清零”由
                # 「彻底重置」统一处理，避免产生互相矛盾的记录。
                continue
            if self._index_of(name) < 0:
                continue                   # 不在当前名单里：没有下标可写
            if not self._append_draw(name, count):
                return False
        return True

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
