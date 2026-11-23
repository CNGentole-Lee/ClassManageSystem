"""冒烟测试 — 不启动完整程序，直接构造各个窗口并模拟操作。

验证的是编译检查发现不了的东西：信号连接、布局、config.ini 落盘、撤销、连抽。

用法:
    python tools/smoke_test.py

MainWindow 会读取真实的 QSettings 并可能重写开机自启动注册表项，所以这里
先把注册表的值备份下来、跑完再原样写回（没装过就什么都不写）。
"""

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()
import tempfile

try:  # 注册表模块只在 Windows 上存在（macOS/Linux 上跳过自启动备份）
    import winreg
except ImportError:  # pragma: no cover - 取决于运行平台
    winreg = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFont, QFontMetrics  # noqa: E402
from shiboken6 import isValid  # noqa: E402

from namepicker import crash_log, theme  # noqa: E402
from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()  # 测试数据不写进真实的隐蔽备份（Windows 注册表 / macOS plist）

from namepicker import log_store  # noqa: E402
from namepicker.config_store import APP_NAME  # noqa: E402
from _v4_fixture import open_store, reopen_store  # noqa: E402
from namepicker.name_engine import NameEngine  # noqa: E402
from namepicker.points_window import PointsWindow, _LogViewerDialog  # noqa: E402
from namepicker.stats_store import StatsStore  # noqa: E402
from namepicker.floating_ball import FloatingBall  # noqa: E402
from namepicker.draw_popup import DrawResultPopup  # noqa: E402
from namepicker.main_window import MainWindow  # noqa: E402

failures = []


def check(label, condition, detail=""):
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(label)


# --- 注册表备份 / 还原（避免测试动到真实的开机自启动）---

def _read_autostart():
    if winreg is None:  # 非 Windows：没有注册表自启动项
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, MainWindow.REG_RUN_KEY,
                             0, winreg.KEY_READ)
    except OSError:
        return None
    try:
        return winreg.QueryValueEx(key, MainWindow.REG_VALUE_NAME)[0]
    except FileNotFoundError:
        return None
    finally:
        winreg.CloseKey(key)


def _write_autostart(value):
    if winreg is None:  # 非 Windows：无需还原
        return
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, MainWindow.REG_RUN_KEY,
                         0, winreg.KEY_SET_VALUE)
    try:
        if value is None:
            try:
                winreg.DeleteValue(key, MainWindow.REG_VALUE_NAME)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, MainWindow.REG_VALUE_NAME, 0,
                              winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def test_scores_per_profile_ui():
    """切换组数相同的预设，积分面板的卡片分数必须跟着换。

    回归：以前 apply_profile 只在组数变化时重建卡片，两个 6 组预设互切
    时卡片还显示上一个预设的分数 —— 数据层独立了，界面却没刷新。
    """
    print("--- Scores follow the active profile (UI) ---")
    from namepicker.ledger import Ledger
    from namepicker.profiles import ProfileStore

    tmp = tempfile.mkdtemp(prefix="cm_ui_profile_")
    cfg = os.path.join(tmp, "config.ini")
    store = open_store(cfg, groups=6)
    ps = ProfileStore(chain=store._ledger)
    pid_a = ps.active_id()

    # 预设 A：6 组，第一组 7 分
    store.set_score(1, 7)
    # 预设 B：同样 6 组，第一组 3 分
    pid_b = ps.create("语文课")
    ps.set_rule(pid_b, 6, 0)
    ps.use(pid_b)
    store.set_score(1, 3)

    points = PointsWindow(store)
    check("panel shows the active profile's score",
          points._cards[0].score() == 3, f"actual {points._cards[0].score()}")

    # 切回预设 A —— 组数没变，但分数必须刷新成 7
    ps.use(pid_a)
    points.apply_profile(ps.active())
    check("switching same-size profiles refreshes the card score",
          points._cards[0].score() == 7,
          f"actual {points._cards[0].score()} (expected 7)")

    # 再切到 B，应为 3
    ps.use(pid_b)
    points.apply_profile(ps.active())
    check("switching back refreshes the score again",
          points._cards[0].score() == 3,
          f"actual {points._cards[0].score()} (expected 3)")


