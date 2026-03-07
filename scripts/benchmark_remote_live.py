#!/usr/bin/env python3
"""真实远端完整链路 benchmark。"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from league_tools.utils.wwiser import Singleton as WwiserSingleton
from league_tools.utils.wwiser import WwiserManager
from loguru import logger
from riotmanifest import RiotGameData, VersionMatchMode

from lol_audio_unpack.app_context import OperationOptions, create_app_context
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.utils import find_data_file
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.disk_usage import (
    DirectoryUsageMonitor,
    compute_unique_disk_usage,
    format_size,
    write_disk_usage_report,
)

DEFAULT_CHAMPION_IDS: tuple[int, ...] = (1, 103, 555)
DEFAULT_MAP_ID = 11
DEFAULT_LIVE_REGION = "EUW"
DEFAULT_GAME_REGION = "zh_CN"
DEFAULT_MATCH_MODE = VersionMatchMode.IGNORE_REVISION
EXPECTED_CHAMPION_BENCHMARK_COUNT = 3


@dataclass(frozen=True)
class RemoteBenchmarkConfig:
    """远端 benchmark 运行配置。"""

    repo_root: Path
    report_path: Path
    output_root: Path
    live_region: str
    game_region: str
    champion_ids: tuple[int, ...]
    map_id: int
    max_workers: int
    sampling_interval: float
    cleanup_remote: bool
    integrate_data: bool
    auto_download_wwiser: bool
    wwiser_path: Path | None
    match_mode: VersionMatchMode = DEFAULT_MATCH_MODE


@dataclass(frozen=True)
class RemoteSnapshotMeta:
    """远端快照元数据。"""

    version: str
    lcu_manifest_url: str
    game_manifest_url: str


@dataclass(frozen=True)
class StageExecutionSpec:
    """单个 benchmark 阶段的执行规格。"""

    stage_name: str
    label: str
    interval_seconds: float
    operation: Any
    validator: Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 可选命令行参数列表。

    Returns:
        解析后的命名空间对象。
    """
    parser = argparse.ArgumentParser(description="执行 remote live 真实完整链路 benchmark")
    parser.add_argument(
        "--live-region",
        default=DEFAULT_LIVE_REGION,
        help=f"远端 live 区服，默认 {DEFAULT_LIVE_REGION}",
    )
    parser.add_argument(
        "--game-region",
        default=DEFAULT_GAME_REGION,
        help=f"音频语言区域，默认 {DEFAULT_GAME_REGION}",
    )
    parser.add_argument(
        "--champion-ids",
        default="1,103,555",
        help="英雄 ID 列表，逗号分隔，默认 1,103,555",
    )
    parser.add_argument(
        "--map-id",
        type=int,
        default=DEFAULT_MAP_ID,
        help=f"地图 ID，默认 {DEFAULT_MAP_ID}",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="extract / mapping 阶段使用的 worker 数，默认 1",
    )
    parser.add_argument(
        "--sampling-interval",
        type=float,
        default=0.5,
        help="磁盘占用采样间隔秒数，默认 0.5",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("benchmarks/remote_live/latest.json"),
        help="最终 JSON 报告路径",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(".cache/remote_live_benchmark"),
        help="benchmark 运行输出根目录",
    )
    parser.add_argument(
        "--wwiser-path",
        type=Path,
        default=None,
        help="显式指定 wwiser.pyz/wwiser.exe 路径；不传则尝试复用或自动下载",
    )
    parser.add_argument(
        "--auto-download-wwiser",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="缺少 wwiser 时是否自动下载，默认开启",
    )
    parser.add_argument(
        "--cleanup-remote",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="每个阶段结束后是否清理远端准备产物，默认开启",
    )
    parser.add_argument(
        "--integrate-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="mapping 阶段是否同时输出 integrated 数据，默认开启",
    )
    return parser.parse_args(argv)


