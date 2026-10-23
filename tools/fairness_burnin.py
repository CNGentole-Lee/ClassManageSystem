"""烧机测试 — 1 万次单抽，回答两个问题：

  1. 长期概率是否真的公平（每个人的抽取次数是否收敛到期望值）
  2. 加权是否真的落地（声明的权重 = 实际抽样频率？偏斜的起点能不能被拉平？）

冷却（默认 10 分钟）是短期过滤器：跨学期长跑时它必然过期，且过期后不留痕迹，
所以长跑模式直接把它关掉，测的是加权本身。另外单独跑一组「真实课间节奏」
（每课 10 抽 + 课前清空历史 + 冷却开启），确认老师的工作流下加权也落地。

关键的一条：测试 4 用 χ² 拟合检验「声明的概率」和「实测频率」是否一致。
这是唯一能证明 `_pick` 真的按 `_weight` 抽签、而不是碰巧看起来均匀的证据。

用法:
    python tools/fairness_burnin.py
"""

import os
import random
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from namepicker.name_engine import NameEngine  # noqa: E402

NAMES = 40
BURNIN = 10_000
LESSON_SIZE = 10
LESSONS = BURNIN // LESSON_SIZE

# χ² 临界值，df=39：p=0.01 → 66.77，p=0.001 → 72.06。取更宽松的 0.001，
# 避免偶发抖动误报，同时真正有偏（χ² 上千）一定被抓住。
CHI2_DF39_P001 = 72.06

failures = []


def check(label, condition, detail=""):
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def note(text):
    print(f"       {text}")


# --- helpers ---

def fresh_engine(n=NAMES, cooldown_seconds=None):
    """A fresh engine over names "1".."n". cooldown_seconds=0 disables cooldown."""
    engine = NameEngine()
    engine.generate_number_list(1, n)
    if cooldown_seconds is not None:
        engine._cooldown_seconds = cooldown_seconds
    return engine


def counts_of(engine, n=NAMES):
    return [engine.get_draw_count(str(i)) for i in range(1, n + 1)]


def spread(counts):
    return max(counts) - min(counts)


def chi_square(observed, expected):
    """χ² = Σ (O-E)²/E."""
    return sum((o - e) ** 2 / e for o, e in zip(observed, expected) if e > 0)


def gini(counts):
    """0 = 完全平均，越大越不均。"""
    xs = sorted(counts)
    n = len(xs)
    total = sum(xs)
    if total == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * cum) / (n * total) - (n + 1) / n


def summarize(counts, expected):
    worst = max(abs(c - expected) for c in counts) / expected
    return (f"{min(counts)}~{max(counts)} draws  σ={statistics.pstdev(counts):.3f}  "
            f"range={spread(counts)}  max deviation={worst:.3%}  Gini={gini(counts):.4f}")


# --- 测试 1：冷启动长跑 ---

def test_long_run():
    print(f"--- Test 1: cold start, {BURNIN} single draws ({NAMES} names, no cooldown) ---")
    engine = fresh_engine(cooldown_seconds=0)
    for _ in range(BURNIN):
        engine.draw_name()

    counts = counts_of(engine)
    expected = BURNIN / NAMES
    print(f"  expected {expected:.0f} per person, actual {summarize(counts, expected)}")

    check("total draw count is correct", sum(counts) == BURNIN, f"{sum(counts)}")
    check("40 names, 10k draws: range <= 2", spread(counts) <= 2, f"range {spread(counts)}")
    check("max deviation < 1%",
          max(abs(c - expected) for c in counts) / expected < 0.01,
          f"{max(abs(c - expected) for c in counts) / expected:.3%}")
    return counts


# --- 测试 2：对照组（纯随机长什么样）---

def test_plain_random_baseline(engine_counts):
    print(f"--- Test 2: baseline - pure random.choice, same {BURNIN} draws ---")
    pool = [str(i) for i in range(1, NAMES + 1)]
    counter = Counter(random.choice(pool) for _ in range(BURNIN))
    counts = [counter[p] for p in pool]
    expected = BURNIN / NAMES
    print(f"  pure random measured   {summarize(counts, expected)}")
    print(f"  this engine measured   {summarize(engine_counts, expected)}")
    note(f"range  pure random {spread(counts)}  ->  this engine {spread(engine_counts)}")
    note(f"Gini  pure random {gini(counts):.4f}  ->  this engine {gini(engine_counts):.4f}")

    check("this engine is clearly more even than pure random (Gini at least 10x smaller)",
          gini(engine_counts) * 10 <= gini(counts),
          f"{gini(engine_counts):.4f} vs {gini(counts):.4f}")


