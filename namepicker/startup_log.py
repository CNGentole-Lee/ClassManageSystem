"""startup_log —— 记录启动与重启过程中的关键事实。

为什么需要：
    「Windows 下切换语言没生效 / 重启失败」这类问题在开发机上复现不了。
    与其反复猜，不如每次启动写几行事实：从哪儿读到的语言、最终用的语言、
    是不是被 `--restarted` 拉起来的、单实例是否抢到、重启是否成功。

日志写在配置文件同目录的 `startup.log`，只保留最近若干条，失败一律静默。
"""

from __future__ import annotations

import os
from datetime import datetime

FILENAME = "startup.log"
MAX_LINES = 40


def path_for() -> str:
    """与 config.dat 同目录（沿用同一套只读目录回退规则）。"""
    try:
        from .config_store import resolve_config_path, data_path_for
        return os.path.join(os.path.dirname(os.path.abspath(resolve_config_path())),
                            FILENAME)
    except Exception:
        return ""


def record(lines, path: str = "") -> None:
    """追加一段带时间戳的记录（自动裁剪到 MAX_LINES 行）。"""
    target = path or path_for()
    if not target:
        return
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        block = [f"[{stamp}] {line}" for line in lines]
        old = []
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8", errors="replace") as fh:
                old = fh.read().splitlines()
        merged = (old + block)[-MAX_LINES:]
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(merged) + "\n")
        os.replace(tmp, target)
    except Exception:
        pass          # 诊断日志绝不能影响启动
