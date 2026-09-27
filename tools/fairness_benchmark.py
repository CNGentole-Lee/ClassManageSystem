"""公平性基准测试 — 验证“加权少抽优先”算法的实际效果.

用法:
    python tools/fairness_benchmark.py

跑两组实验（不需要启动界面，只调用 NameEngine）:

  1. 长期分布 — 40 人抽 400 次，看每人被抽次数是否齐平。
     对照组是纯随机（旧算法），可以直观看到差距。

  2. 单节课重复 — 一节课只抽 10~40 次时，同一人被抽第二次的次数。
     这是学生最容易察觉的“怎么又是他”，所以单独度量。

改了 name_engine.py 里的 FAIRNESS_STRENGTH / RECENT_PENALTY 之后，
重新跑一遍即可看到参数的影响。
"""

import collections
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from namepicker.name_engine import NameEngine  # noqa: E402

NAMES = ["学生%02d" % i for i in range(1, 41)]   # 40 人
TRIALS = 300

# 候选的 FAIRNESS_STRENGTH 取值（name_engine.py 当前用的是 4.0）
STRENGTHS = (2.0, 4.0, 6.0, 9.0)


def draw_with_engine(count, strength=None, penalty=None, names=NAMES):
    """用真实引擎抽 count 次，返回结果列表（测试中关闭冷却）。"""
    engine = NameEngine()
    if strength is not None:
        engine.FAIRNESS_STRENGTH = strength
    if penalty is not None:
        engine.RECENT_PENALTY = penalty
    engine._set_names(names)
    engine._cooldown_seconds = 0          # 基准测试只关心权重，不受冷却影响
    return [engine.draw_name() for _ in range(count)]


def duplicate_count(sequence):
    """重复人次 = 同一人被抽到第 2 次及以上的次数总和（理想为 0）。"""
    counts = collections.Counter(sequence)
    return sum(v - 1 for v in counts.values() if v > 1)


def describe(person_draws):
    """{名字: 被抽次数} → (最少, 最多, 标准差)，衡量各人被抽次数是否齐平。"""
    values = list(person_draws.values())
    lowest, highest = min(values), max(values)
    mean = sum(values) / len(values)
    stddev = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    return lowest, highest, stddev


def experiment_long_run(total_draws=400):
    print("=" * 66)
    print(f"实验 1：长期分布 — {len(NAMES)} 人抽 {total_draws} 次"
          f"（每人理想 {total_draws // len(NAMES)} 次）")
    print("=" * 66)
    print(f"{'算法':<22}{'最少':>6}{'最多':>6}{'极差':>8}{'标准差':>10}")
    print("-" * 66)

    pure = collections.Counter(
        random.choice(NAMES) for _ in range(total_draws)
    )
    lo, hi, sd = describe(pure)
    print(f"{'纯随机(旧)':<22}{lo:>6}{hi:>6}{hi - lo:>8}{sd:>10.2f}")

    for strength in STRENGTHS:
        weighted = collections.Counter(
            draw_with_engine(total_draws, strength=strength)
        )
        lo, hi, sd = describe(weighted)
        marker = "  <- 当前" if strength == NameEngine.FAIRNESS_STRENGTH else ""
        print(f"{('加权少抽 P=' + str(strength)):<22}"
              f"{lo:>6}{hi:>6}{hi - lo:>8}{sd:>10.2f}{marker}")
    print()


def experiment_per_session():
    print("=" * 66)
    print("实验 2：单节课重复情况 — 平均重复人次（越低越好，理想 0）")
    print("=" * 66)
    header = f"{'一节课抽几次':<14}{'纯随机':>10}" + "".join(
        f"{'P=' + str(s):>10}" for s in STRENGTHS
    )
    print(header)
    print("-" * 66)

    for draws in (10, 15, 20, 40):
        pure_total = sum(
            duplicate_count(random.choice(NAMES) for _ in range(draws))
            for _ in range(TRIALS)
        ) / TRIALS
        row = f"{draws:<14}{pure_total:>10.2f}"
        for strength in STRENGTHS:
            weighted_total = sum(
                duplicate_count(draw_with_engine(draws, strength=strength))
                for _ in range(TRIALS)
            ) / TRIALS
            row += f"{weighted_total:>10.2f}"
        print(row)
    print(f"  （name_engine.py 当前使用 FAIRNESS_STRENGTH = "
          f"{NameEngine.FAIRNESS_STRENGTH}）")
    print()


if __name__ == "__main__":
    print()
    experiment_long_run()
    experiment_per_session()
    print(f"（实验 2 每组参数模拟 {TRIALS} 次，取平均）")
