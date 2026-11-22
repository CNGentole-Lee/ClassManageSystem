"""ProfileStore —— 课堂预设（分组制）。

分组制只在一部分课上用（比如化学），其他课不分组。预设就是「一套分组规则」，
课前在悬浮球菜单里点一下就换，不用重启、不用改任何文件。

它存在哪里
    全部在事件链里（OP_PROFILE_*），与分数、抽取次数同一套签名与加密。
    **不产生任何文件** —— 换电脑、导入导出时预设自动跟着走，
    而且别人手改 config.ini 也伪造不出来。

为什么组员按名单下标存
    按名字存的话，名单改一个错别字、重新导入一次，整张组员表就全废了。
    按下标存只要人数没变就还对着。名单变短时越界的项由 C++ 回放丢弃，
    这里只负责在界面上提示一句。

增量的意义
    一次课前通常只挪几个人，链上就只多几条 7 字节的记录，不做全量快照。
    保存界面时用 ``assign_bulk`` 一次性提交，避免误点产生几十条事件。
"""

from .i18n import tr

#: 预设名称长度上限（与 C++ 侧的 64 字节保持一致，按 UTF-8 计）
NAME_BYTES_MAX = 64

#: 组号 0 表示「未分组」
UNGROUPED = 0


class ProfileError(Exception):
    """预设操作被拒绝（链不可用、参数非法等）。"""


def _name_ok(name: str) -> bool:
    return bool(name) and len(name.encode("utf-8")) <= NAME_BYTES_MAX


class ProfileStore:
    """预设的读写门面。chain 为 None 时退化为只读（链不可用）。"""

    def __init__(self, chain=None):
        self.chain = chain
        self._last_error = ""

    # --- 查询 ---

    @property
    def usable(self) -> bool:
        return self.chain is not None

    def last_error(self) -> str:
        return self._last_error

    def _profiles(self) -> list[dict]:
        if self.chain is None:
            return []
        try:
            return list(self.chain.state().get("profiles", []))
        except Exception as exc:                       # noqa: BLE001
            self._last_error = str(exc)
            return []

    def list(self) -> list[dict]:
        """[{id, name, group_count, members, active}]，已按 id 升序。"""
        active = self.active_id()
        out = []
        for p in self._profiles():
            item = dict(p)
            item["active"] = p["id"] == active
            out.append(item)
        return out

    def get(self, pid: int) -> dict | None:
        for p in self._profiles():
            if p["id"] == pid:
                return dict(p)
        return None

    def active_id(self) -> int:
        if self.chain is None:
            return 0
        try:
            return int(self.chain.state().get("active_profile", 0) or 0)
        except Exception as exc:                       # noqa: BLE001
            self._last_error = str(exc)
            return 0

    def active(self) -> dict | None:
        pid = self.active_id()
        return self.get(pid) if pid else None

    def grouping_enabled(self) -> bool:
        """当前是否是"带分组的课堂"。"""
        p = self.active()
        return bool(p and p["group_count"] > 0 and any(p["members"]))

    def group_of(self, index: int) -> int:
        """名单下标 → 组号；未分组或没有预设时返回 0。"""
        p = self.active()
        if not p:
            return 0
        members = p["members"]
        if 0 <= index < len(members):
            return int(members[index])
        return 0

    # --- 写入 ---

    def _apply(self, op: str, **kwargs) -> dict:
        if self.chain is None:
            raise ProfileError("chain unavailable")
        try:
            state = self.chain.apply(op, **kwargs)
        except Exception as exc:                       # noqa: BLE001
            self._last_error = str(exc)
            raise ProfileError(str(exc)) from exc
        self._last_error = ""
        return state

    def create(self, name: str) -> int:
        """新建预设并返回它的 id（取当前最大 id + 1）。"""
        if not _name_ok(name):
            raise ProfileError("bad profile name")
        existing = self._profiles()
        pid = max((p["id"] for p in existing), default=0) + 1
        if pid > 0xFFFF:
            raise ProfileError("too many profiles")
        self._apply("profile-new", id=pid, name=name)
        return pid

    def rename(self, pid: int, name: str) -> None:
        if not _name_ok(name):
            raise ProfileError("bad profile name")
        self._apply("profile-name", id=int(pid), name=name)

    def set_rule(self, pid: int, group_count: int, member_count: int) -> None:
        """设置组数，并预留 member_count 个组员槽位。

        缩小 member_count 时，多出来的下标由 C++ 侧截断；指向已不存在
        组的分配就地清 0。
        """
        group_count = max(1, int(group_count))
        member_count = max(0, int(member_count))
        self._apply("profile-rule", id=int(pid),
                    count=group_count, members=member_count)

    def assign(self, pid: int, index: int, group: int) -> None:
        """给一个名单下标指派组号（0 = 未分组）。"""
        self._apply("profile-member", id=int(pid),
                    index=int(index), group=int(group))

    def assign_bulk(self, pid: int, mapping: dict[int, int]) -> int:
        """一次性提交多个指派，返回实际写入的条数。

        只写**真正变化**的项：界面里点来点去最后又改回原样的下标不产生事件，
        避免把链撑大。
        """
        current = self.get(pid)
        if current is None:
            raise ProfileError("unknown profile")
        old = current["members"]
        written = 0
        for index in sorted(mapping):
            group = int(mapping[index])
            index = int(index)
            if index < 0:
                continue
            if index < len(old) and old[index] == group:
                continue
            self.assign(pid, index, group)
            written += 1
        return written

    def delete(self, pid: int) -> None:
        self._apply("profile-del", id=int(pid))

    def use(self, pid: int) -> None:
        """切换当前预设；传 0 表示不分组。"""
        self._apply("profile-use", id=int(pid))

    # --- 界面辅助 ---

    def balanced_assignment(self, group_count: int, name_count: int) -> dict[int, int]:
        """按人数均分：40 人 4 组 → 前 10 人第 1 组，以此类推。

        界面上的「均分」按钮用它生成初值，再让老师微调。
        """
        group_count = max(1, int(group_count))
        out: dict[int, int] = {}
        for index in range(int(name_count)):
            out[index] = index * group_count // max(1, int(name_count)) + 1
        return out

    @staticmethod
    def group_sizes(members: list[int], group_count: int) -> dict[int, int]:
        """每个组有多少人（未分组的记为 0 号）。"""
        sizes = {g: 0 for g in range(1, int(group_count) + 1)}
        sizes[UNGROUPED] = 0
        for g in members:
            sizes[int(g)] = sizes.get(int(g), 0) + 1
        return sizes

    @staticmethod
    def describe(profile: dict | None) -> str:
        """给菜单用的一行说明。"""
        if not profile:
            return tr("不分班", "No profiles")
        if profile["group_count"] <= 0:
            return tr("未分组", "No groups")
        return tr("{n} 组", "{n} groups", n=profile["group_count"])
