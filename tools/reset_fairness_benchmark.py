"""
重现教师的工作流程，并衡量长期公平性。
教师在大多数课堂开始时都会清空历史记录。如果这次重置也一并清除了抽取次数，那么每节课都会从零重新开始，加权算法便退化为“每节课随机排列”——同一批学生会在整个学期中反复被较早抽到，而这正是所反映的投诉。
Run:  python tools/reset_fairness_benchmark.py
"""

import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from namepicker.name_engine import NameEngine  # noqa: E402

NAMES = 40
SESSIONS = 20
DRAWS_PER_SESSION = 10
TRIALS = 5


def simulate(keep_counts: bool) -> tuple[list[int], list[int]]:
    """Run `SESSIONS` sessions. Returns (totals_per_person, first_draw_counts)."""
    totals = {}
    first_picks = {}

    for _ in range(TRIALS):
        engine = NameEngine()
        engine.generate_number_list(1, NAMES)
        engine._cooldown_seconds = 1  # 各次会话间隔数小时：冷却期已结束

        for _session in range(SESSIONS):
            # 教师在每节课开始时都会清空历史记录。
            if keep_counts:
                # 修正后的语义：`clear_history()` 会保留累计计数，
                # 它只会删除历史记录表和冷却状态。
                engine.clear_history()
            else:
                # 旧语义：重置也会一并清除累计计数。
                engine.reset_fairness()
            # 真实的一节课是在上一节课至少10分钟之后，因此到下一节课开始时，所有冷却都已经过期。
            engine._per_name_cooldown.clear()

            drawn = engine.draw_names(DRAWS_PER_SESSION)
            for name in drawn:
                totals[name] = totals.get(name, 0) + 1
            if drawn:
                first_picks[drawn[0]] = first_picks.get(drawn[0], 0) + 1

    counts = [totals.get(str(i), 0) for i in range(1, NAMES + 1)]
    firsts = [first_picks.get(str(i), 0) for i in range(1, NAMES + 1)]
    return counts, firsts


def describe(label: str, counts: list[int]) -> None:
    total = sum(counts)
    never = sum(1 for c in counts if c == 0)
    print(f"  {label:<22} total_draws={total:<5} each {min(counts)}~{max(counts)} draws "
          f"σ={statistics.pstdev(counts):.2f}  never_drawn={never}")


def main() -> int:
    expected = SESSIONS * DRAWS_PER_SESSION * TRIALS / NAMES
    print(f"Simulating {TRIALS} trials × {SESSIONS} sessions × {DRAWS_PER_SESSION} draws per session "
          f"({NAMES} names, ideal ≈ {expected:.0f} per person)\n")

    print("After clearing history before every session:")
    cur_counts, cur_firsts = simulate(keep_counts=False)
    describe("current behaviour", cur_counts)
    print(f"    times drawn first: {min(cur_firsts)}~{max(cur_firsts)} "
          f"σ={statistics.pstdev(cur_firsts):.2f}")

    fixed_counts, fixed_firsts = simulate(keep_counts=True)
    describe("with long-term counts kept", fixed_counts)
    print(f"    times drawn first: {min(fixed_firsts)}~{max(fixed_firsts)} "
          f"σ={statistics.pstdev(fixed_firsts):.2f}")

    print("\nConclusion:")
    spread_now = max(cur_counts) - min(cur_counts)
    spread_fix = max(fixed_counts) - min(fixed_counts)
    print(f"  spread of per-person totals:  now {spread_now}  ->  after fix {spread_fix}")
    if spread_fix < spread_now:
        print("  >>> Keeping draw counts long-term does even out the distribution; issue confirmed")
        return 0
    print("  >>> No improvement; needs re-analysis")
    return 1


if __name__ == "__main__":
    sys.exit(main())
