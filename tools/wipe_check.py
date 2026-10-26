"""Selective full-reset checks: dialog options + per-part wipe behaviour.

Usage:
    python tools/wipe_check.py

Verifies:
    1. WipeDialog offers the four parts and checks all of them by default;
    2. Each part can be cleared independently (names / scores / fairness / history);
    3. Clearing one part leaves the others untouched;
    4. The operation log is bilingual and is never cleared by a reset.

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

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from namepicker import i18n, log_store, wipe_service  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402
from namepicker.name_engine import NameEngine  # noqa: E402
from namepicker.stats_store import StatsStore  # noqa: E402
from namepicker.wipe_dialog import WipeDialog  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    app = QApplication(sys.argv)
    tmp = tempfile.mkdtemp(prefix="cm_wipe_check_")

    store = ConfigStore(os.path.join(tmp, "config.ini"))
    stats = StatsStore(os.path.join(tmp, "stats.ini"))
    engine = NameEngine()
    engine.generate_number_list(1, 5)

    def seed():
        """Reset everything, then install a known starting state."""
        i18n.set_language("zh")
        store.wipe_group_names()
        store.wipe_scores()
        store.set_group_name(2, "雄鹰组")
        store.set_score(1, 7)
        store.set_score(2, 3)
        store.save()
        stats.clear()
        stats.save({"1": 3, "2": 1})
        engine.reset_fairness()
        engine.set_draw_counts({"1": 3, "2": 1})
        engine.draw_name()

    def state():
        return {
            "name2": store.get_group_name(2),
            "scores": list(store.all_scores()),
            "stats": stats.load(),
            "counts": dict(engine.get_draw_counts()),
            "history": len(engine.get_history()),
        }

    print("--- 1. Dialog options ---")
    dialog = WipeDialog()
    check("four parts offered", set(dialog.selected()) ==
          {"names", "scores", "fairness", "history"}, f"actual {dialog.selected()}")
    check("all parts checked by default", all(dialog.selected().values()),
          f"actual {dialog.selected()}")
    check("labels follow the UI language",
          dialog.selected_labels() == ["组名", "积分", "长期公平记录", "抽取历史与冷却"],
          f"actual {dialog.selected_labels()}")

    dialog._boxes["scores"].setChecked(False)
    check("unchecking works", dialog.selected()["scores"] is False
          and dialog.selected()["names"] is True)
    check("labels list only checked parts", "积分" not in dialog.selected_labels(),
          f"actual {dialog.selected_labels()}")
    dialog.close()

    print("\n--- 1b. Second confirmation ---")
    original_warning = QMessageBox.warning
    original_information = QMessageBox.information
    try:
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Yes)
        ok_dialog = WipeDialog()
        ok_dialog.accept()
        check("accepts only after the second confirmation",
              ok_dialog.result() == QDialog.Accepted)

        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.No)
        no_dialog = WipeDialog()
        no_dialog.accept()
        check("declining the confirmation keeps the dialog open",
              no_dialog.result() != QDialog.Accepted)

        no_dialog._boxes["names"].setChecked(False)
        no_dialog._boxes["scores"].setChecked(False)
        no_dialog._boxes["fairness"].setChecked(False)
        no_dialog._boxes["history"].setChecked(False)
        QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
        no_dialog.accept()
        check("nothing selected -> does not accept",
              no_dialog.result() != QDialog.Accepted)
        for d in (ok_dialog, no_dialog):
            d.close()
    finally:
        QMessageBox.warning = original_warning
        QMessageBox.information = original_information

    print("\n--- 2. Names only ---")
    seed()
    before = state()
    report = wipe_service.perform_wipe(
        store, stats, engine,
        {"names": True, "scores": False, "fairness": False, "history": False})
    check("names-only wipe is saved and verified", report.ok(),
          f"saved={report.saved} verified={report.verified} err={report.error!r}")
    after = state()
    check("group names restored", after["name2"] != before["name2"], after["name2"])
    check("scores untouched", after["scores"] == before["scores"], f"{after['scores']}")
    check("fairness counts untouched", after["counts"] == before["counts"])
    check("history untouched", after["history"] == before["history"])

    print("\n--- 3. Scores only ---")
    seed()
    before = state()
    report = wipe_service.perform_wipe(
        store, stats, engine,
        {"names": False, "scores": True, "fairness": False, "history": False})
    check("scores-only wipe is saved and verified", report.ok(),
          f"saved={report.saved} verified={report.verified} err={report.error!r}")
    after = state()
    check("scores zeroed", after["scores"] == [0] * store.group_count,
          f"actual {after['scores']}")
    check("group names untouched", after["name2"] == before["name2"])
    check("fairness counts untouched", after["counts"] == before["counts"])
    check("history untouched", after["history"] == before["history"])

    print("\n--- 4. Fairness only ---")
    seed()
    before = state()
    wipe_service.perform_wipe(store, stats, engine,
                              {"names": False, "scores": False,
                               "fairness": True, "history": False})
    after = state()
    check("stats.ini cleared", after["stats"] == {}, f"actual {after['stats']}")
    check("in-memory counts cleared", not any(after["counts"].values()),
          f"actual {after['counts']}")
    check("history untouched", after["history"] == before["history"])
    check("scores untouched", after["scores"] == before["scores"])

    print("\n--- 5. History only ---")
    seed()
    before = state()
    wipe_service.perform_wipe(store, stats, engine,
                              {"names": False, "scores": False,
                               "fairness": False, "history": True})
    after = state()
    check("history cleared", after["history"] == 0, f"actual {after['history']}")
    check("fairness counts kept", after["counts"] == before["counts"],
          f"actual {after['counts']}")
    check("scores untouched", after["scores"] == before["scores"])

    print("\n--- 6. All four parts ---")
    seed()
    wipe_service.perform_wipe(store, stats, engine,
                              {"names": True, "scores": True,
                               "fairness": True, "history": True})
    after = state()
    check("all scores zero", after["scores"] == [0] * store.group_count)
    check("all stats cleared", after["stats"] == {})
    check("all history cleared", after["history"] == 0)
    check("names are defaults again", after["name2"] in ("第二组", "Group 2"),
          after["name2"])

    print("\n--- 7. Bilingual log, never cleared ---")
    entries = log_store.load(store.path).entries
    check("log has entries", bool(entries), f"{len(entries)} entries")
    check("every entry has both languages",
          all(zh and en for _s, zh, en in entries),
          f"first={entries[0] if entries else None}")
    check("reset entries are logged",
          any("彻底重置" in zh for _s, zh, _en in entries))
    check("English side uses 'Full reset'",
          any("Full reset" in en for _s, _zh, en in entries))

    print("\n--- 8. A failed write is reported, not silently ignored ---")
    import os as _os, stat as _stat
    ro_dir = tempfile.mkdtemp(prefix="cm_wipe_ro_")
    ro_store = ConfigStore(os.path.join(ro_dir, "config.ini"))
    ro_store.set_score(1, 5)
    ro_store.save()
    ro_stats = StatsStore(os.path.join(ro_dir, "stats.ini"))
    ro_engine = NameEngine()
    ro_engine.generate_number_list(1, 3)
    mode = _os.stat(ro_dir).st_mode
    _os.chmod(ro_dir, _stat.S_IRUSR | _stat.S_IXUSR)      # 只读目录
    try:
        failed = wipe_service.perform_wipe(
            ro_store, ro_stats, ro_engine,
            {"names": False, "scores": True, "fairness": False, "history": False})
        check("failed save is reported as not ok", not failed.ok(),
              f"saved={failed.saved} verified={failed.verified}")
        check("failure carries a reason", bool(failed.error), failed.error)
        # 失败后界面应回到磁盘上的真实数据，而不是继续显示“已清空”
        ro_store.reload_from_disk()
        check("reload_from_disk restores the on-disk values",
              ro_store.get_score(1) == 5, f"actual {ro_store.get_score(1)}")
    finally:
        _os.chmod(ro_dir, mode)

    print("\n--- 9. Windows file locks are retried ---")
    import os as _os2
    from namepicker import atomic as _atomic
    retry_dir = tempfile.mkdtemp(prefix="cm_retry_")
    src = _os2.path.join(retry_dir, "a.tmp")
    dst = _os2.path.join(retry_dir, "a.dat")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write("x")
    real_replace = _os2.replace
    calls = {"n": 0}

    def flaky_replace(a, b):
        calls["n"] += 1
        if calls["n"] < 3:                 # 前两次模拟被杀软/索引占用
            raise PermissionError("file is locked")
        return real_replace(a, b)

    _os2.replace = flaky_replace
    try:
        _atomic.replace_with_retry(src, dst, attempts=3, base_delay=0.01)
        check("transient lock is retried and succeeds",
              calls["n"] == 3 and _os2.path.isfile(dst), f"calls={calls['n']}")
    finally:
        _os2.replace = real_replace

    calls["n"] = 0

    def always_fail(a, b):
        calls["n"] += 1
        raise PermissionError("still locked")

    _os2.replace = always_fail
    try:
        failed_retry = False
        try:
            _atomic.replace_with_retry(src, dst, attempts=2, base_delay=0.01)
        except OSError:
            failed_retry = True
        check("permanent lock still raises after the attempts",
              failed_retry and calls["n"] == 2, f"calls={calls['n']}")
    finally:
        _os2.replace = real_replace

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
