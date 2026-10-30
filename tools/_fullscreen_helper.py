"""全屏测试辅助进程：开一个窗口并进入 macOS 原生全屏（独立 Space）。

只被 tools/macos_check.py --fullscreen 调用，不参与主程序。

用法:
    python tools/_fullscreen_helper.py

输出:
    FULLSCREEN  —— 已确认进入原生全屏（NSWindowStyleMaskFullScreen）
    TIMEOUT     —— 10 秒内没进全屏
"""

import ctypes
import ctypes.util
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

#: NSWindowStyleMaskFullScreen = 1 << 14
FULLSCREEN_MASK = 1 << 14


def _objc():
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    return objc


def main() -> int:
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("FullScreenHelper")
    window.resize(600, 400)
    window.show()

    objc = _objc()
    msg = objc.objc_msgSend

    def sel(name: bytes):
        return objc.sel_registerName(name)

    def ns_window():
        msg.restype = ctypes.c_void_p
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        return msg(ctypes.c_void_p(int(window.winId())), sel(b"window"))

    def toggle():
        msg.restype = None
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        msg(ns_window(), sel(b"toggleFullScreen:"), None)

    def is_fullscreen():
        msg.restype = ctypes.c_ulong
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        return bool(msg(ns_window(), sel(b"styleMask")) & FULLSCREEN_MASK)

    def check(attempt: int = 0):
        if is_fullscreen():
            print("FULLSCREEN", flush=True)
        elif attempt < 40:
            QTimer.singleShot(250, lambda: check(attempt + 1))
        else:
            print("TIMEOUT", flush=True)

    QTimer.singleShot(300, toggle)
    QTimer.singleShot(800, lambda: check(0))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
