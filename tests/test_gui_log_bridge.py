"""GUI 日志桥接测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lol_audio_unpack.gui.common import log_bridge


@pytest.fixture(autouse=True)
def _isolate_log_bridge_state(monkeypatch) -> None:
    """通过显式卸载桥接副作用保证测试隔离。"""
    # 显式依赖 monkeypatch，保证 teardown 发生在 monkeypatch 还原之前。
    _ = monkeypatch
    if log_bridge._qt_log_bridge_state["installed"]:
        log_bridge.remove_qt_message_bridge()
    if log_bridge._pyvgmstream_log_bridge_state["installed"]:
        log_bridge.remove_pyvgmstream_log_bridge(disable_log_callback_fn=lambda: None)

    yield

    if log_bridge._qt_log_bridge_state["installed"]:
        log_bridge.remove_qt_message_bridge()
    if log_bridge._pyvgmstream_log_bridge_state["installed"]:
        log_bridge.remove_pyvgmstream_log_bridge(disable_log_callback_fn=lambda: None)


def test_install_qt_message_bridge_forwards_qt_warning_to_loguru(monkeypatch) -> None:
    installed_handler = None
    log_calls: list[tuple[str, str]] = []

    def fake_install(handler):
        nonlocal installed_handler
        previous = installed_handler
        installed_handler = handler
        return previous

    monkeypatch.setattr(log_bridge, "qInstallMessageHandler", fake_install)
    monkeypatch.setattr(log_bridge.logger, "log", lambda level, message: log_calls.append((level, message)))

    log_bridge.install_qt_message_bridge()
    installed_handler(
        log_bridge.QtMsgType.QtWarningMsg,
        SimpleNamespace(category="qt.multimedia"),
        "QIODevice::read (QBuffer): device not open",
    )

    assert log_calls == [("WARNING", "[Qt][qt.multimedia] QIODevice::read (QBuffer): device not open")]


def test_install_qt_message_bridge_downgrades_qt_info_to_debug(monkeypatch) -> None:
    installed_handler = None
    log_calls: list[tuple[str, str]] = []

    def fake_install(handler):
        nonlocal installed_handler
        previous = installed_handler
        installed_handler = handler
        return previous

    monkeypatch.setattr(log_bridge, "qInstallMessageHandler", fake_install)
    monkeypatch.setattr(log_bridge.logger, "log", lambda level, message: log_calls.append((level, message)))

    log_bridge.install_qt_message_bridge()
    installed_handler(
        log_bridge.QtMsgType.QtInfoMsg,
        SimpleNamespace(category="qt.multimedia"),
        "media backend selected",
    )

    assert log_calls == [("DEBUG", "[Qt][qt.multimedia] media backend selected")]


def test_install_pyvgmstream_log_bridge_forwards_callback_to_loguru(monkeypatch) -> None:
    captured_bridge = None
    log_calls: list[tuple[str, str]] = []

    def fake_set_log_callback(callback, *, level) -> None:
        nonlocal captured_bridge
        captured_bridge = (callback, level)

    monkeypatch.setattr(log_bridge.logger, "log", lambda level, message: log_calls.append((level, message)))

    log_bridge.install_pyvgmstream_log_bridge(set_log_callback_fn=fake_set_log_callback)
    callback, level = captured_bridge
    callback(log_bridge.PyVGMStreamLogLevel.DEBUG, "decoded chunk")

    assert level == log_bridge.PyVGMStreamLogLevel.DEBUG
    assert log_calls == [("DEBUG", "[pyvgmstream][DEBUG] decoded chunk")]


def test_install_pyvgmstream_log_bridge_downgrades_info_to_debug(monkeypatch) -> None:
    captured_bridge = None
    log_calls: list[tuple[str, str]] = []

    def fake_set_log_callback(callback, *, level) -> None:
        nonlocal captured_bridge
        captured_bridge = (callback, level)

    monkeypatch.setattr(log_bridge.logger, "log", lambda level, message: log_calls.append((level, message)))

    log_bridge.install_pyvgmstream_log_bridge(set_log_callback_fn=fake_set_log_callback)
    callback, _level = captured_bridge
    callback(log_bridge.PyVGMStreamLogLevel.INFO, "opened stream")

    assert log_calls == [("DEBUG", "[pyvgmstream][INFO] opened stream")]
