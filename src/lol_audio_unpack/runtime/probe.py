"""启动前的真实后端样本探测，输出可跨进程传递的结果。"""

from __future__ import annotations

import math
import multiprocessing
import os
import struct
import subprocess
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from tempfile import gettempdir, mkdtemp
from threading import Event
from time import monotonic

from loguru import logger

from ..app.types import WavOutputOptions
from .tool_process import ToolError

_DEFAULT_OPTIONS = WavOutputOptions()
_EVENT_ID = 246437813
_ACTION_ID = 399610470
_SOUND_ID = 23311513
_SOURCE_ID = 809620652


@dataclass(frozen=True)
class ToolProbe:
    """一次实际调用的事实；环境故障不能通过更换工具掩盖。"""

    tool: str
    path: str | None
    kind: str = "ok"
    detail: str = ""

    @property
    def success(self) -> bool:
        """返回探测是否通过。"""
        return self.kind == "ok"

    @property
    def can_fallback(self) -> bool:
        """仅外置后端调用故障允许用户选择本次改用内置。"""
        return bool(self.path) and self.kind not in {"ok", "environment", "cancelled"}


def require_tool(tool: str, *, path: str | None = None, options: WavOutputOptions = _DEFAULT_OPTIONS) -> None:
    """为无人交互入口执行探测，失败直接抛出可呈现错误。"""
    root = Path(gettempdir()) / "lol-audio-unpack" / "preflight"
    result = probe_tool(tool, path=path, options=options, scratch_root=root)
    if not result.success:
        raise ValueError(f"{tool} 后端预检失败 [{result.kind}]：{result.detail}")


def validate_wav(path: Path) -> None:
    """检查容器边界并通过内置解码器完整读取，不比较参考音频数值。

    Raises:
        ValueError: WAV 声明、数据或完整读取结果无效。
    """
    from pyvgmstream import DecodeConfig, open_stream  # noqa: PLC0415

    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":  # noqa: PLR2004
            raise ValueError("不是可识别的 RIFF WAV")
        end = struct.unpack_from("<I", header, 4)[0] + 8
        if end > size:
            raise ValueError("WAV 容器被截断")
        data_size = 0
        while stream.tell() < end:
            chunk = stream.read(8)
            if len(chunk) != 8:  # noqa: PLR2004
                raise ValueError("WAV 块头被截断")
            length = struct.unpack_from("<I", chunk, 4)[0]
            data_end = stream.tell() + length
            if data_end > end:
                raise ValueError("WAV 数据块被截断")
            if chunk[:4] == b"data":
                data_size += length
            # PCM24 的最后一个 data 块可为奇数字节，实际工具可能省略文件末尾的对齐字节。
            # 只允许最终块恰好结束；中间块仍按 RIFF 对齐规则跳过 padding。
            stream.seek(min(data_end + (length % 2), end))
        if not data_size:
            raise ValueError("WAV 没有音频数据")
    with open_stream(path, config=DecodeConfig(ignore_loop=True)) as stream:
        if stream.channels <= 0 or stream.sample_rate <= 0:
            raise ValueError("WAV 声道数或采样率无效")
        duration = stream.duration_seconds
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("WAV 时长无效")
        expected = stream.play_samples * stream.channels * stream.sample_size
        count = 0
        while block := stream.read_frames(65536):
            count += len(block)
            if count > expected:
                raise ValueError("WAV 读取量超过自身声明")
        if not count or count != expected:
            raise ValueError("WAV 未完整读取")