# --- 测试 3：加权是否落地（偏斜起点追赶）---

def test_catch_up():
    print(f"--- Test 3: weighting in action - half the names start 30 draws behind ---")
    engine = fresh_engine(cooldown_seconds=0)
    # 1~20 号先记 30 次（领先组），21~40 号 0 次（落后组）
    engine.set_draw_counts({str(i): (30 if i <= 20 else 0)
                            for i in range(1, NAMES + 1)})
    assert engine.get_total_draws() == 20 * 30

    leaders = {str(i) for i in range(1, 21)}
    seq = [engine.draw_name() for _ in range(1000)]

    first_leader = next((i for i, n in enumerate(seq) if n in leaders), None)
    check("first 500 draws all go to the 20 lagging names (the 0-draw group)",
          all(n not in leaders for n in seq[:500]),
          f"{sum(1 for n in seq[:500] if n in leaders)} of the first 500 draws hit the leading group")
    note(f"the leading group is first drawn at draw {first_leader + 1 if first_leader is not None else '>1000'}"
         f" (the lagging group owes 20 x 30 = 600 draws, catching up first is expected)")

    print(f"  after 1000 draws   {summarize(counts_of(engine), engine.get_total_draws() / NAMES)}")
    check("range shrinks to <= 4 after 1000 draws", spread(counts_of(engine)) <= 4,
          f"range {spread(counts_of(engine))}")
    check("the leading group is not sealed off forever (drawn within 1000 draws)",
          first_leader is not None)


# --- 测试 4：声明的权重 vs 实测频率（χ² 拟合）---