def test_points_window(store, config_path):
    print("--- Points panel ---")
    points = PointsWindow(store)
    check("6 group cards", len(points._cards) == 6, f"actual {len(points._cards)}")
    check("default group names", store.get_group_name(1) == "第一组"
          and store.get_group_name(6) == "第六组")
    check("only group 1 is expanded initially",
          points._cards[0].is_selected()
          and not points._cards[1].is_selected())

    # 点第 3 组 → 应该展开它、收起第 1 组
    points._cards[2].selected.emit(3)
    check("clicking group 3 expands and selects it",
          points._cards[2].is_selected() and not points._cards[0].is_selected())
    check("add/subtract buttons visible when expanded", points._cards[2]._ops.isVisibleTo(points._cards[2]))

    # 加分：+2 +2 -1 = 3
    points.apply_delta(3, 2)
    points.apply_delta(3, 2)
    points.apply_delta(3, -1)
    check("group 3 = 3 (+2+2-1)", store.get_score(3) == 3,
          f"actual {store.get_score(3)}")

    # 撤销最后一次 -1 → 4
    points.undo()
    check("after undo = 4", store.get_score(3) == 4, f"actual {store.get_score(3)}")

    check("other groups are still 0",
          all(store.get_score(i) == 0 for i in (1, 2, 4, 5, 6)))

    store.set_group_name(2, "雄鹰组")
    points.save_now()
    check("rename persisted", reopen_store(config_path).get_group_name(2) == "雄鹰组")

    reloaded = reopen_store(config_path)
    check("scores persisted to config.ini", reloaded.get_score(3) == 4,
          f"actual {reloaded.get_score(3)}")

    store.reset_scores()
    points.save_now()
    check("all scores cleared", reopen_store(config_path).all_scores() == [0] * 6)

    # --- 操作日志（唯一入口是底栏按钮）---
    check("bottom bar has an Operation log button next to the group-count button",
          points._log_btn.text() == "操作日志")
    entries = log_store.load(config_path).entries
    check("log auto-recorded the add/subtract/clear above",
          len(entries) > 0 and any("清零" in zh for _s, zh, _en in entries),
          f"actual {len(entries)} entries")
    check("log ciphertext contains no plaintext",
          b"group" not in open(log_store.log_path_for(config_path), "rb").read())
    dialog = _LogViewerDialog(config_path)
    shown = dialog.findChild(QPlainTextEdit).toPlainText()
    check("viewer displays the entries",
          "第" in shown and "→" in shown, f"actual {shown[:40]!r}")
    check("viewer is read-only", dialog.findChild(QPlainTextEdit).isReadOnly())
    check("every log entry has both Chinese and English",
          all(zh and en for _s, zh, en in entries),
          f"actual {entries[0] if entries else None}")
    check("no plaintext log copy (only .dat / .dat.bak)",
          sorted(n for n in os.listdir(os.path.dirname(config_path)) if "log" in n)
          == ["points_log.dat", "points_log.dat.bak"])
    dialog.close()
    dialog.deleteLater()

    # 连续加分的同时关掉面板 —— 分数要落盘，程序不能被关掉
    for _ in range(50):
        points.apply_delta(4, 2)
        app_process()
    points.close()
    app_process()
    check("adding points then closing the panel: scores persisted",
          reopen_store(config_path).get_score(4) == 100,
          f"actual {reopen_store(config_path).get_score(4)}")
    check("adding points then closing the panel: panel not destroyed",
          not not isValid(points) and points.isHidden())
    points.show()
    app_process()
    check("reopens after closing", points.isVisible())
    return points


