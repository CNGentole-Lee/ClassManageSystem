"""导出 / 导入的离线测试（不启动 GUI）。"""

import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

os.environ.setdefault("CLASSMANAGE_STATE_DIR", tempfile.mkdtemp(prefix="cm_exp_"))

from namepicker import export_import as ei      # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402
from namepicker.ledger import Ledger             # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="cm_export_")
    store = ConfigStore(os.path.join(tmp, "config.ini"))
    store.set_group_count(3)
    store.set_group_name(1, "雄鹰组")
    store.set_score(1, 7)
    store.set_score(2, -3)
    store.save()

    payload = ei.export_payload(store)
    check("export carries group count", payload["group_count"] == 3)
    check("export carries names", payload["names"][0] == "雄鹰组", str(payload["names"]))
    check("export carries scores", payload["scores"][:2] == [7, -3], str(payload["scores"]))

    path = os.path.join(tmp, "backup.json")
    ei.save(payload, path)
    check("file is valid JSON",
          json.load(open(path, encoding="utf-8"))["format"] == "classmanage-snapshot")

    loaded = ei.load(path)
    check("round-trip keeps the data",
          loaded["count"] == 3 and loaded["names"][0] == "雄鹰组"
          and loaded["scores"][:2] == [7, -3], str(loaded))

    # 坏文件必须拒绝
    bad = os.path.join(tmp, "bad.json")
    open(bad, "w", encoding="utf-8").write('{"format": "something-else"}')
    try:
        ei.load(bad)
        check("a foreign JSON is rejected", False)
    except ValueError:
        check("a foreign JSON is rejected", True)

    huge = os.path.join(tmp, "huge.json")
    ei.save(dict(payload, group_count=99), huge)
    try:
        ei.load(huge)
        check("out-of-range group count is rejected", False)
    except ValueError:
        check("out-of-range group count is rejected", True)

    # 导入：链上新增一条 init，之后的分数以它为准
    chain = Ledger(os.path.join(tmp, "import", "config.ini"))
    chain.import_snapshot(loaded)
    check("import writes one record", chain.count() == 1, str(chain.count()))
    state = chain.state()
    check("imported state replays", state["scores"][:2] == [7, -3], str(state["scores"]))

    reopened = Ledger(os.path.join(tmp, "import", "config.ini"))
    check("imported chain verifies", reopened.verify(), reopened.verify_error())

    # ---- MainWindow 通过积分面板拿到 store（曾经 AttributeError）----
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from namepicker import i18n, theme
        from namepicker.name_engine import NameEngine
        from namepicker.main_window import MainWindow
        from namepicker.points_window import PointsWindow

        app = QApplication.instance() or QApplication([])
        i18n.set_language("zh")
        theme.apply(app)
        panel = PointsWindow(store)
        win = MainWindow(NameEngine(), app_path="main.py")
        win.set_points_window(panel)
        check("MainWindow resolves the store", win._config_store() is store)
        payload2 = ei.export_payload(win._config_store())
        check("export works from the main window", payload2["group_count"] == 3)
        from PySide6.QtWidgets import QPushButton
        labels = [b.text() for b in win.findChildren(QPushButton)]
        check("bottom bar offers export and import",
              any("导出" in x for x in labels) and any("导入" in x for x in labels),
              str(labels))
    except ImportError:
        check("MainWindow resolves the store (skipped: no PySide6)", True)

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