def test_weight_fidelity():
    print("--- Test 4: declared weights = actual sampling frequency? (chi-square goodness of fit) ---")
    trials = 50_000

    # 造一个「温和偏斜」的状态：10 人 0 次 / 10 人 1 次 / 10 人 2 次 / 10 人 3 次。
    # 故意不用极端偏斜 —— χ² 要求每格期望 ≥ 5，极端状态下最冷门的人期望不足 1，
    # 检验就失效了（那种情况放在测试 5 单独看）。
    engine = fresh_engine(cooldown_seconds=0)
    state = {str(i): min(3, (i - 1) // 10) for i in range(1, NAMES + 1)}
    engine.set_draw_counts(state)
    engine._draw_ordinal = 0
    engine._last_draw_ordinal = {}

    pool = engine.get_names()
    theory = engine.get_draw_probabilities()
    tally = Counter(engine._pick(pool) for _ in range(trials))

    obs = [tally.get(n, 0) for n in pool]
    exp = [theory[n] * trials for n in pool]
    chi2 = chi_square(obs, exp)
    hottest = max(pool, key=lambda n: theory[n])
    coldest = min(pool, key=lambda n: theory[n])

    print(f"  theoretical probability {theory[coldest]:.5f} ~ {theory[hottest]:.5f}"
          f" ({theory[hottest] / theory[coldest]:.0f}x apart)")
    print(f"  measured frequency {min(obs) / trials:.5f} ~ {max(obs) / trials:.5f}"
          f" ({min(obs)} ~ {max(obs)} of {trials})")
    note(f"chi2 = {chi2:.2f} (df=39, p=0.001 critical value {CHI2_DF39_P001})")

    check("every expected cell >= 5 (chi-square precondition)", min(exp) >= 5, f"min expected {min(exp):.1f}")
    check("measured frequencies match declared probabilities (chi-square not significant)", chi2 < CHI2_DF39_P001,
          f"χ²={chi2:.2f}")
    check("the coldest name really is the hardest to draw",
          obs[pool.index(coldest)] < obs[pool.index(hottest)],
          f"{obs[pool.index(coldest)]} vs {obs[pool.index(hottest)]}")
    return chi2


# --- 测试 5：真实课间节奏（含冷却 + 课前清空历史）---

def test_lesson_rhythm():
    print(f"--- Test 5: real lesson rhythm - {LESSONS} lessons x {LESSON_SIZE} draws each"
          f" (cooldown on + history cleared before each lesson) ---")
    engine = fresh_engine()          # 默认 600 秒冷却
    short_lessons = 0
    for _ in range(LESSONS):
        engine.clear_history()       # 老师的习惯动作
        engine._per_name_cooldown.clear()
        picked = [engine.draw_name() for _ in range(LESSON_SIZE)]
        if len(picked) != LESSON_SIZE or any(p is None for p in picked) \
                or len(set(picked)) != LESSON_SIZE:
            short_lessons += 1

    counts = counts_of(engine)
    expected = BURNIN / NAMES
    print(f"  expected {expected:.0f} per person, actual {summarize(counts, expected)}")

    check("every lesson is full with no repeats inside it", short_lessons == 0, f"{short_lessons} abnormal lessons")
    check("only 10 draws per lesson for 40 names, so cooldown excludes nobody", short_lessons == 0)
    check("long-run range <= 6 (clearing history does not hurt weighting)", spread(counts) <= 6,
          f"range {spread(counts)}")
    return counts


# --- 测试 6：最近惩罚（不让人连庄）---

def test_recency():
    print("--- Test 6: recency penalty - probability that the same person is drawn twice in a row ---")
    engine = fresh_engine(cooldown_seconds=0)
    names = engine.get_names()

    seq = []
    expected_repeats = 0.0
    prev = None
    for _ in range(BURNIN):
        if prev is not None:
            # 用引擎自己的权重重算「上一个人再次中签」的概率并累加。
            # 实测次数应该落在这个期望值附近 —— 这才证明 _pick 真的按
            # _weight（含 recency 惩罚）抽签，而不是看着像而已。
            max_count = max(engine._draw_counts.get(n, 0) for n in names)
            weights = {n: engine._weight(n, max_count) for n in names}
            expected_repeats += weights[prev] / sum(weights.values())
        prev = engine.draw_name()
        seq.append(prev)

    repeats = sum(1 for a, b in zip(seq, seq[1:]) if a == b)
    rate = repeats / (BURNIN - 1)
    print(f"  adjacent repeats {repeats} (measured rate {rate:.4%})")
    print(f"  expected from the engine weights {expected_repeats:.1f}"
          f", pure-random baseline {1 / NAMES:.2%}")

    check("adjacent repeat rate is below 1/5 of pure random", rate < (1 / NAMES) / 5,
          f"{rate:.4%} vs {1 / NAMES:.2%}")
    check("measured repeats match the weight-based estimate (±40%)",
          abs(repeats - expected_repeats) <= max(5.0, expected_repeats * 0.4),
          f"{repeats} vs {expected_repeats:.1f}")


# --- 测试 7：领先者会被封印多久（行为提示，不是缺陷）---

def test_leader_freeze():
    print("--- Test 7: how long a big leader is left out ---")
    engine = fresh_engine(cooldown_seconds=0)
    engine.set_draw_counts({str(i): (10 if i == 1 else 0)
                            for i in range(1, NAMES + 1)})
    waited = None
    for i in range(1, 2001):
        if engine.draw_name() == "1":
            waited = i
            break
    print(f"  name 1 leads with 10 draws, the other 39 have 0")
    if waited is None:
        note("name 1 is not drawn again within 2000 draws")
    else:
        note(f"name 1 is drawn again only at draw {waited} (roughly after paying back 39 names x 10 draws)")
    check("the leader is eventually drawn (not permanently excluded)", waited is not None, f"{waited}")


def main():
    print(f"Burn-in test: {NAMES} names, {BURNIN} single draws\n")

    counts = test_long_run()
    print()
    test_plain_random_baseline(counts)
    print()
    test_catch_up()
    print()
    test_weight_fidelity()
    print()
    test_lesson_rhythm()
    print()
    test_recency()
    print()
    test_leader_freeze()

    print()
    if failures:
        print(f"failed {len(failures)}: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
