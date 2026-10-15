"""SingleInstance —— 单实例守护。

为什么不能只看 QSharedMemory：
    Unix（含 macOS）上的共享内存段不会随进程消失而释放。程序一旦被强杀
    （kill -9、崩溃、任务管理器结束进程、打包后的 .app 被强制退出），
    共享内存段会**变成孤儿留在系统里**。下次启动 attach 成功 → 程序判定
    “已有实例在运行” → 静默 sys.exit(0)，用户看到的就是「双击图标没反应」，
    而且永远好不了，只能重启机器。本项目在 macOS 打包验证时真实踩到过。

所以改用「本地套接字」判活：
    QLocalServer 是可靠的存活信号 —— 进程死了，套接字文件就没用了，监听必然失败。
    流程：先试着连已有 server
        连上      → 确实有实例在跑，发唤醒消息后退出
        连不上    → 没有实例；清掉陈旧套接字，自己 listen
        listen 失败 → 兜底再看一眼共享内存，避免极端竞态下起两个实例
共享内存只作为最后的兜底（Windows 上 QLocalServer 的清理语义也和这里一致）。
"""

import os

from PyQt5.QtCore import QObject, QSharedMemory, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

#: 套接字名按用户区分：多用户/多会话登录同一台机器时互不干扰
SERVER_NAME = "RandomNamePicker_LocalServer"
SHARED_MEM_KEY = "RandomNamePicker_SingleInstance"


class SingleInstance(QObject):
    """确保同一时间只有一个实例在运行。

    用法::

        guard = SingleInstance()
        if not guard.try_acquire():
            guard.notify_existing()      # 唤醒已有实例
            sys.exit(0)
        guard.wake_up_requested.connect(main_win.showNormal)
    """

    wake_up_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shared_mem: QSharedMemory | None = None
        self._server: QLocalServer | None = None
        self._stale_removed = False

    # --- 对外 ---

    def try_acquire(self) -> bool:
        """尝试成为唯一实例。True = 本进程就是主实例。"""
        # 1) 先探活：能连上说明真的有人在跑
        if self._probe_existing():
            return False

        # 2) 连不上：清掉可能残留的套接字文件，再自己监听
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        QLocalServer.removeServer(SERVER_NAME)
        self._stale_removed = True
        if self._server.listen(SERVER_NAME):
            self._server.newConnection.connect(self._on_new_connection)
            # 共享内存只作标记（失败不影响单实例判定）
            self._shared_mem = QSharedMemory(SHARED_MEM_KEY)
            if not self._shared_mem.create(1):
                self._shared_mem = None
            return True

        # 3) 监听失败（极少见：套接字路径不可写等）→ 退回共享内存判定
        self._server = None
        mem = QSharedMemory(SHARED_MEM_KEY)
        if mem.attach():
            mem.detach()
            return False        # 确实有实例在跑
        if mem.create(1):
            self._shared_mem = mem
            return True
        return True             # 两套机制都不可用：宁可多开一个，也不要静默不启动

    def notify_existing(self) -> bool:
        """给已有实例发唤醒消息。True = 已送达。"""
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if not socket.waitForConnected(1000):
            return False
        socket.write(b"wake")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        socket.close()
        return True

    def release(self) -> None:
        """主动释放（正常退出时调用，避免留下孤儿资源）。"""
        try:
            if self._server is not None:
                self._server.close()
                QLocalServer.removeServer(SERVER_NAME)
                self._server = None
            if self._shared_mem is not None:
                self._shared_mem.detach()
                self._shared_mem = None
        except Exception:
            pass

    # --- 内部 ---

    @staticmethod
    def _probe_existing() -> bool:
        """试连已有 server：连上 = 有实例在跑。"""
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        connected = socket.waitForConnected(300)
        socket.abort()
        socket.close()
        return bool(connected)

    def _on_new_connection(self) -> None:
        """收到第二个实例的连接 → 发唤醒信号。"""
        while self._server and self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                continue
            try:
                client.waitForReadyRead(500)
                client.readAll()          # 内容不重要，有连接就是唤醒
                client.disconnectFromServer()
                client.close()
            except Exception:
                pass
            self.wake_up_requested.emit()
