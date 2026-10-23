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

from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()  # 测试数据不写进真实的隐蔽备份（Windows 注册表 / macOS plist）

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
    print("--- Default state ---")
    check(f"{DEFAULT_GROUP_COUNT} groups by default",
          len(points._cards) == DEFAULT_GROUP_COUNT, f"actual {len(points._cards)}")
    check("bottom bar has a Group count button",
          any(b.text() == "小组数量..." for b in points.findChildren(QPushButton)))
    check("card grid lives in a scroll area (many groups fit)",
          len(points.findChildren(QScrollArea)) == 1)


def test_change_count(store, points):
    print("\n--- Changing the group count ---")
    applied = store.set_group_count(8)
    points._rebuild_cards()
    check("changed to 8 groups", applied == 8 and len(points._cards) == 8,
          f"applied={applied} cards={len(points._cards)}")
    check("all scores reset to zero after count change", all(c.score() == 0 for c in points._cards),
          f"actual {[c.score() for c in points._cards]}")
    check("group names back to defaults after count change",
          [c._name_label.text() for c in points._cards[:2]] == ["第一组", "第二组"],
          f"actual {[c._name_label.text() for c in points._cards[:3]]}")
    check("UI matches file after count change", *cards_match_store(store, points))

    points.save_now()
    check("group count persisted", ConfigStore(points._store.path).group_count == 8,
          f"actual {ConfigStore(points._store.path).group_count}")

    # 缩小：卡片要跟着减少，且不能留下孤儿控件
    store.set_group_count(4)
    points._rebuild_cards()
    check("shrunk to 4 groups", len(points._cards) == 4, f"actual {len(points._cards)}")
    check("UI matches file after shrinking", *cards_match_store(store, points))


def test_scores_are_wiped(store, points):
    print("\n--- Changing count with scores present -> scores wiped ---")
    store.set_group_count(6)
    points._rebuild_cards()
    for i in range(1, 7):
        points.apply_delta(i, 3)
    check("scores really exist before the count change",
          [c.score() for c in points._cards] == [3] * 6,
          f"actual {[c.score() for c in points._cards]}")

    store.set_group_count(9)
    points._rebuild_cards()
    check("all 9 cards are 0 after the count change", [c.score() for c in points._cards] == [0] * 9,
          f"actual {[c.score() for c in points._cards]}")
    check("scores in the file are also zeroed after the count change",
          [store.get_score(i) for i in range(1, 10)] == [0] * 9,
          f"actual {[store.get_score(i) for i in range(1, 10)]}")
    check("UI matches file after count change", *cards_match_store(store, points))


def test_undo_and_selection(store, points):
    print("\n--- Undo stack and selection after a count change ---")
    store.set_group_count(5)
    points._rebuild_cards()
    points.apply_delta(2, 3)
    check("undo stack has content", points._undo_btn.isEnabled())

    store.set_group_count(7)
    points._rebuild_cards()
    # 撤销栈存的是 (组下标, 增量)，改组数后这些下标已经不指同一批小组了
    check("undo stack cleared after count change", not points._undo_btn.isEnabled())
    check("group 1 selected after count change", points._selected_index == 1,
          f"actual {points._selected_index}")
    check("group 1 is expanded after count change", points._cards[0].is_selected())
    check("only group 1 is expanded after count change",
          sum(1 for c in points._cards if c.is_selected()) == 1)


def test_clamping_and_same_count(store, points):
    print("\n--- Clamping / unchanged count must not touch scores ---")
    check("lower bound clamps to 1", store.set_group_count(0) == 1)
    check("negatives clamp to 1", store.set_group_count(-5) == 1)
    check("upper bound clamps to 24", store.set_group_count(999) == MAX_GROUP_COUNT,
          f"actual {store.group_count}")
    check("invalid value keeps the current count", store.set_group_count("abc") == store.group_count,
          f"actual {store.group_count}")

    # 关键：数量没变时不能白清一次分数
    store.set_group_count(6)
    points._rebuild_cards()
    points.apply_delta(1, 3)
    before = store.get_score(1)
    store.set_group_count(6)
    check("count unchanged -> scores untouched", store.get_score(1) == before,
          f"{before} -> {store.get_score(1)}")


