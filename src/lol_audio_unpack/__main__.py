# 🐍 Unless explicitly silenced.
# 🐼 除非它明确需要如此
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/26 0:34
# @Update  : 2026/3/5 21:48
# @Detail  : 项目命令行入口

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from loguru import logger

from . import __version__, setup_app
from .app_context import AppContext, AppContextValidationError, OperationOptions, SourceMode
from .facade import LolAudioUnpackApp


def create_parser() -> argparse.ArgumentParser:
    """创建和配置命令行参数解析器

    :returns: 配置好的 ArgumentParser 实例
    """
    parser = argparse.ArgumentParser(
        description="一个极简、高效的英雄联盟音频提取工具 (v3)\n支持英雄和地图音频的更新、解包与事件映射",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # 版本信息
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="显示当前脚本的版本号。",
    )

    # 数据更新参数组
    update_group = parser.add_argument_group("数据更新", "更新游戏数据和配置文件")
    update_group.add_argument(
        "--update",
        action="store_true",
        help="更新所有数据（英雄和地图）",
    )
    update_group.add_argument(
        "--update-champions",
        nargs="?",
        const="all",
        metavar="IDs",
        help="更新英雄数据。无参数时更新所有英雄，有参数时更新指定ID（逗号分隔）。例如: --update-champions 103,222,1",
    )
    update_group.add_argument(
        "--update-maps",
        nargs="?",
        const="all",
        metavar="IDs",
        help="更新地图数据。无参数时更新所有地图，有参数时更新指定ID（逗号分隔）。例如: --update-maps 11,12",
    )

    # 音频解包参数组
    extract_group = parser.add_argument_group("音频解包", "解包游戏音频文件")
    extract_group.add_argument(
        "--extract",
        action="store_true",
        help="解包所有音频（英雄和地图）",
    )
    extract_group.add_argument(
        "--extract-champions",
        nargs="?",
        const="all",
        metavar="IDs",
        help="解包英雄音频。无参数时解包所有英雄，有参数时解包指定ID（逗号分隔）。例如: --extract-champions 103,222,1",
    )
    extract_group.add_argument(
        "--extract-maps",
        nargs="?",
        const="all",
        metavar="IDs",
        help="解包地图音频。无参数时解包所有地图，有参数时解包指定ID（逗号分隔）。例如: --extract-maps 11,12",
    )

    # 事件映射参数组
    mapping_group = parser.add_argument_group("事件映射", "构建音频事件哈希映射")
    mapping_group.add_argument(
        "--mapping",
        action="store_true",
        help="构建所有实体的事件映射（英雄和地图）",
    )
    mapping_group.add_argument(
        "--mapping-champions",
        nargs="?",
        const="all",
        metavar="IDs",
        help="构建英雄事件映射。无参数时构建所有英雄，有参数时构建指定ID（逗号分隔）。例如: --mapping-champions 103,222,1",
    )
    mapping_group.add_argument(
        "--mapping-maps",
        nargs="?",
        const="all",
        metavar="IDs",
        help="构建地图事件映射。无参数时构建所有地图，有参数时构建指定ID（逗号分隔）。例如: --mapping-maps 11,12",
    )
    mapping_group.add_argument(
        "--integrate-data",
        action="store_true",
        help="生成整合数据文件（包含完整实体信息、banks和mapping数据），需要与映射参数一起使用",
    )

    # 通用配置参数
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        metavar="N",
        help="当批量解包时，设置使用的最大线程数。默认为 4。",
    )
    parser.add_argument(
        "-l",
        "--log-level",
        type=str,
        default="INFO",
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        help="设置日志输出等级，默认为 'INFO'。",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="启用开发者模式，会加载 .lol.env.dev 配置文件并保留临时文件。",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="强制更新数据，忽略版本检查。仅在更新模式下有效。",
    )
    parser.add_argument(
        "--skip-events",
        action="store_true",
        help="跳过事件数据处理，大幅提升处理速度。仅在更新模式下有效。",
    )
    parser.add_argument(
        "--with-bp-vo",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="在更新/解包流程中附带大厅选用/禁用语音（champion-ban-vo/champion-choose-vo）。",
    )
    parser.add_argument(
        "--enable-league-tools-log",
        action="store_true",
        help="启用 'league_tools' 模块的日志输出，用于深度调试。",
    )
    parser.add_argument(
        "--cleanup-remote",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="remote_snapshot 模式下是否在整轮命令成功后自动清理远端准备产物。",
    )

    # 配置覆盖参数（优先级最高）
    config_group = parser.add_argument_group("配置覆盖", "命令行显式配置（优先级高于系统环境变量和 .env）")
    config_group.add_argument(
        "-g",
        "--game-path",
        type=str,
        metavar="PATH",
        help="显式指定 GAME_PATH（游戏客户端根目录）。",
    )
    config_group.add_argument(
        "-o",
        "--output-path",
        type=str,
        metavar="PATH",
        help="显式指定 OUTPUT_PATH（输出目录）。",
    )
    config_group.add_argument(
        "-r",
        "--game-region",
        type=str,
        metavar="REGION",
        help="显式指定 GAME_REGION（例如 zh_CN、en_US）。",
    )
    config_group.add_argument(
        "-t",
        "--exclude-type",
        type=str,
        metavar="TYPES",
        help="显式指定 EXCLUDE_TYPE（逗号分隔，如 SFX,MUSIC）。",
    )
    config_group.add_argument(
        "-w",
        "--wwiser-path",
        type=str,
        metavar="PATH",
        help="显式指定 WWISER_PATH（wwiser.pyz 或 wwiser.exe）。",
    )
    config_group.add_argument(
        "-b",
        "--group-by-type",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="显式指定 GROUP_BY_TYPE（使用 --group-by-type 或 --no-group-by-type）。",
    )

    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """验证命令行参数的有效性

    :param args: 解析后的命令行参数
    :param parser: ArgumentParser 实例，用于打印帮助信息
    :raises SystemExit: 当参数无效时退出程序
    """
    update_actions = [args.update, args.update_champions, args.update_maps]
    extract_actions = [args.extract, args.extract_champions, args.extract_maps]
    mapping_actions = [args.mapping, args.mapping_champions, args.mapping_maps]

    if not any(update_actions + extract_actions + mapping_actions):
        logger.error("错误：必须提供至少一个操作参数。")
        logger.info("更新数据: --update, --update-champions, --update-maps")
        logger.info("解包音频: --extract, --extract-champions, --extract-maps")
        logger.info("事件映射: --mapping, --mapping-champions, --mapping-maps")
        parser.print_help()
        sys.exit(1)

    active_operations = []
    if any(update_actions):
        active_operations.append("更新数据")
    if any(extract_actions):
        active_operations.append("解包音频")
    if any(mapping_actions):
        active_operations.append("构建事件映射")

    if len(active_operations) > 1:
        logger.info(f"检测到同时指定了多个操作，将按顺序执行：{' -> '.join(active_operations)}。")

    if getattr(args, "integrate_data", False):
        if not any(mapping_actions):
            logger.error(
                "错误：--integrate-data 参数只能与映射参数一起使用（--mapping, --mapping-champions, --mapping-maps）"
            )
            sys.exit(1)
        logger.info("检测到 --integrate-data 参数，将生成整合数据文件")


