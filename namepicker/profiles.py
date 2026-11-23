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

from __future__ import annotations

# 必须有上面这行：ProfileStore 有个方法叫 list()，类体内的注解如 `-> list[int]`
# 在 Python 3.12 及更早会先查类命名空间，把 list 解析成那个方法而不是内置类型，
# 导入时直接抛 "TypeError: 'function' object is not subscriptable"（CI 上真实踩到）。
# 延迟注解求值后注解变成字符串，不再触发。

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
        """设置组数，并预留 member_count 个名单槽位。

        group_count = 0 表示这个预设不启用小组制。
        缩小 member_count 时，多出来的下标由 C++ 侧截断；指向已不存在
        组的分配就地清 0。
        """
        group_count = max(0, int(group_count))
        member_count = max(0, int(member_count))
        self._apply("profile-rule", id=int(pid),
                    count=group_count, members=member_count)

    def sync_roster(self, name_count: int, pid: int | None = None) -> bool:
        """让预设的成员表/次数表跟上名单长度；返回是否真的改了。

        为什么必须有这一步
            链上的抽取次数是 ``draw_counts[名单下标]``。名单变长以后，
            新下标在数组里还不存在，写入时会被 C++ 判为越界**静默丢弃** ——
            公平计数就这么无声地丢了。每次名单加载后对齐一次，它才不会丢。

            增长时原有次数保留（resize 只补 0），缩短时尾部截断，
            与「名单变短丢越界项」的既有语义一致。
        """
        profile = self._pick(pid)
        if profile is None:
            return False
        count = max(0, int(name_count))
        if (len(profile.get("members", [])) == count
                and len(profile.get("draw_counts", [])) == count):
            return False
        self.set_rule(profile["id"], int(profile.get("group_count", 0)), count)
        return True

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

    def ensure_default(self, group_count: int = 6) -> int:
        """首次运行：一条预设都没有时，建一个默认的（默认 6 组）并设为当前。

        为什么需要它
            V4 起组名与分数只存在于预设里。全新安装若不做这件事，
            老师打开程序看到的是「0 个小组」，第一反应是程序坏了 ——
            而 V3 的开箱状态是 6 个小组。这里只是把这份体验补回来。

        什么时候**不**做
            · 已经有预设 —— 绝不覆盖老师的选择
            · 链上不止一条 init —— 说明曾经有过预设（哪怕删光了），
              老师是主动删的，不该每次启动都给他长回来

        返回新建的预设 id；没建则返回 0。
        """
        if self.chain is None:
            return 0
        if self._profiles():
            return 0
        try:
            if self.chain.count() > 1:
                return 0
        except Exception:                              # noqa: BLE001
            return 0
        try:
            pid = self.create(tr("默认预设", "Default"))
            self.set_rule(pid, int(group_count), 0)
            self.use(pid)
        except ProfileError:
            return 0
        return pid

    # --- 每个预设自己的分数 / 组名 / 抽取次数（V4）---

    def require_active(self) -> dict:
        """取当前预设；没有就抛 ProfileError，调用方据此拒绝操作。"""
        profile = self.active()
        if profile is None:
            raise ProfileError("no active profile")
        return profile

    def scores(self, pid: int | None = None) -> list[int]:
        """某个预设（默认当前）的各组分数。"""
        profile = self._pick(pid)
        return list(profile.get("scores", [])) if profile else []

    def get_score(self, group: int, pid: int | None = None) -> int:
        """第 group 组（1 起）的分数；越界返回 0。"""
        scores = self.scores(pid)
        index = int(group) - 1
        return int(scores[index]) if 0 <= index < len(scores) else 0

    def set_score(self, group: int, value: int, pid: int | None = None) -> None:
        """把第 group 组设为 value（内部换算成增量，链上只记 delta）。"""
        target = pid if pid is not None else self.active_id()
        if not target:
            raise ProfileError("no active profile")
        current = self.get_score(group, target)
        delta = int(value) - current
        if delta == 0:
            return
        self._apply("profile-score", id=int(target), group=int(group), delta=delta)

    def add_score(self, group: int, delta: int, pid: int | None = None) -> None:
        """第 group 组加减 delta 分。"""
        target = pid if pid is not None else self.active_id()
        if not target:
            raise ProfileError("no active profile")
        if int(delta) == 0:
            return
        self._apply("profile-score", id=int(target), group=int(group), delta=int(delta))

    def reset_scores(self, pid: int | None = None) -> None:
        """把某个预设（默认当前）的分数全部清零。"""
        target = pid if pid is not None else self.active_id()
        if not target:
            raise ProfileError("no active profile")
        self._apply("profile-clear", id=int(target))

    def group_names(self, pid: int | None = None) -> list[str]:
        """某个预设（默认当前）的组名；空字符串表示用默认名。"""
        profile = self._pick(pid)
        return list(profile.get("group_names", [])) if profile else []

    def get_group_name(self, group: int, pid: int | None = None) -> str:
        """第 group 组（1 起）的自定义组名；没设过返回空串。"""
        names = self.group_names(pid)
        index = int(group) - 1
        return names[index] if 0 <= index < len(names) else ""

    def set_group_name(self, group: int, name: str, pid: int | None = None) -> None:
        """给第 group 组改名；空字符串表示恢复默认组名。"""
        target = pid if pid is not None else self.active_id()
        if not target:
            raise ProfileError("no active profile")
        name = "" if name is None else str(name)
        if len(name.encode("utf-8")) > NAME_BYTES_MAX:
            raise ProfileError("bad group name")
        self._apply("profile-groupname", id=int(target),
                    group=int(group), name=name)

    def draw_counts(self, pid: int | None = None) -> list[int]:
        """某个预设（默认当前）每个名单下标的累计抽取次数。"""
        profile = self._pick(pid)
        return list(profile.get("draw_counts", [])) if profile else []

    def record_draw(self, index: int, total: int, pid: int | None = None) -> None:
        """记一次抽取：名单下标 index 的累计次数变成 total。

        次数只能前进（C++ 侧会拒绝倒退），所以这里直接写新的累计值。
        """
        target = pid if pid is not None else self.active_id()
        if not target:
            raise ProfileError("no active profile")
        self._apply("draw", id=int(target), index=int(index), total=int(total))

    def _pick(self, pid: int | None) -> dict | None:
        return self.get(int(pid)) if pid else self.active()

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
