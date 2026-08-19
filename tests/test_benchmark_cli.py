"""验证本地基准脚本与当前 CLI 参数契约保持一致。"""

import json
import os
from pathlib import Path

from lol_audio_unpack.cli.parser import create_parser
from scripts import benchmark_cli


def test_collect_process_tree_pids_includes_recursive_descendants() -> None:
    """RSS 采样应覆盖 venv launcher 之下的真实解释器进程。"""
    parents = {10: 1, 11: 10, 12: 11, 13: 99}

    assert benchmark_cli.collect_process_tree_pids(10, parents) == {10, 11, 12}


def test_benchmark_commands_follow_current_cli_contract(tmp_path: Path) -> None:
    """各类 benchmark 命令都应能被当前动作式 CLI 解析。"""
    context = benchmark_cli.BenchmarkContext(
        repo_root=tmp_path,
        runner="cli",
        uv_entry="python",
        timeout=30,
        workers=4,
        log_level="INFO",
        run_id="test",
        source=benchmark_cli.BenchmarkSource(root=tmp_path, label="current"),
    )
    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    commands = (
        (
            benchmark_cli.build_update_command(
                context,
                game_path,
                output_path,
                skip_events=True,
                with_bp_vo=None,
            ),
            ["update"],
            None,
            None,
        ),
        (
            benchmark_cli.build_single_vo_command(
                context,
                game_path,
                output_path,
                champion_id="1",
                exclude_type="SFX,MUSIC",
                with_bp_vo=True,
            ),
            ["extract"],
            "1",
            None,
        ),
        (
            benchmark_cli.build_full_extract_command(
                context,
                game_path,
                output_path,
                exclude_type="",
                with_bp_vo=False,
            ),
            ["extract"],
            None,
            None,
        ),
        (
            benchmark_cli.build_targeted_extract_command(
                context,
                game_path,
                output_path,
                champion_ids=("1", "103"),
                map_ids=("11",),
                exclude_type="",
                with_bp_vo=None,
            ),
            ["extract"],
            "1,103",
            "11",
        ),
    )

    parser = create_parser("unpack")
    for command, expected_actions, expected_champions, expected_maps in commands:
        args = parser.parse_args(command[3:])

        assert args.actions == expected_actions
        assert args.champions == expected_champions
        assert args.maps == expected_maps
        assert args.game_path == str(game_path)
        assert args.output_path == str(output_path)


def test_build_scenario_summary_aggregates_elapsed_wems_and_peak_rss(tmp_path: Path) -> None:
    """场景汇总应保留阶段耗时、最终 WEM 指标和最高 RSS。"""
    rows = [
        {
            "scenario": "targeted_champion",
            "step": "update",
            "status": "ok",
            "elapsed_sec": 1.25,
            "peak_rss_bytes": 100,
        },
        {
            "scenario": "targeted_champion",
            "step": "extract",
            "status": "ok",
            "elapsed_sec": 2.5,
            "peak_rss_bytes": 250,
            "wem_files_after": 3,
            "wem_bytes_after": 4096,
        },
    ]

    source = benchmark_cli.BenchmarkSource(root=tmp_path / "baseline", label="baseline")
    summary = benchmark_cli.build_scenario_summary(
        rows,
        runner="cli",
        scenario="targeted_champion",
        output_root=tmp_path,
        source=source,
    )

    assert summary == {
        "runner": "cli",
        "scenario": "targeted_champion",
        "status": "ok",
        "output_root": str(tmp_path),
        "source_label": "baseline",
        "source_root": str(source.root),
        "update_elapsed_sec": 1.25,
        "extract_elapsed_sec": 2.5,
        "end_to_end_elapsed_sec": 3.75,
        "wem_files": 3,
        "wem_bytes": 4096,
        "peak_rss_bytes": 250,
    }


def test_build_source_env_prepends_source_src_and_preserves_existing_pythonpath(monkeypatch, tmp_path: Path) -> None:
    """CLI 子进程环境应优先导入指定源码树，并保留既有 PYTHONPATH。"""
    source = benchmark_cli.BenchmarkSource(root=tmp_path / "baseline", label="baseline")
    monkeypatch.setenv("PYTHONPATH", "existing-path")

    env = benchmark_cli.build_source_env(source)

    assert env["PYTHONPATH"].split(os.pathsep) == [str(source.root / "src"), "existing-path"]


