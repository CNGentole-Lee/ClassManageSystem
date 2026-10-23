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
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()

from PyQt5.QtCore import QSettings  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from namepicker import i18n, log_store, restart, theme  # noqa: E402
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
    from PyQt5.QtWidgets import QMessageBox
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
          program == sys.executable and args == ["/tmp/x/main.py", "--flag"],
          f"{program} {args}")
    sys.frozen = True
    try:
        program, args = restart.restart_arguments(["/Applications/App.app/exe", "--flag"])
    finally:
        del sys.frozen
    check("frozen app passes only user arguments",
          program == sys.executable and args == ["--flag"], f"{program} {args}")
    probe = os.path.join(tempfile.mkdtemp(prefix="cm_restart_"), "probe.py")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("pass\n")
    check("startDetached actually spawns a process", restart.restart([probe]) is True)

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