def _probe_entry(tool: str, path: str | None, options: WavOutputOptions, sample: Path, pipe) -> None:
    """让本机库和输出验证器同样受进程级超时保护。"""
    phase = "environment"
    try:
        # 导入原生后端也在隔离进程内完成；依赖加载失败属于应用环境问题。
        from pyvgmstream import decode_to_wav_file  # noqa: PLC0415

        from .hirc import WwiserTool, load_hirc  # noqa: PLC0415
        from .wav.batch import decode_config  # noqa: PLC0415
        from .wav.external import transcode_file  # noqa: PLC0415

        phase = "decode"
        pipe.send(phase)
        if tool == "wav":
            output = sample.with_suffix(".wav")
            if path:
                transcode_file(sample, output, options)
            else:
                decode_to_wav_file(sample, output, config=decode_config(options.format))
            phase = "validate"
            pipe.send(phase)
            validate_wav(output)
        else:
            hirc = load_hirc(sample, manager=WwiserTool(Path(path)) if path else None, use_cache=False)
            phase = "validate"
            pipe.send(phase)
            banks = hirc.banks.values()
            valid = any(
                _EVENT_ID in bank.events
                and _ACTION_ID in bank.events[_EVENT_ID].event_ids
                and _ACTION_ID in bank.event_actions
                and _SOUND_ID in bank.sounds
                and bank.sounds[_SOUND_ID].source_id == _SOURCE_ID
                for bank in banks
            )
            if not valid:
                raise ValueError("BNK 缺少预期的事件/动作关系或声音来源")
        result = ToolProbe(tool, path)
    except ToolError as exc:
        result = ToolProbe(tool, path, exc.kind, str(exc))
    except ValueError as exc:
        result = ToolProbe(tool, path, "output" if phase == "validate" else phase, str(exc))
    except FileNotFoundError as exc:
        result = ToolProbe(tool, path, "output" if phase == "validate" else "environment", str(exc))
    except (OSError, RuntimeError) as exc:
        # 验证器本身无法工作与输出不合法分开，前者换工具也无法解决。
        result = ToolProbe(tool, path, "environment" if phase == "validate" else phase, str(exc))
    except Exception as exc:  # noqa: BLE001
        result = ToolProbe(tool, path, "environment", f"{phase}：{type(exc).__name__}: {exc}")
    pipe.send(result)
    pipe.close()


def probe_tool(  # noqa: PLR0913, PLR0911
    tool: str,
    *,
    path: str | None = None,
    options: WavOutputOptions = _DEFAULT_OPTIONS,
    scratch_root: Path,
    cancel: Event | None = None,
    timeout: float = 30,
) -> ToolProbe:
    """在隔离目录启动一次探测；取消与迟到结果由调用方共同隔离。

    Args:
        tool: ``wav`` 或 ``hirc``。
        path: 已固定的外部路径，空值选择内置。
        options: 当前实际转码参数。
        scratch_root: 调用方拥有的临时目录，不能是正式输出目录。
        cancel: 可由 UI/调用方异步设置的取消标记。
        timeout: 包括进程启动、真实调用和验证在内的总时间上限。
    """
    if tool not in {"wav", "hirc"}:
        raise ValueError(f"未知探测工具：{tool}")
    if cancel is not None and cancel.is_set():
        return ToolProbe(tool, path, "cancelled", "已取消预检")
    name = "1181676615.wem" if tool == "wav" else "annie-zh-cn-hirc.bnk"
    try:
        sample_bytes = files("lol_audio_unpack").joinpath("resources", "preflight", name).read_bytes()
        scratch_root.mkdir(parents=True, exist_ok=True)
        scratch = Path(mkdtemp(prefix="probe-", dir=scratch_root))
        sample = scratch / name
        sample.write_bytes(sample_bytes)
    except (OSError, ModuleNotFoundError) as exc:
        return ToolProbe(tool, path, "environment", f"无法准备预检样本或临时目录：{exc}")
    if path and not Path(path).is_file():
        return ToolProbe(tool, path, "path", f"工具文件不存在：{path}")
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(
        target=_probe_entry, args=(tool, path, replace(options, backend_path=path), sample, writer)
    )
    try:
        process.start()
        writer.close()
        deadline = monotonic() + timeout
        phase = "environment"
        while True:
            if cancel is not None and cancel.is_set():
                return ToolProbe(tool, path, "cancelled", "已取消预检")
            if monotonic() >= deadline:
                kind = "timeout" if phase == "decode" else "environment"
                return ToolProbe(tool, path, kind, f"预检 {phase} 阶段超过 {timeout:g} 秒")
            if reader.poll(0.05):
                try:
                    message = reader.recv()
                except EOFError:
                    kind = "exit" if phase == "decode" else "environment"
                    result = ToolProbe(tool, path, kind, f"预检 {phase} 阶段退出，未返回诊断")
                    break
                if isinstance(message, ToolProbe):
                    result = message
                    break
                phase = message
            elif not process.is_alive():
                kind = "exit" if phase == "decode" else "environment"
                return ToolProbe(tool, path, kind, f"预检 {phase} 阶段退出码 {process.exitcode}，未返回诊断")
        if not result.success:
            logger.warning("{} 后端预检失败 [{}]：{}", tool, result.kind, result.detail)
        return result
    except (OSError, RuntimeError) as exc:
        return ToolProbe(tool, path, "environment", f"无法启动预检进程：{exc}")
    finally:
        if process.pid is not None:
            if process.is_alive():
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        check=False,
                    )
                else:
                    process.terminate()
            process.join()
        reader.close()
        writer.close()
