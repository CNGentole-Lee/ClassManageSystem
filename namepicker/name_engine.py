"""NameEngine —— 名单加载、公平加权抽取、每人冷却。

为什么不用纯随机：
    ``random.choice`` 对「每一次」抽取是均匀的，但对「每个学生一学期」不是。
    40 人里有人被抽两次、有人一次没抽到很常见（聚集现象），学生看到的就是
    "老抽他"，即使单次抽取本身是公平的。

加权少抽优先模型：
    每个名字带一个长期抽取次数，概率权重为

        weight = (max_count - count + 1) ** FAIRNESS_STRENGTH
                 * recency_penalty

    落后越多权重越高，各人的次数因此收敛而不是发散。顺序从不确定 ——
    落后的人只是概率更高、不是必然，抽签仍是随机的。每人冷却仍是硬性过滤。
"""

import random
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from .i18n import tr


class NameEngine(QObject):
    """非界面逻辑：加载名单、公平抽取、每人冷却、统计。"""

    # --- 公平性参数 ---
    # FAIRNESS_STRENGTH 由 tools/fairness_benchmark.py 选值，该脚本模拟 40 人名单。
    # 每节课 40 次抽取的重复人数（越低越好）：
    #     纯随机 14.4 | P=2 9.3 | P=4 5.6 | P=6 2.5 | P=9 0.3
    # P=9 实际退化成严格轮换，失去了随机感；P=4 能让常规的 10~15 次课堂抽取
    # 基本不重复（重复 0.04~0.15 人次），同时仍是真随机。改这个值后请重跑该脚本。
    FAIRNESS_STRENGTH = 4.0   # 往最少被抽的人身上拉多狠
    RECENT_GAP = 4            # 最近 N 次内被抽过，权重打折
    RECENT_PENALTY = 0.35     # 刚被抽过的人的权重下限（避免连庄）
    MIN_WEIGHT = 0.01         # 保证每个有资格的人仍可被抽中

    # --- 分组（仅当前预设启用分组时生效，无预设时这些值完全不参与计算）---
    # 组权重必须大过个人：否则连续几次单抽全落在同一组，那组一口气多拿好几分，
    # 别组追不回来。两者相乘，真正的「组间优先」倍数是
    # R = GROUP_STRENGTH / FAIRNESS_STRENGTH（8/4 = 2：组间差 1 次 ≈ 组内差 2 次）。
    # tools/fairness_benchmark.py 的「分组」一节验证过这些取值。
    GROUP_STRENGTH = 8.0      # 组权重强度，必须 > FAIRNESS_STRENGTH
    GROUP_STREAK_LOOKBACK = 12   # 回溯最近多少次单抽来算 gap
    GROUP_PENALTY_ADJACENT = 0.05  # gap <= 1（同一组连着被抽）：重罚
    GROUP_PENALTY_GAP = 0.35       # gap == 2：普通罚；gap > 2 不罚

    # --- 信号 ---
    name_drawn = Signal(str)          # (name) —— 滚动结束后的最终结果
    rolling_start = Signal(str)       # (name) —— 引擎选中，开始滚动动画
    names_drawn = Signal(list)        # (list[str]) —— 连抽结果
    multi_rolling_start = Signal(list)  # (list[str]) —— 连抽开始滚动
    names_loaded = Signal(int)        # (count)
    error_occurred = Signal(str)      # (message)
    history_cleared = Signal()
    pool_refilled = Signal(int)       # (pool_size) —— 全员抽完一轮
    cooldowns_updated = Signal()      # 每人冷却变化（供界面刷新）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._names: list[str] = []
        self._history: list[tuple[str, datetime]] = []
        self._cooldown_seconds: int = 600            # 每人冷却秒数（可配置）
        self._per_name_cooldown: dict[str, float] = {}  # name -> 可再抽的时间戳

        # --- 驱动加权公平性的统计 ---
        self._draw_counts: dict[str, int] = {}       # name -> 长期抽取次数
        self._last_draw_ordinal: dict[str, int] = {} # name -> 上次被抽时的序号
        self._draw_ordinal: int = 0                  # 本次会话已抽总次数
        self._last_round_min: int = 0                # 上一轮抽完后的最低次数

        # --- 分组（课堂预设）---
        # name -> 组号（1..N）；空字典 = 这节课不分组，权重复原成纯个人。
        self._group_of: dict[str, int] = {}
        self._group_history: list[int] = []         # 最近被抽中的组号序列

    # --- 名单来源 ---

    def load_names_from_file(self, filepath: str) -> bool:
        """加载 UTF-8 文本文件，一行一个名字，跳过 # 注释和空行。"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                names = [
                    line.strip() for line in f
                    if line.strip() and not line.strip().startswith('#')
                ]
        except FileNotFoundError:
            self.error_occurred.emit(tr("文件不存在: {p}", "File not found: {p}", p=filepath))
            return False
        except PermissionError:
            self.error_occurred.emit(tr("没有权限读取文件: {p}", "Permission denied: {p}", p=filepath))
            return False
        except UnicodeDecodeError:
            self.error_occurred.emit(tr("文件编码不是 UTF-8，请用 UTF-8 保存名单文件。",
                                        "The file is not UTF-8. Please save the name list as UTF-8."))
            return False
        except OSError as e:
            self.error_occurred.emit(tr("读取文件失败: {e}", "Failed to read file: {e}", e=e))
            return False

        if not names:
            self.error_occurred.emit(tr("文件中没有找到任何名字。", "No names found in the file."))
            return False

        self._set_names(names)
        return True

    def generate_number_list(self, start: int, end: int) -> None:
        """生成从 start 到 end（含两端）的数字名单。"""
        if start > end:
            start, end = end, start
        self._set_names([str(i) for i in range(start, end + 1)])

    def _set_names(self, names: list[str]) -> None:
        self._names = list(names)
        self._history.clear()
        self._per_name_cooldown.clear()
        self._draw_counts = {}
        self._last_draw_ordinal = {}
        self._draw_ordinal = 0
        self._last_round_min = 0

        self.names_loaded.emit(len(self._names))
        self.history_cleared.emit()
        self.cooldowns_updated.emit()

    # --- 抽取 ---

    def draw_name(self) -> str | None:
        """抽一个人 —— 偏向抽得最少的，冷却中的除外。"""
        picked = self._pick_many(1)
        if not picked:
            return None

        self.rolling_start.emit(picked[0])
        self.name_drawn.emit(picked[0])
        self.cooldowns_updated.emit()
        return picked[0]

    def draw_names(self, count: int) -> list[str]:
        """连抽 —— 一次抽出最多 count 个互不重复的名字。

        与单抽使用同一套公平加权和冷却规则，逐个抽取，所以连抽不会同一个人
        出两次。剩余候选全部在冷却中时，返回的数量少于 count。
        """
        picked = self._pick_many(count)
        if picked:
            self.multi_rolling_start.emit(picked)
            self.names_drawn.emit(picked)
            self.cooldowns_updated.emit()
        return picked

    def _pick_many(self, count: int) -> list[str]:
        """抽取并记录最多 count 个互不重复的名字，成功时不发信号。"""
        if not self._names:
            self.error_occurred.emit(tr("请先加载名单文件。", "Load a name list first."))
            return []

        now = time.time()
        picked: list[str] = []
        for _ in range(max(1, int(count))):
            available = [
                n for n in self._names
                if self._per_name_cooldown.get(n, 0) <= now
            ]
            if not available:
                break
            name = self._pick(available)
            self._record(name, now)
            picked.append(name)

        if not picked:
            self._report_all_cooling(now)
        return picked

    def _record(self, name: str, now: float) -> None:
        """为一个被抽中的名字写入冷却、历史和公平性统计。"""
        self._per_name_cooldown[name] = now + self._cooldown_seconds
        self._history.append((name, datetime.now()))

        self._draw_ordinal += 1
        self._draw_counts[name] = self._draw_counts.get(name, 0) + 1
        self._last_draw_ordinal[name] = self._draw_ordinal

        group = self._group_of.get(name)
        if group:
            self._group_history.append(group)
            if len(self._group_history) > self.GROUP_STREAK_LOOKBACK * 2:
                del self._group_history[:-self.GROUP_STREAK_LOOKBACK]

        # 轮次边界：现在每个人都至少被抽了 new_min 次
        new_min = min(self._draw_counts.get(n, 0) for n in self._names)
        if new_min > self._last_round_min:
            self._last_round_min = new_min
            self.pool_refilled.emit(len(self._names))

    def _report_all_cooling(self, now: float) -> None:
        """无人可抽时，提示最快哪个名字冷却结束。"""
        best_name = min(
            self._names, key=lambda n: self._per_name_cooldown.get(n, 0)
        )
        wait_secs = max(0, int(self._per_name_cooldown.get(best_name, 0) - now))
        wait_m = wait_secs // 60
        wait_s = wait_secs % 60
        self.error_occurred.emit(
            tr("所有名字都在冷却中！\n最快可用：{n}（{m}分{s:02d}秒后）",
               "All names are cooling down!\nNext available: {n} (in {m}m {s:02d}s)",
               n=best_name, m=wait_m, s=wait_s)
        )

    def _pick(self, pool: list[str]) -> str:
        """从 pool 中按权重选一个，偏向抽得最少的。"""
        if len(pool) == 1:
            return pool[0]

        max_count = max(self._draw_counts.get(n, 0) for n in self._names)
        weights = [self._weight(n, max_count) for n in pool]

        total = sum(weights)
        if total <= 0:
            return random.choice(pool)

        threshold = random.random() * total
        cumulative = 0.0
        for name, weight in zip(pool, weights):
            cumulative += weight
            if threshold <= cumulative:
                return name
        return pool[-1]

    def _weight(self, name: str, max_count: int) -> float:
        """概率权重：落后越多越高，最近被抽过的打折。"""
        deficit = max_count - self._draw_counts.get(name, 0)
        weight = (deficit + 1.0) ** self.FAIRNESS_STRENGTH

        last = self._last_draw_ordinal.get(name)
        if last is not None:
            gap = self._draw_ordinal - last
            if gap < self.RECENT_GAP:
                # 权重随间隔线性恢复到满值，让同一个人不太可能连续两次被抽中。
                ratio = gap / self.RECENT_GAP
                weight *= self.RECENT_PENALTY + (1.0 - self.RECENT_PENALTY) * ratio

        if self._group_of:
            weight *= self._group_weight(name)
            group = self._group_of.get(name)
            # 只有被抽中过的组才有「上次被抽」可言；没抽过的组满权重。
            if group and group in self._group_history:
                weight *= self._group_penalty(group)

        return max(weight, self.MIN_WEIGHT)

    # --- 分组权重 ---

    def _group_counts(self) -> dict[int, int]:
        """{组号: 被抽总次数}。由个人次数累加得出，不单独存。"""
        out: dict[int, int] = {}
        for name, group in self._group_of.items():
            out[group] = out.get(group, 0) + self._draw_counts.get(name, 0)
        return out

    def _group_weight(self, name: str) -> float:
        """落后越多的组权重越高。指数换成 GROUP_STRENGTH/FAIRNESS_STRENGTH，
        这样它和个人权重乘在一起时，倍数是可解释的。"""
        group = self._group_of.get(name)
        if not group:
            return 1.0
        counts = self._group_counts()
        if not counts:
            return 1.0
        deficit = max(counts.values()) - counts.get(group, 0)
        return (deficit + 1.0) ** (self.GROUP_STRENGTH / self.FAIRNESS_STRENGTH)

    def _group_penalty(self, group: int) -> float:
        """按「距离上一次本组被抽隔了几次」给惩罚。

        gap 0/1 = 连着被抽（最该压）；gap 2 = 挨得近；gap > 2 = 正常轮换，不罚。
        这与个人 recency 是同一套思路，只是组的影响更大。
        """
        window = self._group_history[-self.GROUP_STREAK_LOOKBACK:]
        for back, hit in enumerate(reversed(window)):
            if hit == group:
                if back <= 1:
                    return self.GROUP_PENALTY_ADJACENT
                if back == 2:
                    return self.GROUP_PENALTY_GAP
                return 1.0
        return 1.0

    def get_draw_probabilities(self) -> dict[str, float]:
        """每人当前的抽取概率 —— 供界面的公平性视图使用。"""
        now = time.time()
        available = [
            n for n in self._names
            if self._per_name_cooldown.get(n, 0) <= now
        ]
        if not available:
            return {}

        max_count = max(self._draw_counts.get(n, 0) for n in self._names)
        weights = {n: self._weight(n, max_count) for n in available}
        total = sum(weights.values())
        if total <= 0:
            return {n: 1.0 / len(available) for n in available}
        return {n: w / total for n, w in weights.items()}

    # --- 配置 ---

    def set_cooldown(self, minutes: int) -> None:
        """设置每人冷却时长（分钟）。"""
        self._cooldown_seconds = max(1, minutes) * 60

    def get_cooldown_seconds(self) -> int:
        return self._cooldown_seconds

    # --- 状态查询 ---

    def get_per_name_cooldowns(self) -> dict[str, int]:
        """返回当前冷却中的名字及剩余秒数 {name: remaining_seconds}。"""
        now = time.time()
        return {
            name: max(0, int(ts - now))
            for name, ts in self._per_name_cooldown.items()
            if ts > now
        }

    def get_names(self) -> list[str]:
        return list(self._names)

    def get_history(self) -> list[tuple[str, str]]:
        """返回历史记录，[(name, timestamp_str)]，新的在前。"""
        return [(name, dt.strftime('%Y-%m-%d %H:%M:%S'))
                for name, dt in reversed(self._history)]

    def clear_history(self) -> None:
        """清空抽取历史与冷却状态，但**保留**长期抽取次数。

        长期次数是加权（少抽优先）唯一的依据，而老师每节课前都会清一次历史。
        如果连次数一起清掉，每节课都从零开始加权，一学期下来同几个人反复被抽，
        加权就失去了作用。
        """
        self._history.clear()
        self._per_name_cooldown.clear()
        # 这两个必须一起清：recency 惩罚算的是 gap = _draw_ordinal - _last_draw_ordinal，
        # 只清前者会让 gap 变成负数，权重先被算成负数、再被 MIN_WEIGHT 截到下限。
        self._last_draw_ordinal = {}
        self._draw_ordinal = 0
        # 轮次记录跟随保留下来的次数走，否则会误报"全员已抽过一轮"。
        self._last_round_min = (
            min(self._draw_counts.values()) if self._draw_counts else 0
        )
        self.history_cleared.emit()
        self.cooldowns_updated.emit()

    def clear_draw_counts(self) -> None:
        """只清长期抽取次数，保留抽取历史与冷却（选择性重置用）。"""
        self._draw_counts = {}
        self._last_round_min = 0
        self.cooldowns_updated.emit()

    def reset_fairness(self) -> None:
        """连长期抽取次数一起清零（新学期 / 换班级 / 彻底重置）。"""
        self._draw_counts = {}
        self.clear_history()

    def get_remaining_count(self) -> int:
        """当前公平轮次里还没轮到的人数。"""
        if not self._names:
            return 0
        min_count = min(self._draw_counts.get(n, 0) for n in self._names)
        return sum(
            1 for n in self._names if self._draw_counts.get(n, 0) == min_count
        )

    def get_total_count(self) -> int:
        return len(self._names)

    def is_numeric_list(self) -> bool:
        """名单是否全是数字（数字范围模式）。"""
        if not self._names:
            return True  # 空名单视为数字模式
        return all(s.lstrip('-').isdigit() for s in self._names)

    # --- 统计（持久化到事件链，让公平性跨重启保留）---

    def get_draw_counts(self) -> dict[str, int]:
        """当前名单每人的长期抽取次数 {name: lifetime draws}。"""
        return {
            name: self._draw_counts.get(name, 0)
            for name in self._names
        }

    def set_draw_counts(self, counts: dict[str, int]) -> None:
        """恢复已保存的次数；名单外的名字忽略，缺失的记为 0。"""
        self._draw_counts = {}
        for name in self._names:
            try:
                value = int(counts.get(name, 0))
            except (TypeError, ValueError):
                value = 0
            self._draw_counts[name] = max(0, value)
        self._last_round_min = (
            min(self._draw_counts.values()) if self._draw_counts else 0
        )
        self.cooldowns_updated.emit()

    def get_draw_count(self, name: str) -> int:
        return self._draw_counts.get(name, 0)

    def get_total_draws(self) -> int:
        return sum(self._draw_counts.values())

    # --- 分组配置（由 main.py 在切换预设时调用）---

    def set_group_map(self, group_of: dict[str, int] | None) -> None:
        """设定「学生 → 组号」。传空字典 = 不分组，权重复原成纯个人。

        只影响权重，不动任何统计：切换预设不会把已经积累的抽取次数打乱。
        """
        self._group_of = {k: int(v) for k, v in (group_of or {}).items() if int(v) > 0}
        self._group_history = [g for g in self._group_history if g in set(self._group_of.values())]

    def get_group_map(self) -> dict[str, int]:
        return dict(self._group_of)

    def get_group_counts(self) -> dict[int, int]:
        """{组号: 被抽总次数}；不分组时为空。"""
        return self._group_counts() if self._group_of else {}

    def get_group_history(self) -> list[int]:
        """最近被抽中的组号，供界面/测试检查轮换情况。"""
        return list(self._group_history)
