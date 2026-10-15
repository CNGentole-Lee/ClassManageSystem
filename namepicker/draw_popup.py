"""DrawResultPopup —— 居中弹窗，带滚动动画、关闭按钮和自动关闭。

单抽和连抽共用：连抽时每个名字占一个格子，同时滚动、一起揭晓。
窗口随人数增大，字号随人数缩小。
"""

import random
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF,
)
from PyQt5.QtGui import (
    QPainter, QBrush, QColor, QFont, QFontMetrics, QPen, QPainterPath,
)
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QGridLayout, QPushButton, QHBoxLayout,
    QApplication,
)

from .config_store import APP_NAME


class DrawResultPopup(QWidget):
    """居中无边框弹窗，带滚动名字动画。

    约 2 秒快速轮换名字，然后定格在最终结果；有关闭按钮，揭晓 5 秒后自动关闭。
    """

    ROLL_DURATION_MS = 1800       # 名字轮换的总时长
    ROLL_INTERVAL_MS = 60         # 轮换期间名字切换的间隔
    AUTO_CLOSE_MS = 5000          # 揭晓后自动关闭的延时

    CELL_WIDTH = 104
    CELL_HEIGHT = 58

    SUBTITLE_QSS = """
        QLabel {
            color: #FFD700;
            font-family: "Microsoft YaHei";
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_names: list[str] = []
        self._result_names: list[str] = []
        self._name_labels: list[QLabel] = []
        self._roll_timer: QTimer | None = None
        self._roll_count = 0
        self._auto_close_timer: QTimer | None = None

        # 每次抽取重新计算的布局，在 show_results() 里赋值。
        self._columns = 1
        self._font_size = 40
        self._cell_width = self.CELL_WIDTH
        self._cell_height = self.CELL_HEIGHT

        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.setFixedSize(380, 208)

        # --- 顶部栏 + 关闭按钮 ---
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addStretch()

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(30, 30)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ccc;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #fff;
                background: rgba(255, 80, 80, 180);
                border-radius: 4px;
            }
        """)
        self._close_btn.clicked.connect(self._on_close)
        top_bar.addWidget(self._close_btn)

        # --- 副标题 ---
        self._subtitle = QLabel("🎉 恭喜!")
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setStyleSheet(self.SUBTITLE_QSS)

        # --- 名字网格（每次抽取重建）---
        self._name_host = QWidget()
        self._grid = QGridLayout(self._name_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)

        # --- 底部署名 ---
        self._footer = QLabel(APP_NAME)
        self._footer.setAlignment(Qt.AlignCenter)
        self._footer.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 80);
                font-family: "Microsoft YaHei";
                font-size: 11px;
                background: transparent;
            }
        """)

        # --- 布局 ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 8, 20, 12)
        main_layout.setSpacing(4)
        main_layout.addLayout(top_bar)
        main_layout.addStretch()
        main_layout.addWidget(self._subtitle)
        main_layout.addSpacing(6)
        main_layout.addWidget(self._name_host, 0, Qt.AlignCenter)
        main_layout.addStretch()
        main_layout.addWidget(self._footer)

    # --- Public API ---

    def set_name_pool(self, names: list[str]) -> None:
        """Provide the full list of names for the rolling animation."""
        self._all_names = list(names)

    def show_result(self, result_name: str) -> None:
        """Start the rolling animation and reveal a single name."""
        self.show_results([result_name])

    def show_results(self, result_names: list[str]) -> None:
        """Start the rolling animation and reveal `result_names` together."""
        self._result_names = [n for n in result_names if n]
        if not self._result_names:
            return

        self._stop_timers()

        columns, font_size = self._grid_shape(len(self._result_names))
        self._columns = columns
        self._font_size = font_size
        self._cell_width, self._cell_height = self._measure_cell(font_size)

        self._build_name_labels(len(self._result_names))
        self._resize_for(len(self._result_names))
        self._center_on_screen()

        # Show with fade-in
        self.setWindowOpacity(0.0)
        self.show()

        fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        fade_in.setDuration(250)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)
        fade_in.start()

        # Start rolling
        self._roll_count = 0
        self._subtitle.setText("🎉 抽签中...")
        self._subtitle.setStyleSheet(self.SUBTITLE_QSS)
        for label in self._name_labels:
            self._style_rolling(label)

        self._roll_timer = QTimer(self)
        self._roll_timer.timeout.connect(self._on_roll_tick)
        self._roll_timer.start(self.ROLL_INTERVAL_MS)

    # --- Layout ---

    def _grid_shape(self, count: int) -> tuple[int, int]:
        """(列数, 字号) — more names means more columns and smaller text."""
        if count <= 1:
            return 1, 40
        if count <= 3:
            return count, 32
        if count <= 4:
            return 2, 30
        if count <= 6:
            return 3, 26
        if count <= 8:
            return 4, 22
        return 5, 20

    def _measure_cell(self, font_size: int) -> tuple[int, int]:
        """Cell size wide enough for the longest name (rolling shows pool names)."""
        font = QFont("Microsoft YaHei", font_size, QFont.Bold)
        fm = QFontMetrics(font)
        pool = self._all_names or self._result_names
        widest = max((fm.horizontalAdvance(n) for n in pool), default=0)
        width = max(self.CELL_WIDTH, widest + 28)
        height = max(self.CELL_HEIGHT, fm.height() + 16)
        return width, height

    def _build_name_labels(self, count: int) -> None:
        """Tear down the previous grid and create `count` fresh labels."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._name_labels = []

        for index in range(count):
            label = QLabel("抽")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(self._cell_width, self._cell_height)
            label.setProperty("base_font_size", self._font_size)
            self._grid.addWidget(
                label, index // self._columns, index % self._columns
            )
            self._name_labels.append(label)

    def _resize_for(self, count: int) -> None:
        rows = (count + self._columns - 1) // self._columns
        width = max(380, self._columns * self._cell_width + 56)
        height = 104 + rows * self._cell_height + 44
        self.setFixedSize(width, height)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        x = geom.center().x() - self.width() // 2
        y = geom.center().y() - self.height() // 2
        self.move(x, y)

    def _style_rolling(self, label: QLabel) -> None:
        size = label.property("base_font_size") or 36
        label.setStyleSheet(f"""
            QLabel {{
                color: #87CEEB;
                font-family: "Microsoft YaHei";
                font-size: {size}px;
                font-weight: bold;
                background: transparent;
            }}
        """)

    def _style_final(self, label: QLabel) -> None:
        size = (label.property("base_font_size") or 36) + 2
        label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-family: "Microsoft YaHei";
                font-size: {size}px;
                font-weight: bold;
                background: transparent;
            }}
        """)

    # --- Internal ---

    def _on_roll_tick(self) -> None:
        self._roll_count += 1
        elapsed = self._roll_count * self.ROLL_INTERVAL_MS

        if elapsed >= self.ROLL_DURATION_MS:
            # Stop rolling — reveal result
            self._stop_timers()
            self._reveal_result()
            return

        # Show a random set of names — distinct within a single frame, so a
        # 连抽 looks like it is rolling real candidates.
        if self._all_names and self._name_labels:
            sample_size = min(len(self._name_labels), len(self._all_names))
            sample = random.sample(self._all_names, sample_size)
            for label, name in zip(self._name_labels, sample):
                label.setText(name)

    def _reveal_result(self) -> None:
        """Brief pause with the last random names, then reveal."""
        QTimer.singleShot(100, self._show_final)

    def _show_final(self) -> None:
        for label, name in zip(self._name_labels, self._result_names):
            label.setText(name)
            self._style_final(label)

        self._subtitle.setText("🎉 恭喜!")
        self._subtitle.setStyleSheet(self.SUBTITLE_QSS)

        # Auto-close after 5 seconds
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._fade_out)
        self._auto_close_timer.start(self.AUTO_CLOSE_MS)

    def _fade_out(self) -> None:
        """Fade out and close."""
        self._stop_timers()
        fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        fade_out.setDuration(400)
        fade_out.setStartValue(self.windowOpacity())
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)
        fade_out.finished.connect(self._on_close)
        fade_out.start()

    def _on_close(self) -> None:
        self._stop_timers()
        self.hide()

    def _stop_timers(self) -> None:
        for t in (self._roll_timer, self._auto_close_timer):
            if t is not None:
                t.stop()
        self._roll_timer = None
        self._auto_close_timer = None

    # --- Painting ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path.addRoundedRect(rect, 18, 18)

        painter.setBrush(QBrush(QColor(25, 25, 35, 235)))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawPath(path)

        painter.end()
