"""restart —— 切换语言后「立即重启」的实现。

单独抽出来有两个原因：
    * main() 里的闭包没法单测；
    * 源码运行与 PyInstaller 打包后的启动参数完全不同，值得各写一条断言。

注意顺序：**必须先释放单实例锁再拉起新进程**。新进程启动时会先探测
QLocalServer，如果旧进程还占着锁，新进程会以为「已有实例在运行」然后退出，
看起来就像重启失败。
"""

import os
import sys

from PyQt5.QtCore import QProcess


def restart_arguments(argv: list[str] | None = None) -> tuple[str, list[str]]:
    """返回 (可执行文件, 参数)。

    * 打包后（frozen）：sys.executable 就是程序本体，只传用户参数；
    * 源码运行：需要显式把 main.py 的绝对路径作为第一个参数。
    """
    argv = list(sys.argv if argv is None else argv)
    if getattr(sys, "frozen", False):
        return sys.executable, argv[1:]
    program = sys.executable
    script = os.path.abspath(argv[0]) if argv else ""
    return program, ([script] if script else []) + argv[1:]


def restart(argv: list[str] | None = None) -> bool:
    """拉起一个新进程（不等待），返回是否成功。调用方负责随后退出自己。"""
    program, arguments = restart_arguments(argv)
    try:
        return bool(QProcess.startDetached(program, arguments))
    except Exception:
        return False
