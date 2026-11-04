"""班级多用教学辅助终端 — 入口点。

一个基于 PySide6 的教师课堂终端。
功能：
  - 屏幕右侧悬浮球（不遮挡 PPT）
  - 公平加权抽选（加权少抽优先）+ 每个名字 10 分钟冷却
  - 揭晓被抽中名字前的滚动动画
  - 居中结果弹窗，带 X 按钮，5 秒后自动关闭
  - 连抽：右键点击悬浮球 → 一次抽取 2-10 个名字，在同一个弹窗中显示
  - 小组积分面板（默认 6 个小组），分数以**事件链**为准：
    每次变动由原生模块 cmd_native 校验规则、加密、签名后追加到
    Data/ledger.esc；启动时验签并重放。config.dat 里的分数只是缓存。
  - 操作日志（points_log.dat）独立加密保存，入口是积分面板底栏「操作日志」
  - config.ini 只是明文查看副本，程序永不读取
  - config.ini 旁边生成 crash.log / startup.log，便于无控制台时诊断
"""
import sys
import os

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from namepicker import about_dialog
from namepicker.about_dialog import VERSION
from namepicker import crash_log
from namepicker import i18n
from namepicker import macos_window
from namepicker import restart as restart_service
from namepicker import startup_log
from namepicker import win_window
from namepicker import theme
from namepicker.config_store import (
    ConfigStore, app_name, migrate_legacy_plaintext, read_saved_language,
    resolve_config_path,
)
from namepicker.name_engine import NameEngine
from namepicker.floating_ball import FloatingBall
from namepicker.draw_popup import DrawResultPopup
from namepicker.main_window import MainWindow
from namepicker.points_window import PointsWindow
from namepicker.single_instance import SingleInstance
from namepicker.stats_store import StatsStore
from namepicker import wipe_service
from namepicker.i18n import tr


def _get_bundled_path(relative_path: str) -> str:
    """Get the absolute path to a resource, works for both source and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
# 以打包 EXE 方式运行
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def _show_update(parent, remote, cfg, local_pair):
    """有新版本时弹窗：**只跳转浏览器**，不在程序里下载。

    早期实现把「下载到 Downloads」做成阻塞调用，ui 线程被占住，
    点一下整个窗口卡死。现在只给两个链接：直连和 gh-proxy。
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    from namepicker import updater

    box = QMessageBox(parent)
    box.setWindowTitle(tr("发现新版本", "Update available"))
    box.setIcon(QMessageBox.Information)
    box.setText(tr("发现新版本 {v}（当前 {c}）",
                   "New version {v} (current {c})",
                   v=remote["version"], c=local_pair[0]))
    if remote.get("notes"):
        box.setInformativeText(remote["notes"])
    open_btn = box.addButton(tr("打开下载页", "Open download page"),
                             QMessageBox.AcceptRole)
    proxy_btn = box.addButton(tr("用 gh-proxy 打开", "Open via gh-proxy"),
                              QMessageBox.ActionRole)
    box.addButton(tr("稍后", "Later"), QMessageBox.RejectRole)
    box.exec()

    clicked = box.clickedButton()
    if clicked is open_btn:
        QDesktopServices.openUrl(QUrl(updater.release_page(cfg)))
    elif clicked is proxy_btn:
        QDesktopServices.openUrl(QUrl(updater.release_page_via_proxy(cfg)))


def _start_update_check(window):
    """启动后台检查新版本；失败静默，绝不阻塞或报错。"""
    try:
        from namepicker import updater

        if os.environ.get("CLASSMANAGE_NO_UPDATE_CHECK"):
            return
        cfg = updater.load_config()
        if not cfg.get("enabled", True):
            return
        local_pair = updater.local()
        if not local_pair[0]:
            return                       # 源码运行 / 旧包：没有 build-info，跳过
    except Exception:                                  # noqa: BLE001
        return

    from PySide6.QtCore import QUrl
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

    manager = QNetworkAccessManager(window)
    urls = updater.check_urls(cfg)

    def attempt(index: int) -> None:
        """直连失败再试 proxy；都失败就静默放弃。"""
        if index >= len(urls):
            return
        request = QNetworkRequest(QUrl(urls[index]))
        try:
            request.setTransferTimeout(4000)
        except AttributeError:
            pass
        reply = manager.get(request)

        def finished():
            try:
                remote = updater.parse_remote(bytes(reply.readAll().data()))
            except Exception:                          # noqa: BLE001
                remote = None
            reply.deleteLater()
            if remote is None:
                attempt(index + 1)
                return
            if updater.is_newer(remote, local_pair):
                _show_update(window, remote, cfg, local_pair)

        reply.finished.connect(finished)

    attempt(0)