def app_process():
    """Pump the event loop once without blocking (lets timers/layout run)."""
    QApplication.processEvents()


#: 冒烟测试用的名单：1..10（引擎按学号抽）再加一个中文名（彻底重置用）
ROSTER = [str(i) for i in range(1, 11)] + ["张三"]


def _tmp_chain(stats_path):
    """次数存在事件链的「预设」里，冒烟测试给它一条临时链 + 一个预设。"""
    from namepicker.ledger import Ledger
    from namepicker.profiles import ProfileStore
    base = os.path.dirname(stats_path)
    chain = Ledger(os.path.join(base, "config.ini"))
    if chain.count() == 0:
        chain.migrate_from(0, [], [])
    store = ProfileStore(chain=chain)
    if not store.list():
        pid = store.create("化学课")
        store.set_rule(pid, 6, len(ROSTER))
        store.use(pid)
    else:
        # 这条链可能已经被前面的用例建过预设（0 个名单槽位）：
        # 名单槽位不够时 draw 会被静默丢弃，这里对齐到本测试的名单。
        store.sync_roster(len(ROSTER))
    return chain


def _stats(stats_path):
    """带名单的 StatsStore：V4 按下标存次数，名单必须先交给它。"""
    st = StatsStore(stats_path, chain=_tmp_chain(stats_path))
    st.set_names(ROSTER)
    return st


def test_engine_single(stats_path):
    print("\n--- Single draw + long-term counts persisted ---")
    stats = _stats(stats_path)
    engine = NameEngine()
    engine.generate_number_list(1, 10)
    drawn = [engine.draw_name() for _ in range(10)]
    check("10 draws produce 10 results", len(drawn) == 10 and all(drawn))
    check("every draw comes from the name list", all(d in engine.get_names() for d in drawn))
    check("10 draws from 10 names without repeats",
          len(set(drawn)) == 10, f"duplicates: {len(drawn) - len(set(drawn))}")

    stats.save(engine.get_draw_counts())
    loaded = _stats(stats_path).load()
    check("long-term counts recorded in the event chain", loaded.get("1") == 1 and len(loaded) == 10,
          f"{len(loaded)} entries")

    engine2 = NameEngine()
    engine2.generate_number_list(1, 10)
    engine2.set_draw_counts(loaded)
    check("long-term counts can be restored", engine2.get_draw_count("1") == 1
          and engine2.get_total_draws() == 10)

    # 核心：清空历史不能把长期次数一起抹掉
    before = dict(loaded)
    engine2.clear_history()
    check("long-term counts survive clearing history",
          engine2.get_draw_counts() == before,
          f"after clear: {engine2.get_draw_counts()}")
    check("cooldowns are empty after clearing history", engine2.get_per_name_cooldowns() == {})
    check("clearing history does not falsely report that everyone was drawn already",
          engine2._last_round_min == min(before.values()),
          f"_last_round_min={engine2._last_round_min}")

    # recency 记账必须一起清，否则 gap 变负数、权重被算成负数
    engine3 = NameEngine()
    engine3.generate_number_list(1, 5)
    for _ in range(5):
        engine3.draw_name()
    engine3.clear_history()
    weights = [engine3._weight(n, max(engine3._draw_counts.values()))
               for n in engine3.get_names()]
    check("all weights positive after clearing history", all(w > 0 for w in weights),
          f"min weight {min(weights)}")

    # 彻底重置才清长期次数
    loaded2 = dict(engine2.get_draw_counts())
    engine2.reset_fairness()
    check("full reset zeroes long-term counts", engine2.get_total_draws() == 0,
          f"actual {engine2.get_total_draws()}")
    check("long-term counts existed before the full reset", sum(loaded2.values()) == 10)
    return engine


