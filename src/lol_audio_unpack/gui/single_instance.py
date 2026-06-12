"""GUI 单实例运行守卫。"""

from __future__ import annotations

from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

INSTANCE_KEY = "Virace-LolAudioUnpack-GUI"
ACTIVATE_MESSAGE = b"activate"
DEFAULT_TIMEOUT_MS = 300


def activate_window(window: Any) -> None:
    """将已有 GUI 主窗口恢复到前台。

    Args:
        window: 需要恢复和激活的 Qt 窗口对象。
    """
    if window is None:
        return
    if not window.isVisible():
        window.show()
    elif window.isMinimized():
        window.showNormal()
    window.raise_()
    window.activateWindow()


class SingleInstanceGuard(QObject):
    """持有本地服务名，并在收到二次启动请求时激活主窗口。"""

    activated = Signal()

    def __init__(self, server: QLocalServer | None, parent: QObject | None = None) -> None:
        """初始化单实例守卫。

        Args:
            server: 已成功监听的本地服务；为 ``None`` 时退化为无守卫模式。
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._server = server
        self._window: Any = None
        if self._server is not None:
            self._server.newConnection.connect(self._handle_new_connection)
        self.activated.connect(lambda: activate_window(self._window))

    def set_window(self, window: Any) -> None:
        """绑定需要被二次启动请求激活的主窗口。

        Args:
            window: 当前进程创建的主窗口对象。
        """
        self._window = window

    def _handle_new_connection(self) -> None:
        """消费二次启动连接，并触发窗口激活。"""
        if self._server is not None:
            while self._server.hasPendingConnections():
                socket = self._server.nextPendingConnection()
                if socket is not None:
                    socket.readAll()
                    socket.disconnectFromServer()
        self.activated.emit()


def _send_activation_request(
    *,
    key: str,
    socket_cls: type[QLocalSocket],
    timeout_ms: int,
) -> bool:
    """向已有 GUI 实例发送激活请求。"""
    socket = socket_cls()
    socket.connectToServer(key)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(ACTIVATE_MESSAGE)
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


def acquire_or_activate(
    *,
    key: str = INSTANCE_KEY,
    parent: QObject | None = None,
    server_cls: type[QLocalServer] = QLocalServer,
    socket_cls: type[QLocalSocket] = QLocalSocket,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> SingleInstanceGuard | None:
    """获取 GUI 单实例守卫，或激活已有实例后返回 ``None``。

    Args:
        key: 本地服务名。
        parent: Qt 父对象。
        server_cls: 本地服务类，测试中可替换。
        socket_cls: 本地 socket 类，测试中可替换。
        timeout_ms: 连接已有实例时的超时时间。

    Returns:
        新进程应继续启动时返回守卫；已有实例已被激活时返回 ``None``。
    """
    server = server_cls(parent)
    if server.listen(key):
        return SingleInstanceGuard(server, parent=parent)

    if _send_activation_request(key=key, socket_cls=socket_cls, timeout_ms=timeout_ms):
        return None

    server_cls.removeServer(key)
    server = server_cls(parent)
    if server.listen(key):
        return SingleInstanceGuard(server, parent=parent)

    logger.warning("[GUI] 单实例服务监听失败，当前进程将继续以无守卫模式启动。")
    return SingleInstanceGuard(None, parent=parent)
