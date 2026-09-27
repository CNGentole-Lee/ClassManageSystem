"""Single-instance enforcement using QSharedMemory + QLocalServer.

When a second instance is launched, it sends a wake-up message
to the first instance and exits immediately.
"""

from PyQt5.QtCore import QSharedMemory, QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "RandomNamePicker_LocalServer"
SHARED_MEM_KEY = "RandomNamePicker_SingleInstance"


class SingleInstance(QObject):
    """Ensures only one instance of the app runs.

    Usage:
        guard = SingleInstance()
        if not guard.try_acquire():
            # Another instance is already running — wake it and exit
            guard.notify_existing()
            sys.exit(0)

        # We are the first instance; connect wake-up signal
        guard.wake_up_requested.connect(main_win.show_and_activate)
    """

    wake_up_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shared_mem: QSharedMemory | None = None
        self._server: QLocalServer | None = None

    def try_acquire(self) -> bool:
        """Try to become the primary instance. Returns True if successful."""
        # Try to create shared memory segment
        self._shared_mem = QSharedMemory(SHARED_MEM_KEY)
        if self._shared_mem.attach():
            # Already exists → another instance is running
            self._shared_mem.detach()
            return False

        # Create it → we are the first instance
        if not self._shared_mem.create(1):
            # Creation failed (race condition or permissions)
            return False

        # Start local server to receive wake-up calls
        self._server = QLocalServer(self)
        # Remove any stale server
        QLocalServer.removeServer(SERVER_NAME)
        if not self._server.listen(SERVER_NAME):
            return False
        self._server.newConnection.connect(self._on_new_connection)

        return True

    def notify_existing(self) -> bool:
        """Send a wake-up message to the existing instance. Returns True if sent."""
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if socket.waitForConnected(1000):
            socket.write(b'wake')
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            socket.close()
            return True
        return False

    def _on_new_connection(self) -> None:
        """Handle incoming connection from a second instance."""
        while self._server and self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is not None:
                client.waitForReadyRead(500)
                # Any data means wake-up
                client.readAll()
                client.disconnectFromServer()
                client.close()
                self.wake_up_requested.emit()