def parse_id_csv(raw_value: str) -> tuple[int, ...]:
    """把逗号分隔的 ID 字符串解析为元组。

    Args:
        raw_value: 原始 ID 字符串。

    Returns:
        解析后的整数元组。

    Raises:
        ValueError: 输入为空或存在非法 ID 时抛出。
    """
    parts = [part.strip() for part in raw_value.split(",") if part.strip()]
    if not parts:
        raise ValueError("至少需要提供一个有效 ID。")

    try:
        values = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"存在非法 ID: {raw_value}") from exc

    if any(value <= 0 for value in values):
        raise ValueError(f"ID 必须为正整数: {raw_value}")
    return values


def _reset_data_reader_singleton() -> None:
    """重置 `DataReader` 单例，避免跨阶段污染。"""
    Singleton._instances.pop(DataReader, None)


def _resolve_report_path(repo_root: Path, report_path: Path) -> Path:
    """解析报告绝对路径。"""
    if report_path.is_absolute():
        return report_path
    return repo_root / report_path


def _resolve_output_root(repo_root: Path, output_root: Path) -> Path:
    """解析输出根目录绝对路径。"""
    if output_root.is_absolute():
        return output_root
    return repo_root / output_root


def _resolve_snapshot_meta(live_region: str, *, match_mode: VersionMatchMode) -> RemoteSnapshotMeta:
    """解析最新 live 远端清单。

    Args:
        live_region: Riot live 区服。
        match_mode: 版本匹配模式。

    Returns:
        远端快照元数据。
    """
    pair = RiotGameData().resolve_live_manifest_pair(live_region, match_mode=match_mode)
    return RemoteSnapshotMeta(
        version=str(pair.version),
        lcu_manifest_url=pair.lcu.url,
        game_manifest_url=pair.game.url,
    )


def _ensure_wwiser_ready(config: RemoteBenchmarkConfig) -> Path:
    """确保映射阶段所需的 wwiser 可用。

    Args:
        config: benchmark 配置。

    Returns:
        可用的 wwiser 文件路径。

    Raises:
        FileNotFoundError: 当未找到可用 wwiser 且禁用自动下载时抛出。
    """
    if config.wwiser_path is not None:
        if not config.wwiser_path.exists():
            raise FileNotFoundError(f"指定的 wwiser 路径不存在: {config.wwiser_path}")
        return config.wwiser_path

    default_path = config.repo_root / ".cache" / "tools" / "wwiser" / "wwiser.pyz"
    default_path.parent.mkdir(parents=True, exist_ok=True)
    if default_path.exists():
        return default_path

    if not config.auto_download_wwiser:
        raise FileNotFoundError("未找到 wwiser，且已显式关闭自动下载。")

    manager = WwiserManager(wwiser_path=default_path.parent, auto_download=False)
    downloaded_path = manager.download_wwiser(output_dir=default_path.parent)
    WwiserSingleton._instances.pop(WwiserManager, None)
    if downloaded_path is None:
        raise FileNotFoundError("自动下载 wwiser 失败。")
    return downloaded_path


def _build_app(
    *,
    output_path: Path,
    snapshot_meta: RemoteSnapshotMeta,
    config: RemoteBenchmarkConfig,
    wwiser_path: Path,
) -> LolAudioUnpackApp:
    """构建远端 benchmark 专用 app。"""
    ctx = create_app_context(
        cli_overrides={
            "OUTPUT_PATH": str(output_path),
            "GAME_REGION": config.game_region,
            "SOURCE_MODE": "remote_snapshot",
            "REMOTE_VERSION": snapshot_meta.version,
            "REMOTE_LCU_MANIFEST_URL": snapshot_meta.lcu_manifest_url,
            "REMOTE_GAME_MANIFEST_URL": snapshot_meta.game_manifest_url,
            "WWISER_PATH": str(wwiser_path),
            "CLEANUP_REMOTE": config.cleanup_remote,
        },
    )
    return LolAudioUnpackApp(ctx)


def _write_snapshot_context(
    *,
    output_path: Path,
    config: RemoteBenchmarkConfig,
    snapshot_meta: RemoteSnapshotMeta,
    entity_type: str,
    ids: tuple[int, ...],
) -> Path:
    """写入本轮远端上下文说明文件。"""
    payload = {
        "generated_at": datetime.now().isoformat(),
        "live_region": config.live_region,
        "game_region": config.game_region,
        "version": snapshot_meta.version,
        "entity_type": entity_type,
        "ids": list(ids),
        "match_mode": config.match_mode.value,
        "lcu_manifest_url": snapshot_meta.lcu_manifest_url,
        "game_manifest_url": snapshot_meta.game_manifest_url,
    }
    snapshot_file = output_path / "remote_snapshot_context.json"
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return snapshot_file