def test_multi_draw():
    print("\n--- Multi draw ---")
    engine = NameEngine()
    engine.generate_number_list(1, 10)

    events = {
        "multi_rolling": [], "names_drawn": [],
        "single_rolling": [], "single_drawn": [], "errors": [],
    }
    engine.multi_rolling_start.connect(
        lambda names: events["multi_rolling"].append(list(names)))
    engine.names_drawn.connect(
        lambda names: events["names_drawn"].append(list(names)))
    engine.rolling_start.connect(
        lambda name: events["single_rolling"].append(name))
    engine.name_drawn.connect(lambda name: events["single_drawn"].append(name))
    engine.error_occurred.connect(lambda msg: events["errors"].append(msg))

    picked = engine.draw_names(5)
    check("multi draw of 5 returns 5", len(picked) == 5, f"actual {len(picked)}")
    check("5 multi-drawn names are distinct", len(set(picked)) == 5, f"result {picked}")
    check("multi-draw results are all in the name list", all(p in engine.get_names() for p in picked))

    check("names_drawn fires once with all results",
          len(events["names_drawn"]) == 1
          and events["names_drawn"][0] == picked,
          f"{len(events['names_drawn'])} times")
    check("multi_rolling_start fires once",
          len(events["multi_rolling"]) == 1
          and events["multi_rolling"][0] == picked)
    check("multi draw does not fire single-draw signals (avoids two popups)",
          not events["single_rolling"] and not events["single_drawn"])

    cooldowns = engine.get_per_name_cooldowns()
    check("everyone multi-drawn goes on cooldown",
          all(n in cooldowns for n in picked),
          f"{len(cooldowns)} on cooldown")

    # 核对历史记录 — 连抽的 5 条都要落进历史表
    check("all 5 multi-drawn names enter history",
          len(engine.get_history()) == 5, f"actual {len(engine.get_history())}")

    # 剩余 5 人可用 → 请求 6 人只能给 5 人（正常冷却，不做特殊处理）
    picked2 = engine.draw_names(6)
    check("when availability is short, only eligible names are returned (asked 6 -> got 5)",
          len(picked2) == 5, f"actual {len(picked2)}")
    check("second round does not overlap the first",
          not (set(picked) & set(picked2)))

    # 全员冷却中 → 空结果 + 错误提示
    events["errors"].clear()
    picked3 = engine.draw_names(2)
    check("multi draw returns empty when everyone is cooling down", picked3 == [], f"actual {picked3}")
    check("an error is reported when everyone is cooling down", len(events["errors"]) == 1,
          f"{events['errors']}")
    return engine


def test_wipe(store, config_path, stats_path):
    """彻底重置：config.ini 与 stats.ini 都要回到初始状态。"""
    print("\n--- Full reset ---")
    # 先弄脏两个文件
    store.set_score(2, 7)
    store.set_group_name(1, "雄鹰组")
    store.save()
    _stats(stats_path).save({"张三": 5})
    engine = NameEngine()
    engine.generate_number_list(1, 3)
    engine.set_draw_counts({"1": 3, "2": 2, "3": 1})

    # 复刻 main.py 的 wipe 流程
    store.reset_all()
    _stats(stats_path).clear()
    engine.reset_fairness()

    fresh_cfg = reopen_store(config_path)
    check("scores zeroed after reset", fresh_cfg.all_scores() == [0] * 6,
          f"actual {fresh_cfg.all_scores()}")
    check("group names back to defaults after reset",
          fresh_cfg.get_group_name(1) == "第一组"
          and fresh_cfg.get_group_name(2) == "第二组")
    _cleared = _stats(stats_path).load()
    check("long-term counts cleared after reset", _cleared == {}, f"actual {_cleared}")
    check("in-memory counts zeroed after reset", engine.get_total_draws() == 0)


