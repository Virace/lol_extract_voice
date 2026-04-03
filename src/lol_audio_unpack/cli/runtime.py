"""CLI 运行前准备逻辑。

该模块负责处理命令行参数校验、配置文件注入、运行上下文初始化，
以及在 dispatch 之前共享的目标解析与操作选项构造。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from .. import setup_app
from ..app_context import AppContext, AppContextValidationError, OperationOptions, SourceMode, WavOutputOptions
from ..config_loading import (
    load_command_config_from_file,
    load_settings_from_config_file,
    resolve_default_config_file_path,
)
from ..config_schema import BASE_CONTEXT_OPTION_ATTRS, ConfigSection, build_settings_from_namespace
from ..facade import LolAudioUnpackApp
from .invocation import (
    DEFAULT_WAV_FORMAT,
    DEFAULT_WAV_RETRIES,
    DEFAULT_WAV_TIMEOUT,
    DEFAULT_WAV_WORKERS,
    CliInvocationRequest,
    CliInvocationValidationError,
    validate_request,
)


def _validate_config_argv(argv: list[str]) -> None:
    """校验 `-c` 模式下的原始参数边界。

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


def _apply_config_profile(args: argparse.Namespace) -> None:
    """将配置文件中的命令段落注入解析结果。

    Args:
        args: `argparse` 解析后的命名空间对象。
    """
    config_file = _config_path(args)
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
    """验证动作式 CLI 参数的有效性。

    Args:
        args: `argparse` 解析后的命名空间对象。
        parser: 顶层参数解析器。
    """
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
        validate_request(
            build_invocation_request(args),
            check_required_settings=False,
        )
    except CliInvocationValidationError as exc:
        logger.error(f"错误：{exc}")
        sys.exit(1)

    if args.integrate_data is True and "mapping" in args.actions:
        logger.info("检测到 --integrate-data 参数，将生成整合数据文件")


def build_settings(args: argparse.Namespace) -> dict[str, object]:
    """从命令行参数构建显式共享配置。

    Args:
        args: `argparse` 解析后的命名空间对象。

    Returns:
        仅包含显式传入项的共享配置字典。
    """
    return build_settings_from_namespace(args)


def build_invocation_request(args: argparse.Namespace) -> CliInvocationRequest:
    """将解析结果转换为共享的 invocation 请求。

    Args:
        args: `argparse` 解析后的命名空间对象。

    Returns:
        供 CLI 显式命令构造与校验复用的结构化请求对象。
    """
    settings = dict(getattr(args, "_loaded_settings", {}) or build_settings(args))
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


def _config_path(args: argparse.Namespace) -> Path | None:
    """解析当前命令实际使用的配置文件路径。

    Args:
        args: `argparse` 解析后的命名空间对象。

    Returns:
        配置文件路径；未启用配置文件模式时返回 `None`。
    """
    if args.config_file is None:
        return None
    if args.config_file == "":
        return resolve_default_config_file_path(dev_mode=args.dev)
    return Path(args.config_file)


def initialize_app(args: argparse.Namespace) -> AppContext:
    """初始化应用运行上下文。

    Args:
        args: `argparse` 解析后的命名空间对象。

    Returns:
        完成配置校验后的应用上下文对象。
    """
    if not args.enable_league_tools_log:
        logger.disable("league_tools")

    context_settings = build_settings(args)
    config_file = _config_path(args)
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
        validate_request(build_invocation_request(args))
    except CliInvocationValidationError as exc:
        logger.error(f"配置初始化失败: {exc}")
        if config_file is not None:
            logger.error(f"请检查当前命令使用的配置文件: {config_file}")
        else:
            logger.error("当前命令未启用 -c，请通过命令行显式传入缺失的共享配置。")
        sys.exit(1)

    try:
        app_context = setup_app(dev_mode=args.dev, log_level=args.log_level.upper(), settings=context_settings)
    except AppContextValidationError as exc:
        logger.error(f"配置初始化失败: {exc}")
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
    """解析逗号分隔的 CLI 选择器。

    Args:
        id_string: 逗号分隔的 ID 或 alias 字符串。

    Returns:
        去除空白后的字符串列表；当输入为 `None` 或 `all` 时返回 `None`。
    """
    if id_string and id_string != "all":
        return [item.strip() for item in id_string.split(",") if item.strip()]
    return None


def parse_int_ids(id_string: str | None) -> tuple[int, ...] | None:
    """将逗号分隔的整数选择器转换为元组。

    Args:
        id_string: 原始 CLI 选择器。

    Returns:
        整数元组；当输入为 `None` 或 `all` 时返回 `None`。
    """
    raw_ids = parse_ids(id_string)
    if raw_ids is None:
        return None
    return tuple(int(item) for item in raw_ids)


def resolve_champion_ids(
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
        解析后的英雄 ID 元组；当输入为 `None` 或 `all` 时返回 `None`。

    Raises:
        ValueError: 当选择器格式非法、混用 ID 与 alias，或 alias 不存在时抛出。
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


def build_options(
    args: argparse.Namespace,
    champion_ids: tuple[int, ...] | None = None,
    map_ids: tuple[int, ...] | None = None,
) -> OperationOptions:
    """从 CLI 参数构建运行操作选项。

    Args:
        args: `argparse` 解析后的命名空间对象。
        champion_ids: 已解析的英雄 ID 集合。
        map_ids: 已解析的地图 ID 集合。

    Returns:
        供 facade 层消费的操作选项对象。
    """
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


__all__ = [
    "_apply_config_profile",
    "_config_path",
    "_validate_config_argv",
    "build_invocation_request",
    "build_settings",
    "build_options",
    "initialize_app",
    "parse_ids",
    "parse_int_ids",
    "resolve_champion_ids",
    "validate_args",
]
