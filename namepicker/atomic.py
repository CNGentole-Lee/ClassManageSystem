"""atomic —— 跨平台的原子替换，带 Windows 重试。

为什么要重试：
    Windows 的 `os.replace()` 在目标文件被别的程序打开（杀毒软件扫描、
    OneDrive/索引服务、记事本查看 config.ini）时会抛 PermissionError。
    这类占用通常只持续几百毫秒，重试两三次就能成功。

    macOS/Linux 的 `rename()` 允许覆盖正在被打开的文件，所以同样的代码在
    那边从来看不出问题 —— 这也是「Windows 上保存/重置不生效」的根源之一。
"""

from __future__ import annotations

import os
import time

#: 尝试次数与退避间隔（总耗时 < 0.5s，不会让界面明显卡顿）
ATTEMPTS = 3
BASE_DELAY = 0.12


def replace_with_retry(src: str, dst: str,
                       attempts: int = ATTEMPTS,
                       base_delay: float = BASE_DELAY) -> None:
    """`os.replace` 的重试版本；全部失败时抛出最后一次异常。"""
    last_error = None
    for attempt in range(max(1, attempts)):
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(base_delay * (attempt + 1))
    raise last_error
