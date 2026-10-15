"""生成 Windows 应用图标 app.ico（用 Qt 渲染，不依赖 Pillow）。

用法:
    python packaging/make_icon.py

产物: packaging/windows/app.ico
    —— 蓝色圆球 + 白色「抽」，与界面上的悬浮球同一套视觉。
    —— 内含 256/128/64/48/32/16 六种尺寸（PNG 压缩条目，Windows Vista+ 原生支持）。

只在需要换图标时手动跑一次；产物 app.ico 已入库，CI 不依赖本脚本。
"""

import os
import struct
import sys

from PyQt5.QtCore import QBuffer, QByteArray, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QImage, QPainter
from PyQt5.QtWidgets import QApplication

SIZES = (256, 128, 64, 48, 32, 16)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "windows", "app.ico")

BG = QColor(70, 130, 180)      # 钢蓝，与 FloatingBall.COLOR_NORMAL 一致
FG = QColor(255, 255, 255)


def render(size: int) -> QImage:
    """画一个 size×size 的图标：圆形底 + 「抽」字。"""
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    painter.setPen(Qt.NoPen)
    painter.setBrush(BG)
    painter.drawEllipse(QRectF(0, 0, size, size))

    font = QFont()
    font.setFamily("Microsoft YaHei")     # Windows 目标机一定有；macOS 会回退
    font.setPixelSize(int(size * 0.62))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(FG)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "抽")
    painter.end()
    return image


def to_png(image: QImage) -> bytes:
    # 注意：QBuffer 不持有底层 QByteArray 的所有权。写成 QBuffer(QByteArray())
    # 会让那个临时对象立刻被 GC 回收，QBuffer 指向野内存 → 段错误（本文件踩过）。
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(frames: list, path: str) -> None:
    """按 ICO 结构手写容器：ICONDIR + ICONDIRENTRY[] + PNG 数据。"""
    header = struct.pack("<HHH", 0, 1, len(frames))       # reserved, type=icon, count
    offset = len(header) + 16 * len(frames)
    entries, payload = b"", b""
    for size, png in frames:
        dim = 0 if size >= 256 else size                   # 256 在 ICO 里用 0 表示
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(header + entries + payload)


def main() -> int:
    app = QApplication(sys.argv)          # QImage/QPainter 需要 QGuiApplication
    frames = [(size, to_png(render(size))) for size in SIZES]
    write_ico(frames, OUT)
    print(f"已生成 {OUT}（{os.path.getsize(OUT)} 字节，{len(frames)} 种尺寸）")
    # 不要显式 del app：手动销毁 QApplication 再做 Qt 收尾会二次清理（段错误常见来源）
    return 0


if __name__ == "__main__":
    sys.exit(main())
