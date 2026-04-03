"""lol_audio_unpack 的命令行入口。

该模块负责解析命令行参数、构建应用上下文，并分发数据更新、
音频解包和事件映射等流程。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from loguru import logger

from . import __version__, setup_app
from .app_context import AppContext, AppContextValidationError, OperationOptions, SourceMode, WavOutputOptions
from .cli_invocation import (
    DEFAULT_CLI_MAX_WORKERS,
    DEFAULT_WAV_FORMAT,
    DEFAULT_WAV_RETRIES,
    DEFAULT_WAV_TIMEOUT,
    DEFAULT_WAV_WORKERS,
    CliInvocationRequest,
    CliInvocationValidationError,
    validate_cli_invocation_request,
)
from .config_loading import (
    load_command_config_from_file,
    load_settings_from_config_file,
    resolve_default_config_file_path,
)
from .config_schema import BASE_CONTEXT_OPTION_ATTRS, ConfigSection, SettingKey, build_settings_from_namespace
from .facade import LolAudioUnpackApp
from .utils.run_summary import attach_run_summary_sink, emit_cli_run_summary, get_or_create_run_summary
from .wav_background_job import WavBackgroundProcessHandle


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
        default=DEFAULT_CLI_MAX_WORKERS,
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
        help="启用绝对独占的配置文件模式；仅允许同时提供动作列表和配置文件路径。仅写 -c 时读取默认 INI，写 -c PATH 时读取指定 INI。",
    )

    target_group = parser.add_argument_group("实体选择", "多个动作共享的目标范围选择")
    target_group.add_argument(
        "--champions",
        nargs="?",
        const="all",
        metavar="IDs|ALIASES",
        help="指定英雄范围；无参数时表示所有英雄。",
    )
    target_group.add_argument(
        "--maps",
        nargs="?",
        const="all",
        metavar="IDs",
        help="指定地图范围；无参数时表示所有地图。",
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help="生成整合数据文件（包含完整实体信息、banks 和 mapping 数据）。",
    )


def create_parser() -> argparse.ArgumentParser:
    """创建支持多动作的命令行参数解析器。"""
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
    parser.add_argument(
        "actions",
        nargs="*",
        metavar="ACTION",
        help="要执行的动作列表，支持顺序提供多个动作，如 `update extract`。",
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
        help="mapping 阶段是否生成整合数据文件；未显式指定时默认开启。",
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
    return parser


def _validate_config_mode_raw_argv(argv: list[str]) -> None:
    """校验 `-c` 模式下是否只保留动作和配置文件路径。

    Args:
        argv: 原始命令行参数列表，不包含程序名。
    """
    if (
        "-c" not in argv
        and "--config-file" not in argv
        and not any(token.startswith("--config-file=") for token in argv)
    ):
        return

    allowed_actions = {"update", "extract", "mapping"}
    config_flag_tokens = {"-c", "--config-file"}
    index = 0
    while index < len(argv):
        token = argv[index]

        if token in allowed_actions:
            index += 1
            continue

        if token in config_flag_tokens:
            index += 1
            if index < len(argv) and not argv[index].startswith("-"):
                index += 1
            continue

        if token.startswith("--config-file="):
            index += 1
            continue

        logger.error("错误：-c/--config-file 模式下除动作列表和配置文件路径外，不允许再手工传递其他参数。")
        sys.exit(1)


def _apply_config_profile_to_args(args: argparse.Namespace) -> None:
    """将配置文件中的命令参数注入 argparse 结果。"""
    config_file = _resolve_config_file_path(args)
    if config_file is None:
        return

    try:
        loaded_settings = load_settings_from_config_file(config_file, require_exists=True)
    except FileNotFoundError:
        logger.error(f"配置文件不存在: {config_file}")
        logger.error("请先创建标准 INI 配置文件，或移除 -c 改为纯 CLI 显式参数模式。")
        sys.exit(1)

    args._loaded_settings = loaded_settings
    section_sequence = [ConfigSection.TARGETS, ConfigSection.RUNTIME]
    for action in args.actions:
        section_sequence.append(action)
    if ConfigSection.EXTRACT in args.actions:
        section_sequence.append(ConfigSection.WAV)

    merged_options: dict[str, object] = {}
    for section_name in section_sequence:
        merged_options.update(load_command_config_from_file(config_file, command=section_name, require_exists=True))
    for attr_name, value in merged_options.items():
        setattr(args, attr_name, value)


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """验证动作式 CLI 参数的有效性。"""
    if not args.actions:
        logger.error("错误：必须提供至少一个动作：update / extract / mapping。")
        parser.print_help()
        sys.exit(1)

    invalid_actions = [action for action in args.actions if action not in {"update", "extract", "mapping"}]
    if invalid_actions:
        logger.error(f"错误：存在不支持的动作: {invalid_actions}")
        parser.print_help()
        sys.exit(1)

    args.actions = list(dict.fromkeys(args.actions))

    if args.config_file is not None and any(getattr(args, attr) is not None for attr in BASE_CONTEXT_OPTION_ATTRS):
        logger.error("错误：-c/--config-file 模式不能与共享配置参数同时使用。")
        sys.exit(1)

    try:
        validate_cli_invocation_request(
            build_cli_invocation_request(args),
            check_required_settings=False,
        )
    except CliInvocationValidationError as exc:
        logger.error(f"错误：{exc}")
        sys.exit(1)

    if args.integrate_data is True and "mapping" in args.actions:
        logger.info("检测到 --integrate-data 参数，将生成整合数据文件")


def build_context_settings(args: argparse.Namespace) -> dict[str, object]:
    """从命令行参数构建显式共享配置。"""
    return build_settings_from_namespace(args)


def build_cli_invocation_request(args: argparse.Namespace) -> CliInvocationRequest:
    """将 argparse 结果转换为共享的 invocation 请求。"""
    settings = dict(getattr(args, "_loaded_settings", {}) or build_context_settings(args))
    return CliInvocationRequest(
        actions=tuple(args.actions),
        settings=tuple(settings.items()),
        champions=args.champions,
        maps=args.maps,
        max_workers=args.max_workers,
        force=args.force,
        skip_events=args.skip_events,
        integrate_data=args.integrate_data,
        wav_enabled=bool(getattr(args, "wav", False)),
        wav_workers=DEFAULT_WAV_WORKERS if getattr(args, "wav_workers", None) is None else args.wav_workers,
        wav_timeout=DEFAULT_WAV_TIMEOUT if getattr(args, "wav_timeout", None) is None else args.wav_timeout,
        wav_retries=DEFAULT_WAV_RETRIES if getattr(args, "wav_retries", None) is None else args.wav_retries,
        wav_format=DEFAULT_WAV_FORMAT if getattr(args, "wav_format", None) is None else args.wav_format,
    )


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
        loaded_settings = getattr(args, "_loaded_settings", None)
        if loaded_settings is None:
            try:
                loaded_settings = load_settings_from_config_file(config_file, require_exists=True)
            except FileNotFoundError:
                logger.error(f"配置文件不存在: {config_file}")
                logger.error("请先创建标准 INI 配置文件，或移除 -c 改为纯 CLI 显式参数模式。")
                sys.exit(1)
        context_settings = dict(loaded_settings)

    try:
        validate_cli_invocation_request(build_cli_invocation_request(args))
    except CliInvocationValidationError as exc:
        logger.error(f"配置初始化失败: {exc}")
        if config_file is not None:
            logger.error(f"请检查当前命令使用的配置文件: {config_file}")
        else:
            logger.error("当前命令未启用 -c，请通过命令行显式传入缺失的共享配置。")
        sys.exit(1)

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
    integrate_data = False
    if "mapping" in getattr(args, "actions", []):
        integrate_data = True if args.integrate_data is None else args.integrate_data

    return OperationOptions(
        max_workers=args.max_workers,
        force_update=args.force,
        process_events=not args.skip_events,
        integrate_data=integrate_data,
        champion_ids=champion_ids,
        map_ids=map_ids,
        wav_output=WavOutputOptions(
            enabled=getattr(args, "wav", False),
            worker_count=DEFAULT_WAV_WORKERS if getattr(args, "wav_workers", None) is None else args.wav_workers,
            timeout_seconds=DEFAULT_WAV_TIMEOUT if getattr(args, "wav_timeout", None) is None else args.wav_timeout,
            max_retries=DEFAULT_WAV_RETRIES if getattr(args, "wav_retries", None) is None else args.wav_retries,
            format=DEFAULT_WAV_FORMAT if getattr(args, "wav_format", None) is None else args.wav_format,
        ),
    )


def _has_update_actions(args: argparse.Namespace) -> bool:
    """是否存在 update 操作。"""
    return "update" in getattr(args, "actions", [])


def _has_extract_actions(args: argparse.Namespace) -> bool:
    """是否存在 extract 操作。"""
    return "extract" in getattr(args, "actions", [])


def _has_mapping_actions(args: argparse.Namespace) -> bool:
    """是否存在 mapping 操作。"""
    return "mapping" in getattr(args, "actions", [])


def _resolve_cli_targets(
    args: argparse.Namespace,
    *,
    app: LolAudioUnpackApp,
) -> tuple[tuple[int, ...] | None, tuple[int, ...] | None]:
    """解析共享的 CLI 实体选择。"""
    champion_ids = resolve_cli_champion_ids(args.champions, app=app, force_update=args.force)
    map_ids = parse_int_ids(args.maps)
    return champion_ids, map_ids


def _resolve_target_scope(
    *,
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
) -> tuple[str, bool, bool]:
    """根据共享目标选择推导门面目标范围。"""
    if champion_ids is None and map_ids is None:
        return "all", True, True
    if champion_ids is not None and map_ids is not None:
        return "all", True, True
    if champion_ids is not None:
        return "skin", True, False
    return "map", False, True


def _build_target_detail(
    *,
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
    all_detail: str,
    champion_detail: str,
    map_detail: str,
) -> str:
    """根据共享目标范围构建日志详情。"""
    if champion_ids is None and map_ids is None:
        return all_detail
    if champion_ids is not None and map_ids is not None:
        return f"指定英雄和地图: champions={list(champion_ids)}, maps={list(map_ids)}"
    if champion_ids is not None:
        return f"{champion_detail}: {list(champion_ids)}"
    return f"{map_detail}: {list(map_ids) if map_ids is not None else []}"


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


def _build_wav_background_progress_signature(snapshot: dict[str, object]) -> tuple[object, ...]:
    """将后台 WAV 快照压缩为便于去重比较的签名。"""
    return (
        snapshot.get("status"),
        snapshot.get("phase"),
        snapshot.get("submitted_wav_job_count"),
        snapshot.get("running_wav_job_count"),
        snapshot.get("completed_wav_job_count"),
        snapshot.get("failed_wav_job_count"),
        snapshot.get("skipped_wav_job_count"),
        snapshot.get("detail"),
    )


def _format_wav_background_progress(snapshot: dict[str, object]) -> str:
    """将后台 WAV 快照格式化为 CLI 友好的进度文案。"""
    status = str(snapshot.get("status", "running"))
    if status != "running":
        detail = str(snapshot.get("detail", "")).strip()
        return detail or status
    return (
        f"phase={snapshot.get('phase', 'unknown')} · "
        f"已提交 {snapshot.get('submitted_wav_job_count', 0)} · "
        f"运行中 {snapshot.get('running_wav_job_count', 0)} · "
        f"完成 {snapshot.get('completed_wav_job_count', 0)} · "
        f"失败 {snapshot.get('failed_wav_job_count', 0)} · "
        f"跳过 {snapshot.get('skipped_wav_job_count', 0)}"
    )


def _poll_cli_wav_background_progress(
    handle: WavBackgroundProcessHandle | None,
    *,
    last_signature: tuple[object, ...] | None,
    force: bool = False,
) -> tuple[object, ...] | None:
    """按主线节奏主动轮询后台 WAV 进度。"""
    if handle is None:
        return last_signature
    snapshot = handle.read_progress_snapshot()
    if snapshot is None:
        return last_signature
    signature = _build_wav_background_progress_signature(snapshot)
    if not force and signature == last_signature:
        return last_signature

    message = _format_wav_background_progress(snapshot)
    if snapshot.get("status") == "completed":
        logger.success(f"WAV 后台进度[{handle.job_label}]：{message}")
    elif snapshot.get("status") == "failed":
        logger.warning(f"WAV 后台进度[{handle.job_label}]：{message}")
    else:
        logger.info(f"WAV 后台进度[{handle.job_label}]：{message}")
    return signature


def _log_cli_unhandled_error(error: Exception, *, dev_mode: bool) -> None:
    """统一记录 CLI 顶层未处理异常。

    Args:
        error: 未处理异常对象。
        dev_mode: 是否启用开发模式 traceback 输出。
    """
    logger.opt(depth=1, exception=dev_mode).error(f"执行过程中发生错误: {error}")


def execute_remote_entity_workflow(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """仅在 remote 模式下使用的单位驱动执行器。"""
    champion_ids, map_ids = _resolve_cli_targets(args, app=app)
    update_target, extract_include_champions, extract_include_maps = _resolve_target_scope(
        champion_ids=champion_ids,
        map_ids=map_ids,
    )

    update_options = None
    if _has_update_actions(args):
        update_options = build_operation_options(args, champion_ids=champion_ids, map_ids=map_ids)

    extract_options = None
    if _has_extract_actions(args):
        extract_options = build_operation_options(args, champion_ids=champion_ids, map_ids=map_ids)

    mapping_options = None
    if _has_mapping_actions(args):
        mapping_options = build_operation_options(args, champion_ids=champion_ids, map_ids=map_ids)

    app.run_remote_entity_workflow(
        update_options=update_options,
        update_target=update_target,
        extract_options=extract_options,
        mapping_options=mapping_options,
        extract_include_champions=extract_include_champions,
        extract_include_maps=extract_include_maps,
        mapping_include_champions=extract_include_champions,
        mapping_include_maps=extract_include_maps,
    )


def execute_update_operations(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行数据更新操作。"""
    if not _has_update_actions(args):
        return

    champion_ids, map_ids = _resolve_cli_targets(args, app=app)
    target, _, _ = _resolve_target_scope(champion_ids=champion_ids, map_ids=map_ids)

    if args.skip_events:
        logger.info("已启用快速模式：跳过事件数据处理")
    if args.force:
        logger.warning("已启用强制更新模式，将忽略现有文件的版本检查。")

    detail = _build_target_detail(
        champion_ids=champion_ids,
        map_ids=map_ids,
        all_detail="所有数据（英雄和地图）",
        champion_detail="指定英雄数据",
        map_detail="指定地图数据",
    )
    _log_cli_stage_start("数据更新", detail)
    app.update(build_operation_options(args, champion_ids=champion_ids, map_ids=map_ids), target=target)

    _log_cli_stage_complete("数据更新", detail)