def _build_stage_monitor(
    *,
    root: Path,
    label: str,
    interval_seconds: float,
) -> DirectoryUsageMonitor:
    """构建目录占用监控器。"""
    return DirectoryUsageMonitor(root=root, label=label, interval_seconds=interval_seconds)


def _validate_update_artifacts(
    *,
    output_path: Path,
    version: str,
    entity_type: str,
    ids: tuple[int, ...],
) -> tuple[dict[str, Any], list[str]]:
    """校验 update 阶段产物。"""
    manifest_root = output_path / "manifest" / version
    data_file = find_data_file(manifest_root / "data", dev_mode=False)
    artifacts: dict[str, Any] = {
        "data_file": str(data_file) if data_file is not None else "",
        "use_local_bin_flag_exists": (manifest_root / ".use_local_bin").exists(),
        "banks": {},
        "events": {},
    }
    errors: list[str] = []

    if data_file is None:
        errors.append("未找到 manifest data 文件。")

    sub_dir = "champions" if entity_type == "champion" else "maps"
    for entity_id in ids:
        entity_key = str(entity_id)
        banks_file = find_data_file(manifest_root / "banks" / sub_dir / entity_key, dev_mode=False)
        events_file = find_data_file(manifest_root / "events" / sub_dir / entity_key, dev_mode=False)
        artifacts["banks"][entity_key] = str(banks_file) if banks_file is not None else ""
        artifacts["events"][entity_key] = str(events_file) if events_file is not None else ""
        if banks_file is None:
            errors.append(f"未找到 {entity_type} {entity_key} 的 banks 文件。")
        if events_file is None:
            errors.append(f"未找到 {entity_type} {entity_key} 的 events 文件。")

    if not artifacts["use_local_bin_flag_exists"]:
        errors.append("update 阶段未生成 .use_local_bin 标记文件。")

    return artifacts, errors


def _count_champion_wems(audio_root: Path, champion_id: int) -> int:
    """统计单个英雄输出的 wem 文件数量。"""
    if not audio_root.exists():
        return 0

    count = 0
    prefix = f"{champion_id}·"
    for path in audio_root.rglob("*.wem"):
        if any(part.startswith(prefix) for part in path.parts):
            count += 1
    return count


def _count_map_wems(audio_root: Path, map_id: int) -> int:
    """统计单个地图输出的 wem 文件数量。"""
    if not audio_root.exists():
        return 0

    count = 0
    prefix = f"{map_id}·"
    for path in audio_root.rglob("*.wem"):
        if any(part.startswith(prefix) for part in path.parts):
            count += 1
    return count


def _validate_extract_artifacts(
    *,
    output_path: Path,
    version: str,
    entity_type: str,
    ids: tuple[int, ...],
) -> tuple[dict[str, Any], list[str]]:
    """校验 extract 阶段产物。"""
    entity_root = output_path / "audios" / version / ("champions" if entity_type == "champion" else "maps")
    report_root = output_path / "reports" / version / ("champions" if entity_type == "champion" else "maps")
    artifacts: dict[str, Any] = {
        "audio_root_exists": entity_root.exists(),
        "wem_count_by_id": {},
        "report_exists_by_id": {},
    }
    errors: list[str] = []

    if not entity_root.exists():
        errors.append(f"extract 阶段未生成 {entity_type} 音频目录。")

    for entity_id in ids:
        entity_key = str(entity_id)
        if entity_type == "champion":
            wem_count = _count_champion_wems(entity_root, entity_id)
        else:
            wem_count = _count_map_wems(entity_root, entity_id)
        report_file = report_root / f"_{entity_id}_metadata.yaml"
        artifacts["wem_count_by_id"][entity_key] = wem_count
        artifacts["report_exists_by_id"][entity_key] = report_file.exists()

        if wem_count <= 0:
            errors.append(f"{entity_type} {entity_key} 解包后未产生任何 wem 文件。")
        if not report_file.exists():
            errors.append(f"未找到 {entity_type} {entity_key} 的解包报告。")

    return artifacts, errors


