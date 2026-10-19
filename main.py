"""班级多用教学辅助终端 — 入口点。

一个基于 PyQt5 的教师课堂终端。
功能：
  - 屏幕右侧悬浮球（不遮挡 PPT）
  - 公平加权抽选（加权少抽优先）+ 每个名字 10 分钟冷却
  - 揭晓被抽中名字前的滚动动画
  - 居中结果弹窗，带 X 按钮，5 秒后自动关闭
  - 连抽：右键点击悬浮球 → 一次抽取 2-10 个名字，在同一个弹窗中显示
  - 小组积分面板（6 个小组，-1/+1/+2/+3），积分加密保存在 config.dat 中
    （AES-256-GCM + 三级回档：同目录 .bak / 系统级隐蔽备份 / 默认值）
  - config.ini 只是明文查看副本，程序永不读取
  - 每次积分变动自动写入加密操作日志（points_log.dat），唯一查看入口是
    积分面板底栏「操作日志」按钮
  - config.ini 旁边生成 crash.log，以便在没有控制台的情况下诊断故障
"""

import sys
import os

from PyQt5.QtCore import Qt, QSettings, QTimer, QLibraryInfo, QLocale, QTranslator
from PyQt5.QtWidgets import QApplication

from namepicker import crash_log
from namepicker import macos_window
from namepicker import theme
from namepicker.config_store import (
    APP_NAME, ConfigStore, migrate_legacy_plaintext, resolve_config_path,
)
from namepicker.name_engine import NameEngine
from namepicker.floating_ball import FloatingBall
from namepicker.draw_popup import DrawResultPopup
from namepicker.main_window import MainWindow
from namepicker.points_window import PointsWindow
from namepicker.single_instance import SingleInstance
from namepicker.stats_store import StatsStore


