"""崩溃日志 —— 把 Python traceback 和原生故障写到文件里。

为什么需要：
    正式运行时通常没有控制台（pythonw.exe 或窗口版 PyInstaller EXE），出错时
    traceback 写进无人可见的 stderr，程序看起来像凭空消失。crash.log 把证据
    保存在 config.ini 旁边，事后可以诊断难以复现的故障。
"""

import faulthandler
import sys
import traceback
from datetime import datetime

# 让 faulthandler 的文件流存活整个进程 —— faulthandler 只持有文件对象的弱引用。
_log_stream = None
_log_path = ""
_log_count = 0
MAX_LOG_ENTRIES = 200  # 防止同一错误反复触发写满磁盘


def log_path() -> str:
    return _log_path


def log_exception(exc_type, exc, tb, context: str = "") -> None:
    """向 crash.log 追加一条 traceback（尽力而为，绝不抛异常）。"""
    global _log_count
    if _log_count >= MAX_LOG_ENTRIES:
        return
    _log_count += 1
    try:
        if not _log_path:
            return
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} {context} ===\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
    except OSError:
        pass


def install(log_directory: str) -> str:
    """把崩溃日志指向 `log_directory`/crash.log，返回日志路径。"""
    global _log_path, _log_stream
    import os

    _log_path = os.path.join(log_directory, "crash.log")

    # Python 层异常（包括 PyQt 即将因之中止的那些）。
    def _excepthook(exc_type, exc, tb):
        log_exception(exc_type, exc, tb, context="uncaught")
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _excepthook

    # 原生故障（访问违例、栈溢出）：打印堆栈。
    try:
        _log_stream = open(_log_path, "a", encoding="utf-8")
        faulthandler.enable(_log_stream)
    except OSError:
        _log_stream = None

    return _log_path
