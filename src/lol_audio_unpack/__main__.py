# 🐍 Unless explicitly silenced.
# 🐼 除非它明确需要如此
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/26 0:34
# @Update  : 2025/8/3 15:41
# @Detail  : 项目命令行入口


import argparse
import sys
import traceback
from pathlib import Path

from loguru import logger

from . import BinUpdater, DataReader, DataUpdater, __version__, setup_app
from .unpack import unpack_audio_all, unpack_champions, unpack_maps
from .utils.config import config


def create_parser() -> argparse.ArgumentParser:
    """创建和配置命令行参数解析器

    :returns: 配置好的 ArgumentParser 实例
    """
    parser = argparse.ArgumentParser(
        description="一个极简、高效的英雄联盟音频提取工具 (v3-lite)\n支持英雄和地图音频的更新与解包",
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
        "--enable-league-tools-log",
        action="store_true",
        help="启用 'league_tools' 模块的日志输出，用于深度调试。",
    )

    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """验证命令行参数的有效性

    :param args: 解析后的命令行参数
    :param parser: ArgumentParser 实例，用于打印帮助信息
    :raises SystemExit: 当参数无效时退出程序
    """
    # 检查是否提供了任何操作参数
    update_actions = [args.update, args.update_champions, args.update_maps]
    extract_actions = [args.extract, args.extract_champions, args.extract_maps]

    if not any(update_actions + extract_actions):
        logger.error("错误：必须提供至少一个操作参数。")
        logger.info("更新数据: --update, --update-champions, --update-maps")
        logger.info("解包音频: --extract, --extract-champions, --extract-maps")
        parser.print_help()
        sys.exit(1)

    # 如果同时指定了更新和解包操作，则先执行更新再执行解包
    if any(update_actions) and any(extract_actions):
        logger.info("检测到同时指定了更新和解包操作，将按顺序执行：先更新数据，再解包音频。")


def initialize_app(args: argparse.Namespace) -> None:
    """初始化应用程序（日志、配置等）

    :param args: 解析后的命令行参数
    :raises SystemExit: 当配置无效时退出程序
    """
    # 默认禁用第三方库的日志，除非用户显式开启
    if not args.enable_league_tools_log:
        logger.disable("league_tools")

    setup_app(dev_mode=args.dev, log_level=args.log_level.upper())
    logger.info("命令行工具启动...")

    # 检查必要的配置是否存在
    if not config.GAME_PATH or not Path(config.GAME_PATH).exists():
        current_work_dir = Path.cwd()
        logger.error("错误：未找到有效的游戏目录 (GAME_PATH)。")
        logger.error(f"请在当前工作目录创建一个 .lol.env 文件: {current_work_dir / '.lol.env'}")
        logger.error("您可以参考项目中的 .lol.env.example 文件进行配置。")
        sys.exit(1)


def parse_ids(id_string: str | None) -> list[str] | None:
    """解析逗号分隔的ID字符串为列表

    :param id_string: 逗号分隔的ID字符串或None
    :returns: ID字符串列表，如果输入为"all"或None则返回None
    """
    if id_string and id_string != "all":
        return [id.strip() for id in id_string.split(",") if id.strip()]
    return None


