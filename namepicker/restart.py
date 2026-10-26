"""restart —— 切换语言后「立即重启」的实现。

三个要点：
  1. **必须先释放单实例锁再拉起新进程**，否则新进程会以为「已有实例在运行」；
  2. 新进程带 `--restarted` 参数启动，单实例会让它多等几秒 —— 旧进程收尾
     （保存配置、销毁窗口）在 Windows 上比想象中慢，这段时间差足以让新进程
     误判并自杀，用户看到的就是「程序关掉后什么都没起来」；
  3. `QProcess.startDetached` 失败时退回 `subprocess`，Windows 上带
     DETACHED_PROCESS，避免新进程跟着旧进程的控制台一起消失。
"""

import os
import subprocess
import sys

from PyQt5.QtCore import QProcess

#: 新进程的标记参数（main.py 据此开启单实例重试）
RESTART_FLAG = "--restarted"

#: 重启时新进程最多等旧进程退出多少秒
RETRY_SECONDS = 6.0


def _clean_args(argv: list[str]) -> list[str]:
    """去掉 macOS 的 -psn_… 启动参数与重复的 --restarted。"""
    result = []
    for arg in argv:
        if arg.startswith("-psn_"):        # Finder 启动时附加，程序不需要
            continue
        if arg == RESTART_FLAG:
            continue
        result.append(arg)
    return result


def restart_arguments(argv: list[str] | None = None) -> tuple[str, list[str]]:
    """返回 (可执行文件, 参数)。

    * 打包后（frozen）：sys.executable 就是程序本体，只传用户参数；
    * 源码运行：需要显式把 main.py 的绝对路径作为第一个参数。
    """
    argv = list(sys.argv if argv is None else argv)
    user_args = [RESTART_FLAG] + _clean_args(argv[1:])
    if getattr(sys, "frozen", False):
        return sys.executable, user_args
    program = sys.executable
    script = os.path.abspath(argv[0]) if argv else ""
    return program, ([script] if script else []) + user_args


def _fallback(program: str, arguments: list[str]) -> bool:
    """QProcess 失败时的兜底启动。"""
    try:
        kwargs = {"close_fds": True}
        if sys.platform == "win32":
            # 不继承旧进程的控制台/句柄，独立存活
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([program] + arguments, **kwargs)
        return True
    except Exception:
        return False


def restart(argv: list[str] | None = None) -> bool:
    """拉起一个新进程（不等待），返回是否成功。调用方负责随后退出自己。"""
    program, arguments = restart_arguments(argv)
    try:
        if QProcess.startDetached(program, arguments):
            return True
    except Exception:
        pass
    return _fallback(program, arguments)
