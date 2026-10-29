"""生成 README 用的界面截图（真实渲染，不是手绘示意图）。

用法:
    python tools/make_screenshots.py

产物: docs/images/*.png
    - 直接把真实控件 grab() 成图片，界面改了重跑一次就能同步更新。
    - 窗口都移到屏幕外（-5000,-5000）再截图，不会在你屏幕上闪。
    - Retina 上 grab 出来是 2x，这里缩回 1x 输出，控制仓库体积。
    - 用临时目录当数据目录，不碰真实的 config.dat / points_log.dat。

为什么不用系统级截屏：
    那样会把你自己的桌面、其它窗口一并拍进去；这里只截本程序的控件。
"""

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "images")
OFFSCREEN = -5000

# 先把项目根目录加进 sys.path，否则 import namepicker 会失败
sys.path.insert(0, ROOT)
# 截屏脚本不碰真实的隐蔽备份（Windows 注册表 / macOS plist）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _settings_isolation import isolate_settings  # noqa: E402

isolate_settings()

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from namepicker import i18n, theme  # noqa: E402
from namepicker.config_store import ConfigStore  # noqa: E402
from namepicker.draw_popup import DrawResultPopup  # noqa: E402
from namepicker.floating_ball import FloatingBall  # noqa: E402
from namepicker.main_window import MainWindow  # noqa: E402
from namepicker.name_engine import NameEngine  # noqa: E402
from namepicker.points_window import PointsWindow, _LogViewerDialog  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "images")
OFFSCREEN = -5000

#: 运行前用 CLASSMANAGE_THEME=light|dark 指定变体；light 输出常规文件名，
#: dark 输出 foo-dark.png（README 里并排展示深浅两套）。
VARIANT = (os.environ.get("CLASSMANAGE_THEME") or "light").lower()
THEME_SUFFIX = "" if VARIANT == "light" else f"-{VARIANT}"
os.environ["CLASSMANAGE_THEME"] = VARIANT

#: 语言变体：CLASSMANAGE_LANG=zh|en（默认 zh），英文输出带 -en 后缀
LANG = (os.environ.get("CLASSMANAGE_LANG") or "zh").lower()
LANG_SUFFIX = "" if LANG.startswith("zh") else "-en"
SUFFIX = THEME_SUFFIX + LANG_SUFFIX
os.environ["CLASSMANAGE_LANG"] = LANG

SAMPLE_NAMES = ["张伟", "李娜", "王强", "刘洋", "陈静", "杨帆", "赵磊", "黄婷",
                "周涛", "吴敏", "徐鹏", "孙悦", "马超", "朱琳", "胡军", "郭燕"]


