"""lol_audio_unpack 的命令行入口。

该模块负责解析命令行参数、构建应用上下文，并分发数据更新、
音频解包和事件映射等流程。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from . import __version__, setup_app
from .app_context import AppContext, AppContextValidationError, OperationOptions, SourceMode, WavOutputOptions
from .config_loading import load_settings_from_config_file, resolve_default_config_file_path
from .facade import LolAudioUnpackApp
from .utils.run_summary import attach_run_summary_sink, emit_cli_run_summary, get_or_create_run_summary

BASE_CONTEXT_OPTION_ATTRS: tuple[str, ...] = (
    "source_mode",
    "game_path",
    "output_path",
    "game_region",
    "exclude_type",
    "wwiser_path",
    "group_by_type",
    "remote_live_region",
    "cleanup_remote",
    "remote_version",
    "remote_lcu_manifest_url",
    "remote_game_manifest_url",
)


def _create_shared_parser() -> argparse.ArgumentParser:
    """创建各个子命令共享的参数集合。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-l",
        "--log-level",
        type=str,
        default="INFO",
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        help="设置日志输出等级，默认为 INFO。",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="启用开发者模式，默认配置文件名切换为 dev 版本并保留临时文件。",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        metavar="N",
        help="批量运行时使用的最大线程数。默认为 4。",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="强制更新数据，忽略版本检查。",
    )
    parser.add_argument(
        "--skip-events",
        action="store_true",
        help="跳过事件数据处理，仅对 update 流程生效。",
    )
    parser.add_argument(
        "--with-bp-vo",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="是否附带大厅选用/禁用语音资源。",
    )
    parser.add_argument(
        "--enable-league-tools-log",
        action="store_true",
        help="启用 league_tools 模块日志。",
    )
    parser.add_argument(
        "-c",
        "--config-file",
        nargs="?",
        const="",
        metavar="PATH",
        help="启用配置文件模式；仅写 -c 时读取默认 INI，写 -c PATH 时读取指定 INI。",
    )

    config_group = parser.add_argument_group("共享配置", "纯 CLI 模式下显式提供的共享配置")
    config_group.add_argument(
        "--source-mode",
        choices=[SourceMode.LOCAL_PATH.value, SourceMode.REMOTE_SNAPSHOT.value],
        help="显式指定内容来源模式。",
    )
    config_group.add_argument("--game-path", type=str, metavar="PATH", help="显式指定游戏客户端根目录。")
    config_group.add_argument("--output-path", type=str, metavar="PATH", help="显式指定输出目录。")
    config_group.add_argument("--game-region", type=str, metavar="REGION", help="显式指定语言区域。")
    config_group.add_argument("--exclude-type", type=str, metavar="TYPES", help="显式指定排除的音频类型。")
    config_group.add_argument("--wwiser-path", type=str, metavar="PATH", help="显式指定 wwiser 路径。")
    config_group.add_argument(
        "--group-by-type",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="显式指定是否按音频类型分组输出。",
    )
    config_group.add_argument(
        "--remote-live-region",
        type=str,
        metavar="REGION",
        help="显式指定远端快照 live region。",
    )
    config_group.add_argument(
        "--cleanup-remote",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="显式指定 remote_snapshot 模式下是否在成功后清理产物。",
    )
    config_group.add_argument(
        "--remote-version",
        type=str,
        metavar="VERSION",
        help="显式指定远端快照版本。",
    )
    config_group.add_argument(
        "--remote-lcu-manifest-url",
        type=str,
        metavar="URL",
        help="显式指定远端 LCU manifest URL。",
    )
    config_group.add_argument(
        "--remote-game-manifest-url",
        type=str,
        metavar="URL",
        help="显式指定远端 GAME manifest URL。",
    )
    return parser


