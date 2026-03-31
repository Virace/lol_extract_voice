"""GUI 日志桥接测试。"""

from __future__ import annotations

from types import SimpleNamespace

from lol_audio_unpack.gui.common import log_bridge


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
