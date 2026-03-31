"""Qt 试听播放控制器。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioDevice, QAudioFormat, QAudioSink, QMediaDevices
from pyvgmstream import DecodeConfig, SampleFormat, open_stream

PREVIEW_AUDIO_READ_CHUNK_FRAMES = 4096
DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY = "default"


@dataclass(frozen=True, slots=True)
class PreviewAudioDecodePlan:
    """描述 Qt 播放前需要采用的解码策略。"""

    decode_config: DecodeConfig | None
    stream_sample_format: SampleFormat
    qt_sample_format: QAudioFormat.SampleFormat


@dataclass(frozen=True, slots=True)
class PreparedPreviewAudio:
    """描述一段已经准备好交给 Qt 播放的音频负载。"""

    audio_path: Path
    pcm_bytes: bytes
    audio_format: QAudioFormat
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class PreviewPlaybackState:
    """描述当前试听控件需要渲染的播放状态。"""

    audio_id: str | None
    audio_path: Path | None
    progress: float
    is_playing: bool
    is_paused: bool


def build_preview_audio_decode_plan(sample_format: SampleFormat) -> PreviewAudioDecodePlan:
    """为当前上游输出格式构造 Qt 可消费的解码策略。

    Args:
        sample_format: `pyvgmstream` 当前流的输出采样格式。

    Returns:
        PreviewAudioDecodePlan: Qt 播放所需的解码配置与目标采样格式。
    """
    if sample_format is SampleFormat.PCM24:
        return PreviewAudioDecodePlan(
            decode_config=DecodeConfig(sample_format=SampleFormat.PCM32),
            stream_sample_format=SampleFormat.PCM32,
            qt_sample_format=QAudioFormat.SampleFormat.Int32,
        )
    if sample_format is SampleFormat.PCM16:
        return PreviewAudioDecodePlan(
            decode_config=None,
            stream_sample_format=SampleFormat.PCM16,
            qt_sample_format=QAudioFormat.SampleFormat.Int16,
        )
    if sample_format is SampleFormat.PCM32:
        return PreviewAudioDecodePlan(
            decode_config=None,
            stream_sample_format=SampleFormat.PCM32,
            qt_sample_format=QAudioFormat.SampleFormat.Int32,
        )
    if sample_format is SampleFormat.FLOAT:
        return PreviewAudioDecodePlan(
            decode_config=None,
            stream_sample_format=SampleFormat.FLOAT,
            qt_sample_format=QAudioFormat.SampleFormat.Float,
        )
    raise ValueError(f"不支持的预览采样格式: {sample_format!r}")


def decode_preview_audio(
    path: str | Path,
    *,
    open_stream_fn: Callable[..., object] = open_stream,
) -> PreparedPreviewAudio:
    """读取指定音频并准备 Qt 可直接播放的 PCM 负载。

    Args:
        path: 目标音频路径。
        open_stream_fn: 便于测试替换的 `pyvgmstream.open_stream` 入口。

    Returns:
        PreparedPreviewAudio: 预解码后的音频负载。
    """
    audio_path = Path(path).expanduser().resolve()
    with open_stream_fn(audio_path) as probe_stream:
        decode_plan = build_preview_audio_decode_plan(probe_stream.sample_format)

    with open_stream_fn(audio_path, config=decode_plan.decode_config) as stream:
        audio_format = _build_qt_audio_format(
            sample_rate=stream.sample_rate,
            channels=stream.channels,
            sample_format=decode_plan.qt_sample_format,
        )
        chunks: list[bytes] = []
        while True:
            remaining_frames = max(int(stream.play_samples) - int(stream.tell_samples()), 0)
            frame_count = (
                min(PREVIEW_AUDIO_READ_CHUNK_FRAMES, remaining_frames)
                if remaining_frames > 0
                else PREVIEW_AUDIO_READ_CHUNK_FRAMES
            )
            if frame_count <= 0:
                break
            chunk = stream.read_frames(frame_count)
            if not chunk:
                break
            chunks.append(chunk)
            if stream.done:
                break

        return PreparedPreviewAudio(
            audio_path=audio_path,
            pcm_bytes=b"".join(chunks),
            audio_format=audio_format,
            duration_seconds=float(getattr(stream, "duration_seconds", 0.0)),
        )


def _build_qt_audio_format(
    *,
    sample_rate: int,
    channels: int,
    sample_format: QAudioFormat.SampleFormat,
) -> QAudioFormat:
    """构造一份 Qt 原始 PCM 播放格式。"""
    audio_format = QAudioFormat()
    audio_format.setSampleRate(int(sample_rate))
    audio_format.setChannelCount(int(channels))
    audio_format.setSampleFormat(sample_format)
    return audio_format


def _build_audio_output_device_key(device: QAudioDevice) -> str:
    """为 Qt 音频输出设备构造稳定键值。"""
    return f"device:{bytes(device.id()).hex()}"


def resolve_preview_audio_output_device(
    device_key: str,
    *,
    audio_outputs_provider: Callable[[], list[QAudioDevice]] = QMediaDevices.audioOutputs,
    default_audio_output_provider: Callable[[], QAudioDevice] = QMediaDevices.defaultAudioOutput,
) -> QAudioDevice:
    """根据 GUI 保存的设备键值解析 Qt 输出设备。"""
    normalized_key = str(device_key or "").strip() or DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY
    default_device = default_audio_output_provider()
    if normalized_key == DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY:
        return default_device

    for device in audio_outputs_provider():
        if _build_audio_output_device_key(device) == normalized_key:
            return device
    return default_device


class PreviewPlaybackController(QObject):
    """管理总览页试听播放会话与 Qt 音频输出。"""

    playback_state_changed = Signal(object)
    playback_error = Signal(str)

    def __init__(
        self,
        *,
        decode_audio_fn: Callable[[str | Path], PreparedPreviewAudio] = decode_preview_audio,
        audio_sink_factory: Callable[[QAudioDevice, QAudioFormat, QObject | None], object] | None = None,
        audio_outputs_provider: Callable[[], list[QAudioDevice]] = QMediaDevices.audioOutputs,
        default_audio_output_provider: Callable[[], QAudioDevice] = QMediaDevices.defaultAudioOutput,
        parent: QObject | None = None,
    ) -> None:
        """初始化试听播放控制器。"""
        super().__init__(parent)
        self._decode_audio_fn = decode_audio_fn
        self._audio_sink_factory = audio_sink_factory or (
            lambda device, audio_format, parent=None: QAudioSink(device, audio_format, parent)
        )
        self._audio_outputs_provider = audio_outputs_provider
        self._default_audio_output_provider = default_audio_output_provider
        self._volume_percent = 10
        self._output_device_key = DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY
        self._active_audio_id: str | None = None
        self._active_audio_path: Path | None = None
        self._audio_sink = None
        self._audio_buffer: QBuffer | None = None
        self._audio_payload: QByteArray | None = None
        self._retired_audio_buffers: list[QBuffer] = []
        self._payload_size_bytes = 0
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(50)
        self._progress_timer.timeout.connect(self._emit_state_from_sink)
        self._buffer_cleanup_timer = QTimer(self)
        self._buffer_cleanup_timer.setSingleShot(True)
        self._buffer_cleanup_timer.setInterval(0)
        self._buffer_cleanup_timer.timeout.connect(self._drain_retired_audio_buffers)

    def set_volume_percent(self, value: int) -> None:
        """更新当前试听音量。"""
        self._volume_percent = max(0, min(int(value), 100))
        if self._audio_sink is not None and hasattr(self._audio_sink, "setVolume"):
            self._audio_sink.setVolume(self._volume_percent / 100.0)

    def set_output_device_key(self, value: str) -> None:
        """更新下次播放时要使用的输出设备键值。"""
        normalized = str(value or "").strip()
        self._output_device_key = normalized or DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY

    def play(self, *, audio_id: str, audio_path: str | Path) -> None:
        """播放指定音频路径对应的试听资源。"""
        try:
            prepared_audio = self._decode_audio_fn(audio_path)
        except Exception as exc:  # noqa: BLE001
            self._dispose_session(emit_state=False)
            self.playback_error.emit(f"试听音频加载失败：{type(exc).__name__}: {exc}")
            self._emit_stopped_state()
            return

        if not prepared_audio.pcm_bytes:
            self._dispose_session(emit_state=False)
            self.playback_error.emit("当前试听音频未生成可播放的 PCM 数据。")
            self._emit_stopped_state()
            return

        target_device = resolve_preview_audio_output_device(
            self._output_device_key,
            audio_outputs_provider=self._audio_outputs_provider,
            default_audio_output_provider=self._default_audio_output_provider,
        )
        if not target_device.isFormatSupported(prepared_audio.audio_format):
            self._dispose_session(emit_state=False)
            self.playback_error.emit("当前试听输出设备不支持该音频格式。")
            self._emit_stopped_state()
            return

        self._dispose_session(emit_state=False)
        self._active_audio_id = str(audio_id)
        self._active_audio_path = Path(audio_path)
        self._payload_size_bytes = len(prepared_audio.pcm_bytes)
        self._audio_payload = QByteArray(prepared_audio.pcm_bytes)
        self._audio_buffer = QBuffer(self)
        self._audio_buffer.setData(self._audio_payload)
        self._audio_buffer.open(QIODevice.OpenModeFlag.ReadOnly)

        audio_sink = self._audio_sink_factory(target_device, prepared_audio.audio_format, self)
        audio_sink.stateChanged.connect(self._on_sink_state_changed)
        if hasattr(audio_sink, "setVolume"):
            audio_sink.setVolume(self._volume_percent / 100.0)
        audio_sink.start(self._audio_buffer)
        self._audio_sink = audio_sink
        self._progress_timer.start()
        self._emit_state_from_sink()

    def stop(self) -> None:
        """停止当前试听并清空状态。"""
        self._dispose_session(emit_state=True)

    def shutdown(self, *_args: object) -> None:
        """在页面销毁时关闭当前试听资源。"""
        self.stop()

    def _on_sink_state_changed(self, state) -> None:
        """同步底层 Qt 音频状态变化。"""
        if state == QAudio.State.IdleState:
            self._dispose_session(emit_state=True)
            return
        if state == QAudio.State.StoppedState and self._audio_sink is not None:
            error = self._audio_sink.error()
            if error != QAudio.Error.NoError:
                self.playback_error.emit("试听播放过程中发生底层输出错误。")
            self._dispose_session(emit_state=True)
            return
        self._emit_state_from_sink()

    def _emit_state_from_sink(self) -> None:
        """根据当前 Qt sink 状态向界面广播最新播放状态。"""
        if self._audio_sink is None:
            self._emit_stopped_state()
            return

        current_state = self._audio_sink.state()
        self.playback_state_changed.emit(
            PreviewPlaybackState(
                audio_id=self._active_audio_id,
                audio_path=self._active_audio_path,
                progress=self._current_progress(),
                is_playing=current_state == QAudio.State.ActiveState,
                is_paused=current_state == QAudio.State.SuspendedState,
            )
        )

    def _emit_stopped_state(self) -> None:
        """向界面广播一个已停止的空状态。"""
        self.playback_state_changed.emit(
            PreviewPlaybackState(
                audio_id=None,
                audio_path=None,
                progress=0.0,
                is_playing=False,
                is_paused=False,
            )
        )

    def _current_progress(self) -> float:
        """按当前缓冲区读取位置估算试听进度。"""
        if self._audio_buffer is None or self._payload_size_bytes <= 0:
            return 0.0
        progress = float(self._audio_buffer.pos()) / float(self._payload_size_bytes)
        return max(0.0, min(1.0, progress))

    def _drain_retired_audio_buffers(self) -> None:
        """在事件循环下一拍统一回收旧的音频缓冲区。"""
        retired_buffers = tuple(self._retired_audio_buffers)
        self._retired_audio_buffers.clear()
        for buffer in retired_buffers:
            buffer.close()
            buffer.deleteLater()

    def _dispose_session(self, *, emit_state: bool) -> None:
        """释放当前 Qt 音频资源并按需清空界面状态。"""
        if self._progress_timer.isActive():
            self._progress_timer.stop()

        audio_sink = self._audio_sink
        self._audio_sink = None
        if audio_sink is not None:
            try:
                audio_sink.stateChanged.disconnect(self._on_sink_state_changed)
            except (RuntimeError, TypeError, ValueError):
                pass
            try:
                audio_sink.stop()
            except RuntimeError:
                pass
            delete_later = getattr(audio_sink, "deleteLater", None)
            if callable(delete_later):
                delete_later()

        if self._audio_buffer is not None:
            self._retired_audio_buffers.append(self._audio_buffer)
            if not self._buffer_cleanup_timer.isActive():
                self._buffer_cleanup_timer.start()
            self._audio_buffer = None
        self._audio_payload = None
        self._payload_size_bytes = 0
        self._active_audio_id = None
        self._active_audio_path = None

        if emit_state:
            self._emit_stopped_state()