def execute_update_operations(args: argparse.Namespace) -> None:
    """执行数据更新操作

    :param args: 解析后的命令行参数
    """
    update_actions = [args.update, args.update_champions, args.update_maps]
    if not any(update_actions):
        return

    force = args.force
    process_events = not args.skip_events  # 默认处理事件，除非明确跳过

    if args.skip_events:
        logger.info("已启用快速模式：跳过事件数据处理")
    if force:
        logger.warning("已启用强制更新模式，将忽略现有文件的版本检查。")

    # 确定更新目标和ID列表
    champion_ids = None
    map_ids = None
    target = "all"  # 默认

    if args.update:
        logger.info("开始更新所有数据（英雄和地图）...")
        target = "all"
    elif args.update_champions:
        champion_ids = parse_ids(args.update_champions)
        if champion_ids:
            logger.info(f"开始更新指定英雄数据：{champion_ids}")
            target = "skin"
        else:
            logger.info("开始更新所有英雄数据...")
            target = "skin"
    elif args.update_maps:
        map_ids = parse_ids(args.update_maps)
        if map_ids:
            logger.info(f"开始更新指定地图数据：{map_ids}")
            target = "map"
        else:
            logger.info("开始更新所有地图数据...")
            target = "map"

    # DataUpdater总是需要先运行，以确保有最新的data.json
    DataUpdater(force_update=force).check_and_update()

    # 使用BinUpdater更新数据
    updater = BinUpdater(force_update=force, process_events=process_events)
    updater.update(target=target, champion_ids=champion_ids, map_ids=map_ids)

    logger.success("数据更新完成！")


def execute_extract_operations(args: argparse.Namespace) -> None:
    """执行音频解包操作

    :param args: 解析后的命令行参数
    """
    extract_actions = [args.extract, args.extract_champions, args.extract_maps]
    if not any(extract_actions):
        return

    logger.info("加载数据读取器...")
    reader = DataReader()

    # 输出全局音频配置信息
    logger.info(
        f"音频类型配置 - 包含: {config.INCLUDE_TYPE}{f', 排除: {list(config.EXCLUDE_TYPE)}' if config.EXCLUDE_TYPE else ''}"
    )
    logger.info(f"输出路径: {config.OUTPUT_PATH}")
    logger.info(f"语言: {config.GAME_REGION}")

    if args.extract:
        logger.info("开始解包所有音频（英雄和地图）...")
        unpack_audio_all(reader=reader, max_workers=args.max_workers)
    elif args.extract_champions:
        champion_ids = parse_ids(args.extract_champions)
        if champion_ids:
            logger.info(f"开始解包指定英雄音频：{champion_ids}")
            try:
                champion_ids_int = [int(cid) for cid in champion_ids]
                unpack_champions(reader=reader, champion_ids=champion_ids_int, max_workers=args.max_workers)
            except ValueError as e:
                logger.error(f"解包英雄失败: {e}")
            except Exception as e:
                logger.error(f"解包英雄时出错: {e}")
        else:
            logger.info("开始解包所有英雄音频...")
            unpack_audio_all(reader=reader, max_workers=args.max_workers, include_maps=False)
    elif args.extract_maps:
        map_ids = parse_ids(args.extract_maps)
        if map_ids:
            logger.info(f"开始解包指定地图音频：{map_ids}")
            try:
                map_ids_int = [int(mid) for mid in map_ids]
                unpack_maps(reader=reader, map_ids=map_ids_int, max_workers=args.max_workers)
            except ValueError as e:
                logger.error(f"解包地图失败: {e}")
            except Exception as e:
                logger.error(f"解包地图时出错: {e}")
        else:
            logger.info("开始解包所有地图音频...")
            unpack_audio_all(reader=reader, max_workers=args.max_workers, include_champions=False)

    logger.success("音频解包完成！")


def main():
    """主程序入口，协调处理命令行参数和执行相应操作"""
    try:
        # 1. 创建和解析命令行参数
        parser = create_parser()
        args = parser.parse_args()

        # 2. 验证参数
        validate_args(args, parser)

        # 3. 初始化应用
        initialize_app(args)

        # 4. 执行操作
        execute_update_operations(args)
        execute_extract_operations(args)

    except KeyboardInterrupt:
        logger.warning("用户中断操作")
        sys.exit(1)
    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
        # 如果args已定义且为开发模式，打印详细错误信息
        try:
            if "args" in locals() and args.dev:
                logger.debug(traceback.format_exc())
        except (NameError, AttributeError):
            pass  # 如果访问args失败，忽略详细错误信息
        sys.exit(1)


if __name__ == "__main__":
    main()