def main():
# 必须在任何 Qt 对象之前存在，这样启动阶段的故障也能被捕获。
    crash_log.install(os.path.dirname(resolve_config_path()))

    # Qt6 起高分屏缩放与高清图标默认开启，AA_EnableHighDpiScaling /
    # AA_UseHighDpiPixmaps 已废弃（设置它们只会产生 DeprecationWarning），
    # 所以这里不再显式设置。

    app = QApplication(sys.argv)
# 内部（ASCII）标识保持不变，这样在重命名后 QSettings 路径 / 单实例键 后仍能继续正常工作。
    app.setApplicationName("RandomNamePicker")
    app.setApplicationDisplayName(app_name())
    app.setOrganizationName("NamePicker")

    # 该应用常驻托盘：悬浮球是一个 Qt.Tool 窗口（Qt 不将其视为“主”窗口），
    # 而主窗口是隐藏到托盘而不是关闭。因此一旦主窗口被收起，积分面板
    # 就成了最后一个主窗口——在默认的 quitOnLastWindowClosed = True 下，
    # 关闭面板会导致整个应用退出。唯一预期的退出方式是托盘中的“退出”菜单。
    app.setQuitOnLastWindowClosed(False)

# --- 单实例守护 ---
    # 由「切换语言 → 立即重启」拉起来的新进程带 --restarted：旧进程可能还在
    # 收尾（保存配置、销毁窗口），这里多等几秒，避免误判「已有实例」而自杀。
    _restarted = restart_service.RESTART_FLAG in sys.argv
    single = SingleInstance()
    _retry = restart_service.RETRY_SECONDS if _restarted else 0.0
    if not single.try_acquire(retry_seconds=_retry):