def _validate_mapping_artifacts(
    *,
    output_path: Path,
    version: str,
    entity_type: str,
    ids: tuple[int, ...],
    integrate_data: bool,
) -> tuple[dict[str, Any], list[str]]:
    """校验 mapping 阶段产物。"""
    hash_root = output_path / "hashes" / version / ("champions" if entity_type == "champion" else "maps")
    integrated_root = (
        output_path / "hashes" / version / "integrated" / ("champions" if entity_type == "champion" else "maps")
    )
    artifacts: dict[str, Any] = {
        "mapping_files": {},
        "integrated_files": {},
    }
    errors: list[str] = []

    for entity_id in ids:
        entity_key = str(entity_id)
        mapping_file = find_data_file(hash_root / entity_key, dev_mode=False)
        artifacts["mapping_files"][entity_key] = str(mapping_file) if mapping_file is not None else ""
        if not integrate_data and mapping_file is None:
            errors.append(f"未找到 {entity_type} {entity_key} 的 mapping 输出。")

        if integrate_data:
            integrated_file = find_data_file(integrated_root / entity_key, dev_mode=False)
            artifacts["integrated_files"][entity_key] = str(integrated_file) if integrated_file is not None else ""
            if integrated_file is None:
                errors.append(f"未找到 {entity_type} {entity_key} 的 integrated 输出。")

    return artifacts, errors


def _cleanup_stage(app: LolAudioUnpackApp, output_path: Path) -> tuple[float, int, str]:
    """执行阶段收尾清理并统计耗时与剩余占用。"""
    cleanup_start = time.perf_counter()
    cleanup_error = ""
    try:
        app.cleanup_remote_artifacts()
    except Exception as exc:  # noqa: BLE001
        cleanup_error = f"{type(exc).__name__}: {exc}"
    cleanup_seconds = round(time.perf_counter() - cleanup_start, 3)
    post_cleanup_bytes = compute_unique_disk_usage(output_path)
    return cleanup_seconds, post_cleanup_bytes, cleanup_error


def _run_stage(
    *,
    app: LolAudioUnpackApp,
    output_path: Path,
    spec: StageExecutionSpec,
) -> dict[str, Any]:
    """执行单个 benchmark 阶段。"""
    monitor = _build_stage_monitor(root=output_path, label=spec.label, interval_seconds=spec.interval_seconds)
    stage_started_at = datetime.now().isoformat()
    monitor.start()
    status = "ok"
    error = ""
    traceback_tail = ""
    validation_errors: list[str] = []
    artifacts: dict[str, Any] = {}
    cleanup_error = ""

    try:
        spec.operation()
        artifacts, validation_errors = spec.validator()
        if validation_errors:
            status = "fail"
            error = "; ".join(validation_errors)
    except Exception as exc:  # noqa: BLE001
        status = "fail"
        error = f"{type(exc).__name__}: {exc}"
        traceback_tail = traceback.format_exc()[-4000:]
    finally:
        report = monitor.stop()
        report_path = write_disk_usage_report(output_path, report)
        cleanup_seconds, post_cleanup_bytes, cleanup_error = _cleanup_stage(app, output_path)
        _reset_data_reader_singleton()

    if cleanup_error:
        status = "fail"
        error = f"{error}; 清理失败: {cleanup_error}".strip("; ")

    return {
        "stage": spec.stage_name,
        "status": status,
        "started_at": stage_started_at,
        "ended_at": datetime.now().isoformat(),
        "duration_seconds": round(report.duration_seconds, 3),
        "peak_bytes": report.peak_bytes,
        "peak_human": format_size(report.peak_bytes),
        "post_stage_bytes": report.final_bytes,
        "post_stage_human": format_size(report.final_bytes),
        "post_cleanup_bytes": post_cleanup_bytes,
        "post_cleanup_human": format_size(post_cleanup_bytes),
        "cleanup_duration_seconds": cleanup_seconds,
        "cleanup_error": cleanup_error,
        "space_report_path": str(report_path),
        "artifacts": artifacts,
        "error": error,
        "traceback_tail": traceback_tail,
        "validation_errors": validation_errors,
    }


