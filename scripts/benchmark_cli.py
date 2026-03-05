#!/usr/bin/env python3
"""CLI 基准脚本（mock + local_game 小样本）。"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import msgpack
from ruamel.yaml import YAML

CHAMPION_ID_POOL: list[str] = [
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
    "950"
]
MAP_ID_POOL: list[str] = ["0", "11", "12", "21", "22", "30", "33", "35"]


@dataclass
class BenchmarkContext:
    """基准脚本运行上下文。"""

    repo_root: Path
    uv_entry: str
    timeout: int
    workers: int
    sample_size: int


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="运行 unpack CLI 基准测试（避免全量 real 压测）")
    parser.add_argument(
        "--mode",
        choices=["mock", "local_game", "both"],
        default="both",
        help="基准模式：mock / local_game / both",
    )
    parser.add_argument("--sample-size", type=int, default=10, help="local_game 模式抽样 ID 数量")
    parser.add_argument(
        "--max-workers",
        default="auto",
        help="worker 数，默认 auto（使用 os.cpu_count()）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/latest.json"),
        help="基准结果输出路径",
    )
    parser.add_argument(
        "--uv-entry",
        default="uv",
        help="uv 可执行文件或入口命令，默认直接使用 uv",
    )
    parser.add_argument(
        "--game-path",
        type=Path,
        default=None,
        help="游戏目录（默认读取 LOL_GAME_PATH）",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="输出目录（默认读取 LOL_OUTPUT_PATH）",
    )
    parser.add_argument(
        "--wwiser-path",
        type=Path,
        default=None,
        help="Wwiser 路径（默认读取 LOL_WWISER_PATH）",
    )
    parser.add_argument(
        "--prepare-update",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="local_game 模式是否先执行 unpack --update --skip-events（默认开启）",
    )
    parser.add_argument("--timeout", type=int, default=3600, help="单条命令超时秒数")
    return parser.parse_args()


def resolve_workers(raw_workers: str) -> int:
    """解析并归一化 worker 参数。"""
    if raw_workers == "auto":
        return max(1, os.cpu_count() or 1)
    try:
        value = int(raw_workers)
    except ValueError as e:
        raise ValueError(f"max_workers 非法: {raw_workers}") from e
    return max(1, value)


def run_command(
    cmd: list[str],
    cwd: Path,
    timeout: int,
    expected_fail: bool = False,
    fail_markers: list[str] | None = None,
) -> dict[str, Any]:
    """执行单条命令并返回结构化结果。"""
    start = time.perf_counter()
    env = os.environ.copy()
    markers = fail_markers or []

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        elapsed = time.perf_counter() - start
        success = (proc.returncode == 0) if not expected_fail else (proc.returncode != 0)
        matched_markers: list[str] = []
        if success and markers:
            output_text = f"{proc.stdout}\n{proc.stderr}"
            matched_markers = [marker for marker in markers if marker in output_text]
            if matched_markers:
                success = False
        status = "ok" if success else "fail"
        result = {
            "status": status,
            "returncode": proc.returncode,
            "elapsed_sec": round(elapsed, 3),
            "stdout_tail": proc.stdout[-800:],
            "stderr_tail": proc.stderr[-800:],
        }
        if matched_markers:
            result["fail_markers"] = matched_markers
        return result
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return {
            "status": "timeout",
            "returncode": None,
            "elapsed_sec": round(elapsed, 3),
            "stdout_tail": "",
            "stderr_tail": f"命令超时({timeout}s)",
        }


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
    """按后缀读取 manifest data 数据。"""
    if path.suffix == ".msgpack":
        return msgpack.unpackb(path.read_bytes(), raw=False)
    if path.suffix in {".yml", ".yaml"}:
        yaml = YAML(typ="safe")
        data = yaml.load(path.read_text(encoding="utf-8"))
        return data or {}
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"不支持的 data 文件格式: {path}")


def sample_ids(pool: list[str], size: int) -> list[str]:
    """从固定池中随机抽样。"""
    if not pool:
        return []
    if len(pool) <= size:
        return pool
    return random.sample(pool, size)


def pick_ids_from_fixed_pool(available_ids: list[str], fixed_pool: list[str]) -> list[str]:
    """按固定池顺序筛选当前版本可用 ID。

    Args:
        available_ids: 当前版本 manifest 中可用的 ID 列表。
        fixed_pool: 固定池 ID 列表。

    Returns:
        与当前版本交集后的可用 ID 列表，顺序与固定池一致。
    """
    available_set = set(available_ids)
    return [entity_id for entity_id in fixed_pool if entity_id in available_set]


def build_unpack_extract_cmd(
    ctx: BenchmarkContext,
    target: str,
    ids: list[str],
    game_path: Path,
    output_path: Path,
) -> list[str]:
    """构建解包命令。"""
    return [
        ctx.uv_entry,
        "run",
        "unpack",
        f"--extract-{target}",
        ",".join(ids),
        "--max-workers",
        str(ctx.workers),
        "--game-path",
        str(game_path),
        "--output-path",
        str(output_path),
    ]


def execute_benchmark_cmd(
    ctx: BenchmarkContext,
    cmd: list[str],
    fail_markers: list[str] | None = None,
) -> dict[str, Any]:
    """执行基准命令并应用失败标记。"""
    return run_command(
        cmd=cmd,
        cwd=ctx.repo_root,
        timeout=ctx.timeout,
        fail_markers=fail_markers,
    )


def build_unpack_mapping_cmd(  # noqa: PLR0913
    ctx: BenchmarkContext,
    target: str,
    ids: list[str],
    game_path: Path,
    output_path: Path,
    wwiser_path: Path,
) -> list[str]:
    """构建映射命令。"""
    return [
        ctx.uv_entry,
        "run",
        "unpack",
        f"--mapping-{target}",
        ",".join(ids),
        "--max-workers",
        str(ctx.workers),
        "--game-path",
        str(game_path),
        "--output-path",
        str(output_path),
        "--wwiser-path",
        str(wwiser_path),
    ]


def build_unpack_update_cmd(
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    skip_events: bool,
) -> list[str]:
    """构建更新 manifest 数据命令。"""
    cmd = [
        ctx.uv_entry,
        "run",
        "unpack",
        "--update",
        "--max-workers",
        str(ctx.workers),
        "--game-path",
        str(game_path),
        "--output-path",
        str(output_path),
    ]
    if skip_events:
        cmd.append("--skip-events")
    return cmd


def add_result(results: list[dict[str, Any]], stage: str, name: str, command: list[str], extra: dict[str, Any]) -> None:
    """追加单条结果记录。"""
    row = {
        "stage": stage,
        "name": name,
        "command": " ".join(command),
    }
    row.update(extra)
    results.append(row)


def run_mock_suite(ctx: BenchmarkContext, results: list[dict[str, Any]]) -> None:
    """执行 mock 基准集。"""
    mock_commands: list[tuple[str, list[str], bool]] = [
        ("unpack_version", [ctx.uv_entry, "run", "unpack", "--version"], False),
        ("unpack_help", [ctx.uv_entry, "run", "unpack", "--help"], False),
        ("unpack_no_action_should_fail", [ctx.uv_entry, "run", "unpack"], True),
    ]
    for name, cmd, expected_fail in mock_commands:
        info = run_command(cmd=cmd, cwd=ctx.repo_root, timeout=ctx.timeout, expected_fail=expected_fail)
        add_result(results, stage="mock", name=name, command=cmd, extra=info)


def run_local_game_suite(  # noqa: PLR0911,PLR0913
    ctx: BenchmarkContext,
    game_path: Path | None,
    output_path: Path | None,
    wwiser_path: Path | None,
    prepare_update: bool,
    results: list[dict[str, Any]],
) -> None:
    """执行 local_game 小样本基准。"""
    resolved_game_path = game_path or Path(os.environ.get("LOL_GAME_PATH", ""))
    resolved_output_path = output_path or Path(os.environ.get("LOL_OUTPUT_PATH", ""))
    resolved_wwiser_path = wwiser_path or Path(os.environ.get("LOL_WWISER_PATH", ""))
    mapping_enabled = bool(str(resolved_wwiser_path) and resolved_wwiser_path.exists())

    if not str(resolved_game_path) or not resolved_game_path.exists():
        add_result(
            results,
            stage="local_game",
            name="precheck_game_path",
            command=[],
            extra={"status": "skip", "reason": "未提供有效 GAME_PATH（参数或 LOL_GAME_PATH）"},
        )
        return
    if not str(resolved_output_path):
        add_result(
            results,
            stage="local_game",
            name="precheck_output_path",
            command=[],
            extra={"status": "skip", "reason": "未提供 OUTPUT_PATH（参数或 LOL_OUTPUT_PATH）"},
        )
        return

    if prepare_update:
        # 需要执行 mapping 时必须保留 events 数据，否则会出现“缺少事件数据”。
        skip_events = not mapping_enabled
        prepare_cmd = build_unpack_update_cmd(
            ctx=ctx,
            game_path=resolved_game_path,
            output_path=resolved_output_path,
            skip_events=skip_events,
        )
        info = execute_benchmark_cmd(
            ctx=ctx,
            cmd=prepare_cmd,
            fail_markers=["更新数据时发生错误", "执行过程中发生错误"],
        )
        add_result(results, stage="local_game", name="prepare_update", command=prepare_cmd, extra=info)
        if info.get("status") != "ok":
            return

    try:
        version = get_game_version(resolved_game_path)
    except Exception as e:
        add_result(
            results,
            stage="local_game",
            name="precheck_game_version",
            command=[],
            extra={"status": "skip", "reason": f"读取游戏版本失败: {e}"},
        )
        return

    data_file = find_manifest_data_file(resolved_output_path, version)
    if data_file is None:
        add_result(
            results,
            stage="local_game",
            name="precheck_manifest_data",
            command=[],
            extra={
                "status": "skip",
                "reason": f"未找到 manifest data 文件: {resolved_output_path / 'manifest' / version / 'data.*'}",
            },
        )
        return

    try:
        merged = load_manifest_data(data_file)
    except Exception as e:
        add_result(
            results,
            stage="local_game",
            name="precheck_load_manifest_data",
            command=[],
            extra={"status": "skip", "reason": f"读取 data 文件失败: {e}"},
        )
        return

    champion_ids = sorted(list((merged.get("champions") or {}).keys()), key=int)
    map_ids = sorted(list((merged.get("maps") or {}).keys()), key=int)
    champion_pool = pick_ids_from_fixed_pool(champion_ids, CHAMPION_ID_POOL)
    map_pool = pick_ids_from_fixed_pool(map_ids, MAP_ID_POOL)

    sampled_champion_ids = sample_ids(champion_pool, ctx.sample_size)
    sampled_map_ids = sample_ids(map_pool, ctx.sample_size)

    if not sampled_champion_ids:
        add_result(
            results,
            stage="local_game",
            name="precheck_champion_ids",
            command=[],
            extra={"status": "skip", "reason": "固定英雄ID池与当前版本数据无交集"},
        )
        return

    extract_champion_cmd = build_unpack_extract_cmd(
        ctx=ctx,
        target="champions",
        ids=sampled_champion_ids,
        game_path=resolved_game_path,
        output_path=resolved_output_path,
    )
    info = execute_benchmark_cmd(
        ctx=ctx,
        cmd=extract_champion_cmd,
        fail_markers=["解包时发生错误", "执行过程中发生错误"],
    )
    add_result(
        results,
        stage="local_game",
        name="extract_champions_sample",
        command=extract_champion_cmd,
        extra={**info, "sample_ids": sampled_champion_ids},
    )

    if sampled_map_ids:
        extract_map_cmd = build_unpack_extract_cmd(
            ctx=ctx,
            target="maps",
            ids=sampled_map_ids,
            game_path=resolved_game_path,
            output_path=resolved_output_path,
        )
        info = execute_benchmark_cmd(
            ctx=ctx,
            cmd=extract_map_cmd,
            fail_markers=["解包时发生错误", "执行过程中发生错误"],
        )
        add_result(
            results,
            stage="local_game",
            name="extract_maps_sample",
            command=extract_map_cmd,
            extra={**info, "sample_ids": sampled_map_ids},
        )

    if not mapping_enabled:
        add_result(
            results,
            stage="local_game",
            name="mapping_champions_sample",
            command=[],
            extra={"status": "skip", "reason": "未提供有效 WWISER_PATH（参数或 LOL_WWISER_PATH）"},
        )
        return

    mapping_cmd = build_unpack_mapping_cmd(
        ctx=ctx,
        target="champions",
        ids=sampled_champion_ids,
        game_path=resolved_game_path,
        output_path=resolved_output_path,
        wwiser_path=resolved_wwiser_path,
    )
    info = execute_benchmark_cmd(
        ctx=ctx,
        cmd=mapping_cmd,
        fail_markers=["缺少事件数据，请使用 include_events=True 创建实体数据", "映射时发生错误", "执行过程中发生错误"],
    )
    add_result(
        results,
        stage="local_game",
        name="mapping_champions_sample",
        command=mapping_cmd,
        extra={**info, "sample_ids": sampled_champion_ids},
    )


def main() -> int:
    """脚本主入口。"""
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    workers = resolve_workers(args.max_workers)
    ctx = BenchmarkContext(
        repo_root=repo_root,
        uv_entry=args.uv_entry,
        timeout=args.timeout,
        workers=workers,
        sample_size=max(1, args.sample_size),
    )
    results: list[dict[str, Any]] = []

    if args.mode in {"mock", "both"}:
        run_mock_suite(ctx=ctx, results=results)

    if args.mode in {"local_game", "both"}:
        run_local_game_suite(
            ctx=ctx,
            game_path=args.game_path,
            output_path=args.output_path,
            wwiser_path=args.wwiser_path,
            prepare_update=args.prepare_update,
            results=results,
        )

    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "mode": args.mode,
            "sample_size": args.sample_size,
            "workers": workers,
        },
        "results": results,
    }
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"基准完成，结果已写入: {output_path}")
    failed = [r for r in results if r.get("status") in {"fail", "timeout"}]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