def execute_extract_operations(args: argparse.Namespace, app: LolAudioUnpackApp) -> WavBackgroundProcessHandle | None:
    """执行音频解包操作。"""
    if not _has_extract_actions(args):
        return None

    try:
        champion_ids, map_ids = _resolve_cli_targets(args, app=app)
    except ValueError as e:
        logger.error(f"解包目标失败: {e}")
        return

    _, include_champions, include_maps = _resolve_target_scope(champion_ids=champion_ids, map_ids=map_ids)
    detail = _build_extract_stage_detail(
        _build_target_detail(
            champion_ids=champion_ids,
            map_ids=map_ids,
            all_detail="所有音频（英雄和地图）",
            champion_detail="指定英雄音频",
            map_detail="指定地图音频",
        ),
        wav_enabled=args.wav,
    )
    _log_cli_stage_start("音频解包", detail)
    wav_background_handle = app.extract(
        build_operation_options(args, champion_ids=champion_ids, map_ids=map_ids),
        include_champions=include_champions,
        include_maps=include_maps,
        detach_wav_sidecar=args.wav,
        wav_job_label=f"cli-{int(time.time() * 1000)}",
    )

    _log_cli_stage_complete("音频解包", detail)
    return wav_background_handle


def _log_mapping_runtime_error(error: ValueError) -> None:
    """记录 mapping 运行时错误，并在 wwiser 配置错误时补充指引。"""
    message = str(error)
    logger.error(f"构建事件映射失败: {message}")

    if "Wwiser 工具路径" not in message and SettingKey.WWISER_PATH not in message:
        return

    logger.error(
        "如果需要使用 WwiserHIRC 回退路径，请通过 --wwiser-path 显式传入，或在 -c 指定的 INI 中配置 wwiser_path。"
    )
    logger.error(
        "WWISER_PATH 应指向 wwiser.pyz 或 wwiser.exe 文件；如果不需要 wwiser，请移除该配置并直接使用默认 NativeHIRC。"
    )