def test_wipe_returns_to_default(store, points):
    print("\n--- Full reset -> card count back to default ---")
    store.set_group_count(11)
    points._rebuild_cards()
    check("first change to 11 groups", len(points._cards) == 11, f"actual {len(points._cards)}")

    store.reset_all()
    points.reload_from_store()
    check(f"back to {DEFAULT_GROUP_COUNT} cards after full reset",
          len(points._cards) == DEFAULT_GROUP_COUNT, f"actual {len(points._cards)}")
    check("group names back to defaults after full reset",
          points._cards[0]._name_label.text() == "第一组",
          f"actual {points._cards[0]._name_label.text()!r}")
    check("UI matches file after full reset", *cards_match_store(store, points))


def test_no_stray_windows(store, points):
    """改组数时旧卡片不能变成独立窗口闪出来。

    可见的控件一旦 setParent(None) 就会变成顶层窗口 —— 每个旧卡片都会在屏幕上
    闪一个独立小窗，直到 deleteLater() 生效。这个回归测试就是为了盯住它。
    """
    print("\n--- Count change must not flash stray top-level windows ---")
    store.set_group_count(8)
    points._rebuild_cards()
    QApplication.processEvents()
    check("panel is visible (otherwise the checks below are meaningless)", points.isVisible())

    store.set_group_count(11)
    points._rebuild_cards()          # deleteLater 还没跑，旧卡片此刻仍然活着
    strays = [w for w in QApplication.topLevelWidgets()
              if isinstance(w, GroupCard) and w.isVisible()]
    check("old cards did not become visible top-level windows", not strays,
          f"{len(strays)} stray windows" if strays else "")
    check("new cards are children of the panel, not windows",
          all(not c.isWindow() for c in points._cards))
    QApplication.processEvents()
    check("old cards are gone after the event loop runs",
          not [w for w in QApplication.topLevelWidgets()
               if isinstance(w, GroupCard) and w.isVisible()])


def test_stress(store, points):
    print(f"\n--- Stress: repeated count changes x score changes x card rebuilds ---")
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

    print(f"  ran {rounds} rounds, up to {MAX_GROUP_COUNT} groups each")
    check(f"panel not destroyed after {rounds} rounds", not sip.isdeleted(points))
    check(f"{rounds} rounds -> {MAX_GROUP_COUNT} cards",
          len(points._cards) == MAX_GROUP_COUNT, f"actual {len(points._cards)}")
    check("scores not all 0 after stress (consistency check is meaningful)",
          any(c.score() > 0 for c in points._cards),
          f"actual {[c.score() for c in points._cards][:6]}…")
    check("UI matches file after stress", *cards_match_store(store, points))

    reread = ConfigStore(points._store.path)
    check("config.ini still parses after stress", reread.group_count == MAX_GROUP_COUNT,
          f"actual {reread.group_count}")
    check("scores read back from file match after stress",
          [reread.get_score(i) for i in range(1, MAX_GROUP_COUNT + 1)]
          == [c.score() for c in points._cards])

    # 24 组是 8 行 × 200px 卡片，窗口装不下 —— 滚动条必须真的在干活。
    # 布局高度要等事件循环跑一轮才落定，先 pump 一次再量。
    QApplication.processEvents()
    scroll = points.findChildren(QScrollArea)[0]
    content_h = scroll.widget().height()
    viewport_h = scroll.viewport().height()
    print(f"  at 24 groups: content height {content_h}px, viewport height {viewport_h}px")
    check("at 24 groups the content exceeds the viewport (scrolling works)", content_h > viewport_h,
          f"{content_h}px vs {viewport_h}px")
    check("content height fits 8 rows of cards (not squashed by the viewport)",
          content_h >= 8 * 200, f"{content_h}px")

    # 反面：SetMinimumSize 不能让内容的最小高度顶到窗口上，否则 24 组时
    # 窗口会被撑成 1684px 高、比屏幕还高，而且再也缩不小
    points.resize(760, 560)
    QApplication.processEvents()
    hint_h = points.minimumSizeHint().height()
    print(f"  at 24 groups: min height hint {hint_h}px, actual window height {points.height()}px")
    check("24 groups does not force a huge minimum window height", hint_h <= 700, f"{hint_h}px")
    check("scrolling still works after shrinking the window to 560 high",
          scroll.widget().height() > scroll.viewport().height(),
          f"{scroll.widget().height()} vs {scroll.viewport().height()}")

    # 压力之后面板还得能正常用
    before = points._cards[0].score()
    points.apply_delta(1, 3)
    points.save_now()
    check("can still add points and persist after stress",
          ConfigStore(points._store.path).get_score(1) == before + 3,
          f"actual {ConfigStore(points._store.path).get_score(1)}")


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
        print(f"failed {len(failures)}: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
