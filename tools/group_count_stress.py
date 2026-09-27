"""小组数量功能的测试 + 压力测试。

覆盖两件事：
  1. 功能 — 改数量 = 整段重来（组名回默认、分数归零），边界夹取，落盘，
     彻底重置后卡片数跟着回到默认；数量没变时不许动分数
  2. 压力 — 反复改组数 × 加减分 × 重建卡片 × 存盘，程序不能崩、文件不能坏

用法:
    python tools/group_count_stress.py
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QPushButton, QScrollArea  # noqa: E402
from PyQt5 import sip  # noqa: E402

from namepicker.config_store import (  # noqa: E402
    DEFAULT_GROUP_COUNT, MAX_GROUP_COUNT, ConfigStore,
)
from namepicker.points_window import DELTAS, GroupCard, PointsWindow  # noqa: E402

failures = []


def check(label, condition, detail=""):
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def cards_match_store(store, points):
    """界面上显示的分数 == 文件里的分数？"""
    stored = [store.get_score(i) for i in range(1, len(points._cards) + 1)]
    shown = [c.score() for c in points._cards]
    return stored == shown, f"{stored} vs {shown}"


def test_defaults(store, points):
    print("--- 默认状态 ---")
    check(f"默认 {DEFAULT_GROUP_COUNT} 个小组",
          len(points._cards) == DEFAULT_GROUP_COUNT, f"实际 {len(points._cards)}")
    check("底栏有 小组数量 按钮",
          any(b.text() == "小组数量..." for b in points.findChildren(QPushButton)))
    check("卡片网格在滚动区域里（大组数放得下）",
          len(points.findChildren(QScrollArea)) == 1)


def test_change_count(store, points):
    print("\n--- 改小组数量 ---")
    applied = store.set_group_count(8)
    points._rebuild_cards()
    check("改成 8 个小组", applied == 8 and len(points._cards) == 8,
          f"applied={applied} cards={len(points._cards)}")
    check("改组数后分数全部归零", all(c.score() == 0 for c in points._cards),
          f"实际 {[c.score() for c in points._cards]}")
    check("改组数后组名回默认",
          [c._name_label.text() for c in points._cards[:2]] == ["第一组", "第二组"],
          f"实际 {[c._name_label.text() for c in points._cards[:3]]}")
    check("改组数后界面与文件一致", *cards_match_store(store, points))

    points.save_now()
    check("小组数量落盘", ConfigStore(points._store.path).group_count == 8,
          f"实际 {ConfigStore(points._store.path).group_count}")

    # 缩小：卡片要跟着减少，且不能留下孤儿控件
    store.set_group_count(4)
    points._rebuild_cards()
    check("缩小到 4 个小组", len(points._cards) == 4, f"实际 {len(points._cards)}")
    check("缩小后界面与文件一致", *cards_match_store(store, points))


def test_scores_are_wiped(store, points):
    print("\n--- 有分数时改组数 → 分数被清空 ---")
    store.set_group_count(6)
    points._rebuild_cards()
    for i in range(1, 7):
        points.apply_delta(i, 3)
    check("改组数前确实有分",
          [c.score() for c in points._cards] == [3] * 6,
          f"实际 {[c.score() for c in points._cards]}")

    store.set_group_count(9)
    points._rebuild_cards()
    check("改组数后 9 张卡全为 0", [c.score() for c in points._cards] == [0] * 9,
          f"实际 {[c.score() for c in points._cards]}")
    check("改组数后文件里的分也清零",
          [store.get_score(i) for i in range(1, 10)] == [0] * 9,
          f"实际 {[store.get_score(i) for i in range(1, 10)]}")
    check("改组数后界面与文件一致", *cards_match_store(store, points))


def test_undo_and_selection(store, points):
    print("\n--- 改组数后撤销栈与选中态 ---")
    store.set_group_count(5)
    points._rebuild_cards()
    points.apply_delta(2, 3)
    check("撤销栈有内容", points._undo_btn.isEnabled())

    store.set_group_count(7)
    points._rebuild_cards()
    # 撤销栈存的是 (组下标, 增量)，改组数后这些下标已经不指同一批小组了
    check("改组数后撤销栈清空", not points._undo_btn.isEnabled())
    check("改组数后选中第 1 组", points._selected_index == 1,
          f"实际 {points._selected_index}")
    check("改组数后第 1 组是展开的", points._cards[0].is_selected())
    check("改组数后只有第 1 组展开",
          sum(1 for c in points._cards if c.is_selected()) == 1)


def test_clamping_and_same_count(store, points):
    print("\n--- 边界夹取 / 数量没变不许动分 ---")
    check("下限夹到 1", store.set_group_count(0) == 1)
    check("负数夹到 1", store.set_group_count(-5) == 1)
    check("上限夹到 24", store.set_group_count(999) == MAX_GROUP_COUNT,
          f"实际 {store.group_count}")
    check("非法值保持原值", store.set_group_count("abc") == store.group_count,
          f"实际 {store.group_count}")

    # 关键：数量没变时不能白清一次分数
    store.set_group_count(6)
    points._rebuild_cards()
    points.apply_delta(1, 3)
    before = store.get_score(1)
    store.set_group_count(6)
    check("数量没变 → 分数不动", store.get_score(1) == before,
          f"{before} -> {store.get_score(1)}")


def test_wipe_returns_to_default(store, points):
    print("\n--- 彻底重置 → 卡片数回到默认 ---")
    store.set_group_count(11)
    points._rebuild_cards()
    check("先改成 11 个小组", len(points._cards) == 11, f"实际 {len(points._cards)}")

    store.reset_all()
    points.reload_from_store()
    check(f"彻底重置后回到 {DEFAULT_GROUP_COUNT} 张卡",
          len(points._cards) == DEFAULT_GROUP_COUNT, f"实际 {len(points._cards)}")
    check("彻底重置后组名回默认",
          points._cards[0]._name_label.text() == "第一组",
          f"实际 {points._cards[0]._name_label.text()!r}")
    check("彻底重置后界面与文件一致", *cards_match_store(store, points))


def test_no_stray_windows(store, points):
    """改组数时旧卡片不能变成独立窗口闪出来。

    可见的控件一旦 setParent(None) 就会变成顶层窗口 —— 每个旧卡片都会在屏幕上
    闪一个独立小窗，直到 deleteLater() 生效。这个回归测试就是为了盯住它。
    """
    print("\n--- 改组数不能闪出独立小窗 ---")
    store.set_group_count(8)
    points._rebuild_cards()
    QApplication.processEvents()
    check("面板可见（否则下面测不出东西）", points.isVisible())

    store.set_group_count(11)
    points._rebuild_cards()          # deleteLater 还没跑，旧卡片此刻仍然活着
    strays = [w for w in QApplication.topLevelWidgets()
              if isinstance(w, GroupCard) and w.isVisible()]
    check("旧卡片没有变成可见的独立窗口", not strays,
          f"闪出 {len(strays)} 个窗口" if strays else "")
    check("新卡片是面板的子控件、不是窗口",
          all(not c.isWindow() for c in points._cards))
    QApplication.processEvents()
    check("事件循环跑完后旧卡片已被回收",
          not [w for w in QApplication.topLevelWidgets()
               if isinstance(w, GroupCard) and w.isVisible()])


def test_stress(store, points):
    print(f"\n--- 压力：反复改组数 × 加减分 × 重建卡片 ---")
    rounds = 300
    for i in range(rounds):
        n = (i % MAX_GROUP_COUNT) + 1
        store.set_group_count(n)
        points._rebuild_cards()
        for _ in range(3):
            points.apply_delta(random.randint(1, n), random.choice(DELTAS))
        points.save_now()
        # deleteLater() 要有事件循环才真正释放控件，否则 300 轮会堆几千张卡
        QApplication.processEvents()

    # 收尾到一个确定状态再断言
    store.set_group_count(MAX_GROUP_COUNT)
    points._rebuild_cards()
    # 每一轮改组数都会清分，所以结尾必须是"清了之后再打分"，否则下面
    # 一致性检查比的是一堆 0，等于什么都没验证。
    for i in range(1, MAX_GROUP_COUNT + 1):
        points.apply_delta(i, (i % 4) + 1)
    points.save_now()

    print(f"  跑了 {rounds} 轮，每轮最多改到 {MAX_GROUP_COUNT} 组")
    check(f"{rounds} 轮后面板没被销毁", not sip.isdeleted(points))
    check(f"{rounds} 轮后是 {MAX_GROUP_COUNT} 张卡",
          len(points._cards) == MAX_GROUP_COUNT, f"实际 {len(points._cards)}")
    check("压力后分数不是全 0（一致性检查才有意义）",
          any(c.score() > 0 for c in points._cards),
          f"实际 {[c.score() for c in points._cards][:6]}…")
    check("压力后界面与文件一致", *cards_match_store(store, points))

    reread = ConfigStore(points._store.path)
    check("压力后 config.ini 仍可解析", reread.group_count == MAX_GROUP_COUNT,
          f"实际 {reread.group_count}")
    check("压力后分数从文件读回来一致",
          [reread.get_score(i) for i in range(1, MAX_GROUP_COUNT + 1)]
          == [c.score() for c in points._cards])

    # 24 组是 8 行 × 200px 卡片，窗口装不下 —— 滚动条必须真的在干活。
    # 布局高度要等事件循环跑一轮才落定，先 pump 一次再量。
    QApplication.processEvents()
    scroll = points.findChildren(QScrollArea)[0]
    content_h = scroll.widget().height()
    viewport_h = scroll.viewport().height()
    print(f"  24 组时内容高 {content_h}px，视口高 {viewport_h}px")
    check("24 组时内容超出视口（滚动条生效）", content_h > viewport_h,
          f"{content_h}px vs {viewport_h}px")
    check("内容高度容得下 8 行卡片（没被视口压扁）",
          content_h >= 8 * 200, f"{content_h}px")

    # 反面：SetMinimumSize 不能让内容的最小高度顶到窗口上，否则 24 组时
    # 窗口会被撑成 1684px 高、比屏幕还高，而且再也缩不小
    points.resize(760, 560)
    QApplication.processEvents()
    hint_h = points.minimumSizeHint().height()
    print(f"  24 组时窗口最小高度提示 {hint_h}px，窗口实际高 {points.height()}px")
    check("24 组不会把窗口顶得缩不小", hint_h <= 700, f"{hint_h}px")
    check("窗口缩到 560 高之后依然能滚动",
          scroll.widget().height() > scroll.viewport().height(),
          f"{scroll.widget().height()} vs {scroll.viewport().height()}")

    # 压力之后面板还得能正常用
    before = points._cards[0].score()
    points.apply_delta(1, 3)
    points.save_now()
    check("压力后仍能加分并落盘",
          ConfigStore(points._store.path).get_score(1) == before + 3,
          f"实际 {ConfigStore(points._store.path).get_score(1)}")


def main():
    app = QApplication(sys.argv)

    tmp_dir = tempfile.mkdtemp()
    config_path = os.path.join(tmp_dir, "config.ini")
    store = ConfigStore(config_path)
    store.reset_scores()

    points = PointsWindow(store)
    points.show()
    app.processEvents()

    test_defaults(store, points)
    test_change_count(store, points)
    test_scores_are_wiped(store, points)
    test_undo_and_selection(store, points)
    test_clamping_and_same_count(store, points)
    test_wipe_returns_to_default(store, points)
    test_no_stray_windows(store, points)
    test_stress(store, points)

    points.close()
    print()
    if failures:
        print(f"失败 {len(failures)} 项: {failures}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
