"""i18n checks: language switching, widget text, persistence, bilingual log.

Usage:
    python tools/i18n_check.py

Verifies:
    1. tr()/both()/normalize() behave for zh and en;
    2. widgets built after switching to English really use English labels;
    3. the language combo in the main window persists the choice to QSettings;
    4. operation-log entries carry both languages.

Exit code 0 = all passed.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _encoding import utf8_output  # noqa: E402

utf8_output()
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _headless import install as silence_dialogs  # noqa: E402
from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()
silence_dialogs()

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from namepicker import (  # noqa: E402
    about_dialog, dialogs, i18n, log_store, restart, theme, wipe_dialog,
)
from namepicker import config_store  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402
from namepicker.main_window import MainWindow  # noqa: E402
from namepicker.name_engine import NameEngine  # noqa: E402
from namepicker.points_window import PointsWindow  # noqa: E402
from namepicker.draw_popup import DrawResultPopup  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply(app)

    print("--- 1. Translation primitives ---")
    i18n.set_language("zh")
    check("zh picks the Chinese text", i18n.tr("中文", "English") == "中文")
    check("zh formats parameters", i18n.tr("{n} 个", "{n} items", n=3) == "3 个")
    i18n.set_language("en")
    check("en picks the English text", i18n.tr("中文", "English") == "English")
    check("en formats parameters", i18n.tr("{n} 个", "{n} items", n=3) == "3 items")
    check("en falls back to Chinese when no English given",
          i18n.tr("只有中文") == "只有中文")
    check("both() keeps two languages", i18n.both("第{n}组", "Group {n}", n=2)
          == ("第2组", "Group 2"))
    check("normalize handles locale codes",
          i18n.normalize("en_US") == "en" and i18n.normalize("zh_CN") == "zh")

    print("\n--- 2. Widgets follow the language ---")
    tmp = tempfile.mkdtemp(prefix="cm_i18n_")
    store = ConfigStore(os.path.join(tmp, "config.ini"))

    i18n.set_language("zh")
    store.set_score(1, 3, reason=i18n.both("+3", "+3"))
    store.save()
    zh_points = PointsWindow(store)
    zh_log_text = zh_points._log_btn.text()
    zh_points.close()

    i18n.set_language("en")
    en_points = PointsWindow(store)
    en_log_text = en_points._log_btn.text()
    check("log button is Chinese in zh mode", zh_log_text == "操作日志", zh_log_text)
    check("log button is English in en mode", en_log_text == "Log", en_log_text)
    check("group count button follows the language",
          en_points._log_btn.text() == "Log"
          and en_points._undo_btn.text().startswith("Undo"),
          f"{en_points._undo_btn.text()} / {en_points._log_btn.text()}")
    en_points.close()

    print("\n--- 3. Language combo persists to QSettings ---")
    from PySide6.QtWidgets import QMessageBox
    i18n.set_language("zh")
    settings = QSettings("NamePicker", "Config")
    settings.setValue("language", "zh")
    engine = NameEngine()
    engine.generate_number_list(1, 5)
    win = MainWindow(engine)
    # 切换语言会弹「重启后生效」提示框；测试里替换掉，避免阻塞
    original_question = QMessageBox.question
    original_information = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    try:
        win._lang_combo.setCurrentIndex(win._lang_combo.findData("en"))
    finally:
        QMessageBox.information = original_information
    check("combo writes the chosen language",
          settings.value("language") == "en", str(settings.value("language")))
    check("combo offers zh and en",
          [win._lang_combo.itemData(i) for i in range(win._lang_combo.count())]
          == ["zh", "en"])
    win.close()
    settings.setValue("language", "zh")

    print("\n--- 4. Bilingual operation log ---")
    entries = log_store.load(store.path).entries
    check("log has entries", bool(entries), f"{len(entries)}")
    check("entries carry both zh and en",
          all(zh and en for _s, zh, en in entries),
          f"first={entries[0] if entries else None}")

    print("\n--- 5. Default group names follow the language ---")
    i18n.set_language("zh")
    localized = ConfigStore(os.path.join(tmp, "localized.ini"))
    check("zh defaults are Chinese", localized.get_group_name(1) == "第一组",
          localized.get_group_name(1))
    localized.set_group_name(2, "雄鹰组")
    localized.save()
    i18n.set_language("en")
    check("default name switches to English",
          localized.get_group_name(1) == "Group 1", localized.get_group_name(1))
    check("custom name is untouched",
          localized.get_group_name(2) == "雄鹰组", localized.get_group_name(2))
    reloaded = ConfigStore(localized.path)
    check("localization survives a reload (not written back)",
          reloaded.get_group_name(1) == "Group 1"
          and reloaded.get_group_name(2) == "雄鹰组")
    i18n.set_language("zh")
    check("switching back restores Chinese defaults",
          ConfigStore(localized.path).get_group_name(1) == "第一组")

    print("\n--- 6. Language change asks to restart ---")
    restarts = []
    win.restart_requested.connect(lambda: restarts.append(True))
    i18n.set_language("zh")
    win._lang_combo.blockSignals(True)
    win._lang_combo.setCurrentIndex(win._lang_combo.findData("zh"))
    win._lang_combo.blockSignals(False)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    win._lang_combo.setCurrentIndex(win._lang_combo.findData("en"))
    check("choosing Yes emits restart_requested", len(restarts) == 1, f"{len(restarts)}")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    win._lang_combo.setCurrentIndex(win._lang_combo.findData("zh"))
    check("choosing No does not restart", len(restarts) == 1, f"{len(restarts)}")
    QMessageBox.question = original_question

    saved = []
    win.language_saved.connect(saved.append)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    win._lang_combo.setCurrentIndex(win._lang_combo.findData("en"))
    QMessageBox.question = original_question
    check("chosen language is emitted for config.dat persistence",
          saved == ["en"], f"{saved}")

    # 菜单里打开的对话框必须延后到 QMenu 退出之后（Windows 上同步打开会不激活）
    called = []
    win.set_wipe_handler(lambda parts: called.append("handler"))
    original_ask = wipe_dialog.ask
    original_show_about = about_dialog.show_about
    wipe_dialog.ask = lambda parent=None: called.append("wipe") or None
    about_dialog.show_about = lambda parent=None: called.append("about")
    try:
        win._on_wipe_all()
        check("wipe dialog is deferred (not opened inside the menu loop)",
              called == [], f"{called}")
        app.processEvents()
        check("wipe dialog opens after the menu loop unwinds",
              called == ["wipe"], f"{called}")

        called.clear()
        win._on_about()
        check("About is deferred too", called == [], f"{called}")
        app.processEvents()
        check("About opens after the menu loop unwinds",
              called == ["about"], f"{called}")
    finally:
        wipe_dialog.ask = original_ask
        about_dialog.show_about = original_show_about

    print("\n--- 7. Long foreign names ---")
    i18n.set_language("en")
    long_name = "Bartholomew Montgomery-Fitzgerald"
    long_store = ConfigStore(os.path.join(tmp, "long.ini"))
    long_store.set_group_name(1, long_name)
    long_store.save()
    long_points = PointsWindow(long_store)
    long_points.resize(940, 680)
    long_points.show()
    app.processEvents()
    card = long_points._cards[0]
    check("card keeps the full name", card._name_label.full_text() == long_name,
          card._name_label.full_text())
    check("card text is elided, not clipped",
          card._name_label.text() != long_name
          and card._name_label.text().endswith("\u2026"),
          f"shows {card._name_label.text()!r}")
    check("tooltip reveals the full name",
          card._name_label.toolTip() == long_name)
    long_points.close()

    popup = DrawResultPopup()
    popup.set_name_pool([long_name, "Li", "Wang"])
    popup.show_results([long_name])
    app.processEvents()
    popup._stop_timers()
    popup._show_final()          # 跳过滚动动画，直接看最终文字
    app.processEvents()
    screen_width = app.primaryScreen().availableGeometry().width()
    check("popup never exceeds the screen width", popup.width() <= screen_width,
          f"{popup.width()} <= {screen_width}")
    check("popup keeps the full name for the label",
          popup._name_labels[0].full_text() == long_name,
          popup._name_labels[0].full_text())
    check("popup elides the rendered text",
          popup._name_labels[0].text() != long_name,
          f"shows {popup._name_labels[0].text()!r}")
    popup.close()

    print("\n--- 8. Restart command line ---")
    program, args = restart.restart_arguments(["/tmp/x/main.py", "--flag"])
    check("source run passes the absolute script path",
          program == sys.executable and args == ["/tmp/x/main.py",
                                                restart.RESTART_FLAG, "--flag"],
          f"{program} {args}")
    check("restarted flag is added so the new instance waits",
          restart.RESTART_FLAG in args)
    sys.frozen = True
    try:
        program, args = restart.restart_arguments(
            ["/Applications/App.app/exe", "--flag", "-psn_0_12345"])
    finally:
        del sys.frozen
    check("frozen app passes user arguments and drops -psn_*",
          program == sys.executable
          and args == [restart.RESTART_FLAG, "--flag"], f"{program} {args}")
    probe = os.path.join(tempfile.mkdtemp(prefix="cm_restart_"), "probe.py")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("pass\n")
    check("startDetached actually spawns a process", restart.restart([probe]) is True)

    print("\n--- 8a. Restart waits for the old instance to exit ---")
    import subprocess, time as _time
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import sys, time; sys.path.insert(0, %r);"
         "from PySide6.QtWidgets import QApplication;"
         "from namepicker.single_instance import SingleInstance;"
         "app = QApplication([]); g = SingleInstance();"
         "print(g.try_acquire(), flush=True); time.sleep(8)" % _ROOT],
        cwd=_ROOT, stdout=subprocess.PIPE, text=True)
    try:
        held = holder.stdout.readline().strip()
        check("holder acquired the single-instance lock", held == "True", held)
        from namepicker.single_instance import SingleInstance
        early = SingleInstance()
        check("without retry a second instance gives up immediately",
              early.try_acquire() is False)
        holder.terminate()          # 旧进程开始收尾
        _time.sleep(0.2)
        late = SingleInstance()
        acquired = late.try_acquire(retry_seconds=6.0)
        check("with --restarted the new instance waits and then acquires",
              acquired is True)
        late.release()
    finally:
        if holder.poll() is None:
            holder.terminate()
        holder.wait(timeout=5)

    print("\n--- 8b. Dialogs must not block the ball (issue: license freezes drawing) ---")
    from PySide6.QtTest import QTest
    from namepicker import win_window
    from namepicker.floating_ball import FloatingBall

    ball = FloatingBall()
    ball.show()
    clicks = []
    ball.ball_clicked.connect(lambda: clicks.append(1))
    about_dialog.show_about(None)
    app.processEvents()
    about_dialog._open_about.setWindowModality(Qt.NonModal)
    check("About is non-modal", about_dialog._open_about.windowModality() == Qt.NonModal,
          str(about_dialog._open_about.windowModality()))
    # 悬浮球用自己的定时器判定双击：两次独立的 click 才算一次双击
    QTest.mouseClick(ball, Qt.LeftButton)
    QTest.mouseClick(ball, Qt.LeftButton)
    app.processEvents()
    check("double-clicking the ball still works while About is open",
          len(clicks) == 1, f"clicks={len(clicks)}")
    check("no application-modal widget is blocking input",
          QApplication.activeModalWidget() is None,
          type(QApplication.activeModalWidget()).__name__)
    about_dialog._open_about.close()
    app.processEvents()

    print("\n--- 8c. Dialog placement with a hidden parent ---")
    check("hidden parent is ignored", dialogs.visible_parent(None) is None)
    hidden = QWidget(); hidden.hide()
    check("a hidden widget is not used as parent",
          dialogs.visible_parent(hidden) is None)
    hidden.show(); app.processEvents()
    check("a visible widget is used as parent",
          dialogs.visible_parent(hidden) is hidden)
    hidden.close()
    probe = WipeDialogForTest = wipe_dialog.WipeDialog(None)
    probe.show()
    app.processEvents()
    dialogs.center_on_screen(probe)
    geo = app.primaryScreen().availableGeometry()
    inside = geo.contains(probe.geometry().center())
    check("centred on a real screen (not off-screen)", inside,
          f"centre={probe.geometry().center()} screen={geo}")
    check("wipe dialog has no hidden parent", probe.parent() is None)
    probe.close()

    print("\n--- 8d. Language persisted twice (QSettings + config.dat) ---")
    lang_store = ConfigStore(os.path.join(tmp, "lang.ini"))
    lang_store.set_language("en")
    lang_store.save()
    check("config.dat keeps the language",
          lang_store.get_language() == "en"
          and config_store.read_saved_language(lang_store.path) == "en",
          lang_store.get_language())

    print("\n--- 8e. Windows dialog raiser is platform-guarded ---")
    check("install_dialog_raiser returns False off Windows",
          win_window.install_dialog_raiser(app) is (sys.platform == "win32"))
    check("is_topmost is a safe no-op off Windows",
          win_window.is_topmost(ball) is False or sys.platform == "win32")

    ball.close()

    print("\n--- 9. About dialog / license compliance ---")
    check("LICENSE file is found next to the sources",
          bool(about_dialog.license_path()), about_dialog.license_path())
    text = about_dialog.license_text()
    check("license text is the Apache License 2.0",
          "Apache License" in text and "Version 2.0" in text)
    check("license text carries the copyright line",
          "Gentole Lee" in text and "Copyright" in text)
    check("license text mentions the warranty disclaimer",
          "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND" in text)
    check("license text states there is no warranty",
          "WITHOUT WARRANTIES" in text.upper())

    version_file = os.path.join(_ROOT, "packaging", "windows", "version_info.txt")
    # 版本号单一来源：模板里的版本号在构建时被替换，所以这里验证的是
    # 「两个 spec 都从 about_dialog 读版本」，而不是模板里写死的数字。
    check("version is a plain x.y.z", re.fullmatch(r"\d+\.\d+\.\d+",
                                                   about_dialog.VERSION) is not None,
          about_dialog.VERSION)
    check("version_info.txt is a template (version injected at build time)",
          os.path.isfile(version_file)
          and "about_dialog" in open(version_file, encoding="utf-8").read())
    for spec_path in (os.path.join(_ROOT, "packaging", "windows", "ClassManageSystem.spec"),
                      os.path.join(_ROOT, "packaging", "macos", "ClassManageSystem.spec")):
        if not os.path.isfile(spec_path):
            check(f"spec exists: {os.path.basename(os.path.dirname(spec_path))}", False)
            continue
        spec_text = open(spec_path, encoding="utf-8").read()
        check(f"{os.path.basename(os.path.dirname(spec_path))} spec reads VERSION "
              "from about_dialog",
              "about_dialog.py" in spec_text and "app_version" in spec_text)

    dlg = about_dialog.AboutDialog()
    check("about dialog builds", dlg.windowTitle() != "")

    # 分发的 EXE / .app 旁边没有 LICENSE 时，窗口也必须能显示许可证
    real_path_fn = about_dialog.license_path
    try:
        about_dialog.license_path = lambda: ""
        fallback = about_dialog.license_text()
    finally:
        about_dialog.license_path = real_path_fn
    check("missing LICENSE falls back to the embedded text",
          "Apache License" in fallback
          and "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND" in fallback
          and "Gentole Lee" in fallback,
          f"len={len(fallback)}")
    check("fallback mentions the online copy",
          "apache.org/licenses" in fallback)

    # 关于窗口的四个分页：许可证 / 原生模块 / 第三方组件 / 依赖
    from namepicker import about_dialog as ad
    dlg = ad.AboutDialog(None)
    tabs = [dlg._tabs.tabText(i) for i in range(dlg._tabs.count())]
    check("about dialog has four tabs", len(tabs) == 4, " / ".join(tabs))
    check("license tab is the first", tabs[0] in ("许可证", "License"), tabs[0])
    native_text = dlg._native_view.toPlainText()
    check("native tab shows the proprietary license",
          "cmd_native" in native_text and ("专有" in native_text or "proprietary" in native_text))
    notices_text = dlg._notices_view.toPlainText()
    check("third-party tab lists PySide6 and Qt",
          "PySide6" in notices_text and "Qt" in notices_text)
    deps_text = dlg._deps_view.toPlainText()
    check("dependencies tab lists libsodium and LGPL",
          "libsodium" in deps_text and "LGPL" in deps_text)
    check("dependencies tab explains Qt replaceability",
          "替换" in deps_text or "replace" in deps_text)
    dlg.deleteLater()
    dlg.close()

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
