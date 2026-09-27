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
import tempfile
import winreg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication  # noqa: E402
from PyQt5.QtCore import QTimer  # noqa: E402
from PyQt5.QtGui import QFont, QFontMetrics  # noqa: E402
from PyQt5 import sip  # noqa: E402

from namepicker import crash_log  # noqa: E402
from namepicker.config_store import APP_NAME, ConfigStore  # noqa: E402
from namepicker.name_engine import NameEngine  # noqa: E402
from namepicker.points_window import PointsWindow  # noqa: E402
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


def test_points_window(store, config_path):
    print("--- 积分面板 ---")
    points = PointsWindow(store)
    check("6 个小组卡片", len(points._cards) == 6, f"实际 {len(points._cards)}")
    check("默认组名", store.get_group_name(1) == "第一组"
          and store.get_group_name(6) == "第六组")
    check("初始只展开第 1 组",
          points._cards[0].is_selected()
          and not points._cards[1].is_selected())

    # 点第 3 组 → 应该展开它、收起第 1 组
    points._cards[2].selected.emit(3)
    check("单击第 3 组后展开并选中",
          points._cards[2].is_selected() and not points._cards[0].is_selected())
    check("展开后加减按钮可见", points._cards[2]._ops.isVisibleTo(points._cards[2]))

    # 加分：+2 +2 -1 = 3
    points.apply_delta(3, 2)
    points.apply_delta(3, 2)
    points.apply_delta(3, -1)
    check("第 3 组 = 3 (+2+2-1)", store.get_score(3) == 3,
          f"实际 {store.get_score(3)}")

    # 撤销最后一次 -1 → 4
    points.undo()
    check("撤销后 = 4", store.get_score(3) == 4, f"实际 {store.get_score(3)}")

    check("其余小组仍为 0",
          all(store.get_score(i) == 0 for i in (1, 2, 4, 5, 6)))

    store.set_group_name(2, "雄鹰组")
    points.save_now()
    check("重命名落盘", ConfigStore(config_path).get_group_name(2) == "雄鹰组")

    reloaded = ConfigStore(config_path)
    check("积分持久化到 config.ini", reloaded.get_score(3) == 4,
          f"实际 {reloaded.get_score(3)}")

    store.reset_scores()
    points.save_now()
    check("全部清零", ConfigStore(config_path).all_scores() == [0] * 6)

    # 连续加分的同时关掉面板 —— 分数要落盘，程序不能被关掉
    for _ in range(50):
        points.apply_delta(4, 2)
        app_process()
    points.close()
    app_process()
    check("边加分边关面板：分数已落盘",
          ConfigStore(config_path).get_score(4) == 100,
          f"实际 {ConfigStore(config_path).get_score(4)}")
    check("边加分边关面板：面板没有被销毁",
          not sip.isdeleted(points) and points.isHidden())
    points.show()
    app_process()
    check("关掉后还能重新打开", points.isVisible())
    return points


def app_process():
    """Pump the event loop once without blocking (lets timers/layout run)."""
    QApplication.processEvents()