def _build_scenario_summary(stage_results: list[dict[str, Any]], output_path: Path) -> dict[str, Any]:
    """构建单个场景的汇总信息。"""
    peak_bytes = max((int(item["peak_bytes"]) for item in stage_results), default=0)
    final_bytes = compute_unique_disk_usage(output_path)
    failed_stages = [item["stage"] for item in stage_results if item["status"] != "ok"]
    return {
        "status": "ok" if not failed_stages else "fail",
        "stage_count": len(stage_results),
        "failed_stages": failed_stages,
        "overall_peak_bytes": peak_bytes,
        "overall_peak_human": format_size(peak_bytes),
        "final_bytes": final_bytes,
        "final_human": format_size(final_bytes),
        "total_duration_seconds": round(sum(float(item["duration_seconds"]) for item in stage_results), 3),
    }


def _run_champion_scenario(
    *,
    config: RemoteBenchmarkConfig,
    snapshot_meta: RemoteSnapshotMeta,
    wwiser_path: Path,
    run_root: Path,
) -> dict[str, Any]:
    """执行英雄完整链路场景。"""
    output_path = run_root / "champions"
    output_path.mkdir(parents=True, exist_ok=True)
    _write_snapshot_context(
        output_path=output_path,
        config=config,
        snapshot_meta=snapshot_meta,
        entity_type="champion",
        ids=config.champion_ids,
    )
    app = _build_app(output_path=output_path, snapshot_meta=snapshot_meta, config=config, wwiser_path=wwiser_path)
    options = OperationOptions(max_workers=config.max_workers, champion_ids=config.champion_ids)

    stages = [
        _run_stage(
            app=app,
            output_path=output_path,
            spec=StageExecutionSpec(
                stage_name="update",
                label=f"champions_update_{'_'.join(str(item) for item in config.champion_ids)}",
                interval_seconds=config.sampling_interval,
                operation=lambda: app.update(options, target="skin"),
                validator=lambda: _validate_update_artifacts(
                    output_path=output_path,
                    version=snapshot_meta.version,
                    entity_type="champion",
                    ids=config.champion_ids,
                ),
            ),
        ),
        _run_stage(
            app=app,
            output_path=output_path,
            spec=StageExecutionSpec(
                stage_name="extract",
                label=f"champions_extract_{'_'.join(str(item) for item in config.champion_ids)}",
                interval_seconds=config.sampling_interval,
                operation=lambda: app.extract(options, include_maps=False),
                validator=lambda: _validate_extract_artifacts(
                    output_path=output_path,
                    version=snapshot_meta.version,
                    entity_type="champion",
                    ids=config.champion_ids,
                ),
            ),
        ),
        _run_stage(
            app=app,
            output_path=output_path,
            spec=StageExecutionSpec(
                stage_name="mapping",
                label=f"champions_mapping_{'_'.join(str(item) for item in config.champion_ids)}",
                interval_seconds=config.sampling_interval,
                operation=lambda: app.mapping(
                    OperationOptions(
                        max_workers=config.max_workers,
                        champion_ids=config.champion_ids,
                        integrate_data=config.integrate_data,
                    ),
                    include_maps=False,
                ),
                validator=lambda: _validate_mapping_artifacts(
                    output_path=output_path,
                    version=snapshot_meta.version,
                    entity_type="champion",
                    ids=config.champion_ids,
                    integrate_data=config.integrate_data,
                ),
            ),
        ),
    ]

    return {
        "scenario": "champions_full_chain",
        "entity_type": "champion",
        "ids": list(config.champion_ids),
        "output_path": str(output_path),
        "stages": stages,
        "summary": _build_scenario_summary(stages, output_path),
    }