# 已有另一个实例正在运行——唤醒它并退出
        single.notify_existing()
        startup_log.record([f"exit: another instance is running "
                            f"(restarted={_restarted})"])
        sys.exit(0)

    # 界面语言：环境变量 > config.dat > QSettings > 系统语言。
    # config.dat 是已在 Windows 上实测可靠的存储，QSettings 作为兜底。
    # 必须在建窗口之前定好。
    _ui_settings = QSettings("NamePicker", "Config")
    _cfg_lang = read_saved_language()
    _qsettings_lang = str(_ui_settings.value("language", "") or "")
    _env_lang = os.environ.get("CLASSMANAGE_LANG", "").strip()
    i18n.set_language(_env_lang or _cfg_lang or _qsettings_lang
                      or i18n.system_language())

    # 深/浅色自适应：字体、调色板与样式表都由 theme 统一生成（见 namepicker/theme.py）。
    # 必须在创建任何窗口之前应用，否则先建出来的控件会拿到默认字体。
    theme.apply(app)

    # macOS：必须切到 accessory 激活策略，悬浮球才能加入别的 App 的全屏 Space。
    # 代价是没有 Dock 图标（Alfred / Raycast 同样如此）；这不是可选项 ——
    # regular 策略下窗口会留在桌面 Space，PPT 全屏时必然被盖住。
    macos_window.set_accessory_policy()

    # Qt 自带控件的文案（对话框按钮等）：zh 装中文翻译，en 用 Qt 默认英文。
    i18n.translator_for_qt(app, i18n.language())

    # macOS：积分面板/弹窗是 level 25 的浮层，普通对话框（改名、确认框）会被
    # 它盖住并表现为假死。这里统一把对话框抬到 level 26。
    macos_window.install_dialog_raiser(app)
    # Windows：同样的问题换了个形式 —— 对话框是普通窗口，会被全屏 PPT 盖住，
    # 用户看到的是「点了没弹出窗口」。这里把它们钉到 topmost 层。
    win_window.install_dialog_raiser(app)

    # 启动事实（诊断「重启失败 / 语言没生效」用），失败静默
    startup_log.record([
        f"start version={VERSION} frozen={getattr(sys, 'frozen', False)}"
        f" restarted={_restarted}",
        f"lang env={_env_lang!r} config={_cfg_lang!r} "
        f"qsettings={_qsettings_lang!r} -> {i18n.language()!r}",
    ])


    # --- 旧版明文迁移（一次性）---
    # 老版本把分数明文写在 config.ini 里；如果还没有加密主文件，先把旧数据加密
    # 落盘，之后就再也不读明文 config.ini 了（它只是给人看的副本）。
    migrate_legacy_plaintext()

    # --- 层 2：原生模块完整性（被换/损坏 → 尝试一键还原） -----------
    native_state = {"ok": True, "restored": False, "reason": "OK"}
    try:
        from namepicker import guard as _guard
        native_state = _guard.check_both()
        if native_state["restored"]:
            startup_log.record([f"native module restored from backup: {native_state['reason']}"])
            try:
                from namepicker import integrity as _integrity_pre
                _integrity_pre.append_tamper_log(
                    os.path.dirname(resolve_config_path()), "critical",
                    "NATIVE_REPLACED", native_state["reason"])
            except Exception:                  # noqa: BLE001
                pass
        elif not native_state["ok"]:
            startup_log.record([f"native module rejected: {native_state['reason']}"])
    except Exception as exc:                      # noqa: BLE001
        native_state = {"ok": False, "restored": False, "reason": str(exc)}
        startup_log.record([f"native module unavailable: {exc}"])

    store = ConfigStore()

    # --- 事件链：校验 / 迁移 / 重放 --------------------------------
    # 分数以事件链为准：启动时先验签，通过则重放出组名与分数；
    # 失败说明文件被替换或损坏，此时**不采用**链上数据，并记录告警。
    class _ForeignData(Exception):
        """链属于另一个用户/机器，解密不可能成功。"""

    ledger_state = {"ok": True, "error": ""}
    security = {"level": "info", "problems": [], "ntp": {}}
    chain = None                                  # 链不可用时保持 None
    from namepicker import guard as _guard

    def _guard_pubkey() -> str:
        try:
            return _guard.pubkey_b64()
        except Exception:                         # noqa: BLE001
            return ""

    try:
        from namepicker import ledger as _ledger
        chain = _ledger.Ledger(store.path)
        if getattr(chain, "_resigned", False):
            startup_log.record(["ledger re-signed: legacy gen>0 records repaired"])
        if chain.count() == 0:
            # 首次运行：把现有配置写成期初事件（只做一次）
            chain.migrate_from(
                store.group_count,
                [store.get_group_name(i) for i in range(1, store.group_count + 1)],
                store.all_scores(),
            )
        problem = ""
        # 先看公钥：锚点记录的公钥与当前机器/用户的不一致，
        # 说明整条链是用另一把密钥加密的，解密必然失败 —— 这不是篡改，
        # 而是“换了机器或换了用户”，要给出不同的提示。
        _anchor = chain.read_anchor_full()
        _current_pub = _guard_pubkey()
        if (_anchor.get("pubkey") and _current_pub
                and _anchor["pubkey"] != _current_pub):
            ledger_state = {"ok": False, "foreign": True,
                            "error": _current_pub}
            startup_log.record([
                "ledger belongs to another user/machine: "
                f"anchor={_anchor['pubkey'][:8]}… current={_current_pub[:8]}…"])
            raise _ForeignData()

        if chain.count() and not chain.verify():
            problem = chain.verify_error() or "BAD_CHAIN"
        elif chain.count():
            problem = chain.rollback_reason()

        if problem and chain.restore_from_shadow():
            # 主链被删/被换，但安全副本完好：直接恢复，并告诉老师发生过什么
            state = chain.state()
            store.apply_ledger_state(state)
            pubkey = _guard_pubkey()
            chain._pubkey_b64 = pubkey
            chain.write_anchor(chain.count(), chain.head(), ts=int(state.get("ts", 0)),
                               digest=chain.state_digest(state), pubkey=pubkey)
            security = _guard.evaluate(chain, state, pubkey, _guard.network_time())
            ledger_state = {"ok": True, "error": problem, "recovered": True}
            # 回滚事件本身必须留档：恢复成功不代表没发生过
            try:
                from namepicker import integrity as _integrity_rec
                _integrity_rec.append_tamper_log(
                    os.path.dirname(store.path), "warn", "SHADOW_RESTORED",
                    f"detected={problem}")
            except Exception:                      # noqa: BLE001
                pass
            startup_log.record([f"ledger restored from shadow: {problem}"])
        elif problem:
            ledger_state = {"ok": False, "error": problem}
            startup_log.record([f"ledger rejected: {problem}"])
            try:
                from namepicker import integrity as _integrity_rej
                _integrity_rej.append_tamper_log(
                    os.path.dirname(store.path), "critical", "LEDGER_REJECTED", problem)
            except Exception:                  # noqa: BLE001
                pass
        elif chain.count():
            state = chain.state()
            store.apply_ledger_state(state)
            pubkey = _guard_pubkey()
            chain._pubkey_b64 = pubkey
            chain.write_anchor(chain.count(), chain.head(), ts=int(state.get("ts", 0)),
                               digest=chain.state_digest(state), pubkey=pubkey)
            security = _guard.evaluate(chain, state, pubkey, _guard.network_time())

        # 只有链可信时才挂上：链不可信还继续追加，会把坏链写得更长
        if ledger_state["ok"]:
            store.attach_ledger(chain)
        else:
            startup_log.record(["ledger not attached: chain is not trustworthy"])
    except _ForeignData:
        pass                                      # 已经设置好 foreign 状态
    except Exception as exc:                      # noqa: BLE001
        # 这里只可能是“安全模块不可用 / 程序内部错误”，不是数据被篡改。
        # 两者必须分开提示：把程序 bug 说成“数据被替换”会误导老师。
        ledger_state = {"ok": False, "internal": True, "error": str(exc)}
        startup_log.record([f"ledger unavailable: {type(exc).__name__}: {exc}"])

    # 长期抽取次数现在是事件链的一部分（op=draw），不再有明文文件
    stats = StatsStore(chain=chain if ledger_state["ok"] else None)
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

    def wipe_everything(parts: dict) -> None:
        """按勾选项执行彻底重置（实现见 namepicker/wipe_service.py）。"""
        report = wipe_service.perform_wipe(store, stats, engine, parts)
        if not report.ok():
            # 没写进磁盘就别在界面上假装已清空：回到磁盘上的真实数据
            store.reload_from_disk()
        points_win.reload_from_store(ok=report.ok())
        if report.ok():
            main_win.on_wipe_complete(
                tr("已重置：{x}", "Reset: {x}",
                   x=tr("、", ", ").join(report.labels))
                if report.labels else "")
        else:
            main_win.on_wipe_complete(
                tr("重置未生效：{e}", "Reset did not apply: {e}",
                   e=report.error or "unknown"), ok=False)

        # 关键：写入失败/读回校验失败必须让用户看见，不能静默装作成功。
        # （Windows 上文件被占用/目录只读时 os.replace 会失败，以前是静默的。）
        startup_log.record([
            f"wipe parts={parts} saved={report.saved} "
            f"verified={report.verified} error={report.error!r}",
        ])
        if not report.ok():
            from namepicker import dialogs as _dialogs
            QMessageBox.warning(
                _dialogs.visible_parent(main_win),
                tr("重置没有完全生效", "Reset did not fully apply"),
                tr("部分数据没能写入磁盘，或写入后校验不一致。\n\n"
                   "原因：{e}\n\n请确认程序所在目录可写、文件没有被其它程序占用后重试。",
                   "Some data could not be written to disk, or did not verify.\n\n"
                   "Reason: {e}\n\nMake sure the program directory is writable and "
                   "the files are not locked by another program, then try again.",
                   e=report.error or "unknown"),
            )

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

    # 事件链校验失败：必须让老师看见，而不是静默用旧数据
    if ledger_state.get("recovered"):
        main_win.statusBar().showMessage(
            tr("⚠ 检测到数据被删除或替换，已从安全副本恢复（{e}）。",
               "⚠ Data deletion or replacement detected; restored from a safe copy ({e}).",
               e=ledger_state["error"]),
            0,
        )
    elif ledger_state.get("foreign"):
        main_win.statusBar().showMessage(
            tr("⚠ 这份数据属于另一个用户或另一台电脑，本机无法解密。"
               "如需继续使用，请在积分面板按 config.ini 重新录入。",
               "⚠ This data belongs to another user or machine and cannot be "
               "decrypted here. Re-enter the scores from config.ini if needed."),
            0,
        )
    elif ledger_state.get("internal"):
        main_win.statusBar().showMessage(
            tr("⚠ 安全模块异常：{e}。已暂停记录新变动，请检查安装是否完整。",
               "⚠ Security module error: {e}. New changes are not being recorded; "
               "check the installation.",
               e=ledger_state["error"]),
            0,
        )
    elif not ledger_state["ok"]:
        main_win.statusBar().showMessage(
            tr("⚠ 数据校验失败：{e}。分数可能被替换过，已暂停采用链上数据。",
               "⚠ Integrity check failed: {e}. Scores may have been replaced; "
               "chain data is not being used.",
               e=ledger_state["error"]),
            0,
        )

    # --- 层 2/3/5/6 的结果：分级提示 + 归档 -------------------------
    # 原则：上课时尽量不打断（warn 只放状态栏），critical 才弹一次窗。
    from namepicker import integrity as _integrity

    log_dir = os.path.dirname(store.path)
    if not native_state["ok"]:
        _integrity.append_tamper_log(log_dir, "critical", "NATIVE_REJECTED",
                                     native_state["reason"])
        main_win.statusBar().showMessage(
            tr("⚠ 原生模块不可用（{e}），本次以只读模式运行。",
               "⚠ Native module unavailable ({e}); running read-only.",
               e=native_state["reason"]),
            0,
        )

    if security["problems"]:
        detail = "；".join(_guard.describe(p) for p in security["problems"])
        _integrity.append_tamper_log(log_dir, security["level"], "SECURITY", detail)
        main_win.statusBar().showMessage(
            tr("⚠ 数据完整性提示：{d}", "⚠ Integrity notice: {d}", d=detail), 0)
        if security["level"] == "critical" and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.warning(
                main_win,
                tr("数据可能被还原过", "Data may have been rolled back"),
                tr("检测到以下情况：\n\n{d}\n\n"
                   "程序会继续以只读方式使用当前数据，并已记录到 tamper.log。",
                   "Detected:\n\n{d}\n\n"
                   "The app keeps running read-only and logged this to tamper.log.",
                   d=detail),
            )

    def restart_app() -> None:
        """切换语言后立即重启：先释放单实例锁，再拉起新进程，最后退出自己。"""
        single.release()
        started = restart_service.restart()
        startup_log.record([f"restart requested -> started={started}"])
        if not started:
            QMessageBox.warning(
                main_win,
                tr("重启失败", "Restart failed"),
                tr("无法自动重启，请手动关闭后重新打开。",
                   "Could not restart automatically. Please close and reopen the app."),
            )
            return
        app.quit()

    def save_language(code: str) -> None:
        """语言写入 config.dat（QSettings 之外的第二份保险）。"""
        try:
            store.set_language(code)
            store.save()
        except Exception:
            pass

    main_win.language_saved.connect(save_language)
    main_win.restart_requested.connect(restart_app)

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
    ball.about_requested.connect(lambda: about_dialog.show_about(main_win))
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

    # 更新检查：窗口出来之后再查，失败静默（学校网络常访问不到 CDN）
    _start_update_check(main_win)

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
    exit_code = app.exec()
    main_win.save_settings()
    points_win.save_now()
    save_stats()
    # 主动释放单实例资源，避免留下孤儿套接字/共享内存（被强杀时仍可能残留，
    # SingleInstance 的探活逻辑已经能容忍这种情况）。
    single.release()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