def _add_update_subcommand(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    """注册 update 子命令。"""
    parser = subparsers.add_parser("update", parents=[shared_parser], help="更新游戏数据")
    parser.set_defaults(command="update", update=True)
    parser.add_argument(
        "--champions",
        nargs="?",
        const="all",
        dest="update_champions",
        metavar="IDs|ALIASES",
        help="更新英雄数据；无参数时更新所有英雄。",
    )
    parser.add_argument(
        "--maps",
        nargs="?",
        const="all",
        dest="update_maps",
        metavar="IDs",
        help="更新地图数据；无参数时更新所有地图。",
    )


def _add_extract_subcommand(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    """注册 extract 子命令。"""
    parser = subparsers.add_parser("extract", parents=[shared_parser], help="解包音频资源")
    parser.set_defaults(command="extract", extract=True)
    parser.add_argument(
        "--champions",
        nargs="?",
        const="all",
        dest="extract_champions",
        metavar="IDs|ALIASES",
        help="解包英雄音频；无参数时解包所有英雄。",
    )
    parser.add_argument(
        "--maps",
        nargs="?",
        const="all",
        dest="extract_maps",
        metavar="IDs",
        help="解包地图音频；无参数时解包所有地图。",
    )
    parser.add_argument("--wav", action="store_true", help="在解包后并行派生 WAV 输出。")
    parser.add_argument("--wav-workers", type=int, default=None, metavar="N", help="设置 WAV 转码并发进程数。")
    parser.add_argument(
        "--wav-timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="设置单个 WAV 转码任务的超时时间（秒）。",
    )
    parser.add_argument(
        "--wav-retries",
        type=int,
        default=None,
        metavar="N",
        help="设置单个 WAV 转码任务的最大重试次数。",
    )
    parser.add_argument(
        "--wav-format",
        choices=("auto", "pcm16", "pcm24", "pcm32", "float"),
        default=None,
        help="设置 WAV 输出格式。",
    )


def _add_mapping_subcommand(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    """注册 mapping 子命令。"""
    parser = subparsers.add_parser("mapping", parents=[shared_parser], help="构建事件映射")
    parser.set_defaults(command="mapping", mapping=True)
    parser.add_argument(
        "--champions",
        nargs="?",
        const="all",
        dest="mapping_champions",
        metavar="IDs|ALIASES",
        help="构建英雄事件映射；无参数时构建所有英雄。",
    )
    parser.add_argument(
        "--maps",
        nargs="?",
        const="all",
        dest="mapping_maps",
        metavar="IDs",
        help="构建地图事件映射；无参数时构建所有地图。",
    )
    parser.add_argument(
        "--integrate-data",
        action="store_true",
        help="生成整合数据文件（包含完整实体信息、banks 和 mapping 数据）。",
    )


def create_parser() -> argparse.ArgumentParser:
    """创建动作式命令行参数解析器。"""
    shared_parser = _create_shared_parser()
    parser = argparse.ArgumentParser(
        description="一个极简、高效的英雄联盟音频提取工具 (v3)",
        formatter_class=argparse.RawTextHelpFormatter,
        parents=[shared_parser],
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="显示当前脚本的版本号。",
    )
    parser.set_defaults(
        command=None,
        update=False,
        extract=False,
        mapping=False,
        update_champions=None,
        update_maps=None,
        extract_champions=None,
        extract_maps=None,
        mapping_champions=None,
        mapping_maps=None,
        integrate_data=False,
        wav=False,
        wav_workers=None,
        wav_timeout=None,
        wav_retries=None,
        wav_format=None,
    )

    subparsers = parser.add_subparsers(dest="command", metavar="ACTION")
    _add_update_subcommand(subparsers, shared_parser)
    _add_extract_subcommand(subparsers, shared_parser)
    _add_mapping_subcommand(subparsers, shared_parser)
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """验证动作式 CLI 参数的有效性。"""
    if args.command is None:
        logger.error("错误：必须提供一个动作子命令：update / extract / mapping。")
        parser.print_help()
        sys.exit(1)

    if args.config_file is not None and any(getattr(args, attr) is not None for attr in BASE_CONTEXT_OPTION_ATTRS):
        logger.error("错误：-c/--config-file 模式不能与共享配置参数同时使用。")
        sys.exit(1)

    wav_tuning_explicit = any(
        value is not None for value in (args.wav_workers, args.wav_timeout, args.wav_retries, args.wav_format)
    )
    if getattr(args, "wav", False) and args.command != "extract":
        logger.error("错误：--wav 只能与 extract 子命令一起使用。")
        sys.exit(1)

    if wav_tuning_explicit and not getattr(args, "wav", False):
        logger.error("错误：--wav-workers / --wav-timeout / --wav-retries / --wav-format 只能与 --wav 一起使用。")
        sys.exit(1)

    if getattr(args, "integrate_data", False) and args.command != "mapping":
        logger.error("错误：--integrate-data 只能与 mapping 子命令一起使用。")
        sys.exit(1)
    if getattr(args, "integrate_data", False):
        logger.info("检测到 --integrate-data 参数，将生成整合数据文件")


def build_context_settings(args: argparse.Namespace) -> dict[str, object]:
    """从命令行参数构建显式共享配置。"""
    mapping = {
        "SOURCE_MODE": args.source_mode,
        "GAME_PATH": args.game_path,
        "OUTPUT_PATH": args.output_path,
        "GAME_REGION": args.game_region,
        "EXCLUDE_TYPE": args.exclude_type,
        "WWISER_PATH": args.wwiser_path,
        "GROUP_BY_TYPE": args.group_by_type,
        "REMOTE_LIVE_REGION": args.remote_live_region,
        "CLEANUP_REMOTE": args.cleanup_remote,
        "REMOTE_VERSION": args.remote_version,
        "REMOTE_LCU_MANIFEST_URL": args.remote_lcu_manifest_url,
        "REMOTE_GAME_MANIFEST_URL": args.remote_game_manifest_url,
        "WITH_BP_VO": args.with_bp_vo,
    }
    return {key: value for key, value in mapping.items() if value is not None}


def _resolve_config_file_path(args: argparse.Namespace) -> Path | None:
    """解析当前命令使用的配置文件路径。"""
    if args.config_file is None:
        return None
    if args.config_file == "":
        return resolve_default_config_file_path(dev_mode=args.dev)
    return Path(args.config_file)


def initialize_app(args: argparse.Namespace) -> AppContext:
    """初始化应用程序（日志、配置等）并返回运行上下文。"""
    if not args.enable_league_tools_log:
        logger.disable("league_tools")

    context_settings = build_context_settings(args)
    config_file = _resolve_config_file_path(args)
    if config_file is not None:
        try:
            file_settings = load_settings_from_config_file(config_file, require_exists=True)
        except FileNotFoundError:
            logger.error(f"配置文件不存在: {config_file}")
            logger.error("请先创建标准 INI 配置文件，或移除 -c 改为纯 CLI 显式参数模式。")
            sys.exit(1)
        context_settings = {**file_settings, **context_settings}

    try:
        app_context = setup_app(dev_mode=args.dev, log_level=args.log_level.upper(), settings=context_settings)
    except AppContextValidationError as e:
        logger.error(f"配置初始化失败: {e}")
        if config_file is not None:
            logger.error(f"请检查当前命令使用的配置文件: {config_file}")
        else:
            logger.error("当前命令未启用 -c，请通过命令行显式传入缺失的共享配置。")
        sys.exit(1)

    logger.info("命令行工具启动...")

    if app_context.config.source_mode is SourceMode.LOCAL_PATH and not Path(app_context.config.game_path).exists():
        logger.error("错误：未找到有效的游戏目录 (GAME_PATH)。")
        if config_file is not None:
            logger.error(f"请检查配置文件中的 game_path: {config_file}")
        else:
            logger.error("请通过 --game-path 显式指定游戏目录，或使用 -c 读取配置文件。")
        sys.exit(1)

    return app_context


def parse_ids(id_string: str | None) -> list[str] | None:
    """解析逗号分隔的ID字符串为列表

    :param id_string: 逗号分隔的ID字符串或None
    :returns: ID字符串列表，如果输入为"all"或None则返回None
    """
    if id_string and id_string != "all":
        return [id.strip() for id in id_string.split(",") if id.strip()]
    return None


def parse_int_ids(id_string: str | None) -> tuple[int, ...] | None:
    """解析并转换 ID 列表为整数元组。"""
    raw_ids = parse_ids(id_string)
    if raw_ids is None:
        return None
    return tuple(int(item) for item in raw_ids)


def resolve_cli_champion_ids(
    id_string: str | None,
    *,
    app: LolAudioUnpackApp,
    force_update: bool = False,
) -> tuple[int, ...] | None:
    """解析 CLI 英雄选择器，支持纯 ID 或纯 alias。

    Args:
        id_string: 命令行传入的英雄选择器字符串。
        app: 应用门面实例。
        force_update: 是否强制刷新结构化数据。

    Returns:
        解析后的英雄 ID 元组；当输入为 ``None`` 或 ``all`` 时返回 ``None``。

    Raises:
        ValueError: 当选择器格式非法、混用 ID/alias 或 alias 不存在时抛出。
    """
    raw_ids = parse_ids(id_string)
    if raw_ids is None:
        return None

    has_numeric_selector = any(item.isdigit() for item in raw_ids)
    has_alias_selector = any(not item.isdigit() for item in raw_ids)
    if has_numeric_selector and has_alias_selector:
        raise ValueError("CLI 暂不支持在同一次英雄选择中混用 ID 与 alias。")
    if has_numeric_selector:
        return tuple(int(item) for item in raw_ids)

    app.prepare_update_data(force_update=force_update)
    return app.resolve_champion_ids(raw_ids)


def build_operation_options(
    args: argparse.Namespace,
    champion_ids: tuple[int, ...] | None = None,
    map_ids: tuple[int, ...] | None = None,
) -> OperationOptions:
    """从命令行参数构建操作选项对象。"""
    return OperationOptions(
        max_workers=args.max_workers,
        force_update=args.force,
        process_events=not args.skip_events,
        integrate_data=getattr(args, "integrate_data", False),
        champion_ids=champion_ids,
        map_ids=map_ids,
        wav_output=WavOutputOptions(
            enabled=getattr(args, "wav", False),
            worker_count=2 if getattr(args, "wav_workers", None) is None else args.wav_workers,
            timeout_seconds=5 if getattr(args, "wav_timeout", None) is None else args.wav_timeout,
            max_retries=3 if getattr(args, "wav_retries", None) is None else args.wav_retries,
            format="pcm16" if getattr(args, "wav_format", None) is None else args.wav_format,
        ),
    )


def _has_update_actions(args: argparse.Namespace) -> bool:
    """是否存在 update 操作。"""
    return any([args.update, args.update_champions, args.update_maps])


def _has_extract_actions(args: argparse.Namespace) -> bool:
    """是否存在 extract 操作。"""
    return any([args.extract, args.extract_champions, args.extract_maps])


def _has_mapping_actions(args: argparse.Namespace) -> bool:
    """是否存在 mapping 操作。"""
    return any([args.mapping, args.mapping_champions, args.mapping_maps])


def _build_extract_stage_detail(base_detail: str, *, wav_enabled: bool) -> str:
    """构建音频解包阶段摘要。

    Args:
        base_detail: 原始解包范围描述。
        wav_enabled: 是否启用 WAV sidecar。

    Returns:
        拼接后的阶段摘要文本。
    """
    if not wav_enabled:
        return base_detail
    return f"{base_detail} + WAV sidecar"


def _log_cli_stage_start(stage_label: str, detail: str | None = None) -> None:
    """输出 CLI 阶段开始日志，并保持调用方归属。

    Args:
        stage_label: 阶段名称。
        detail: 阶段详情摘要。
    """
    message = f"{stage_label}阶段开始"
    if detail:
        message = f"{message}: {detail}"
    logger.opt(depth=1).info(message)


def _log_cli_stage_complete(stage_label: str, detail: str | None = None) -> None:
    """输出 CLI 阶段完成日志，并保持调用方归属。

    Args:
        stage_label: 阶段名称。
        detail: 阶段详情摘要。
    """
    message = f"{stage_label}阶段完成"
    if detail:
        message = f"{message}: {detail}"
    logger.opt(depth=1).success(message)


def _log_cli_unhandled_error(error: Exception, *, dev_mode: bool) -> None:
    """统一记录 CLI 顶层未处理异常。

    Args:
        error: 未处理异常对象。
        dev_mode: 是否启用开发模式 traceback 输出。
    """
    logger.opt(depth=1, exception=dev_mode).error(f"执行过程中发生错误: {error}")


def execute_remote_entity_workflow(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """仅在 remote 模式下使用的单位驱动执行器。"""
    update_options = None
    update_target = "all"
    if args.update:
        update_options = build_operation_options(args)
    elif args.update_champions:
        champion_ids = resolve_cli_champion_ids(args.update_champions, app=app, force_update=args.force)
        update_options = build_operation_options(args, champion_ids=champion_ids)
        update_target = "skin"
    elif args.update_maps:
        map_ids = parse_int_ids(args.update_maps)
        update_options = build_operation_options(args, map_ids=map_ids)
        update_target = "map"

    extract_options = None
    extract_include_champions = False
    extract_include_maps = False
    if args.extract:
        extract_options = build_operation_options(args)
        extract_include_champions = True
        extract_include_maps = True
    elif args.extract_champions:
        extract_options = build_operation_options(
            args,
            champion_ids=resolve_cli_champion_ids(args.extract_champions, app=app, force_update=args.force),
        )
        extract_include_champions = True
    elif args.extract_maps:
        extract_options = build_operation_options(args, map_ids=parse_int_ids(args.extract_maps))
        extract_include_maps = True

    mapping_options = None
    mapping_include_champions = False
    mapping_include_maps = False
    if args.mapping:
        mapping_options = build_operation_options(args)
        mapping_include_champions = True
        mapping_include_maps = True
    elif args.mapping_champions:
        mapping_options = build_operation_options(
            args,
            champion_ids=resolve_cli_champion_ids(args.mapping_champions, app=app, force_update=args.force),
        )
        mapping_include_champions = True
    elif args.mapping_maps:
        mapping_options = build_operation_options(args, map_ids=parse_int_ids(args.mapping_maps))
        mapping_include_maps = True

    app.run_remote_entity_workflow(
        update_options=update_options,
        update_target=update_target,
        extract_options=extract_options,
        mapping_options=mapping_options,
        extract_include_champions=extract_include_champions,
        extract_include_maps=extract_include_maps,
        mapping_include_champions=mapping_include_champions,
        mapping_include_maps=mapping_include_maps,
    )


def execute_update_operations(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行数据更新操作。"""
    update_actions = [args.update, args.update_champions, args.update_maps]
    if not any(update_actions):
        return

    if args.skip_events:
        logger.info("已启用快速模式：跳过事件数据处理")
    if args.force:
        logger.warning("已启用强制更新模式，将忽略现有文件的版本检查。")

    if args.update:
        detail = "所有数据（英雄和地图）"
        _log_cli_stage_start("数据更新", detail)
        app.update(build_operation_options(args), target="all")
    elif args.update_champions:
        champion_ids = resolve_cli_champion_ids(args.update_champions, app=app, force_update=args.force)
        if champion_ids:
            detail = f"指定英雄数据: {list(champion_ids)}"
        else:
            detail = "所有英雄数据"
        _log_cli_stage_start("数据更新", detail)
        app.update(build_operation_options(args, champion_ids=champion_ids), target="skin")
    elif args.update_maps:
        map_ids = parse_int_ids(args.update_maps)
        if map_ids:
            detail = f"指定地图数据: {list(map_ids)}"
        else:
            detail = "所有地图数据"
        _log_cli_stage_start("数据更新", detail)
        app.update(build_operation_options(args, map_ids=map_ids), target="map")

    _log_cli_stage_complete("数据更新", detail)


def execute_extract_operations(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行音频解包操作。"""
    extract_actions = [args.extract, args.extract_champions, args.extract_maps]
    if not any(extract_actions):
        return

    if args.extract:
        detail = _build_extract_stage_detail("所有音频（英雄和地图）", wav_enabled=args.wav)
        _log_cli_stage_start("音频解包", detail)
        app.extract(build_operation_options(args))
    elif args.extract_champions:
        try:
            champion_ids = resolve_cli_champion_ids(args.extract_champions, app=app, force_update=args.force)
        except ValueError as e:
            logger.error(f"解包英雄失败: {e}")
            return

        if champion_ids:
            detail = _build_extract_stage_detail(f"指定英雄音频: {list(champion_ids)}", wav_enabled=args.wav)
            _log_cli_stage_start("音频解包", detail)
            app.extract(
                build_operation_options(args, champion_ids=champion_ids),
                include_maps=False,
            )
        else:
            detail = _build_extract_stage_detail("所有英雄音频", wav_enabled=args.wav)
            _log_cli_stage_start("音频解包", detail)
            app.extract(build_operation_options(args), include_maps=False)
    elif args.extract_maps:
        try:
            map_ids = parse_int_ids(args.extract_maps)
        except ValueError as e:
            logger.error(f"解包地图失败: {e}")
            return

        if map_ids:
            detail = _build_extract_stage_detail(f"指定地图音频: {list(map_ids)}", wav_enabled=args.wav)
            _log_cli_stage_start("音频解包", detail)
            app.extract(
                build_operation_options(args, map_ids=map_ids),
                include_champions=False,
            )
        else:
            detail = _build_extract_stage_detail("所有地图音频", wav_enabled=args.wav)
            _log_cli_stage_start("音频解包", detail)
            app.extract(build_operation_options(args), include_champions=False)

    _log_cli_stage_complete("音频解包", detail)


def _log_mapping_runtime_error(error: ValueError) -> None:
    """记录 mapping 运行时错误，并在 wwiser 配置错误时补充指引。"""
    message = str(error)
    logger.error(f"构建事件映射失败: {message}")

    if "Wwiser 工具路径" not in message and "WWISER_PATH" not in message:
        return

    logger.error("如果需要使用 WwiserHIRC 回退路径，请通过 --wwiser-path 显式传入，或在 -c 指定的 INI 中配置 wwiser_path。")
    logger.error(
        "WWISER_PATH 应指向 wwiser.pyz 或 wwiser.exe 文件；如果不需要 wwiser，请移除该配置并直接使用默认 NativeHIRC。"
    )


def execute_mapping_operations(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行事件映射操作。"""
    mapping_actions = [args.mapping, args.mapping_champions, args.mapping_maps]
    if not any(mapping_actions):
        return

    if getattr(args, "integrate_data", False):
        logger.info("启用整合数据功能，将生成包含完整实体信息的整合文件")

    if args.mapping:
        detail = "所有实体（英雄和地图）"
        _log_cli_stage_start("事件映射", detail)
        mapping_options = build_operation_options(args)
        mapping_kwargs = {}
    elif args.mapping_champions:
        try:
            champion_ids = resolve_cli_champion_ids(args.mapping_champions, app=app, force_update=args.force)
        except ValueError as e:
            logger.error(f"构建英雄映射失败: {e}")
            return

        if champion_ids:
            detail = f"指定英雄事件映射: {list(champion_ids)}"
            mapping_options = build_operation_options(args, champion_ids=champion_ids)
        else:
            detail = "所有英雄事件映射"
            mapping_options = build_operation_options(args)
        _log_cli_stage_start("事件映射", detail)
        mapping_kwargs = {"include_maps": False}
    elif args.mapping_maps:
        try:
            map_ids = parse_int_ids(args.mapping_maps)
        except ValueError as e:
            logger.error(f"构建地图映射失败: {e}")
            return

        if map_ids:
            detail = f"指定地图事件映射: {list(map_ids)}"
            mapping_options = build_operation_options(args, map_ids=map_ids)
        else:
            detail = "所有地图事件映射"
            mapping_options = build_operation_options(args)
        _log_cli_stage_start("事件映射", detail)
        mapping_kwargs = {"include_champions": False}
    else:
        return

    try:
        app.mapping(mapping_options, **mapping_kwargs)
    except ValueError as e:
        _log_mapping_runtime_error(e)
        sys.exit(1)

    _log_cli_stage_complete("事件映射", detail)


def main() -> None:
    """主程序入口，协调处理命令行参数和执行相应操作。"""
    app_context: AppContext | None = None
    run_summary = None
    summary_sink_id: int | None = None
    try:
        parser = create_parser()
        args = parser.parse_args()

        validate_args(args, parser)

        app_context = initialize_app(args)
        app = LolAudioUnpackApp(app_context)
        run_summary = get_or_create_run_summary(app_context.runtime_cache)
        summary_sink_id = attach_run_summary_sink(run_summary)

        if app_context.config.source_mode is SourceMode.REMOTE_SNAPSHOT and (
            _has_extract_actions(args) or _has_mapping_actions(args)
        ):
            with run_summary.stage_context("remote_workflow", label="远端实体工作流"):
                execute_remote_entity_workflow(args, app)
            return

        if _has_update_actions(args):
            with run_summary.stage_context("update", label="数据更新"):
                execute_update_operations(args, app)
        if _has_extract_actions(args):
            with run_summary.stage_context("extract", label="音频解包"):
                execute_extract_operations(args, app)
        if _has_mapping_actions(args):
            with run_summary.stage_context("mapping", label="事件映射"):
                execute_mapping_operations(args, app)
        app.cleanup_remote_artifacts()

    except KeyboardInterrupt:
        logger.warning("用户中断操作")
        sys.exit(1)
    except Exception as e:
        _log_cli_unhandled_error(e, dev_mode=bool(getattr(locals().get("args"), "dev", False)))
        sys.exit(1)
    finally:
        if summary_sink_id is not None:
            logger.remove(summary_sink_id)
        if app_context is not None and run_summary is not None:
            emit_cli_run_summary(run_summary, log_path=app_context.paths.log_path)


if __name__ == "__main__":
    main()