def _run_map_scenario(
    *,
    config: RemoteBenchmarkConfig,
    snapshot_meta: RemoteSnapshotMeta,
    wwiser_path: Path,
    run_root: Path,
) -> dict[str, Any]:
    """执行地图完整链路场景。"""
    output_path = run_root / "maps"
    output_path.mkdir(parents=True, exist_ok=True)
    map_ids = (config.map_id,)
    _write_snapshot_context(
        output_path=output_path,
        config=config,
        snapshot_meta=snapshot_meta,
        entity_type="map",
        ids=map_ids,
    )
    app = _build_app(output_path=output_path, snapshot_meta=snapshot_meta, config=config, wwiser_path=wwiser_path)
    options = OperationOptions(max_workers=config.max_workers, map_ids=map_ids)

    stages = [
        _run_stage(
            app=app,
            output_path=output_path,
            spec=StageExecutionSpec(
                stage_name="update",
                label=f"maps_update_{config.map_id}",
                interval_seconds=config.sampling_interval,
                operation=lambda: app.update(options, target="map"),
                validator=lambda: _validate_update_artifacts(
                    output_path=output_path,
                    version=snapshot_meta.version,
                    entity_type="map",
                    ids=map_ids,
                ),
            ),
        ),
        _run_stage(
            app=app,
            output_path=output_path,
            spec=StageExecutionSpec(
                stage_name="extract",
                label=f"maps_extract_{config.map_id}",
                interval_seconds=config.sampling_interval,
                operation=lambda: app.extract(options, include_champions=False),
                validator=lambda: _validate_extract_artifacts(
                    output_path=output_path,
                    version=snapshot_meta.version,
                    entity_type="map",
                    ids=map_ids,
                ),
            ),
        ),
        _run_stage(
            app=app,
            output_path=output_path,
            spec=StageExecutionSpec(
                stage_name="mapping",
                label=f"maps_mapping_{config.map_id}",
                interval_seconds=config.sampling_interval,
                operation=lambda: app.mapping(
                    OperationOptions(
                        max_workers=config.max_workers,
                        map_ids=map_ids,
                        integrate_data=config.integrate_data,
                    ),
                    include_champions=False,
                ),
                validator=lambda: _validate_mapping_artifacts(
                    output_path=output_path,
                    version=snapshot_meta.version,
                    entity_type="map",
                    ids=map_ids,
                    integrate_data=config.integrate_data,
                ),
            ),
        ),
    ]

    return {
        "scenario": "map_full_chain",
        "entity_type": "map",
        "ids": [config.map_id],
        "output_path": str(output_path),
        "stages": stages,
        "summary": _build_scenario_summary(stages, output_path),
    }