def build_cli_overrides(args: argparse.Namespace) -> dict[str, object]:
    """从命令行参数构建显式配置覆盖项（仅包含显式传入值）"""
    mapping = {
        "GAME_PATH": args.game_path,
        "OUTPUT_PATH": args.output_path,
        "GAME_REGION": args.game_region,
        "EXCLUDE_TYPE": args.exclude_type,
        "CLEANUP_REMOTE": args.cleanup_remote,
        "WITH_BP_VO": args.with_bp_vo,
        "WWISER_PATH": args.wwiser_path,
        "GROUP_BY_TYPE": args.group_by_type,
    }
    return {key: value for key, value in mapping.items() if value is not None}


def initialize_app(args: argparse.Namespace) -> AppContext:
    """初始化应用程序（日志、配置等）并返回运行上下文。"""
    if not args.enable_league_tools_log:
        logger.disable("league_tools")

    cli_overrides = build_cli_overrides(args)

    try:
        app_context = setup_app(dev_mode=args.dev, log_level=args.log_level.upper(), cli_overrides=cli_overrides)
    except AppContextValidationError as e:
        current_work_dir = Path.cwd()
        logger.error(f"配置初始化失败: {e}")
        logger.error(f"请在当前工作目录创建并配置 .lol.env 文件: {current_work_dir / '.lol.env'}")
        logger.error("您可以参考项目中的 .lol.env.example 文件进行配置。")
        sys.exit(1)

    logger.info("命令行工具启动...")

    if app_context.config.source_mode is SourceMode.LOCAL_PATH and not Path(app_context.config.game_path).exists():
        current_work_dir = Path.cwd()
        logger.error("错误：未找到有效的游戏目录 (GAME_PATH)。")
        logger.error(f"请在当前工作目录创建一个 .lol.env 文件: {current_work_dir / '.lol.env'}")
        logger.error("您可以参考项目中的 .lol.env.example 文件进行配置。")
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