def test_engine_single(stats_path):
    print("\n--- 单抽 + 长期次数落盘 ---")
    stats = StatsStore(stats_path)
    engine = NameEngine()
    engine.generate_number_list(1, 10)
    drawn = [engine.draw_name() for _ in range(10)]
    check("抽 10 次得到 10 个结果", len(drawn) == 10 and all(drawn))
    check("抽到的都在名单里", all(d in engine.get_names() for d in drawn))
    check("10 人名单抽 10 次无重复",
          len(set(drawn)) == 10, f"重复: {len(drawn) - len(set(drawn))} 次")

    stats.save(engine.get_draw_counts())
    loaded = StatsStore(stats_path).load()
    check("长期次数写入 stats.ini", loaded.get("1") == 1 and len(loaded) == 10,
          f"{len(loaded)} 条")

    engine2 = NameEngine()
    engine2.generate_number_list(1, 10)
    engine2.set_draw_counts(loaded)
    check("长期次数可恢复", engine2.get_draw_count("1") == 1
          and engine2.get_total_draws() == 10)

    # 核心：清空历史不能把长期次数一起抹掉
    before = dict(loaded)
    engine2.clear_history()
    check("清空历史后长期次数保留",
          engine2.get_draw_counts() == before,
          f"清空后 {engine2.get_draw_counts()}")
    check("清空历史后冷却是空的", engine2.get_per_name_cooldowns() == {})
    check("清空历史不会误报『全员已抽过一轮』",
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
    check("清空历史后权重全为正数", all(w > 0 for w in weights),
          f"最小权重 {min(weights)}")

    # 彻底重置才清长期次数
    loaded2 = dict(engine2.get_draw_counts())
    engine2.reset_fairness()
    check("彻底重置清零长期次数", engine2.get_total_draws() == 0,
          f"实际 {engine2.get_total_draws()}")
    check("彻底重置前的确有时数", sum(loaded2.values()) == 10)
    return engine


def test_multi_draw():
    print("\n--- 连抽 ---")
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
    check("连抽 5 人得到 5 个", len(picked) == 5, f"实际 {len(picked)}")
    check("连抽 5 人互不重复", len(set(picked)) == 5, f"结果 {picked}")
    check("连抽结果都在名单内", all(p in engine.get_names() for p in picked))

    check("names_drawn 只发一次且带全部结果",
          len(events["names_drawn"]) == 1
          and events["names_drawn"][0] == picked,
          f"{len(events['names_drawn'])} 次")
    check("multi_rolling_start 只发一次",
          len(events["multi_rolling"]) == 1
          and events["multi_rolling"][0] == picked)
    check("连抽不触发单抽信号（避免弹两个窗）",
          not events["single_rolling"] and not events["single_drawn"])

    cooldowns = engine.get_per_name_cooldowns()
    check("连抽的每个人都进入冷却",
          all(n in cooldowns for n in picked),
          f"冷却中 {len(cooldowns)} 人")

    # 核对历史记录 — 连抽的 5 条都要落进历史表
    check("连抽 5 人全部写入历史",
          len(engine.get_history()) == 5, f"实际 {len(engine.get_history())}")

    # 剩余 5 人可用 → 请求 6 人只能给 5 人（正常冷却，不做特殊处理）
    picked2 = engine.draw_names(6)
    check("可用不足时只给能抽到的人（请求 6 → 得到 5）",
          len(picked2) == 5, f"实际 {len(picked2)}")
    check("第二轮与第一轮不重叠",
          not (set(picked) & set(picked2)))

    # 全员冷却中 → 空结果 + 错误提示
    events["errors"].clear()
    picked3 = engine.draw_names(2)
    check("全员冷却时连抽返回空", picked3 == [], f"实际 {picked3}")
    check("全员冷却时给出提示", len(events["errors"]) == 1,
          f"{events['errors']}")
    return engine


def test_wipe(store, config_path, stats_path):
    """彻底重置：config.ini 与 stats.ini 都要回到初始状态。"""
    print("\n--- 彻底重置 ---")
    # 先弄脏两个文件
    store.set_score(2, 7)
    store.set_group_name(1, "雄鹰组")
    store.save()
    StatsStore(stats_path).save({"张三": 5})
    engine = NameEngine()
    engine.generate_number_list(1, 3)
    engine.set_draw_counts({"1": 3, "2": 2, "3": 1})

    # 复刻 main.py 的 wipe 流程
    store.reset_all()
    StatsStore(stats_path).clear()
    engine.reset_fairness()

    fresh_cfg = ConfigStore(config_path)
    check("重置后积分归零", fresh_cfg.all_scores() == [0] * 6,
          f"实际 {fresh_cfg.all_scores()}")
    check("重置后组名恢复默认",
          fresh_cfg.get_group_name(1) == "第一组"
          and fresh_cfg.get_group_name(2) == "第二组")
    check("重置后 stats.ini 清空", StatsStore(stats_path).load() == {},
          f"实际 {StatsStore(stats_path).load()}")
    check("重置后内存次数清零", engine.get_total_draws() == 0)


def test_floating_ball():
    print("\n--- 悬浮球右键菜单 ---")
    ball = FloatingBall()
    check("有 积分管理 信号", hasattr(ball, "points_panel_requested"))
    check("有 打开管理面板 信号", hasattr(ball, "open_panel_requested"))
    check("有 连抽 信号", hasattr(ball, "multi_draw_requested"))
    check("连抽档位为 2~10 人", ball.MULTI_DRAW_CHOICES == tuple(range(2, 11)),
          f"实际 {ball.MULTI_DRAW_CHOICES}")

    menu = ball.build_context_menu()
    texts = [a.text() for a in menu.actions()]
    check("菜单顶层为 连抽 / 积分管理 / 打开管理面板",
          texts == ["连抽", "积分管理", "", "打开管理面板"], f"实际 {texts}")

    multi = menu.actions()[0].menu()
    sub_texts = [a.text() for a in multi.actions()]
    check("连抽子菜单竖排 9 个档位",
          sub_texts == [f"{n} 人" for n in range(2, 11)], f"实际 {sub_texts}")
    check("不再有画蛇添足的 抽取一个", "抽取一个" not in texts)

    grabbed = []
    ball.multi_draw_requested.connect(grabbed.append)
    multi.actions()[3].trigger()  # “5 人”
    check("点 5 人 → 发出 multi_draw_requested(5)", grabbed == [5],
          f"实际 {grabbed}")

    ball.points_panel_requested.connect(lambda: grabbed.append("points"))
    menu.actions()[1].trigger()
    check("点 积分管理 → 发出 points_panel_requested",
          grabbed[-1] == "points", f"实际 {grabbed}")
    ball.close()


def test_popup(engine):
    print("\n--- 结果弹窗 ---")
    app = QApplication.instance()
    popup = DrawResultPopup()
    check("弹窗底部显示终端名称", popup._footer.text() == APP_NAME,
          f"实际 {popup._footer.text()!r}")

    check("1 人 → 1 列", popup._grid_shape(1) == (1, 40))
    check("10 人 → 5 列 2 行", popup._grid_shape(10)[0] == 5)

    popup.set_name_pool(engine.get_names())

    # 单抽走的是 show_results([name])，先确认它确实只建一个格子
    popup.show_result("7")
    check("单抽只建 1 个名字格", len(popup._name_labels) == 1,
          f"实际 {len(popup._name_labels)}")
    popup._on_close()

    # 名字不能左右被裁掉：格宽要能容下名单里最长的名字
    popup.set_name_pool(["欧阳娜娜", "1", "2"])
    popup.show_result("欧阳娜娜")
    fm = QFontMetrics(QFont("Microsoft YaHei", popup._font_size, QFont.Bold))
    check("长名字不被裁切",
          popup._cell_width >= fm.horizontalAdvance("欧阳娜娜") + 16,
          f"格宽 {popup._cell_width}px")
    popup._on_close()

    # 连抽：一个大弹窗，N 个人同时滚动
    results = ["1", "2", "3", "4", "5"]
    popup.show_results(results)
    check("连抽建 5 个名字格", len(popup._name_labels) == 5,
          f"实际 {len(popup._name_labels)}")
    check("连抽弹窗按人数放大", popup.width() >= 380 and popup.height() > 208,
          f"{popup.width()}x{popup.height()}")

    QTimer.singleShot(3000, app.quit)
    app.exec_()
    shown = [lb.text() for lb in popup._name_labels]
    check("滚动结束后同时揭晓 5 个结果", shown == results, f"实际 {shown}")
    popup._on_close()


def test_main_window(engine):
    print("\n--- 主窗口 ---")
    backup = _read_autostart()
    try:
        win = MainWindow(engine, app_path=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "main.py")))
        check("窗口标题带终端名称", APP_NAME in win.windowTitle(),
              f"实际 {win.windowTitle()!r}")
        check("底栏有 积分管理 按钮", win._points_btn.text() == "积分管理")
        win._points_window = None
        win.set_points_window("dummy")
        check("能挂上积分窗口", win._points_window == "dummy")

        tray = win._tray_icon
        if tray is not None and tray.contextMenu() is not None:
            tray_texts = [a.text() for a in tray.contextMenu().actions()]
            check("托盘菜单有 彻底重置", "彻底重置..." in tray_texts,
                  f"实际 {tray_texts}")
        else:
            print("[SKIP] 本机没有系统托盘，跳过托盘菜单检查")

        # 未接 handler 时不能崩，应给出提示
        called = []
        win.set_wipe_handler(lambda: called.append(True))
        win._wipe_handler = lambda: called.append(True)
        check("能挂上彻底重置回调", callable(win._wipe_handler))
        win.on_wipe_complete()
        check("重置后状态栏更新", "重置" in win._status_label.text(),
              f"实际 {win._status_label.text()!r}")
        win.hide()
        win.deleteLater()
    finally:
        if _read_autostart() != backup:
            _write_autostart(backup)
            print("  (已还原注册表自启动项)")


