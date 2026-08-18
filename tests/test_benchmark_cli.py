"""验证本地基准脚本与当前 CLI 参数契约保持一致。"""

from pathlib import Path

from lol_audio_unpack.cli.parser import create_parser
from scripts import benchmark_cli


def test_benchmark_commands_follow_current_cli_contract(tmp_path: Path) -> None:
    """三类 benchmark 命令都应能被当前动作式 CLI 解析。"""
    context = benchmark_cli.BenchmarkContext(
        repo_root=tmp_path,
        runner="cli",
        uv_entry="python",
        timeout=30,
        workers=4,
        log_level="INFO",
        run_id="test",
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
        ),
    )

    parser = create_parser("unpack")
    for command, expected_actions, expected_champions in commands:
        args = parser.parse_args(command[3:])

        assert args.actions == expected_actions
        assert args.champions == expected_champions
        assert args.game_path == str(game_path)
        assert args.output_path == str(output_path)