def execute_remote_entity_workflow(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """仅在 remote 模式下使用的单位驱动执行器。"""
    update_options = None
    update_target = "all"
    if args.update:
        update_options = build_operation_options(args)
    elif args.update_champions:
        champion_ids = parse_int_ids(args.update_champions)
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
        extract_options = build_operation_options(args, champion_ids=parse_int_ids(args.extract_champions))
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
        mapping_options = build_operation_options(args, champion_ids=parse_int_ids(args.mapping_champions))
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
        logger.info("开始更新所有数据（英雄和地图）...")
        app.update(build_operation_options(args), target="all")
    elif args.update_champions:
        champion_ids = parse_int_ids(args.update_champions)
        if champion_ids:
            logger.info(f"开始更新指定英雄数据：{list(champion_ids)}")
        else:
            logger.info("开始更新所有英雄数据...")
        app.update(build_operation_options(args, champion_ids=champion_ids), target="skin")
    elif args.update_maps:
        map_ids = parse_int_ids(args.update_maps)
        if map_ids:
            logger.info(f"开始更新指定地图数据：{list(map_ids)}")
        else:
            logger.info("开始更新所有地图数据...")
        app.update(build_operation_options(args, map_ids=map_ids), target="map")

    logger.success("数据更新完成！")


def execute_extract_operations(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行音频解包操作。"""
    extract_actions = [args.extract, args.extract_champions, args.extract_maps]
    if not any(extract_actions):
        return

    if args.extract:
        logger.info("开始解包所有音频（英雄和地图）...")
        app.extract(build_operation_options(args))
    elif args.extract_champions:
        try:
            champion_ids = parse_int_ids(args.extract_champions)
        except ValueError as e:
            logger.error(f"解包英雄失败: {e}")
            return

        if champion_ids:
            logger.info(f"开始解包指定英雄音频：{list(champion_ids)}")
            app.extract(
                build_operation_options(args, champion_ids=champion_ids),
                include_maps=False,
            )
        else:
            logger.info("开始解包所有英雄音频...")
            app.extract(build_operation_options(args), include_maps=False)
    elif args.extract_maps:
        try:
            map_ids = parse_int_ids(args.extract_maps)
        except ValueError as e:
            logger.error(f"解包地图失败: {e}")
            return

        if map_ids:
            logger.info(f"开始解包指定地图音频：{list(map_ids)}")
            app.extract(
                build_operation_options(args, map_ids=map_ids),
                include_champions=False,
            )
        else:
            logger.info("开始解包所有地图音频...")
            app.extract(build_operation_options(args), include_champions=False)

    logger.success("音频解包完成！")


def execute_mapping_operations(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行事件映射操作。"""
    mapping_actions = [args.mapping, args.mapping_champions, args.mapping_maps]
    if not any(mapping_actions):
        return

    if getattr(args, "integrate_data", False):
        logger.info("启用整合数据功能，将生成包含完整实体信息的整合文件")

    try:
        if args.mapping:
            logger.info("开始构建所有实体的事件映射（英雄和地图）...")
            app.mapping(build_operation_options(args))
        elif args.mapping_champions:
            champion_ids = parse_int_ids(args.mapping_champions)
            if champion_ids:
                logger.info(f"开始构建指定英雄的事件映射：{list(champion_ids)}")
                app.mapping(
                    build_operation_options(args, champion_ids=champion_ids),
                    include_maps=False,
                )
            else:
                logger.info("开始构建所有英雄的事件映射...")
                app.mapping(build_operation_options(args), include_maps=False)
        elif args.mapping_maps:
            map_ids = parse_int_ids(args.mapping_maps)
            if map_ids:
                logger.info(f"开始构建指定地图的事件映射：{list(map_ids)}")
                app.mapping(
                    build_operation_options(args, map_ids=map_ids),
                    include_champions=False,
                )
            else:
                logger.info("开始构建所有地图的事件映射...")
                app.mapping(build_operation_options(args), include_champions=False)
    except ValueError as e:
        current_work_dir = Path.cwd()
        logger.error(str(e))
        logger.error(f"请在当前工作目录的 .lol.env 文件中配置 WWISER_PATH: {current_work_dir / '.lol.env'}")
        logger.error("WWISER_PATH 应指向 wwiser.pyz 或 wwiser.exe 文件的完整路径。")
        logger.error("您可以从 https://github.com/bnnm/wwiser/releases 下载 Wwiser 工具。")
        sys.exit(1)

    logger.success("事件映射构建完成！")


def main() -> None:
    """主程序入口，协调处理命令行参数和执行相应操作。"""
    try:
        parser = create_parser()
        args = parser.parse_args()

        validate_args(args, parser)

        app_context = initialize_app(args)
        app = LolAudioUnpackApp(app_context)

        if app_context.config.source_mode is SourceMode.REMOTE_SNAPSHOT and (
            _has_extract_actions(args) or _has_mapping_actions(args)
        ):
            execute_remote_entity_workflow(args, app)
            return

        execute_update_operations(args, app)
        execute_extract_operations(args, app)
        execute_mapping_operations(args, app)
        app.cleanup_remote_artifacts()

    except KeyboardInterrupt:
        logger.warning("用户中断操作")
        sys.exit(1)
    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
        try:
            if "args" in locals() and args.dev:
                logger.debug(traceback.format_exc())
        except (NameError, AttributeError):
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