def test_floating_ball():
    print("\n--- Floating ball context menu ---")
    ball = FloatingBall()
    check("has a points-panel signal", hasattr(ball, "points_panel_requested"))
    check("has an open-panel signal", hasattr(ball, "open_panel_requested"))
    check("has a multi-draw signal", hasattr(ball, "multi_draw_requested"))
    check("multi-draw choices are 2..10", ball.MULTI_DRAW_CHOICES == tuple(range(2, 11)),
          f"actual {ball.MULTI_DRAW_CHOICES}")

    menu = ball.build_context_menu()
    texts = [a.text() for a in menu.actions()]
    check("menu contains multi draw / points / profiles / open panel",
          texts[:6] == ["连抽", "积分管理", "", "预设", "", "打开管理面板"],
          f"actual {texts}")

    # 预设子菜单：没有预设时也必须有「管理预设…」，否则第一次用的人
    # 永远找不到新建入口
    profile_menu = next(a.menu() for a in menu.actions() if a.text() == "预设")
    sub_texts = [x.text() for x in profile_menu.actions()]
    check("profiles submenu always offers management",
          any("管理预设" in t for t in sub_texts), f"actual {sub_texts}")

    # 有预设时，选中项打勾
    ball.set_profiles([{"id": 1, "name": "化学课", "group_count": 4},
                       {"id": 2, "name": "语文课", "group_count": 0}], 1)
    menu2 = ball.build_context_menu([{"id": 1, "name": "化学课", "group_count": 4},
                                     {"id": 2, "name": "语文课", "group_count": 0}], 1)
    sub2 = next(a.menu() for a in menu2.actions() if a.text() == "预设")
    checked = [x.text() for x in sub2.actions() if x.isCheckable() and x.isChecked()]
    check("the active profile is ticked", checked == ["化学课（4 组）"], f"actual {checked}")
    check("profiles submenu keeps management with profiles present",
          any("管理预设" in x.text() for x in sub2.actions()))
    # 托盘在 macOS 上可能不可见（无 Dock 图标 + 菜单栏自动隐藏），
    # 这些动作必须能通过悬浮球右键菜单触达
    check("menu fallback contains draw name / full reset / quit",
          "抽取名字" in texts and "彻底重置..." in texts and "退出" in texts,
          f"actual {texts}")
    check("has full-reset / quit signals",
          hasattr(ball, "wipe_requested") and hasattr(ball, "quit_requested"))

    multi = menu.actions()[0].menu()
    sub_texts = [a.text() for a in multi.actions()]
    check("multi-draw submenu lists 9 choices",
          sub_texts == [f"{n} 人" for n in range(2, 11)], f"actual {sub_texts}")
    check("no redundant single-draw entry any more", "抽取一个" not in texts)

    grabbed = []
    ball.multi_draw_requested.connect(grabbed.append)
    multi.actions()[3].trigger()  # “5 人”
    check("clicking 5 people emits multi_draw_requested(5)", grabbed == [5],
          f"actual {grabbed}")

    ball.points_panel_requested.connect(lambda: grabbed.append("points"))
    menu.actions()[1].trigger()
    check("clicking points emits points_panel_requested",
          grabbed[-1] == "points", f"actual {grabbed}")
    ball.close()


