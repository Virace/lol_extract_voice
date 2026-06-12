"""GUI 单实例守卫测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.single_instance import (
    ACTIVATE_MESSAGE,
    acquire_or_activate,
    activate_window,
)


class _FakeSignal:
    """记录信号连接。"""

    def __init__(self) -> None:
        self.slots = []

    def connect(self, slot) -> None:
        """记录一个槽函数。"""
        self.slots.append(slot)


class _FakeServer:
    """模拟 ``QLocalServer`` 的 listen/remove 行为。"""

    listen_results: list[bool] = []
    instances: list[_FakeServer] = []
    removed_names: list[str] = []

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.newConnection = _FakeSignal()
        self.listened_names: list[str] = []
        _FakeServer.instances.append(self)

    def listen(self, name: str) -> bool:
        """按预设结果返回监听状态。"""
        self.listened_names.append(name)
        return _FakeServer.listen_results.pop(0)

    @classmethod
    def removeServer(cls, name: str) -> None:  # noqa: N802
        """记录清理僵尸本地服务名。"""
        cls.removed_names.append(name)


class _ConnectedSocket:
    """模拟可连接到已有实例的 ``QLocalSocket``。"""

    written_payloads: list[bytes] = []

    def __init__(self) -> None:
        self.server_name = ""

    def connectToServer(self, name: str) -> None:  # noqa: N802
        """记录连接目标。"""
        self.server_name = name

    def waitForConnected(self, _timeout_ms: int) -> bool:  # noqa: N802
        """模拟连接成功。"""
        return True

    def write(self, payload: bytes) -> int:
        """记录激活消息。"""
        self.written_payloads.append(payload)
        return len(payload)

    def flush(self) -> bool:
        """模拟 flush 成功。"""
        return True

    def waitForBytesWritten(self, _timeout_ms: int) -> bool:  # noqa: N802
        """模拟写入成功。"""
        return True

    def disconnectFromServer(self) -> None:  # noqa: N802
        """模拟主动断开。"""
        return None


class _DisconnectedSocket(_ConnectedSocket):
    """模拟无法连接到已有实例的 ``QLocalSocket``。"""

    def waitForConnected(self, _timeout_ms: int) -> bool:  # noqa: N802
        """模拟连接失败。"""
        return False


class _FakeWindow:
    """模拟可被激活的窗口。"""

    def __init__(self, *, visible: bool, minimized: bool) -> None:
        self._visible = visible
        self._minimized = minimized
        self.calls: list[str] = []

    def isVisible(self) -> bool:  # noqa: N802
        """返回窗口可见状态。"""
        return self._visible

    def isMinimized(self) -> bool:  # noqa: N802
        """返回窗口最小化状态。"""
        return self._minimized

    def show(self) -> None:
        """记录普通显示调用。"""
        self.calls.append("show")

    def showNormal(self) -> None:  # noqa: N802
        """记录从最小化恢复调用。"""
        self.calls.append("showNormal")

    def raise_(self) -> None:
        """记录置顶调用。"""
        self.calls.append("raise_")

    def activateWindow(self) -> None:  # noqa: N802
        """记录激活调用。"""
        self.calls.append("activateWindow")


def _reset_fakes() -> None:
    """清理所有 fake 的共享记录。"""
    _FakeServer.listen_results = []
    _FakeServer.instances = []
    _FakeServer.removed_names = []
    _ConnectedSocket.written_payloads = []


def test_acquire_or_activate_requests_existing_instance() -> None:
    """已有本地服务时，新进程应发激活消息并退出。"""
    _reset_fakes()
    _FakeServer.listen_results = [False]

    guard = acquire_or_activate(
        key="test-instance",
        server_cls=_FakeServer,
        socket_cls=_ConnectedSocket,
        timeout_ms=1,
    )

    assert guard is None
    assert _ConnectedSocket.written_payloads == [ACTIVATE_MESSAGE]
    assert _FakeServer.removed_names == []


def test_acquire_or_activate_removes_stale_server_name() -> None:
    """连接不到已有实例时，应清理僵尸服务名并重新监听。"""
    _reset_fakes()
    _FakeServer.listen_results = [False, True]

    guard = acquire_or_activate(
        key="stale-instance",
        server_cls=_FakeServer,
        socket_cls=_DisconnectedSocket,
        timeout_ms=1,
    )

    assert guard is not None
    assert _FakeServer.removed_names == ["stale-instance"]
    assert _ConnectedSocket.written_payloads == []
    assert _FakeServer.instances[-1].newConnection.slots


def test_activate_window_restores_minimized_window() -> None:
    """收到激活请求时，最小化窗口应先恢复再置前。"""
    window = _FakeWindow(visible=True, minimized=True)

    activate_window(window)

    assert window.calls == ["showNormal", "raise_", "activateWindow"]
