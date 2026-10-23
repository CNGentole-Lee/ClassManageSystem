"""复现「关掉积分面板把整个程序关掉」的最小实验。

构造和真实程序一样的窗口拓扑：
  - 悬浮球：Qt.Tool（不算"主窗口"，不影响 lastWindowClosed）
  - 积分面板：普通 QWidget（算"主窗口"）

然后关掉面板，看 app.exec_() 是不是提前返回（= 程序被 quitOnLastWindowClosed 关掉）。
"""

import sys
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget

app = QApplication(sys.argv)
print("quitOnLastWindowClosed =", app.quitOnLastWindowClosed())
app.setQuitOnLastWindowClosed(False)   # 修复：托盘应用不该被"最后一个窗口关闭"带崩
print("quitOnLastWindowClosed after fix =", app.quitOnLastWindowClosed())

ball = QWidget(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
ball.show()

panel = QWidget()
panel.show()

start = time.time()
QTimer.singleShot(300, panel.close)          # 关掉面板
QTimer.singleShot(2000, app.quit)            # 安全网：如果没被关掉，2 秒后手动退出

app.exec_()
elapsed = time.time() - start
print(f"exec_ returned after {elapsed:.2f}s")
if elapsed < 1.5:
    print(">>> Reproduced: closing the panel quits the whole app (quitOnLastWindowClosed is active)")
else:
    print(">>> Not reproduced: the app survives after the panel closes")
