"""CLI 参数解析器模块。

该模块集中维护命令行解析器的构建逻辑，并从文本目录读取帮助文案，
为后续 runtime 逻辑拆分提供稳定边界。
"""

from __future__ import annotations

import argparse
from typing import Literal

from .. import __version__
from ..app_context import SourceMode
from .invocation import DEFAULT_CLI_MAX_WORKERS
from .text import text

EntryMode = Literal["unpack", "mapping"]


def _create_shared_parser() -> argparse.ArgumentParser:
    """创建各个子命令共享的参数集合。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-l",
        "--log-level",
        type=str,
        default="INFO",
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        help=text("help.log_level"),
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help=text("help.dev"),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_CLI_MAX_WORKERS,
        metavar="N",
        help=text("help.max_workers"),
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help=text("help.force"),
    )
    parser.add_argument(
        "--skip-events",
        action="store_true",
        help=text("help.skip_events"),
    )
    parser.add_argument(
        "--with-bp-vo",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=text("help.with_bp_vo"),
    )
    parser.add_argument(
        "--enable-league-tools-log",
        action="store_true",
        help=text("help.enable_league_tools_log"),
    )
    parser.add_argument(
        "-c",
        "--config-file",
        nargs="?",
        const="",
        metavar="PATH",
        help=text("help.config_file"),
    )

    target_group = parser.add_argument_group(text("group.target.title"), text("group.target.description"))
    target_group.add_argument(
        "--champions",
        nargs="?",
        const="all",
        metavar="IDs|ALIASES",
        help=text("help.shared.champions"),
    )
    target_group.add_argument(
        "--maps",
        nargs="?",
        const="all",
        metavar="IDs",
        help=text("help.shared.maps"),
    )

    config_group = parser.add_argument_group(text("group.config.title"), text("group.config.description"))
    config_group.add_argument(
        "--source-mode",
        choices=[SourceMode.LOCAL_PATH.value, SourceMode.REMOTE_SNAPSHOT.value],
        help=text("help.source_mode"),
    )
    config_group.add_argument("--game-path", type=str, metavar="PATH", help=text("help.game_path"))
    config_group.add_argument("--output-path", type=str, metavar="PATH", help=text("help.output_path"))
    config_group.add_argument("--game-region", type=str, metavar="REGION", help=text("help.game_region"))
    config_group.add_argument("--exclude-type", type=str, metavar="TYPES", help=text("help.exclude_type"))
    config_group.add_argument("--wwiser-path", type=str, metavar="PATH", help=text("help.wwiser_path"))
    config_group.add_argument(
        "--group-by-type",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=text("help.group_by_type"),
    )
    config_group.add_argument(
        "--remote-live-region",
        type=str,
        metavar="REGION",
        help=text("help.remote_live_region"),
    )
    config_group.add_argument(
        "--cleanup-remote",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=text("help.cleanup_remote"),
    )
    config_group.add_argument(
        "--remote-version",
        type=str,
        metavar="VERSION",
        help=text("help.remote_version"),
    )
    config_group.add_argument(
        "--remote-lcu-manifest-url",
        type=str,
        metavar="URL",
        help=text("help.remote_lcu_manifest_url"),
    )
    config_group.add_argument(
        "--remote-game-manifest-url",
        type=str,
        metavar="URL",
        help=text("help.remote_game_manifest_url"),
    )
    return parser


def _add_update_subcommand(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    """注册 update 子命令。"""
    parser = subparsers.add_parser("update", parents=[shared_parser], help=text("action.update"))
    parser.set_defaults(command="update", update=True)
    parser.add_argument(
        "--champions",
        nargs="?",
        const="all",
        dest="update_champions",
        metavar="IDs|ALIASES",
        help=text("help.update.champions"),
    )
    parser.add_argument(
        "--maps",
        nargs="?",
        const="all",
        dest="update_maps",
        metavar="IDs",
        help=text("help.update.maps"),
    )


def _add_extract_subcommand(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    """注册 extract 子命令。"""
    parser = subparsers.add_parser("extract", parents=[shared_parser], help=text("action.extract"))
    parser.set_defaults(command="extract", extract=True)
    parser.add_argument(
        "--champions",
        nargs="?",
        const="all",
        dest="extract_champions",
        metavar="IDs|ALIASES",
        help=text("help.extract.champions"),
    )
    parser.add_argument(
        "--maps",
        nargs="?",
        const="all",
        dest="extract_maps",
        metavar="IDs",
        help=text("help.extract.maps"),
    )
    parser.add_argument("--wav", action="store_true", help=text("help.wav"))
    parser.add_argument("--wav-workers", type=int, default=None, metavar="N", help=text("help.wav_workers"))
    parser.add_argument(
        "--wav-timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help=text("help.wav_timeout"),
    )
    parser.add_argument(
        "--wav-retries",
        type=int,
        default=None,
        metavar="N",
        help=text("help.wav_retries"),
    )
    parser.add_argument(
        "--wav-format",
        choices=("auto", "pcm16", "pcm24", "pcm32", "float"),
        default=None,
        help=text("help.wav_format"),
    )


def _add_mapping_subcommand(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    """注册 mapping 子命令。"""
    parser = subparsers.add_parser("mapping", parents=[shared_parser], help=text("action.mapping"))
    parser.set_defaults(command="mapping", mapping=True)
    parser.add_argument(
        "--champions",
        nargs="?",
        const="all",
        dest="mapping_champions",
        metavar="IDs|ALIASES",
        help=text("help.mapping.champions"),
    )
    parser.add_argument(
        "--maps",
        nargs="?",
        const="all",
        dest="mapping_maps",
        metavar="IDs",
        help=text("help.mapping.maps"),
    )
    parser.add_argument(
        "--integrate-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=text("help.mapping.integrate_data"),
    )


def create_parser(mode: EntryMode = "unpack") -> argparse.ArgumentParser:
    """创建支持多动作的命令行参数解析器。

    Args:
        mode: 当前入口脚本模式。

    Returns:
        配置完成的顶层 CLI 解析器。
    """
    shared_parser = _create_shared_parser()
    parser = argparse.ArgumentParser(
        prog="mapping" if mode == "mapping" else "unpack",
        description=text("parser.mapping.description") if mode == "mapping" else text("parser.unpack.description"),
        formatter_class=argparse.RawTextHelpFormatter,
        parents=[shared_parser],
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help=text("help.version"),
    )
    parser.add_argument(
        "actions",
        nargs="*",
        metavar="ACTION",
        help=text("help.actions"),
    )
    parser.set_defaults(
        actions=[],
        champions=None,
        maps=None,
        integrate_data=None,
        wav=False,
        wav_workers=None,
        wav_timeout=None,
        wav_retries=None,
        wav_format=None,
    )
    parser.add_argument(
        "--integrate-data",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=text("help.mapping.integrate_data_global"),
    )
    parser.add_argument("--wav", action="store_true", help=text("help.wav"))
    parser.add_argument("--wav-workers", type=int, default=None, metavar="N", help=text("help.wav_workers"))
    parser.add_argument(
        "--wav-timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help=text("help.wav_timeout"),
    )
    parser.add_argument(
        "--wav-retries",
        type=int,
        default=None,
        metavar="N",
        help=text("help.wav_retries"),
    )
    parser.add_argument(
        "--wav-format",
        choices=("auto", "pcm16", "pcm24", "pcm32", "float"),
        default=None,
        help=text("help.wav_format"),
    )
    return parser


__all__ = [
    "_add_extract_subcommand",
    "_add_mapping_subcommand",
    "_add_update_subcommand",
    "_create_shared_parser",
    "EntryMode",
    "create_parser",
]