def test_popup(engine):
    print("\n--- Result popup ---")
    app = QApplication.instance()
    popup = DrawResultPopup()
    check("popup footer shows the app name", popup._footer.text() == APP_NAME,
          f"actual {popup._footer.text()!r}")

    check("1 name -> 1 column", popup._grid_shape(1) == (1, 40))
    check("10 names -> 5 columns, 2 rows", popup._grid_shape(10)[0] == 5)

    popup.set_name_pool(engine.get_names())

    # 单抽走的是 show_results([name])，先确认它确实只建一个格子
    popup.show_result("7")
    check("single draw creates only 1 name cell", len(popup._name_labels) == 1,
          f"actual {len(popup._name_labels)}")
    popup._on_close()

    # 名字不能左右被裁掉：格宽要能容下名单里最长的名字
    # 老外的名字真的很长，用这个当测试标准稳稳的
    popup.set_name_pool(["abcdefghijklmn", "1", "2"])
    popup.show_result("abcdefghijklmn")
    fm = QFontMetrics(theme.font(popup._font_size, bold=True))
    check("long names are not clipped",
          popup._cell_width >= fm.horizontalAdvance("abcdefghijklmn") + 16,
          f"cell width {popup._cell_width}px")
    popup._on_close()

    # 连抽：一个大弹窗，N 个人同时滚动
    results = ["1", "2", "3", "4", "5"]
    popup.show_results(results)
    check("multi draw creates 5 name cells", len(popup._name_labels) == 5,
          f"actual {len(popup._name_labels)}")
    check("multi-draw popup scales with the number of names", popup.width() >= 380 and popup.height() > 208,
          f"{popup.width()}x{popup.height()}")

    QTimer.singleShot(3000, app.quit)
    app.exec()
    shown = [lb.text() for lb in popup._name_labels]
    check("all 5 results revealed together when rolling stops", shown == results, f"actual {shown}")
    popup._on_close()


def test_main_window(engine):
    print("\n--- Main window ---")
    backup = _read_autostart()
    try:
        win = MainWindow(engine, app_path=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "main.py")))
        check("window title contains the app name", APP_NAME in win.windowTitle(),
              f"actual {win.windowTitle()!r}")
        check("bottom bar has a points button", win._points_btn.text() == "积分管理")
        win._points_window = None
        win.set_points_window("dummy")
        check("points window can be attached", win._points_window == "dummy")

        tray = win._tray_icon
        if tray is not None and tray.contextMenu() is not None:
            tray_texts = [a.text() for a in tray.contextMenu().actions()]
            check("tray menu has full reset", "彻底重置..." in tray_texts,
                  f"actual {tray_texts}")
        else:
            print("[SKIP] no system tray on this machine; skipping tray menu checks")

        # 未接 handler 时不能崩，应给出提示
        called = []
        win.set_wipe_handler(lambda: called.append(True))
        win._wipe_handler = lambda: called.append(True)
        check("full-reset callback can be attached", callable(win._wipe_handler))
        win.on_wipe_complete()
        check("status bar updates after reset", "重置" in win._status_label.text(),
              f"actual {win._status_label.text()!r}")
        win.hide()
        win.deleteLater()
    finally:
        if _read_autostart() != backup:
            _write_autostart(backup)
            print("  (autostart registry entry restored)")


def test_crash_log():
    """A traceback must end up in crash.log (no console in the real app)."""
    print("\n--- Crash log ---")
    log_dir = tempfile.mkdtemp()
    saved_hook = sys.excepthook
    try:
        path = crash_log.install(log_dir)
        check("log written to the specified directory", os.path.dirname(path) == log_dir, path)

        # The hook also forwards to the console, which is what we want in the
        # real app but is just noise here — swallow it for this check.
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                raise ValueError("模拟错误")
            except ValueError:
                sys.excepthook(*sys.exc_info())

        content = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
        check("exception written to crash.log", "模拟错误" in content and "ValueError" in content)
        check("log contains a stack trace", "Traceback" in content)
    finally:
        sys.excepthook = saved_hook


def main():
    app = QApplication(sys.argv)

    tmp_dir = tempfile.mkdtemp()
    config_path = os.path.join(tmp_dir, "config.ini")
    stats_path = os.path.join(tmp_dir, "stats.ini")
    store = open_store(config_path)
    # 真实 config.ini 里的分数/组名不能影响测试结论
    store.reset_scores()

    test_crash_log()
    test_scores_per_profile_ui()
    test_points_window(store, config_path)
    engine = test_engine_single(stats_path)
    test_wipe(store, config_path, stats_path)
    test_multi_draw()
    test_floating_ball()
    test_popup(engine)
    test_main_window(engine)

    print()
    if failures:
        print(f"failed {len(failures)}: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