def test_source_root_comparison_rejects_in_process_api_runner(tmp_path: Path) -> None:
    """外部源码树不能被误标为当前进程中的 API runner。"""
    source = benchmark_cli.BenchmarkSource(root=tmp_path / "baseline", label="baseline")

    assert benchmark_cli._source_runner_error("cli", source, tmp_path) is None
    assert benchmark_cli._source_runner_error("api", source, tmp_path) is not None
    assert benchmark_cli._source_runner_error("both", source, tmp_path) is not None


def test_build_targeted_summary_uses_latest_v2_index_snapshot_and_marks_v1_unavailable(tmp_path: Path) -> None:
    """targeted 汇总应避免累计指标重复求和，并诚实处理 v1 artifact。"""
    version = "16.16"
    artifact_data = (
        (
            "maps",
            "0",
            {
                "candidateWads": 10,
                "cacheHits": 2,
                "cacheMisses": 1,
                "uniqueTocLoads": 1,
                "duplicatePhysicalWadLoads": 0,
                "tocSeconds": 0.1,
            },
        ),
        (
            "maps",
            "11",
            {
                "candidateWads": 10,
                "cacheHits": 8,
                "cacheMisses": 3,
                "uniqueTocLoads": 3,
                "duplicatePhysicalWadLoads": 0,
                "tocSeconds": 0.4,
            },
        ),
    )
    for entity_dir, entity_id, index in artifact_data:
        artifact = tmp_path / "manifest" / version / "banks" / entity_dir / f"{entity_id}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            json.dumps({"resourceSchemaVersion": 2, "diagnostics": {"index": index}}),
            encoding="utf-8",
        )

    rows = [
        {"scenario": "targeted_map", "step": "update", "status": "ok", "elapsed_sec": 1.0},
        {
            "scenario": "targeted_map",
            "step": "extract",
            "status": "ok",
            "elapsed_sec": 2.0,
            "wem_files_after": 5,
            "wem_bytes_after": 8192,
        },
    ]
    summary = benchmark_cli.build_targeted_summary(
        rows,
        runner="cli",
        scenario="targeted_map",
        output_root=tmp_path,
        source=benchmark_cli.BenchmarkSource(root=tmp_path, label="current"),
        game_version=version,
        map_ids=("11",),
        diagnostic_map_ids=("0", "11"),
    )

    assert summary["targets"] == {"champion_ids": [], "map_ids": ["11"]}
    assert summary["resource_index"] == {
        "status": "available",
        "aggregation": "max_cumulative_snapshot",
        "entities": [
            {
                "entity_type": "map",
                "entity_id": "0",
                "status": "available",
                "index": {
                    "candidateWads": 10,
                    "cacheHits": 2,
                    "cacheMisses": 1,
                    "uniqueTocLoads": 1,
                    "duplicatePhysicalWadLoads": 0,
                    "tocSeconds": 0.1,
                },
            },
            {
                "entity_type": "map",
                "entity_id": "11",
                "status": "available",
                "index": {
                    "candidateWads": 10,
                    "cacheHits": 8,
                    "cacheMisses": 3,
                    "uniqueTocLoads": 3,
                    "duplicatePhysicalWadLoads": 0,
                    "tocSeconds": 0.4,
                },
            },
        ],
        "unavailable_entities": [],
        "candidateWads": 10,
        "cacheHits": 8,
        "cacheMisses": 3,
        "uniqueTocLoads": 3,
        "duplicatePhysicalWadLoads": 0,
        "tocSeconds": 0.4,
    }

    v1_artifact = tmp_path / "manifest" / version / "banks" / "champions" / "1.json"
    v1_artifact.parent.mkdir(parents=True, exist_ok=True)
    v1_artifact.write_text(json.dumps({"banks": {"VO": []}}), encoding="utf-8")
    v1_summary = benchmark_cli.summarize_resource_index(
        tmp_path,
        version,
        champion_ids=("1",),
    )

    assert v1_summary["status"] == "unavailable"
    assert all(v1_summary[field] is None for field in benchmark_cli.RESOURCE_INDEX_FIELDS)
