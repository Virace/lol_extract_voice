"""Qt 试听播放控制器测试。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtMultimedia import QAudio, QAudioFormat
from pyvgmstream import DecodeConfig, SampleFormat

from lol_audio_unpack.gui.controllers.preview_playback_controller import (
    PreparedPreviewAudio,
    PreviewAudioDecodePlan,
    PreviewPlaybackController,
    PreviewPlaybackState,
    build_preview_audio_decode_plan,
)

EXPECTED_SELECTED_VOLUME = 0.25


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def disconnect(self, callback) -> None:
        self._callbacks.remove(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)


class _FakeAudioDevice:
    def __init__(self, raw_id: bytes, *, supported: bool = True) -> None:
        self._raw_id = raw_id
        self._supported = supported
        self.checked_formats: list[QAudioFormat] = []

    def id(self) -> bytes:
        return self._raw_id

    def isFormatSupported(self, audio_format: QAudioFormat) -> bool:
        self.checked_formats.append(audio_format)
        return self._supported


class _FakeAudioSink:
    def __init__(self, device, audio_format: QAudioFormat, parent=None) -> None:
        _ = parent
        self.device = device
        self.audio_format = audio_format
        self.stateChanged = _FakeSignal()
        self.started_device = None
        self.volume = None
        self.stopped = False
        self._state = QAudio.State.StoppedState
        self._error = QAudio.Error.NoError

    def setVolume(self, value: float) -> None:
        self.volume = value

    def start(self, device):
        self.started_device = device
        self._state = QAudio.State.ActiveState
        return device

    def stop(self) -> None:
        self.stopped = True
        self._state = QAudio.State.StoppedState

    def state(self):
        return self._state

    def error(self):
        return self._error


class _PendingStartAudioSink(_FakeAudioSink):
    def start(self, device):
        self.started_device = device
        return device


class _FakeAudioBuffer:
    def __init__(self) -> None:
        self.closed = False
        self.deleted = False

    def close(self) -> None:
        self.closed = True

    def deleteLater(self) -> None:
        self.deleted = True


def _build_fake_audio_sink(device, audio_format: QAudioFormat, parent=None) -> _FakeAudioSink:
    return _FakeAudioSink(device, audio_format, parent)


def _build_pending_start_audio_sink(device, audio_format: QAudioFormat, parent=None) -> _PendingStartAudioSink:
    return _PendingStartAudioSink(device, audio_format, parent)


def test_build_preview_audio_decode_plan_promotes_pcm24_to_pcm32() -> None:
    plan = build_preview_audio_decode_plan(SampleFormat.PCM24)

    assert plan == PreviewAudioDecodePlan(
        decode_config=DecodeConfig(sample_format=SampleFormat.PCM32),
        stream_sample_format=SampleFormat.PCM32,
        qt_sample_format=QAudioFormat.SampleFormat.Int32,
    )


def test_build_preview_audio_decode_plan_preserves_float_output() -> None:
    plan = build_preview_audio_decode_plan(SampleFormat.FLOAT)

    assert plan == PreviewAudioDecodePlan(
        decode_config=None,
        stream_sample_format=SampleFormat.FLOAT,
        qt_sample_format=QAudioFormat.SampleFormat.Float,
    )


def test_preview_playback_controller_play_uses_selected_device_and_emits_state() -> None:
    selected_device = _FakeAudioDevice(b"selected-device")
    default_device = _FakeAudioDevice(b"default-device")
    created_sinks: list[_FakeAudioSink] = []
    controller = PreviewPlaybackController(
        decode_audio_fn=lambda path: PreparedPreviewAudio(
            audio_path=Path(path),
            pcm_bytes=b"\x01\x02\x03\x04",
            audio_format=_build_qt_audio_format(),
            duration_seconds=1.0,
        ),
        audio_sink_factory=lambda device, audio_format, parent: created_sinks.append(
            _FakeAudioSink(device, audio_format, parent)
        )
        or created_sinks[-1],
        audio_outputs_provider=lambda: [selected_device],
        default_audio_output_provider=lambda: default_device,
    )
    states: list[PreviewPlaybackState] = []
    controller.playback_state_changed.connect(states.append)
    controller.set_output_device_key(f"device:{selected_device.id().hex()}")
    controller.set_volume_percent(25)

    controller.play(audio_id="1001", audio_path=Path("1001.wem"))

    assert created_sinks[0].device is selected_device
    assert created_sinks[0].volume == EXPECTED_SELECTED_VOLUME
    assert states[-1] == PreviewPlaybackState(
        audio_id="1001",
        audio_path=Path("1001.wem"),
        progress=0.0,
        is_playing=True,
        is_paused=False,
    )

    controller.stop()

    assert created_sinks[0].stopped is True
    assert states[-1] == PreviewPlaybackState(
        audio_id=None,
        audio_path=None,
        progress=0.0,
        is_playing=False,
        is_paused=False,
    )


def test_preview_playback_controller_emits_error_when_device_rejects_format() -> None:
    unsupported_device = _FakeAudioDevice(b"unsupported-device", supported=False)
    controller = PreviewPlaybackController(
        decode_audio_fn=lambda path: PreparedPreviewAudio(
            audio_path=Path(path),
            pcm_bytes=b"\x01\x02",
            audio_format=_build_qt_audio_format(),
            duration_seconds=1.0,
        ),
        audio_sink_factory=_build_fake_audio_sink,
        audio_outputs_provider=lambda: [unsupported_device],
        default_audio_output_provider=lambda: unsupported_device,
    )
    errors: list[str] = []
    states: list[PreviewPlaybackState] = []
    controller.playback_error.connect(errors.append)
    controller.playback_state_changed.connect(states.append)
    controller.set_output_device_key(f"device:{unsupported_device.id().hex()}")

    controller.play(audio_id="1001", audio_path=Path("1001.wem"))

    assert errors == ["当前试听输出设备不支持该音频格式。"]
    assert states[-1] == PreviewPlaybackState(
        audio_id=None,
        audio_path=None,
        progress=0.0,
        is_playing=False,
        is_paused=False,
    )


def test_preview_playback_controller_marks_audio_active_during_backend_start_gap() -> None:
    default_device = _FakeAudioDevice(b"default-device")
    controller = PreviewPlaybackController(
        decode_audio_fn=lambda path: PreparedPreviewAudio(
            audio_path=Path(path),
            pcm_bytes=b"\x01\x02",
            audio_format=_build_qt_audio_format(),
            duration_seconds=1.0,
        ),
        audio_sink_factory=_build_pending_start_audio_sink,
        audio_outputs_provider=lambda: [],
        default_audio_output_provider=lambda: default_device,
    )
    states: list[PreviewPlaybackState] = []
    controller.playback_state_changed.connect(states.append)

    controller.play(audio_id="1001", audio_path=Path("1001.wem"))

    assert states[-1] == PreviewPlaybackState(
        audio_id="1001",
        audio_path=Path("1001.wem"),
        progress=0.0,
        is_playing=True,
        is_paused=False,
    )


def test_preview_playback_controller_defers_audio_buffer_close_until_cleanup() -> None:
    controller = PreviewPlaybackController(
        decode_audio_fn=lambda path: PreparedPreviewAudio(
            audio_path=Path(path),
            pcm_bytes=b"\x01\x02",
            audio_format=_build_qt_audio_format(),
            duration_seconds=1.0,
        ),
        audio_sink_factory=_build_fake_audio_sink,
        audio_outputs_provider=lambda: [],
        default_audio_output_provider=lambda: _FakeAudioDevice(b"default-device"),
    )
    fake_buffer = _FakeAudioBuffer()
    controller._audio_buffer = fake_buffer
    controller._audio_sink = _FakeAudioSink(_FakeAudioDevice(b"default-device"), _build_qt_audio_format())

    controller._dispose_session(emit_state=False)

    assert fake_buffer.closed is False
    assert fake_buffer.deleted is False

    controller._drain_retired_audio_buffers()

    assert fake_buffer.closed is True
    assert fake_buffer.deleted is True


def _build_qt_audio_format() -> QAudioFormat:
    audio_format = QAudioFormat()
    audio_format.setSampleRate(48000)
    audio_format.setChannelCount(2)
    audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return audio_format
