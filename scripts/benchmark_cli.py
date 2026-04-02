#!/usr/bin/env python3
"""真实链路基准脚本（更新 -> 解包）。

支持两类场景：
1. `single_vo`：更新后仅解包单个英雄（VO-only）。
2. `full_extract`：更新后执行全量解包（英雄 + 地图，默认全类型）。

支持两种执行引擎：
1. `cli`：通过命令行子进程执行，模拟真实用户调用。
2. `api`：直接调用 Python API，便于排查编排层问题。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import msgpack
from loguru import logger
from ruamel.yaml import YAML

from lol_audio_unpack.app_context import OperationOptions, create_app_context
from lol_audio_unpack.facade import LolAudioUnpackApp

CHAMPION_ID_POOL: tuple[str, ...] = (
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "39",
    "40",
    "41",
    "42",
    "43",
    "44",
    "45",
    "48",
    "50",
    "51",
    "53",
    "54",
    "55",
    "56",
    "57",
    "58",
    "59",
    "60",
    "61",
    "62",
    "63",
    "64",
    "67",
    "68",
    "69",
    "72",
    "74",
    "75",
    "76",
    "77",
    "78",
    "79",
    "80",
    "81",
    "82",
    "83",
    "84",
    "85",
    "86",
    "89",
    "90",
    "91",
    "92",
    "96",
    "98",
    "99",
    "101",
    "102",
    "103",
    "104",
    "105",
    "106",
    "107",
    "110",
    "111",
    "112",
    "113",
    "114",
    "115",
    "117",
    "119",
    "120",
    "121",
    "122",
    "126",
    "127",
    "131",
    "133",
    "134",
    "136",
    "141",
    "142",
    "143",
    "145",
    "147",
    "150",
    "154",
    "157",
    "161",
    "163",
    "164",
    "166",
    "200",
    "201",
    "202",
    "203",
    "221",
    "222",
    "223",
    "233",
    "234",
    "235",
    "236",
    "238",
    "240",
    "245",
    "246",
    "254",
    "266",
    "267",
    "268",
    "350",
    "360",
    "412",
    "420",
    "421",
    "427",
    "429",
    "432",
    "497",
    "498",
    "516",
    "517",
    "518",
    "523",
    "526",
    "555",
    "711",
    "777",
    "799",
    "800",
    "804",
    "875",
    "876",
    "887",
    "888",
    "893",
    "895",
    "897",
    "901",
    "902",
    "904",
    "910",
    "950",
)


@dataclass(frozen=True)
class BenchmarkContext:
    """基准脚本运行上下文。"""

    repo_root: Path
    runner: str
    uv_entry: str
    timeout: int
    workers: int
    log_level: str
    run_id: str


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="执行更新 -> 解包真实链路基准测试")
    parser.add_argument(
        "--mode",
        choices=["single_vo", "full_extract", "both"],
        default="both",
        help="执行模式：single_vo / full_extract / both",
    )
    parser.add_argument(
        "--runner",
        choices=["cli", "api", "both"],
        default="cli",
        help="执行引擎：cli / api / both",
    )
    parser.add_argument(
        "--single-vo-id",
        type=str,
        default=None,
        help="single_vo 模式指定英雄 ID，不传则从 manifest 自动选择",
    )
    parser.add_argument(
        "--max-workers",
        default="auto",
        help="worker 数，默认 auto（使用 os.cpu_count()）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/latest.json"),
        help="基准结果输出路径（JSON）",
    )
    parser.add_argument(
        "--uv-entry",
        default="uv",
        help="uv 可执行入口，默认 uv",
    )
    parser.add_argument(
        "--game-path",
        type=Path,
        default=None,
        help="游戏目录（必填）",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="输出目录根（必填）",
    )
    parser.add_argument(
        "--prepare-update",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否在解包前执行 --update（默认开启）",
    )
    parser.add_argument(
        "--skip-events",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="更新阶段是否跳过事件处理（默认不跳过）",
    )
    parser.add_argument(
        "--with-bp-vo",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="显式覆盖 WITH_BP_VO（未设置则沿用默认配置）",
    )
    parser.add_argument(
        "--single-vo-exclude-type",
        type=str,
        default="SFX,MUSIC",
        help="single_vo 模式 EXCLUDE_TYPE，默认仅保留 VO（SFX,MUSIC）",
    )
    parser.add_argument(
        "--full-extract-exclude-type",
        type=str,
        default="",
        help="full_extract 模式 EXCLUDE_TYPE，默认空字符串表示全类型",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="CLI 子命令超时秒数",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        help="执行日志级别",
    )
    parser.add_argument(
        "--enable-league-tools-log",
        action="store_true",
        help="启用 league_tools 日志（默认关闭，避免超大量输出）",
    )
    return parser.parse_args()


def resolve_workers(raw_workers: str) -> int:
    """解析并归一化 worker 参数。

    Args:
        raw_workers: 命令行输入值，支持 `auto` 或正整数。

    Returns:
        实际 worker 数。

    Raises:
        ValueError: 输入不是合法值时抛出。
    """
    if raw_workers == "auto":
        return max(1, os.cpu_count() or 1)
    try:
        value = int(raw_workers)
    except ValueError as e:
        raise ValueError(f"max_workers 非法: {raw_workers}") from e
    return max(1, value)


def read_file_tail(path: Path, *, max_chars: int = 1200) -> str:
    """读取文本文件尾部内容。"""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def run_command(cmd: list[str], cwd: Path, timeout: int, *, log_file: Path | None = None) -> dict[str, Any]:
    """执行子进程命令并返回结构化结果。"""
    start = time.perf_counter()
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if log_file is None:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            stdout_tail = proc.stdout[-1200:]
            stderr_tail = proc.stderr[-1200:]
        else:
            with log_file.open("a", encoding="utf-8") as sink:
                proc = subprocess.run(
                    cmd,
                    cwd=str(cwd),
                    env=os.environ.copy(),
                    stdout=sink,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            stdout_tail = read_file_tail(log_file)
            stderr_tail = ""

        elapsed = round(time.perf_counter() - start, 3)
        result: dict[str, Any] = {
            "status": "ok" if proc.returncode == 0 else "fail",
            "returncode": proc.returncode,
            "elapsed_sec": elapsed,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
        }
        if log_file is not None:
            result["log_file"] = str(log_file)
        return result
    except subprocess.TimeoutExpired:
        elapsed = round(time.perf_counter() - start, 3)
        result = {
            "status": "timeout",
            "returncode": None,
            "elapsed_sec": elapsed,
            "stdout_tail": read_file_tail(log_file) if log_file is not None else "",
            "stderr_tail": f"命令超时({timeout}s)",
        }
        if log_file is not None:
            result["log_file"] = str(log_file)
        return result


def get_game_version(game_path: Path) -> str:
    """读取并解析游戏版本号。"""
    meta = game_path / "Game" / "content-metadata.json"
    if not meta.is_file():
        raise FileNotFoundError(f"缺少版本文件: {meta}")
    raw = json.loads(meta.read_text(encoding="utf-8"))
    version_str = str(raw.get("version", ""))
    match = re.match(r"^(\d+\.\d+)\.", version_str)
    if not match:
        raise ValueError(f"无法解析版本号: {version_str}")
    return match.group(1)


def find_manifest_data_file(output_path: Path, version: str) -> Path | None:
    """定位目标版本 manifest 的 data 文件。"""
    base = output_path / "manifest" / version / "data"
    for suffix in (".msgpack", ".yml", ".json"):
        candidate = base.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def load_manifest_data(path: Path) -> dict[str, Any]:
    """按后缀读取 manifest data。"""
    if path.suffix == ".msgpack":
        return msgpack.unpackb(path.read_bytes(), raw=False)
    if path.suffix in {".yml", ".yaml"}:
        yaml = YAML(typ="safe")
        data = yaml.load(path.read_text(encoding="utf-8"))
        return data or {}
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"不支持的 data 文件格式: {path}")


def add_result(  # noqa: PLR0913
    results: list[dict[str, Any]],
    *,
    runner: str,
    scenario: str,
    step: str,
    output_root: Path,
    command: str | None,
    data: dict[str, Any],
) -> None:
    """追加单条结果记录。"""
    row = {
        "runner": runner,
        "scenario": scenario,
        "step": step,
        "output_root": str(output_root),
        "command": command or "",
    }
    row.update(data)
    results.append(row)


def snapshot_wem_metrics(output_root: Path) -> dict[str, int]:
    """统计当前输出目录中的 wem 文件数量与大小。"""
    audio_root = output_root / "audios"
    if not audio_root.exists():
        return {"wem_files": 0, "wem_bytes": 0}
    file_count = 0
    total_bytes = 0
    for wem_file in audio_root.rglob("*.wem"):
        if wem_file.is_file():
            file_count += 1
            total_bytes += wem_file.stat().st_size
    return {"wem_files": file_count, "wem_bytes": total_bytes}


def build_metric_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """构建指标增量。"""
    return {
        "wem_files_before": before["wem_files"],
        "wem_files_after": after["wem_files"],
        "wem_files_delta": after["wem_files"] - before["wem_files"],
        "wem_bytes_before": before["wem_bytes"],
        "wem_bytes_after": after["wem_bytes"],
        "wem_bytes_delta": after["wem_bytes"] - before["wem_bytes"],
    }


def pick_single_vo_champion_id(manifest_data: dict[str, Any], preferred_id: str | None) -> str:
    """从 manifest 中确定 single_vo 目标英雄 ID。

    Args:
        manifest_data: 当前版本 data 文件内容。
        preferred_id: 用户显式指定 ID。

    Returns:
        可用英雄 ID 字符串。

    Raises:
        ValueError: 无可用英雄 ID 时抛出。
    """
    champions = manifest_data.get("champions") or {}
    champion_ids = sorted((str(champ_id) for champ_id in champions.keys()), key=int)
    if preferred_id:
        if preferred_id not in champion_ids:
            raise ValueError(f"指定 single_vo 英雄ID不存在于当前版本: {preferred_id}")
        return preferred_id

    available_set = set(champion_ids)
    for candidate in CHAMPION_ID_POOL:
        if candidate in available_set:
            return candidate
    if champion_ids:
        return champion_ids[0]
    raise ValueError("当前 manifest 不包含任何英雄数据，无法执行 single_vo")


def build_cli_base_command(ctx: BenchmarkContext) -> list[str]:
    """构建 CLI 基础命令前缀。

    约定：
    - `--uv-entry uv`（默认）：使用 `uv run python -m ...`。
    - `--uv-entry python`：使用当前解释器 `sys.executable -m ...`，避免嵌套 `uv run`。
    """
    if ctx.uv_entry == "python":
        return [sys.executable, "-m", "lol_audio_unpack"]
    return [ctx.uv_entry, "run", "python", "-m", "lol_audio_unpack"]


def append_optional_bool_flag(cmd: list[str], flag: str, value: bool | None) -> None:
    """按值追加 bool 可选参数。"""
    if value is None:
        return
    cmd.append(flag if value else f"--no-{flag.removeprefix('--')}")


def build_update_command(
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    *,
    skip_events: bool,
    with_bp_vo: bool | None,
) -> list[str]:
    """构建更新命令。"""
    cmd = build_cli_base_command(ctx)
    cmd.extend(
        [
            "--update",
            "--max-workers",
            str(ctx.workers),
            "--log-level",
            ctx.log_level,
            "--game-path",
            str(game_path),
            "--output-path",
            str(output_path),
        ]
    )
    if skip_events:
        cmd.append("--skip-events")
    append_optional_bool_flag(cmd, "--with-bp-vo", with_bp_vo)
    return cmd


def build_single_vo_command(  # noqa: PLR0913
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    *,
    champion_id: str,
    exclude_type: str,
    with_bp_vo: bool | None,
) -> list[str]:
    """构建 single_vo 解包命令。"""
    cmd = build_cli_base_command(ctx)
    cmd.extend(
        [
            "--extract-champions",
            champion_id,
            "--max-workers",
            str(ctx.workers),
            "--log-level",
            ctx.log_level,
            "--game-path",
            str(game_path),
            "--output-path",
            str(output_path),
            "--exclude-type",
            exclude_type,
        ]
    )
    append_optional_bool_flag(cmd, "--with-bp-vo", with_bp_vo)
    return cmd


def build_full_extract_command(
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    *,
    exclude_type: str,
    with_bp_vo: bool | None,
) -> list[str]:
    """构建全量解包命令。"""
    cmd = build_cli_base_command(ctx)
    cmd.extend(
        [
            "--extract",
            "--max-workers",
            str(ctx.workers),
            "--log-level",
            ctx.log_level,
            "--game-path",
            str(game_path),
            "--output-path",
            str(output_path),
            "--exclude-type",
            exclude_type,
        ]
    )
    append_optional_bool_flag(cmd, "--with-bp-vo", with_bp_vo)
    return cmd


def run_cli_step(
    ctx: BenchmarkContext,
    *,
    cmd: list[str],
    output_root: Path,
    step_name: str,
) -> dict[str, Any]:
    """执行单个 CLI 步骤，并附带 wem 指标增量。"""
    before = snapshot_wem_metrics(output_root)
    log_file = output_root / "reports" / f"benchmark_{ctx.runner}_{step_name}.log"
    result = run_command(cmd=cmd, cwd=ctx.repo_root, timeout=ctx.timeout, log_file=log_file)
    after = snapshot_wem_metrics(output_root)
    result.update(build_metric_delta(before, after))
    return result


def run_api_step(output_root: Path, handler: Any) -> dict[str, Any]:
    """执行单个 API 步骤，并附带 wem 指标增量。"""
    before = snapshot_wem_metrics(output_root)
    start = time.perf_counter()
    try:
        handler()
        status = "ok"
        error: str | None = None
        trace_tail = ""
    except Exception as e:  # noqa: BLE001
        status = "fail"
        error = f"{type(e).__name__}: {e}"
        trace_tail = traceback.format_exc()[-1200:]
    elapsed = round(time.perf_counter() - start, 3)
    after = snapshot_wem_metrics(output_root)

    payload: dict[str, Any] = {
        "status": status,
        "elapsed_sec": elapsed,
        **build_metric_delta(before, after),
    }
    if error:
        payload["error"] = error
        payload["traceback_tail"] = trace_tail
    return payload


def create_api_app(
    *,
    game_path: Path,
    output_path: Path,
    exclude_type: str,
    with_bp_vo: bool | None,
    log_level: str,
) -> Any:
    """创建 API 运行时 app 实例。"""
    settings: dict[str, Any] = {
        "GAME_PATH": str(game_path),
        "OUTPUT_PATH": str(output_path),
        "EXCLUDE_TYPE": exclude_type,
    }
    if with_bp_vo is not None:
        settings["WITH_BP_VO"] = with_bp_vo

    _ = log_level
    app_context = create_app_context(dev_mode=False, settings=settings)
    return LolAudioUnpackApp(app_context)


def run_update_api(  # noqa: PLR0913
    *,
    game_path: Path,
    output_path: Path,
    skip_events: bool,
    with_bp_vo: bool | None,
    log_level: str,
    workers: int,
    exclude_type: str,
) -> None:
    """执行 API 更新步骤。"""
    app = create_api_app(
        game_path=game_path,
        output_path=output_path,
        exclude_type=exclude_type,
        with_bp_vo=with_bp_vo,
        log_level=log_level,
    )
    options = OperationOptions(max_workers=workers, process_events=not skip_events)
    app.update(options, target="all")


def run_single_vo_api(  # noqa: PLR0913
    *,
    game_path: Path,
    output_path: Path,
    champion_id: str,
    with_bp_vo: bool | None,
    log_level: str,
    workers: int,
    exclude_type: str,
) -> None:
    """执行 API single_vo 解包步骤。"""
    app = create_api_app(
        game_path=game_path,
        output_path=output_path,
        exclude_type=exclude_type,
        with_bp_vo=with_bp_vo,
        log_level=log_level,
    )
    options = OperationOptions(max_workers=workers, champion_ids=(int(champion_id),))
    app.extract(options, include_maps=False)


def run_full_extract_api(  # noqa: PLR0913
    *,
    game_path: Path,
    output_path: Path,
    with_bp_vo: bool | None,
    log_level: str,
    workers: int,
    exclude_type: str,
) -> None:
    """执行 API 全量解包步骤。"""
    app = create_api_app(
        game_path=game_path,
        output_path=output_path,
        exclude_type=exclude_type,
        with_bp_vo=with_bp_vo,
        log_level=log_level,
    )
    options = OperationOptions(max_workers=workers)
    app.extract(options)


def execute_single_vo_scenario(
    ctx: BenchmarkContext,
    args: argparse.Namespace,
    *,
    game_path: Path,
    scenario_output: Path,
    results: list[dict[str, Any]],
) -> None:
    """执行 single_vo 场景（更新 -> 单英雄 VO 解包）。"""
    scenario_output.mkdir(parents=True, exist_ok=True)
    exclude_type = args.single_vo_exclude_type

    if args.prepare_update:
        if ctx.runner == "cli":
            update_cmd = build_update_command(
                ctx,
                game_path,
                scenario_output,
                skip_events=args.skip_events,
                with_bp_vo=args.with_bp_vo,
            )
            update_result = run_cli_step(ctx, cmd=update_cmd, output_root=scenario_output, step_name="single_vo_update")
            add_result(
                results,
                runner=ctx.runner,
                scenario="single_vo",
                step="update",
                output_root=scenario_output,
                command=" ".join(update_cmd),
                data=update_result,
            )
        else:
            update_result = run_api_step(
                scenario_output,
                lambda: run_update_api(
                    game_path=game_path,
                    output_path=scenario_output,
                    skip_events=args.skip_events,
                    with_bp_vo=args.with_bp_vo,
                    log_level=ctx.log_level,
                    workers=ctx.workers,
                    exclude_type=exclude_type,
                ),
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario="single_vo",
                step="update",
                output_root=scenario_output,
                command="api:update(target=all)",
                data=update_result,
            )
        if update_result.get("status") != "ok":
            return

    try:
        version = get_game_version(game_path)
        data_file = find_manifest_data_file(scenario_output, version)
        if data_file is None:
            raise FileNotFoundError(f"未找到 manifest data: {scenario_output / 'manifest' / version / 'data.*'}")
        manifest_data = load_manifest_data(data_file)
        champion_id = pick_single_vo_champion_id(manifest_data, args.single_vo_id)
    except Exception as e:  # noqa: BLE001
        add_result(
            results,
            runner=ctx.runner,
            scenario="single_vo",
            step="precheck",
            output_root=scenario_output,
            command="",
            data={"status": "fail", "error": f"{type(e).__name__}: {e}"},
        )
        return

    if ctx.runner == "cli":
        extract_cmd = build_single_vo_command(
            ctx,
            game_path,
            scenario_output,
            champion_id=champion_id,
            exclude_type=exclude_type,
            with_bp_vo=args.with_bp_vo,
        )
        extract_result = run_cli_step(
            ctx,
            cmd=extract_cmd,
            output_root=scenario_output,
            step_name="single_vo_extract",
        )
        add_result(
            results,
            runner=ctx.runner,
            scenario="single_vo",
            step="extract",
            output_root=scenario_output,
            command=" ".join(extract_cmd),
            data={**extract_result, "champion_id": champion_id},
        )
        return

    extract_result = run_api_step(
        scenario_output,
        lambda: run_single_vo_api(
            game_path=game_path,
            output_path=scenario_output,
            champion_id=champion_id,
            with_bp_vo=args.with_bp_vo,
            log_level=ctx.log_level,
            workers=ctx.workers,
            exclude_type=exclude_type,
        ),
    )
    add_result(
        results,
        runner=ctx.runner,
        scenario="single_vo",
        step="extract",
        output_root=scenario_output,
        command=f"api:extract(champion_id={champion_id}, include_maps=False)",
        data={**extract_result, "champion_id": champion_id},
    )


def execute_full_extract_scenario(
    ctx: BenchmarkContext,
    args: argparse.Namespace,
    *,
    game_path: Path,
    scenario_output: Path,
    results: list[dict[str, Any]],
) -> None:
    """执行 full_extract 场景（更新 -> 全量解包）。"""
    scenario_output.mkdir(parents=True, exist_ok=True)
    exclude_type = args.full_extract_exclude_type

    if args.prepare_update:
        if ctx.runner == "cli":
            update_cmd = build_update_command(
                ctx,
                game_path,
                scenario_output,
                skip_events=args.skip_events,
                with_bp_vo=args.with_bp_vo,
            )
            update_result = run_cli_step(
                ctx,
                cmd=update_cmd,
                output_root=scenario_output,
                step_name="full_extract_update",
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario="full_extract",
                step="update",
                output_root=scenario_output,
                command=" ".join(update_cmd),
                data=update_result,
            )
        else:
            update_result = run_api_step(
                scenario_output,
                lambda: run_update_api(
                    game_path=game_path,
                    output_path=scenario_output,
                    skip_events=args.skip_events,
                    with_bp_vo=args.with_bp_vo,
                    log_level=ctx.log_level,
                    workers=ctx.workers,
                    exclude_type=exclude_type,
                ),
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario="full_extract",
                step="update",
                output_root=scenario_output,
                command="api:update(target=all)",
                data=update_result,
            )
        if update_result.get("status") != "ok":
            return

    if ctx.runner == "cli":
        extract_cmd = build_full_extract_command(
            ctx,
            game_path,
            scenario_output,
            exclude_type=exclude_type,
            with_bp_vo=args.with_bp_vo,
        )
        extract_result = run_cli_step(
            ctx,
            cmd=extract_cmd,
            output_root=scenario_output,
            step_name="full_extract_extract",
        )
        add_result(
            results,
            runner=ctx.runner,
            scenario="full_extract",
            step="extract",
            output_root=scenario_output,
            command=" ".join(extract_cmd),
            data=extract_result,
        )
        return

    extract_result = run_api_step(
        scenario_output,
        lambda: run_full_extract_api(
            game_path=game_path,
            output_path=scenario_output,
            with_bp_vo=args.with_bp_vo,
            log_level=ctx.log_level,
            workers=ctx.workers,
            exclude_type=exclude_type,
        ),
    )
    add_result(
        results,
        runner=ctx.runner,
        scenario="full_extract",
        step="extract",
        output_root=scenario_output,
        command="api:extract(all)",
        data=extract_result,
    )


def execute_runner(  # noqa: PLR0913
    args: argparse.Namespace,
    *,
    runner: str,
    game_path: Path,
    output_path: Path,
    repo_root: Path,
    results: list[dict[str, Any]],
) -> None:
    """按指定执行引擎运行目标场景。"""
    workers = resolve_workers(args.max_workers)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    ctx = BenchmarkContext(
        repo_root=repo_root,
        runner=runner,
        uv_entry=args.uv_entry,
        timeout=args.timeout,
        workers=workers,
        log_level=args.log_level,
        run_id=run_id,
    )

    base_run_dir = output_path / "benchmark_runs" / f"{ctx.run_id}_{runner}"
    if args.mode in {"single_vo", "both"}:
        execute_single_vo_scenario(
            ctx,
            args,
            game_path=game_path,
            scenario_output=base_run_dir / "single_vo",
            results=results,
        )

    if args.mode in {"full_extract", "both"}:
        execute_full_extract_scenario(
            ctx,
            args,
            game_path=game_path,
            scenario_output=base_run_dir / "full_extract",
            results=results,
        )


def resolve_runtime_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    """解析运行路径。"""
    return args.game_path, args.output_path


def main() -> int:
    """脚本主入口。"""
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    results: list[dict[str, Any]] = []

    if not args.enable_league_tools_log:
        logger.disable("league_tools")

    game_path, output_path = resolve_runtime_paths(args)
    if game_path is None or not game_path.exists():
        add_result(
            results,
            runner="n/a",
            scenario="precheck",
            step="game_path",
            output_root=repo_root,
            command="",
            data={"status": "fail", "error": "未提供有效 GAME_PATH（请使用 --game-path）"},
        )
    elif output_path is None:
        add_result(
            results,
            runner="n/a",
            scenario="precheck",
            step="output_path",
            output_root=repo_root,
            command="",
            data={"status": "fail", "error": "未提供 OUTPUT_PATH（请使用 --output-path）"},
        )
    else:
        output_path.mkdir(parents=True, exist_ok=True)
        runners = [args.runner] if args.runner != "both" else ["cli", "api"]
        for runner in runners:
            execute_runner(
                args,
                runner=runner,
                game_path=game_path,
                output_path=output_path,
                repo_root=repo_root,
                results=results,
            )

    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "mode": args.mode,
            "runner": args.runner,
            "prepare_update": args.prepare_update,
            "skip_events": args.skip_events,
            "workers": resolve_workers(args.max_workers),
            "platform": platform.platform(),
            "game_path": str(game_path) if game_path else "",
            "output_path": str(output_path) if output_path else "",
        },
        "results": results,
    }

    output_json = args.output if args.output.is_absolute() else repo_root / args.output
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [row for row in results if row.get("status") in {"fail", "timeout"}]
    print(f"基准完成，结果已写入: {output_json}")
    print(f"总步骤: {len(results)}，失败步骤: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
