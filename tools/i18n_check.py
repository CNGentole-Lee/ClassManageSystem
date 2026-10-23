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

from namepicker import i18n, log_store, theme  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402
from namepicker.main_window import MainWindow  # noqa: E402
from namepicker.name_engine import NameEngine  # noqa: E402
from namepicker.points_window import PointsWindow  # noqa: E402

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

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