def process(app, ms: int = 150) -> None:
    """跑一小段事件循环，让布局与动画推进到稳定状态。"""
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def save(widget, name: str, scale: int = 2) -> None:
    """渲染控件并保存为 1x PNG（scale=2 表示从 Retina 的 2x 缩回 1x）。"""
    pix = widget.grab()
    if scale > 1:
        pix = pix.scaled(pix.width() // scale, pix.height() // scale,
                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
    name = name.replace(".png", f"{SUFFIX}.png")
    path = os.path.join(OUT_DIR, name)
    pix.save(path, "PNG")
    print(f"  {name:26} {pix.width()}x{pix.height()}  {os.path.getsize(path) // 1024} KB")


def shot_floating_ball(app) -> None:
    """悬浮球：真实控件渲染 + 一块示意底衬（说明它默认贴在屏幕右侧边缘）。"""
    ball = FloatingBall()
    ball.move(OFFSCREEN, OFFSCREEN)
    ball.show()
    process(app, 300)

    w, h = 720, 240
    canvas = QImage(w, h, QImage.Format_ARGB32)
    dark = theme.is_dark()
    canvas.fill(QColor(28, 30, 34) if dark else QColor(246, 247, 249))
    painter = QPainter(canvas)
    painter.setPen(QColor(70, 74, 82) if dark else QColor(206, 210, 216))
    painter.drawLine(0, 26, w, 26)                    # 屏幕右边缘
    painter.setPen(QColor(226, 230, 236) if dark else QColor(120, 126, 136))
    painter.setFont(theme.font(13))
    painter.drawText(26, 66, i18n.tr("悬浮球：50×50，默认贴在屏幕右侧边缘",
                                    "Floating ball: 50x50, docked to the right screen edge"))
    painter.setFont(theme.font(12))
    painter.setPen(QColor(168, 176, 186) if dark else QColor(140, 146, 156))
    painter.drawText(26, 108, i18n.tr("双击 = 抽 1 人", "Double-click = draw one name"))
    painter.drawText(26, 138, i18n.tr("右键 = 连抽 2~10 人 · 积分管理 · 打开管理面板",
                                     "Right-click = draw 2-10 · points · open panel"))
    painter.drawText(26, 186, i18n.tr("始终置顶、不抢焦点，可在 PPT 全屏放映时操作",
                                     "Always on top, never steals focus, works over full-screen slides"))
    painter.setPen(QColor(70, 74, 82) if dark else QColor(206, 210, 216))
    painter.drawLine(26, 204, w - 26, 204)
    painter.end()

    ball_pix = ball.grab().scaled(ball.width(), ball.height(),
                                  Qt.KeepAspectRatio, Qt.SmoothTransformation)
    final = QImage(w, h, QImage.Format_ARGB32)
    final.fill(Qt.transparent)
    compose = QPainter(final)
    compose.drawImage(0, 0, canvas)
    compose.drawPixmap(w - ball_pix.width() - 12, (h - ball_pix.height()) // 2 - 6, ball_pix)
    compose.end()

    name = f"floating-ball{SUFFIX}.png"
    path = os.path.join(OUT_DIR, name)
    final.save(path, "PNG")
    print(f"  {name:26} {w}x{h}  {os.path.getsize(path) // 1024} KB")
    ball.hide()
    ball.deleteLater()


def scrub_paths(widget) -> None:
    """把控件里显示的临时绝对路径换成文件名。

    README 截图里出现 /var/folders/xxx/cm_shots_yyy/ 这种测试路径没有意义，
    所以只把「路径」这一部分换成文件名，其余文字保持原样（不改运行逻辑）。
    """
    from PySide6.QtWidgets import QLabel
    for label in widget.findChildren(QLabel):
        text = label.text()
        if "加密保存于" in text or "配置" in text or "Encrypted at" in text or "Config" in text:
            import re
            text = re.sub(r"(/[^\s（(]+/)([^/\s（(]+\.(?:dat|ini))", r"\2", text)
            label.setText(text)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    app = QApplication(sys.argv)
    # 与 main.py 一致：语言、字体、调色板、全局样式表，必须在建控件之前
    i18n.set_language(LANG)
    theme.apply(app)
    i18n.translator_for_qt(app, LANG)

    tmp = tempfile.mkdtemp(prefix="cm_shots_")

    # 造一份看起来像真实课堂的数据（临时目录，不影响你的真实数据）
    store = ConfigStore(os.path.join(tmp, "config.ini"))
    demo_names = (["第一组", "雄鹰组", "第三组", "飞虎组", "第五组", "第六组"]
                  if LANG.startswith("zh")
                  else ["Group 1", "Eagles", "Group 3", "Tigers", "Group 5", "Group 6"])
    for i, name in enumerate(demo_names, 1):
        store.set_group_name(i, name)
    store.set_score(1, 12, reason="+2")
    store.set_score(2, 8, reason="+3")
    store.set_score(3, 4, reason="+1")
    store.set_score(4, -2, reason="-1")
    store.set_score(1, 14, reason="+2")
    store.set_score(2, 5, reason="撤销 +3")
    store.save()

    names_file = os.path.join(tmp, "names.txt")
    with open(names_file, "w", encoding="utf-8") as f:
        f.write("\n".join(SAMPLE_NAMES))

    print("Generating screenshots:")
    shot_floating_ball(app)

    points = PointsWindow(store)
    points.move(OFFSCREEN, OFFSCREEN)
    points.resize(940, 680)
    points.show()
    process(app, 400)
    scrub_paths(points)
    process(app, 100)
    save(points, "points-panel.png")

    dlg = _LogViewerDialog(store.path, None)
    dlg.move(OFFSCREEN, OFFSCREEN)
    dlg.resize(720, 500)
    dlg.show()
    process(app, 300)
    scrub_paths(dlg)
    process(app, 100)
    save(dlg, "log-viewer.png")
    dlg.close()

    # 管理面板要在构造之后再喂数据，并且要自己接线：
    # 信号是在 main.py 里连的，MainWindow 自身不连接引擎，
    # 不补这几行截图里就是空名单、空历史。
    engine = NameEngine()
    win = MainWindow(engine, app_path="main.py")
    engine.names_loaded.connect(win.on_names_loaded)
    engine.name_drawn.connect(win.on_name_drawn)
    engine.cooldowns_updated.connect(win.on_cooldowns_updated)
    engine.history_cleared.connect(win.on_history_cleared)
    win.move(OFFSCREEN, OFFSCREEN)
    win.resize(900, 640)
    win.showNormal()
    process(app, 300)

    engine.load_names_from_file(names_file)
    process(app, 300)
    for _ in range(7):                      # 造点抽取历史，让冷却/历史有内容
        engine.draw_name()
        process(app, 60)
    process(app, 500)
    save(win, "main-window.png")

    popup = DrawResultPopup()
    popup.set_name_pool(SAMPLE_NAMES)
    popup.move(OFFSCREEN, OFFSCREEN)
    popup.show_results(["张伟", "李娜", "王强", "刘洋", "陈静"])
    process(app, 2600)                      # > ROLL_DURATION_MS(1800) + 揭晓延时
    save(popup, "draw-popup.png", scale=1)
    popup._on_close()

    print(f"\nDone, output directory: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
