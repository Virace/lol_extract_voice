"""外部 vgmstream-cli 的单文件执行与有界并发批处理。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event

from pyvgmstream.transcode import BatchTranscodeItemResult, BatchTranscodeProgress, BatchTranscodeSummary

from ...app.types import WavOutputOptions
from ..tool_process import ToolError, run_tool

_FORMATS = {"pcm16": "1", "pcm24": "2", "pcm32": "3", "float": "4"}


def transcode_file(source: Path, output: Path, options: WavOutputOptions, cancel: Event | None = None) -> None:
    """按正式参数转换一个文件，失败不重试或切换后端。"""
    tool = Path(options.backend_path) if options.backend_path else None
    if tool is None or not tool.is_file():
        raise ToolError("path", f"vgmstream-cli 文件不存在：{tool}")
    args = [str(tool.resolve()), "-i"]
    format_name = options.format.strip().lower()
    if format_name == "auto":
        args.append("-w")
    elif format_name in _FORMATS:
        args.extend(["-W", _FORMATS[format_name]])
    else:
        raise ValueError(f"不支持的 WAV 格式：{options.format}")
    output.parent.mkdir(parents=True, exist_ok=True)
    detail = run_tool(
        [*args, "-o", str(output.resolve()), str(source.resolve())], timeout=options.timeout_seconds, cancel=cancel
    )
    if not output.is_file() or not output.stat().st_size:
        raise ToolError("output", f"未生成 WAV：{detail or '未返回诊断'}")


def transcode_external(  # noqa: PLR0913
    sources: Sequence[Path],
    destination: Path,
    *,
    input_root: Path | None,
    options: WavOutputOptions,
    progress: Callable[[BatchTranscodeProgress], None] | None = None,
    cancel: Event | None = None,
) -> BatchTranscodeSummary:
    """复用批处理结果合同，以线程等待外部进程而不串行解码。"""

    def convert(source: Path) -> BatchTranscodeItemResult:
        relative = source.relative_to(input_root) if input_root else Path(source.name)
        output = destination / relative.with_suffix(".wav")
        try:
            transcode_file(source, output, options, cancel)
            return BatchTranscodeItemResult(source, output, 0, output.stat().st_size)
        except (ToolError, OSError, ValueError) as exc:
            return BatchTranscodeItemResult(source, output, 0, 0, str(exc))

    results = []
    failed = 0
    with ThreadPoolExecutor(max_workers=options.worker_count) as pool:
        futures = [pool.submit(convert, source) for source in sources]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            failed += result.error is not None
            if progress is not None:
                progress(BatchTranscodeProgress(len(results), len(sources), failed))
    return BatchTranscodeSummary(input_root, destination, len(results), failed, tuple(results))
