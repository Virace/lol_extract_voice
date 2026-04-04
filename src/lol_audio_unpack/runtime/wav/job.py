"""后台 WAV 转码作业、清单记录器与轮询句柄。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from ...app_context import AppContext, WavOutputOptions
from .transcode import TranscodeCoordinator, TranscodeProgress


@dataclass(slots=True, frozen=True)
class JobSpec:
    """描述单个后台 WAV 转码作业。

    Args:
        job_label: 关联的后台作业标识。
        manifest_path: 提取阶段写出的 WEM 清单文件。
        audio_root: 当前版本的音频输出根目录。
        wav_root: 当前版本的 WAV 输出根目录。
        report_root: 当前作业的报告目录。
        progress_path: 当前作业的进度快照文件。
        worker_count: WAV 转码并发数。
        timeout_seconds: 单个 WAV 转码超时时间。
        max_retries: WAV 转码最大重试次数。
        wav_format: WAV 输出格式。
    """

    job_label: str
    manifest_path: Path
    audio_root: Path
    wav_root: Path
    report_root: Path
    progress_path: Path
    worker_count: int
    timeout_seconds: int
    max_retries: int
    wav_format: str


@dataclass(slots=True)
class JobHandle:
    """封装后台 WAV 转码进程与可轮询元数据。"""

    job_label: str
    process: subprocess.Popen[bytes]
    progress_path: Path
    report_root: Path

    def poll(self) -> int | None:
        """返回当前后台进程的退出码。"""
        return self.process.poll()

    def terminate(self) -> None:
        """通知后台 WAV 进程终止。"""
        self.process.terminate()

    def read_progress_snapshot(self) -> dict[str, Any] | None:
        """读取最近一次进度快照。"""
        if not self.progress_path.exists():
            return None
        try:
            return json.loads(self.progress_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None


class ManifestRecorder:
    """以线程安全方式记录本轮解包产出的 WEM 清单。"""

    def __init__(self, manifest_path: Path) -> None:
        """初始化清单写入器。

        Args:
            manifest_path: 清单文件路径。
        """
        self.manifest_path = manifest_path
        self._lock = threading.Lock()
        self.recorded_count = 0

    def record(self, wem_path: Path) -> None:
        """追加记录一条已落盘的 WEM 路径。"""
        normalized_path = Path(wem_path)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.manifest_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{normalized_path}\n")
            self.recorded_count += 1

    def has_records(self) -> bool:
        """返回当前是否已记录过任意 WEM 路径。"""
        return self.recorded_count > 0


def build_recorder(*, ctx: AppContext, job_label: str) -> ManifestRecorder:
    """为 detached WAV 转码作业构造清单记录器。"""
    manifest_path = Path(ctx.paths.report_path) / "_wav_manifests" / f"{job_label}.txt"
    if manifest_path.exists():
        manifest_path.unlink(missing_ok=True)
    return ManifestRecorder(manifest_path)


def build_job_spec(  # noqa: PLR0913
    *,
    job_label: str,
    manifest_path: Path,
    audio_root: Path,
    wav_root: Path,
    report_root: Path,
    worker_count: int,
    timeout_seconds: int,
    max_retries: int,
    wav_format: str,
) -> JobSpec:
    """根据路径与运行参数构造后台 WAV 作业规格。"""
    return JobSpec(
        job_label=job_label,
        manifest_path=manifest_path,
        audio_root=audio_root,
        wav_root=wav_root,
        report_root=report_root,
        progress_path=report_root / "progress.json",
        worker_count=worker_count,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        wav_format=wav_format,
    )


def launch_job(spec: JobSpec) -> JobHandle:
    """启动独立的后台 WAV 转码进程。"""
    command = [
        sys.executable,
        "-m",
        "lol_audio_unpack.runtime.wav.job",
        "--task-id",
        spec.job_label,
        "--manifest",
        str(spec.manifest_path),
        "--audio-root",
        str(spec.audio_root),
        "--wav-root",
        str(spec.wav_root),
        "--report-root",
        str(spec.report_root),
        "--progress-path",
        str(spec.progress_path),
        "--workers",
        str(spec.worker_count),
        "--timeout",
        str(spec.timeout_seconds),
        "--retries",
        str(spec.max_retries),
        "--format",
        spec.wav_format,
    ]
    spec.report_root.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return JobHandle(
        job_label=spec.job_label,
        process=process,
        progress_path=spec.progress_path,
        report_root=spec.report_root,
    )


def launch_detached(
    *,
    ctx: AppContext,
    wav_output: WavOutputOptions,
    recorder: ManifestRecorder,
    job_label: str,
) -> JobHandle | None:
    """根据已记录的 WEM 清单启动后台 WAV 进程。"""
    if not recorder.has_records() or not recorder.manifest_path.exists():
        return None

    manifest_lines = [
        line.strip()
        for line in recorder.manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not manifest_lines:
        return None

    first_wem_path = Path(manifest_lines[0])
    audio_root = Path(ctx.paths.audio_path)
    relative_parts = first_wem_path.relative_to(audio_root).parts
    if not relative_parts:
        return None

    version = relative_parts[0]
    spec = build_job_spec(
        job_label=job_label,
        manifest_path=recorder.manifest_path,
        audio_root=audio_root / version,
        wav_root=Path(ctx.paths.wav_path) / version,
        report_root=Path(ctx.paths.report_path) / version / "transcode_wav" / job_label,
        worker_count=wav_output.worker_count,
        timeout_seconds=wav_output.timeout_seconds,
        max_retries=wav_output.max_retries,
        wav_format=wav_output.format,
    )
    return launch_job(spec)


def _write_progress(progress_path: Path, snapshot: TranscodeProgress) -> None:
    """将当前转码快照写入 JSON 进度文件。"""
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(
            {
                "status": "running",
                **asdict(snapshot),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_status(progress_path: Path, *, status: str, job_label: str, detail: str = "") -> None:
    """写入后台 WAV 作业的终态快照。"""
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(
            {
                "status": status,
                "job_label": job_label,
                "detail": detail,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def run_job(spec: JobSpec) -> int:
    """执行后台 WAV 转码作业并返回退出码。"""
    manifest_lines = []
    if spec.manifest_path.exists():
        manifest_lines = [
            line.strip()
            for line in spec.manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if not manifest_lines:
        _write_status(spec.progress_path, status="skipped", job_label=spec.job_label, detail="no_wem_paths")
        return 0

    coordinator = TranscodeCoordinator(
        options=WavOutputOptions(
            enabled=True,
            worker_count=spec.worker_count,
            timeout_seconds=spec.timeout_seconds,
            max_retries=spec.max_retries,
            format=spec.wav_format,
        ),
        audio_root=spec.audio_root,
        wav_root=spec.wav_root,
        report_root=spec.report_root,
        progress_callback=lambda snapshot: _write_progress(spec.progress_path, snapshot),
    )

    try:
        logger.info(
            "[WAV 后台] 作业 {} 启动转码：{} 个文件，workers={}，timeout={}s，retries={}，format={}",
            spec.job_label,
            len(manifest_lines),
            spec.worker_count,
            spec.timeout_seconds,
            spec.max_retries,
            spec.wav_format,
        )
        for raw_path in manifest_lines:
            coordinator.submit(Path(raw_path))
        coordinator.finish_extract()
        summary = coordinator.finish()
        _write_status(
            spec.progress_path,
            status="completed",
            job_label=spec.job_label,
            detail=(
                f"completed={summary.completed_wav_job_count},"
                f"failed={summary.failed_wav_job_count},"
                f"skipped={summary.skipped_wav_job_count}"
            ),
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[WAV 后台] 作业 {spec.job_label} 转码失败: {exc}")
        _write_status(
            spec.progress_path,
            status="failed",
            job_label=spec.job_label,
            detail=f"{type(exc).__name__}: {exc}",
        )
        return 1
    finally:
        if spec.manifest_path.exists():
            spec.manifest_path.unlink(missing_ok=True)


def parse_job_spec(argv: list[str] | None = None) -> JobSpec:
    """从命令行参数解析后台 WAV 作业规格。"""
    parser = argparse.ArgumentParser(description="后台 WAV 转码作业")
    parser.add_argument("--task-id", type=str, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--wav-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--progress-path", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--timeout", type=int, required=True)
    parser.add_argument("--retries", type=int, required=True)
    parser.add_argument("--format", type=str, required=True)
    args = parser.parse_args(argv)
    return JobSpec(
        job_label=str(args.task_id),
        manifest_path=args.manifest,
        audio_root=args.audio_root,
        wav_root=args.wav_root,
        report_root=args.report_root,
        progress_path=args.progress_path,
        worker_count=args.workers,
        timeout_seconds=args.timeout,
        max_retries=args.retries,
        wav_format=args.format,
    )


def main(argv: list[str] | None = None) -> int:
    """执行命令行入口并返回退出码。"""
    spec = parse_job_spec(argv)
    return run_job(spec)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "JobHandle",
    "JobSpec",
    "ManifestRecorder",
    "build_job_spec",
    "build_recorder",
    "launch_detached",
    "launch_job",
    "parse_job_spec",
    "run_job",
]
