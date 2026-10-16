"""生成 macOS 应用图标 app.icns（用 Qt 渲染 + 标准库拼装，不依赖 Pillow）。

用法:
    python packaging/macos/make_icns.py

产物: packaging/macos/app.icns
    —— 蓝色圆球 + 白色「抽」，与悬浮球/Windows 图标同一套视觉。
    —— 含 16/32/64/128/256/512/1024 七档；icns 要求 512@2x 与 1024 用
       JPEG2000 编码，macOS 自带 `sips` 完成这一步（Windows/Linux 上跳过）。

只在换图标时手动跑一次；产物 app.icns 已入库，打包脚本不会重复生成。
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile

from PyQt5.QtCore import QBuffer, QByteArray, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QImage, QPainter
from PyQt5.QtWidgets import QApplication

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.icns")

#: icns 里各档的 OSType 与像素尺寸。前四档用 PNG，后两档 macOS 要求 JPEG2000。
PNG_SIZES = ((b"icp4", 16), (b"icp5", 32), (b"icp6", 64),
             (b"ic07", 128), (b"ic08", 256), (b"ic09", 512))
JP2_SIZES = ((b"ic10", 1024), (b"ic14", 1024), (b"ic13", 512))

BG = QColor(70, 130, 180)      # 钢蓝，与 FloatingBall.COLOR_NORMAL 一致
FG = QColor(255, 255, 255)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(BG)
    painter.drawEllipse(QRectF(0, 0, size, size))

    font = QFont()
    font.setFamily("PingFang SC")
    font.setPixelSize(int(size * 0.62))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(FG)
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "抽")
    painter.end()
    return image


def to_png(image: QImage) -> bytes:
    # QBuffer 不持有底层 QByteArray 的所有权：千万别写 QBuffer(QByteArray())，
    # 临时对象会被 GC 回收导致段错误（本项目踩过）。
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def to_jp2(image: QImage, tmpdir: str) -> bytes:
    """用 macOS 自带的 sips 转 JPEG2000；非 macOS 或无 sips 则返回 PNG 兜底。"""
    png = os.path.join(tmpdir, "src.png")
    jp2 = os.path.join(tmpdir, "out.jp2")
    with open(png, "wb") as f:
        f.write(to_png(image))
    sips = shutil.which("sips")
    if not sips:
        return to_png(image)
    try:
        subprocess.run([sips, "-s", "format", "jp2", png, "--out", jp2],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(jp2, "rb") as f:
            return f.read()
    except Exception:
        return to_png(image)


def write_icns(chunks: list, path: str) -> None:
    body = b""
    for ostype, payload in chunks:
        body += ostype + struct.pack(">I", len(payload) + 8) + payload
    with open(path, "wb") as f:
        f.write(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> int:
    app = QApplication(sys.argv)          # QImage/QPainter 需要 QGuiApplication
    chunks = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for ostype, size in PNG_SIZES:
            chunks.append((ostype, to_png(render(size))))
        for ostype, size in JP2_SIZES:
            chunks.append((ostype, to_jp2(render(size), tmpdir)))
    write_icns(chunks, OUT)
    print(f"已生成 {OUT}（{os.path.getsize(OUT)} 字节，{len(chunks)} 档）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
