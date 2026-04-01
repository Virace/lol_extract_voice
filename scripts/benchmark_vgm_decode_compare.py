#!/usr/bin/env python3
"""对比目录扫描型 vgmstream CLI 与 pyvgmstream 的批量解码性能。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import pyvgmstream

DEFAULT_READ_CHUNK_FRAMES = 65536
DEFAULT_DISPATCH_CHUNKSIZE = 64
DEFAULT_DECODE_WORKERS = "1,2,4,8,12,16,24,32"
DEFAULT_TRANSCODE_WORKERS = "1,2,4,8,12,16,24,32"


@dataclass(frozen=True)
class BenchResult:
    """描述单次 benchmark 的核心指标。"""

    name: str
    mode: str
    workers: int
    file_count: int
    input_bytes: int
    output_count: int
    output_bytes: int
    elapsed_seconds: float
    files_per_second: float
    input_mib_per_second: float


@dataclass(frozen=True)
class BenchPayload:
    """描述生成结果对象所需的原始字段。"""

    name: str
    mode: str
    workers: int
    file_count: int
    input_bytes: int
    output_count: int
    output_bytes: int


@dataclass(frozen=True)
class ReportContext:
    """描述构建 JSON 报告所需的上下文。"""

    input_root: Path
    cli_path: Path
    cli_label: str
    decode_workers: list[int]
    transcode_workers: list[int]
    full_paths: list[Path]
    subset_paths: list[Path]


@dataclass(frozen=True)
class FormatSpec:
    """描述 benchmark 使用的输出格式策略。"""

    mode: str
    cli_args: tuple[str, ...]
    decode_config: pyvgmstream.DecodeConfig


CliInputMode = Literal["auto", "directory", "file-list"]


@dataclass(frozen=True)
class CliBenchContext:
    """描述 CLI benchmark 运行所需的上下文。"""

    cli_path: Path
    cli_label: str
    cli_input_mode: CliInputMode
    format_spec: FormatSpec


def _parse_args() -> argparse.Namespace:
    """解析脚本参数。"""

    parser = argparse.ArgumentParser(
        description=(
            "比较目录扫描型 vgmstream CLI 与 pyvgmstream 的批量解码/转 WAV 性能。"
            "注意：本脚本假设传入的 CLI 支持直接接收目录作为输入；"
            "原版 vgmstream-cli 走“多进程单文件重复拉起”的方式不适合做公平比较。"
        )
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="包含 .wem 样本的根目录。",
    )
    parser.add_argument(
        "--vgm-cli",
        type=Path,
        required=True,
        help="要参与对比的 vgmstream CLI 路径，必须支持目录输入。",
    )
    parser.add_argument(
        "--cli-label",
        type=str,
        default=None,
        help="报告中使用的 CLI 名称，不传时默认使用可执行文件名。",
    )
    parser.add_argument(
        "--subset-count",
        type=int,
        default=512,
        help="端到端转 WAV 场景使用的分层抽样文件数。",
    )
    parser.add_argument(
        "--cli-input-mode",
        choices=("auto", "directory", "file-list"),
        default="auto",
        help=(
            "CLI 输入模式。`directory` 直接传目录，`file-list` 传平铺后的文件列表，"
            "`auto` 先尝试目录，失败时回退到文件列表。"
        ),
    )
    parser.add_argument(
        "--sample-format",
        choices=("pcm16", "pcm24", "pcm32", "float", "source"),
        default="pcm16",
        help=(
            "统一对比时使用的输出格式策略。"
            "`source` 表示尽量沿用源/当前输出格式；"
            "默认 `pcm16`，因为这是 vgmstream CLI 最常见且最稳的基线。"
        ),
    )
    parser.add_argument(
        "--decode-workers",
        type=str,
        default=DEFAULT_DECODE_WORKERS,
        help="decode-only 场景的 pyvgmstream workers 列表，逗号分隔。",
    )
    parser.add_argument(
        "--transcode-workers",
        type=str,
        default=DEFAULT_TRANSCODE_WORKERS,
        help="transcode-to-wav 场景的 pyvgmstream workers 列表，逗号分隔。",
    )
    parser.add_argument(
        "--temp-root",
        type=Path,
        default=Path(".temp"),
        help="临时输入镜像和中间输出根目录，默认 .temp。",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="可选，写出完整 JSON 报告的目标路径。",
    )
    return parser.parse_args()


def _parse_workers(raw_value: str) -> list[int]:
    """解析 workers 列表。"""

    values: list[int] = []
    for item in raw_value.split(","):
        worker = int(item.strip())
        if worker <= 0:
            raise ValueError(f"workers must be positive: {raw_value}")
        values.append(worker)
    return sorted(dict.fromkeys(values))


def _iter_wem_files(root: Path) -> list[Path]:
    """稳定枚举目录下全部 WEM 文件。"""

    return sorted(root.rglob("*.wem"))


def _total_input_bytes(paths: Iterable[Path]) -> int:
    """统计输入文件总字节数。"""

    return sum(path.stat().st_size for path in paths)


def _pick_stratified_subset(paths: list[Path], count: int) -> list[Path]:
    """按文件大小做简单分层抽样。"""

    if count >= len(paths):
        return list(paths)

    sorted_paths = sorted(paths, key=lambda path: (path.stat().st_size, path.as_posix()))
    selected: list[Path] = []
    seen: set[Path] = set()
    total = len(sorted_paths)
    for index in range(count):
        candidate = sorted_paths[min((index * total) // count, total - 1)]
        if candidate not in seen:
            selected.append(candidate)
            seen.add(candidate)

    cursor = 0
    while len(selected) < count:
        candidate = sorted_paths[cursor]
        if candidate not in seen:
            selected.append(candidate)
            seen.add(candidate)
        cursor += 1

    return sorted(selected, key=lambda path: path.as_posix())


def _ensure_clean_dir(path: Path) -> None:
    """重建干净目录。"""

    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_flattened_inputs(paths: list[Path], target_root: Path) -> list[Path]:
    """将样本复制到 ASCII-only 临时目录，避免路径编码干扰结果。"""

    _ensure_clean_dir(target_root)
    copied_paths: list[Path] = []
    for index, source_path in enumerate(paths, start=1):
        destination_path = target_root / f"{index:06d}{source_path.suffix.lower()}"
        shutil.copy2(source_path, destination_path)
        copied_paths.append(destination_path)
    return copied_paths


def _remove_wavs(root: Path) -> None:
    """删除目录下全部 WAV 输出。"""

    for wav_path in root.rglob("*.wav"):
        wav_path.unlink()


def _resolve_format_spec(mode: str) -> FormatSpec:
    """将用户选择的 sample format 模式转换为两端参数。"""

    if mode == "source":
        return FormatSpec(
            mode=mode,
            cli_args=("-w",),
            decode_config=pyvgmstream.DecodeConfig(sample_format=None, ignore_loop=True),
        )

    sample_format_map = {
        "pcm16": (pyvgmstream.SampleFormat.PCM16, "1"),
        "pcm24": (pyvgmstream.SampleFormat.PCM24, "2"),
        "pcm32": (pyvgmstream.SampleFormat.PCM32, "3"),
        "float": (pyvgmstream.SampleFormat.FLOAT, "4"),
    }
    sample_format, cli_value = sample_format_map[mode]
    return FormatSpec(
        mode=mode,
        cli_args=("-W", cli_value),
        decode_config=pyvgmstream.DecodeConfig(sample_format=sample_format, ignore_loop=True),
    )


def _collect_wav_stats(root: Path) -> tuple[int, int]:
    """统计目录下 WAV 文件数量与总大小。"""

    wav_paths = list(root.rglob("*.wav"))
    return len(wav_paths), sum(path.stat().st_size for path in wav_paths)


def _run_subprocess(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """执行外部命令并在失败时抛出详细异常。"""

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        cwd=None if cwd is None else str(cwd),
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"command failed with exit code {completed.returncode}: {' '.join(command)}\n{stderr[:4000]}"
        )
    return completed


def _decode_only_one_file(job: tuple[str, str]) -> int:
    """读取全部帧但不落盘，用于 decode-only 场景。"""

    path_text, format_mode = job
    format_spec = _resolve_format_spec(format_mode)
    handle = pyvgmstream.open_stream(path_text, config=format_spec.decode_config)
    total_bytes = 0
    try:
        while not handle.done:
            chunk = handle.read_frames(DEFAULT_READ_CHUNK_FRAMES)
            if not chunk:
                break
            total_bytes += len(chunk)
        return total_bytes
    finally:
        handle.close()


def _make_result(payload: BenchPayload, elapsed_seconds: float) -> BenchResult:
    """生成带派生指标的结果对象。"""

    return BenchResult(
        name=payload.name,
        mode=payload.mode,
        workers=payload.workers,
        file_count=payload.file_count,
        input_bytes=payload.input_bytes,
        output_count=payload.output_count,
        output_bytes=payload.output_bytes,
        elapsed_seconds=elapsed_seconds,
        files_per_second=(payload.file_count / elapsed_seconds) if elapsed_seconds else 0.0,
        input_mib_per_second=((payload.input_bytes / (1024 * 1024)) / elapsed_seconds) if elapsed_seconds else 0.0,
    )


def _run_cli_batch(
    context: CliBenchContext,
    input_root: Path,
    *,
    decode_only: bool,
) -> None:
    """执行一轮 CLI 批量任务，并在需要时自动回退到文件列表模式。"""

    base_args = [str(context.cli_path)]
    if decode_only:
        base_args.append("-O")
    base_args.extend(["-i", *context.format_spec.cli_args])

    if not decode_only:
        base_args.extend(["-o", "?p?b.wav"])

    def run_directory_mode() -> None:
        _run_subprocess([*base_args, str(input_root)])

    def run_file_list_mode() -> None:
        input_names = [path.name for path in sorted(input_root.glob("*.wem"))]
        if not input_names:
            raise FileNotFoundError(f"no flattened .wem files found under: {input_root}")
        _run_subprocess([*base_args, *input_names], cwd=input_root)

    if context.cli_input_mode == "directory":
        run_directory_mode()
        return
    if context.cli_input_mode == "file-list":
        run_file_list_mode()
        return

    try:
        run_directory_mode()
    except RuntimeError:
        run_file_list_mode()


def _bench_cli_decode_only(context: CliBenchContext, input_root: Path, input_bytes: int) -> BenchResult:
    """运行 CLI 的 decode-only benchmark。"""

    started = time.perf_counter()
    _run_cli_batch(
        context,
        input_root,
        decode_only=True,
    )
    elapsed_seconds = time.perf_counter() - started
    return _make_result(
        BenchPayload(
            name=context.cli_label,
            mode="decode_only",
            workers=1,
            file_count=len(list(input_root.glob("*.wem"))),
            input_bytes=input_bytes,
            output_count=0,
            output_bytes=0,
        ),
        elapsed_seconds,
    )


def _bench_cli_transcode(context: CliBenchContext, input_root: Path, input_bytes: int) -> BenchResult:
    """运行 CLI 的端到端转 WAV benchmark。"""

    _remove_wavs(input_root)
    started = time.perf_counter()
    _run_cli_batch(
        context,
        input_root,
        decode_only=False,
    )
    elapsed_seconds = time.perf_counter() - started
    output_count, output_bytes = _collect_wav_stats(input_root)
    result = _make_result(
        BenchPayload(
            name=context.cli_label,
            mode="transcode_wav",
            workers=1,
            file_count=len(list(input_root.glob("*.wem"))),
            input_bytes=input_bytes,
            output_count=output_count,
            output_bytes=output_bytes,
        ),
        elapsed_seconds,
    )
    _remove_wavs(input_root)
    return result


def _bench_py_decode_only(paths: list[Path], workers: int, input_bytes: int, format_spec: FormatSpec) -> BenchResult:
    """运行 pyvgmstream 的 decode-only benchmark。"""

    started = time.perf_counter()
    jobs = [(str(path), format_spec.mode) for path in paths]
    if workers == 1:
        output_bytes = sum(_decode_only_one_file(job) for job in jobs)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            output_bytes = sum(
                executor.map(
                    _decode_only_one_file,
                    jobs,
                    chunksize=DEFAULT_DISPATCH_CHUNKSIZE,
                )
            )
    elapsed_seconds = time.perf_counter() - started
    return _make_result(
        BenchPayload(
            name="pyvgmstream",
            mode="decode_only",
            workers=workers,
            file_count=len(paths),
            input_bytes=input_bytes,
            output_count=len(paths),
            output_bytes=output_bytes,
        ),
        elapsed_seconds,
    )


def _bench_py_transcode(
    input_root: Path,
    workers: int,
    input_bytes: int,
    format_spec: FormatSpec,
) -> BenchResult:
    """运行 pyvgmstream 的端到端转 WAV benchmark。"""

    _remove_wavs(input_root)
    started = time.perf_counter()
    summary = pyvgmstream.transcode_tree(
        input_root,
        input_root,
        workers=workers,
        dispatch_chunksize=DEFAULT_DISPATCH_CHUNKSIZE,
        config=format_spec.decode_config,
    )
    elapsed_seconds = time.perf_counter() - started
    if summary.failed_count:
        failed_items = [item for item in summary.results if item.error][:5]
        raise RuntimeError(f"pyvgmstream transcode failed: {failed_items}")
    output_count, output_bytes = _collect_wav_stats(input_root)
    result = _make_result(
        BenchPayload(
            name="pyvgmstream",
            mode="transcode_wav",
            workers=workers,
            file_count=len(list(input_root.glob("*.wem"))),
            input_bytes=input_bytes,
            output_count=output_count,
            output_bytes=output_bytes,
        ),
        elapsed_seconds,
    )
    _remove_wavs(input_root)
    return result


def _warm_up(cli_path: Path, sample_file: Path, format_spec: FormatSpec) -> None:
    """预热 DLL 与基本解码路径。"""

    _decode_only_one_file((str(sample_file), format_spec.mode))
    _run_subprocess([str(cli_path), "-O", "-i", *format_spec.cli_args, str(sample_file)])


def _print_result(result: BenchResult) -> None:
    """输出一行摘要结果。"""

    print(
        f"{result.mode:>13} | {result.name:13} | workers={result.workers:>2} | "
        f"elapsed={result.elapsed_seconds:8.3f}s | files/s={result.files_per_second:8.2f} | "
        f"input MiB/s={result.input_mib_per_second:8.2f} | outputs={result.output_count:>4}",
        flush=True,
    )


def _build_report(context: ReportContext, results: list[BenchResult]) -> dict[str, object]:
    """整理为 JSON 友好的报告结构。"""

    decode_results = [result for result in results if result.name == "pyvgmstream" and result.mode == "decode_only"]
    transcode_results = [
        result for result in results if result.name == "pyvgmstream" and result.mode == "transcode_wav"
    ]
    best_decode = min(decode_results, key=lambda item: item.elapsed_seconds) if decode_results else None
    best_transcode = min(transcode_results, key=lambda item: item.elapsed_seconds) if transcode_results else None
    return {
        "input_root": str(context.input_root),
        "vgm_cli": str(context.cli_path),
        "cli_label": context.cli_label,
        "decode_workers": context.decode_workers,
        "transcode_workers": context.transcode_workers,
        "full_file_count": len(context.full_paths),
        "full_input_bytes": _total_input_bytes(context.full_paths),
        "subset_file_count": len(context.subset_paths),
        "subset_input_bytes": _total_input_bytes(context.subset_paths),
        "best_pyvgmstream_decode_workers": None if best_decode is None else best_decode.workers,
        "best_pyvgmstream_transcode_workers": None if best_transcode is None else best_transcode.workers,
        "results": [asdict(result) for result in results],
    }


def main() -> int:
    """执行 benchmark。"""

    args = _parse_args()
    input_root = args.input_root.resolve()
    cli_path = args.vgm_cli.resolve()
    if not input_root.is_dir():
        raise FileNotFoundError(f"input root does not exist: {input_root}")
    if not cli_path.is_file():
        raise FileNotFoundError(f"vgm cli does not exist: {cli_path}")

    cli_label = args.cli_label or cli_path.stem
    cli_input_mode: CliInputMode = args.cli_input_mode
    decode_workers = _parse_workers(args.decode_workers)
    transcode_workers = _parse_workers(args.transcode_workers)
    format_spec = _resolve_format_spec(args.sample_format)
    cli_context = CliBenchContext(
        cli_path=cli_path,
        cli_label=cli_label,
        cli_input_mode=cli_input_mode,
        format_spec=format_spec,
    )
    temp_root = args.temp_root.resolve()
    full_temp_root = temp_root / "benchmark_full_input"
    subset_temp_root = temp_root / "benchmark_subset_input"

    original_paths = _iter_wem_files(input_root)
    if not original_paths:
        raise FileNotFoundError(f"no .wem files found under: {input_root}")

    subset_original_paths = _pick_stratified_subset(original_paths, args.subset_count)
    full_paths = _copy_flattened_inputs(original_paths, full_temp_root)
    subset_paths = _copy_flattened_inputs(subset_original_paths, subset_temp_root)

    print("NOTE: this benchmark assumes the provided CLI supports directory input.", flush=True)
    print(
        "NOTE: stock vgmstream-cli launched once per file is dominated by process startup cost and is excluded.",
        flush=True,
    )
    print(
        "NOTE: `pcm16` is the safest apples-to-apples baseline; `source` may change the actual decode/write payload.",
        flush=True,
    )
    print(f"input_root={input_root}", flush=True)
    print(f"vgm_cli={cli_path}", flush=True)
    print(f"cli_input_mode={cli_input_mode}", flush=True)
    print(f"sample_format={format_spec.mode}", flush=True)
    print(f"full_file_count={len(full_paths)} full_input_bytes={_total_input_bytes(full_paths)}", flush=True)
    print(f"subset_file_count={len(subset_paths)} subset_input_bytes={_total_input_bytes(subset_paths)}", flush=True)

    results: list[BenchResult] = []
    try:
        _warm_up(cli_path, full_paths[0], format_spec)

        full_input_bytes = _total_input_bytes(full_paths)
        cli_decode_result = _bench_cli_decode_only(cli_context, full_temp_root, full_input_bytes)
        results.append(cli_decode_result)
        _print_result(cli_decode_result)

        for workers in decode_workers:
            result = _bench_py_decode_only(full_paths, workers, full_input_bytes, format_spec)
            results.append(result)
            _print_result(result)

        subset_input_bytes = _total_input_bytes(subset_paths)
        cli_transcode_result = _bench_cli_transcode(cli_context, subset_temp_root, subset_input_bytes)
        results.append(cli_transcode_result)
        _print_result(cli_transcode_result)

        for workers in transcode_workers:
            result = _bench_py_transcode(subset_temp_root, workers, subset_input_bytes, format_spec)
            results.append(result)
            _print_result(result)

        report = _build_report(
            ReportContext(
                input_root=input_root,
                cli_path=cli_path,
                cli_label=cli_label,
                decode_workers=decode_workers,
                transcode_workers=transcode_workers,
                full_paths=full_paths,
                subset_paths=subset_paths,
            ),
            results,
        )
        report["sample_format"] = format_spec.mode
        report["cli_input_mode"] = cli_input_mode
        if args.report_json is not None:
            report_path = args.report_json.resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("JSON_REPORT_BEGIN", flush=True)
        print(json.dumps(report, indent=2), flush=True)
        print("JSON_REPORT_END", flush=True)
        return 0
    finally:
        shutil.rmtree(full_temp_root, ignore_errors=True)
        shutil.rmtree(subset_temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