def _get_bundled_path(relative_path: str) -> str:
    """Get the absolute path to a resource, works for both source and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
# 以打包 EXE 方式运行
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def main():
# 必须在任何 Qt 对象之前存在，这样启动阶段的故障也能被捕获。
    crash_log.install(os.path.dirname(resolve_config_path()))

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
# 内部（ASCII）标识保持不变，这样在重命名后 QSettings 路径 / 单实例键 后仍能继续正常工作。
    app.setApplicationName("RandomNamePicker")
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("NamePicker")

    # 该应用常驻托盘：悬浮球是一个 Qt.Tool 窗口（Qt 不将其视为“主”窗口），
    # 而主窗口是隐藏到托盘而不是关闭。因此一旦主窗口被收起，积分面板
    # 就成了最后一个主窗口——在默认的 quitOnLastWindowClosed = True 下，
    # 关闭面板会导致整个应用退出。唯一预期的退出方式是托盘中的“退出”菜单。
    app.setQuitOnLastWindowClosed(False)

# --- 单实例守护 ---
    single = SingleInstance()
    if not single.try_acquire():
# 已有另一个实例正在运行——唤醒它并退出
        single.notify_existing()
        sys.exit(0)

    # 深/浅色自适应：字体、调色板与样式表都由 theme 统一生成（见 namepicker/theme.py）。
    # 必须在创建任何窗口之前应用，否则先建出来的控件会拿到默认字体。
    theme.apply(app)

    # macOS：必须切到 accessory 激活策略，悬浮球才能加入别的 App 的全屏 Space。
    # 代价是没有 Dock 图标（Alfred / Raycast 同样如此）；这不是可选项 ——
    # regular 策略下窗口会留在桌面 Space，PPT 全屏时必然被盖住。
    macos_window.set_accessory_policy()

    # Qt 自带控件的文案（对话框的 Yes/No/Cancel/OK 等）本地化。
    # 找不到 .qm 时静默跳过，不影响功能。
    translator = QTranslator(app)
    _tr_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    if translator.load(QLocale(QLocale.Chinese, QLocale.China), "qtbase", "_", _tr_path):
        app.installTranslator(translator)
    elif translator.load("qt_zh_CN", _tr_path):
        app.installTranslator(translator)


    # --- 旧版明文迁移（一次性）---
    # 老版本把分数明文写在 config.ini 里；如果还没有加密主文件，先把旧数据加密
    # 落盘，之后就再也不读明文 config.ini 了（它只是给人看的副本）。
    migrate_legacy_plaintext()

    store = ConfigStore()
    stats = StatsStore()
    engine = NameEngine()

# --- 公平性统计：stats.ini <-> 引擎 ------------------------
    # 抽取计数必须在重启后仍然保留，这样“加权少抽优先”才有意义，
    # 而且它们必须在“清空历史”后也仍然保留——这就是为什么它们
    # 存放在自己的文件中，而不是 config.ini 里。每次滚动动画
    # 最多只发生一次抽取，所以每次抽取都写入并没有任何开销。
    def save_stats() -> None:
        stats.save(engine.get_draw_counts())

    def restore_stats() -> None:
        engine.set_draw_counts(stats.load())

# 在首次加载之前恢复，这样历史计数会立即生效。
    engine.names_loaded.connect(lambda _count: restore_stats())
    engine.name_drawn.connect(lambda _name: save_stats())

    def wipe_everything() -> None:
        """彻底重置：config.ini 与 stats.ini 全部回到初始状态。"""
        store.reset_all()          # 组名 / 分数 → 默认
        stats.clear()              # 长期抽取次数 → 清空
        engine.reset_fairness()    # 内存里的次数 / 历史 / 冷却
        points_win.reload_from_store()
        main_win.on_wipe_complete()

    # --- UI ---
    ball = FloatingBall()
    popup = DrawResultPopup()
    points_win = PointsWindow(store)
# 对于 PyInstaller 打包：sys.executable 就是 EXE 路径
    # 对于源码运行：使用 __file__
    if getattr(sys, 'frozen', False):
        app_path = sys.executable
    else:
        app_path = os.path.abspath(__file__)
    main_win = MainWindow(engine, app_path=app_path)
    main_win.set_ball(ball)
    main_win.set_points_window(points_win)
    main_win.set_wipe_handler(wipe_everything)

# --- 信号连接 ---

    # 单实例：唤醒 → 显示主窗口
    single.wake_up_requested.connect(main_win.showNormal)
    single.wake_up_requested.connect(main_win.activateWindow)
    # 双击悬浮球 → 抽取
    ball.ball_clicked.connect(engine.draw_name)

    # 右键点击悬浮球 → 打开管理面板
    ball.open_panel_requested.connect(main_win.showNormal)
    ball.open_panel_requested.connect(main_win.activateWindow)

    # 右键点击悬浮球 → 打开小组积分面板
    ball.points_panel_requested.connect(points_win.show_and_activate)

    # 右键菜单里的兜底动作（macOS 没有 Dock 图标、菜单栏可能自动隐藏）
    ball.wipe_requested.connect(main_win._on_wipe_all)
    ball.quit_requested.connect(app.quit)

    # 滚动开始 → 显示带滚动动画的弹窗
    def on_rolling_start(name: str):
        popup.set_name_pool(engine.get_names())
        popup.show_result(name)

    engine.rolling_start.connect(on_rolling_start)

    # 抽取到名字 → 悬浮球闪烁 + 主窗口更新
    def on_name_drawn(name: str):
        ball.flash_drawing()
        main_win.on_name_drawn(name)

    engine.name_drawn.connect(on_name_drawn)

    # 连抽 → 一个弹窗，所有名字同时滚动
    def on_multi_rolling_start(names: list):
        popup.set_name_pool(engine.get_names())
        popup.show_results(names)

    engine.multi_rolling_start.connect(on_multi_rolling_start)

    def on_names_drawn(names: list):
        ball.flash_drawing()
        main_win.on_names_drawn(names)

    engine.names_drawn.connect(on_names_drawn)

    # 右键点击悬浮球 → 连抽 N 人（人数不足时提示）
    def on_multi_draw_requested(count: int):
        drawn = engine.draw_names(count)
        if drawn and len(drawn) < count:
            main_win.on_partial_multi_draw(len(drawn), count)

    ball.multi_draw_requested.connect(on_multi_draw_requested)

    # 每个名字的冷却时间已更新
    engine.cooldowns_updated.connect(main_win.on_cooldowns_updated)

    # 名字已加载 → 主窗口 + 更新弹窗候选池
    def on_names_loaded(count: int):
        main_win.on_names_loaded(count)
        popup.set_name_pool(engine.get_names())

    engine.names_loaded.connect(on_names_loaded)

    # Errors
    engine.error_occurred.connect(main_win.on_error)

    # Pool refilled
    engine.pool_refilled.connect(main_win.on_pool_refilled)

    # History cleared
    engine.history_cleared.connect(main_win.on_history_cleared)

    # --- Show ---
    ball.show()
    main_win.show()

    # --- Auto-load last file (or default to 1-99 on first run) ---
    settings = QSettings("NamePicker", "Config")
    last_file = settings.value("last_file", "")
    if last_file and os.path.isfile(last_file):
        engine.load_names_from_file(last_file)
        popup.set_name_pool(engine.get_names())
    elif not engine.get_names():
        # First run with no saved file: default to numbers 1-99
        engine.generate_number_list(1, 99)
        popup.set_name_pool(engine.get_names())

    # --- Run ---
    exit_code = app.exec_()
    main_win.save_settings()
    points_win.save_now()
    save_stats()
    # 主动释放单实例资源，避免留下孤儿套接字/共享内存（被强杀时仍可能残留，
    # SingleInstance 的探活逻辑已经能容忍这种情况）。
    single.release()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
