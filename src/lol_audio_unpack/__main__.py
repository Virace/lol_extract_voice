# 🐍 Unless explicitly silenced.
# 🐼 除非它明确需要如此
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/26 0:34
# @Update  : 2025/7/30 7:55
# @Detail  : 项目命令行入口


import argparse
import sys
import traceback
from pathlib import Path

from loguru import logger

from . import BinUpdater, DataReader, DataUpdater, __version__, setup_app
from .unpack import unpack_audio, unpack_audio_all
from .utils.config import config


def main():
    """主程序入口，处理命令行参数和执行相应操作"""
    parser = argparse.ArgumentParser(
        description="一个极简、高效的英雄联盟音频提取工具 (v3-lite)",
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

    # 主功能参数组，更新数据和解包音频是互斥的操作
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--update-data",
        nargs="?",
        const="all",
        choices=["skin", "map", "all"],
        help="""更新并生成所有必要的数据文件。
可以指定只更新特定部分:
- 'skin': 只更新皮肤数据
- 'map': 只更新地图数据
- (无值): 更新所有数据 (默认)
""",
    )
    action_group.add_argument(
        "--hero-id",
        type=int,
        metavar="ID",
        help="仅解包指定ID的单个英雄的音频。",
    )
    action_group.add_argument(
        "--all",
        action="store_true",
        help="解包所有英雄的音频文件。",
    )

    # 通用配置参数
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        metavar="N",
        help="当解包所有英雄时，设置使用的最大线程数。默认为 4。",
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
        help="强制更新数据，忽略版本检查。仅在 --update-data 模式下有效。",
    )
    parser.add_argument(
        "--enable-league-tools-log",
        action="store_true",
        help="启用 'league_tools' 模块的日志输出，用于深度调试。",
    )

    args = parser.parse_args()

    # 如果没有提供任何主要操作，则打印帮助信息并退出
    if not (args.update_data or args.hero_id is not None or args.all):
        logger.error("错误：必须提供一个操作参数，例如 --update-data, --hero-id <ID>, 或 --all。")
        parser.print_help()
        sys.exit(1)

    # 1. 初始化应用 (配置和日志)
    # 默认禁用第三方库的日志，除非用户显式开启
    if not args.enable_league_tools_log:
        logger.disable("league_tools")

    setup_app(dev_mode=args.dev, log_level=args.log_level.upper())
    logger.info("命令行工具启动...")

    # 2. 检查必要的配置是否存在
    if not config.GAME_PATH or not Path(config.GAME_PATH).exists():
        current_work_dir = Path.cwd()
        logger.error("错误：未找到有效的游戏目录 (GAME_PATH)。")
        logger.error(f"请在当前工作目录创建一个 .lol.env 文件: {current_work_dir / '.lol.env'}")
        logger.error("您可以参考项目中的 .lol.env.example 文件进行配置。")
        sys.exit(1)

    # 3. 根据参数执行相应操作
    try:
        if args.update_data:
            target = args.update_data
            force = args.force
            if force:
                logger.warning("已启用强制更新模式，将忽略现有文件的版本检查。")
            logger.info(f"开始更新数据 (目标: {target})...")
            # DataUpdater总是需要先运行，以确保有最新的data.json
            DataUpdater(force_update=force).check_and_update()
            BinUpdater(target=target, force_update=force).update()
            logger.success(f"数据更新完成 (目标: {target})！")

        elif args.hero_id or args.all:
            logger.info("加载数据读取器...")
            reader = DataReader()

            if args.hero_id:
                logger.info(f"准备解包单个英雄，ID: {args.hero_id}")
                unpack_audio(hero_id=args.hero_id, reader=reader)
            elif args.all:
                logger.info("准备解包所有英雄...")
                unpack_audio_all(reader=reader, max_workers=args.max_workers)

        else:
            # 理论上因为 group(required=True) 不会到这里，但作为保险
            parser.print_help()

    except Exception as e:
        logger.critical(f"程序执行过程中发生未捕获的严重错误: {e}")
        logger.debug(traceback.format_exc())  # if log-level is low enough
        sys.exit(1)


if __name__ == "__main__":
    main()
