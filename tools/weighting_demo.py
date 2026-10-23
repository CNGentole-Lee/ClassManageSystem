import sys, random, collections
sys.path.insert(0, ".")
from namepicker.name_engine import NameEngine

NAMES = [f"学生{i:02d}" for i in range(1, 41)]   # 40 人
DRAWS = 400                                       # 每人期望 10 次

# --- 新算法：加权少抽优先 ---
e = NameEngine()
e._set_names(NAMES)
e._cooldown_seconds = 0        # 测试中关闭冷却，只看权重效果
for _ in range(DRAWS):
    e.draw_name()
fair = collections.Counter(e.get_draw_counts().values())

# --- 旧算法：纯随机（对照） ---
pure = collections.Counter()
for _ in range(DRAWS):
    pure[random.choice(NAMES)] += 1
purec = collections.Counter(pure.values())

def report(title, counts):
    lo, hi = min(counts), max(counts)
    tot = sum(k*v for k, v in counts.items())
    mean = tot / sum(counts.values())
    var = sum(v*(k-mean)**2 for k, v in counts.items()) / sum(counts.values())
    print(f"{title}: min={lo} max={hi} range={hi-lo} sd={var**0.5:.2f}")
    print("        distribution", dict(sorted(counts.items())))

print(f"40 people, {DRAWS} draws (ideal 10 each)")
print("=" * 60)
report("weighted least-drawn (new)", fair)
print()
report("pure random       (old)", purec)

# 逐轮检查：每轮 40 次内是否基本每人恰好一次
print()
print("=" * 60)
e2 = NameEngine(); e2._set_names(NAMES); e2._cooldown_seconds = 0
seq = [e2.draw_name() for _ in range(160)]
for r in range(4):
    chunk = seq[r*40:(r+1)*40]
    dup = [n for n, c in collections.Counter(chunk).items() if c > 1]
    print(f"round {r+1} (40 draws): people drawn more than once={len(dup)}  {dup[:5]}")