def execute_mapping_operations(
    args: argparse.Namespace,
    app: LolAudioUnpackApp,
    *,
    wav_background_handle: WavBackgroundProcessHandle | None = None,
) -> None:
    """执行事件映射操作。"""
    if not _has_mapping_actions(args):
        return

    if build_operation_options(args).integrate_data:
        logger.info("启用整合数据功能，将生成包含完整实体信息的整合文件")

    try:
        champion_ids, map_ids = _resolve_cli_targets(args, app=app)
    except ValueError as e:
        logger.error(f"构建映射目标失败: {e}")
        return

    _, include_champions, include_maps = _resolve_target_scope(champion_ids=champion_ids, map_ids=map_ids)
    detail = _build_target_detail(
        champion_ids=champion_ids,
        map_ids=map_ids,
        all_detail="所有实体（英雄和地图）",
        champion_detail="指定英雄事件映射",
        map_detail="指定地图事件映射",
    )
    _log_cli_stage_start("事件映射", detail)
    mapping_options = build_operation_options(args, champion_ids=champion_ids, map_ids=map_ids)
    mapping_kwargs = {
        "include_champions": include_champions,
        "include_maps": include_maps,
    }
    last_wav_progress_signature: tuple[object, ...] | None = None

    def emit_mapping_progress(_entity_type: str, _current: int, _total: int, _message: str) -> None:
        nonlocal last_wav_progress_signature
        last_wav_progress_signature = _poll_cli_wav_background_progress(
            wav_background_handle,
            last_signature=last_wav_progress_signature,
        )

    try:
        if wav_background_handle is None:
            app.mapping(mapping_options, **mapping_kwargs)
        else:
            app.mapping(mapping_options, progress_callback=emit_mapping_progress, **mapping_kwargs)
    except ValueError as e:
        _log_mapping_runtime_error(e)
        sys.exit(1)

    _poll_cli_wav_background_progress(
        wav_background_handle,
        last_signature=last_wav_progress_signature,
        force=True,
    )
    _log_cli_stage_complete("事件映射", detail)


def main() -> None:
    """主程序入口，协调处理命令行参数和执行相应操作。"""
    app_context: AppContext | None = None
    run_summary = None
    summary_sink_id: int | None = None
    try:
        parser = create_parser()
        argv = sys.argv[1:]
        args = parser.parse_args(argv)
        _validate_config_mode_raw_argv(argv)
        _apply_config_profile_to_args(args)

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
        wav_background_handle = None
        if _has_extract_actions(args):
            with run_summary.stage_context("extract", label="音频解包"):
                wav_background_handle = execute_extract_operations(args, app)
        if _has_mapping_actions(args):
            with run_summary.stage_context("mapping", label="事件映射"):
                execute_mapping_operations(args, app, wav_background_handle=wav_background_handle)
        if wav_background_handle is not None:
            _poll_cli_wav_background_progress(
                wav_background_handle,
                last_signature=None,
                force=True,
            )
            if wav_background_handle.poll() is None:
                logger.info("WAV 后台作业仍在继续，CLI 主流程将先结束。")
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
