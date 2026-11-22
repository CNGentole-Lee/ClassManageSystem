"""分组权重检查 — 验证「多次单抽不会全落在同一组」。

用法:
    TMPDIR=$PWD/.tmptest python tools/group_check.py

背景：化学课分组计分，6 次单抽如果全抽到同一个组，那组一口气 +6 分，
别的组再也追不上。这里用真实 NameEngine 验证加上组权重后不会发生。

所有数字都是模拟出来的，不读也不写任何用户数据。
"""

import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from namepicker.name_engine import NameEngine  # noqa: E402

failures = []

GROUPS = 4
PER_GROUP = 10
LESSON_DRAWS = 10
LESSONS = 40
ROUNDS = 30

#: 单课某组最多应该占多少人次：⌈10/4⌉ + 1 = 4
BOUND = -(-LESSON_DRAWS // GROUPS) + 1


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def build(grouped: bool):
    """返回 (名字列表, 组员表)。组员表始终构造出来，只是分组时才交给引擎。"""
    names = [f"学生{g}{i:02d}" for g in range(1, GROUPS + 1) for i in range(1, PER_GROUP + 1)]
    group_of = {name: g for g in range(1, GROUPS + 1)
                for name in names[(g - 1) * PER_GROUP: g * PER_GROUP]}
    return names, group_of


def fresh(grouped: bool):
    names, group_of = build(grouped)
    engine = NameEngine()
    engine._set_names(names)
    engine._cooldown_seconds = 0        # 只测权重，不受个人冷却影响
    if grouped:
        engine.set_group_map(group_of)
    return engine, group_of


def simulate(grouped: bool, rounds: int = ROUNDS):
    """返回 (单课同组最大人次列表, 组间标准差/平均列表, 最长连串列表)。"""
    names, group_of = build(grouped)
    worst, spreads, streaks = [], [], []
    for _ in range(rounds):
        engine, _ = fresh(grouped)
        for _lesson in range(LESSONS):
            engine.clear_history()
            picked = [engine.draw_name() for _ in range(LESSON_DRAWS)]
            per_group = Counter(group_of[n] for n in picked)
            # 即使不分组也照样统计：组员表在内存里，只是没有交给引擎
            worst.append(max(per_group.values()))
            seq = [group_of[n] for n in picked]
            best = cur = 1
            for i in range(1, len(seq)):
                cur = cur + 1 if seq[i] == seq[i - 1] else 1
                best = max(best, cur)
            streaks.append(best)
        if grouped:
            gc = list(engine.get_group_counts().values())
            mean = statistics.mean(gc)
            spreads.append(statistics.pstdev(gc) / mean if mean else 0.0)
    return worst, spreads or [0.0], streaks


def main() -> int:
    print(f"场景：{GROUPS} 组 × {PER_GROUP} 人，每课 {LESSON_DRAWS} 抽，"
          f"{LESSONS} 课，{ROUNDS} 轮\n")

    plain_worst, _, plain_streaks = simulate(grouped=False)
    print("--- 1. 不分组（现状）作对照 ---")
    print(f"       单课同组最大人次 均值 {statistics.mean(plain_worst):.2f}  "
          f"p95 {sorted(plain_worst)[int(len(plain_worst) * 0.95)]}  "
          f"最大 {max(plain_worst)}")
    print(f"       最长连串 均值 {statistics.mean(plain_streaks):.2f}  最大 {max(plain_streaks)}")
    check("对照组确实会出现「一组吃掉一半名额」（说明这不是伪问题）",
          max(plain_worst) >= 5, f"max {max(plain_worst)}")

    worst, spreads, streaks = simulate(grouped=True)
    p95 = sorted(worst)[int(len(worst) * 0.95)]
    print("\n--- 2. 分组权重生效 ---")
    print(f"       单课同组最大人次 均值 {statistics.mean(worst):.2f}  "
          f"p95 {p95}  最大 {max(worst)}")
    print(f"       最长连串        均值 {statistics.mean(streaks):.2f}  最大 {max(streaks)}")
    print(f"       组间σ/μ         均值 {statistics.mean(spreads):.4f}")
    check(f"单课同组 p95 <= {BOUND}", p95 <= BOUND, f"p95 {p95}")
    check("单课同组最大人次 <= 6（极端兜底）", max(worst) <= 6, f"max {max(worst)}")
    check("连续同一组最多 3 次", max(streaks) <= 3, f"max {max(streaks)}")
    check("组间σ/μ < 1%", statistics.mean(spreads) < 0.01,
          f"{statistics.mean(spreads):.4f}")
    check("分组后比不分组明显更均匀",
          statistics.mean(worst) < statistics.mean(plain_worst),
          f"{statistics.mean(worst):.2f} < {statistics.mean(plain_worst):.2f}")

    print("\n--- 3. 个人公平性没有被组权重压坏 ---")
    names, group_of = build(True)
    reps = []
    for _ in range(ROUNDS):
        engine, _ = fresh(True)
        seq = [engine.draw_name() for _ in range(40)]
        reps.append(sum(v - 1 for v in Counter(seq).values() if v > 1))
    print(f"       40 人 40 抽重复人次 均值 {statistics.mean(reps):.2f}")
    check("个人重复人次 <= 7（现状基准 5.6 附近）", statistics.mean(reps) <= 7,
          f"{statistics.mean(reps):.2f}")

    print("\n--- 4. 关掉分组后行为完全不变 ---")
    engine_plain, _ = fresh(False)
    check("没有分组时组权重不参与计算", engine_plain.get_group_counts() == {})
    engine_grouped, _ = fresh(True)
    engine_grouped.set_group_map({})
    check("set_group_map({}) 回到不分组",
          engine_grouped.get_group_counts() == {} and engine_grouped.get_group_map() == {})

    print("\n--- 5. 组惩罚按间隔区分 ---")
    engine, gmap = fresh(True)
    check("从未被抽过的组没有惩罚", engine._group_penalty(1) == 1.0)
    first = next(n for n in engine.get_names() if gmap[n] == 1)
    engine._record(first, 0.0)
    check("刚被抽过的组（gap 0）重罚",
          engine._group_penalty(1) == NameEngine.GROUP_PENALTY_ADJACENT,
          str(engine._group_penalty(1)))
    other = next(n for n in engine.get_names() if gmap[n] == 2)
    engine._record(other, 0.0)
    check("隔一次（gap 1）仍是重罚",
          engine._group_penalty(1) == NameEngine.GROUP_PENALTY_ADJACENT,
          str(engine._group_penalty(1)))
    engine._record(other, 0.0)
    check("隔两次（gap 2）普通罚",
          engine._group_penalty(1) == NameEngine.GROUP_PENALTY_GAP,
          str(engine._group_penalty(1)))
    engine._record(other, 0.0)
    check("隔三次以上不罚", engine._group_penalty(1) == 1.0,
          str(engine._group_penalty(1)))

    print("\n--- 6. 组权重强于个人权重 ---")
    check("GROUP_STRENGTH > FAIRNESS_STRENGTH",
          NameEngine.GROUP_STRENGTH > NameEngine.FAIRNESS_STRENGTH,
          f"{NameEngine.GROUP_STRENGTH} > {NameEngine.FAIRNESS_STRENGTH}")

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