def test_crash_log():
    """A traceback must end up in crash.log (no console in the real app)."""
    print("\n--- 崩溃日志 ---")
    log_dir = tempfile.mkdtemp()
    saved_hook = sys.excepthook
    try:
        path = crash_log.install(log_dir)
        check("日志写在指定目录", os.path.dirname(path) == log_dir, path)

        # The hook also forwards to the console, which is what we want in the
        # real app but is just noise here — swallow it for this check.
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                raise ValueError("模拟错误")
            except ValueError:
                sys.excepthook(*sys.exc_info())

        content = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
        check("异常写进 crash.log", "模拟错误" in content and "ValueError" in content)
        check("日志带堆栈", "Traceback" in content)
    finally:
        sys.excepthook = saved_hook


def main():
    app = QApplication(sys.argv)

    tmp_dir = tempfile.mkdtemp()
    config_path = os.path.join(tmp_dir, "config.ini")
    stats_path = os.path.join(tmp_dir, "stats.ini")
    store = ConfigStore(config_path)
    # 真实 config.ini 里的分数/组名不能影响测试结论
    store.reset_scores()

    test_crash_log()
    test_points_window(store, config_path)
    engine = test_engine_single(stats_path)
    test_wipe(store, config_path, stats_path)
    test_multi_draw()
    test_floating_ball()
    test_popup(engine)
    test_main_window(engine)

    print()
    if failures:
        print(f"失败 {len(failures)} 项: {failures}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