def build_markdown_summary(payload: dict[str, Any]) -> str:
    """构建人类可读的 Markdown 报告。"""
    meta = payload["meta"]
    lines = [
        "# Remote Live Benchmark 报告",
        "",
        f"- 生成时间：{meta['generated_at']}",
        f"- live 区服：{meta['live_region']}",
        f"- 游戏语言：{meta['game_region']}",
        f"- 版本：{meta['version']}",
        f"- 版本匹配模式：{meta['match_mode']}",
        f"- 英雄：{', '.join(str(item) for item in meta['champion_ids'])}",
        f"- 地图：{meta['map_id']}",
        f"- `integrate_data`：{meta['integrate_data']}",
        f"- `cleanup_remote`：{meta['cleanup_remote']}",
        f"- `wwiser_path`：{meta['wwiser_path']}",
        "",
    ]

    for scenario in payload["scenarios"]:
        summary = scenario["summary"]
        lines.extend(
            [
                f"## {scenario['scenario']}",
                "",
                f"- 状态：{summary['status']}",
                f"- 总耗时：{summary['total_duration_seconds']}s",
                f"- 峰值占用：{summary['overall_peak_human']}",
                f"- 最终占用：{summary['final_human']}",
                f"- 输出目录：`{scenario['output_path']}`",
                "",
                "| 阶段 | 状态 | 用时(s) | 峰值占用 | 阶段结束占用 | 清理后占用 |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for stage in scenario["stages"]:
            lines.append(
                "| "
                f"{stage['stage']} | {stage['status']} | {stage['duration_seconds']} | "
                f"{stage['peak_human']} | {stage['post_stage_human']} | {stage['post_cleanup_human']} |"
            )
            if stage["error"]:
                lines.append("")
                lines.append(f"- `{stage['stage']}` 错误：{stage['error']}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def run_remote_benchmark(config: RemoteBenchmarkConfig) -> dict[str, Any]:
    """执行完整远端 benchmark 并返回结构化结果。"""
    snapshot_meta = _resolve_snapshot_meta(config.live_region, match_mode=config.match_mode)
    wwiser_path = _ensure_wwiser_ready(config)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = config.output_root / config.live_region.lower() / snapshot_meta.version / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    logger.disable("league_tools")
    started = time.perf_counter()
    scenarios = [
        _run_champion_scenario(config=config, snapshot_meta=snapshot_meta, wwiser_path=wwiser_path, run_root=run_root),
        _run_map_scenario(config=config, snapshot_meta=snapshot_meta, wwiser_path=wwiser_path, run_root=run_root),
    ]
    total_seconds = round(time.perf_counter() - started, 3)

    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "platform": platform.platform(),
            "live_region": config.live_region,
            "game_region": config.game_region,
            "version": snapshot_meta.version,
            "match_mode": config.match_mode.value,
            "champion_ids": list(config.champion_ids),
            "map_id": config.map_id,
            "max_workers": config.max_workers,
            "sampling_interval": config.sampling_interval,
            "cleanup_remote": config.cleanup_remote,
            "integrate_data": config.integrate_data,
            "wwiser_path": str(wwiser_path),
            "lcu_manifest_url": snapshot_meta.lcu_manifest_url,
            "game_manifest_url": snapshot_meta.game_manifest_url,
            "run_root": str(run_root),
            "report_path": str(config.report_path),
            "total_duration_seconds": total_seconds,
        },
        "scenarios": scenarios,
    }
    return payload


def build_config(args: argparse.Namespace, repo_root: Path) -> RemoteBenchmarkConfig:
    """根据命令行参数构建 benchmark 配置。"""
    champion_ids = parse_id_csv(args.champion_ids)
    if len(champion_ids) != EXPECTED_CHAMPION_BENCHMARK_COUNT:
        raise ValueError(
            "当前 benchmark 约定需要 "
            f"{EXPECTED_CHAMPION_BENCHMARK_COUNT} 个英雄，实际收到 {len(champion_ids)} 个。"
        )
    if args.max_workers <= 0:
        raise ValueError("max-workers 必须大于 0。")
    if args.sampling_interval <= 0:
        raise ValueError("sampling-interval 必须大于 0。")

    return RemoteBenchmarkConfig(
        repo_root=repo_root,
        report_path=_resolve_report_path(repo_root, args.report),
        output_root=_resolve_output_root(repo_root, args.output_root),
        live_region=args.live_region,
        game_region=args.game_region,
        champion_ids=champion_ids,
        map_id=int(args.map_id),
        max_workers=int(args.max_workers),
        sampling_interval=float(args.sampling_interval),
        cleanup_remote=bool(args.cleanup_remote),
        integrate_data=bool(args.integrate_data),
        auto_download_wwiser=bool(args.auto_download_wwiser),
        wwiser_path=args.wwiser_path,
        match_mode=DEFAULT_MATCH_MODE,
    )


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    repo_root = Path(__file__).resolve().parents[1]
    args = parse_args(argv)
    try:
        config = build_config(args, repo_root)
        payload = run_remote_benchmark(config)
    except Exception as exc:  # noqa: BLE001
        failure_payload = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "status": "fail",
            },
            "error": f"{type(exc).__name__}: {exc}",
            "traceback_tail": traceback.format_exc()[-4000:],
        }
        report_path = _resolve_report_path(repo_root, args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(failure_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"remote benchmark 失败，报告已写入: {report_path}")
        return 1

    config.report_path.parent.mkdir(parents=True, exist_ok=True)
    config.report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = config.report_path.with_suffix(".md")
    markdown_path.write_text(build_markdown_summary(payload), encoding="utf-8")

    failed = [scenario for scenario in payload["scenarios"] if scenario["summary"]["status"] != "ok"]
    print(f"remote benchmark 完成，JSON 报告: {config.report_path}")
    print(f"remote benchmark 完成，Markdown 报告: {markdown_path}")
    print(f"场景数: {len(payload['scenarios'])}，失败场景: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
