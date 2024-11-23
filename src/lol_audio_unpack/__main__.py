# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/9/3 10:21
# @Update  : 2024/9/3 11:56
# @Detail  : 

import argparse
import json
import re
import sys
from typing import Optional, Dict, Any
from loguru import logger


def parse_arguments() -> Dict[str, Any]:
    """
    解析命令行参数，并处理配置文件与命令行参数的冲突。

    :return: 合并后的最终参数字典
    """
    parser = argparse.ArgumentParser(description="处理音频文件的工具。")

    # 全局参数
    parser.add_argument('-c', '--config', type=str, help='指定配置文件')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='增加详细日志信息的等级：-v, -vv, -vvv')

    # 独立参数
    parser.add_argument('--GAME_PATH', type=str, help='游戏目录路径')
    parser.add_argument('--GAME_REGION', type=str, default='zh_CN', help='游戏区域')
    parser.add_argument('--OUTPUT_PATH', type=str, help='输出文件路径')
    parser.add_argument('--EXCLUDE_TYPE', type=str, default='SFX, MUSIC', help='要排除的类型，逗号分隔')
    parser.add_argument('--VGMSTREAM_PATH', type=str, help='VGMStream可执行文件路径')

    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='子命令帮助')

    # get_audio 子命令
    parser_get_audio = subparsers.add_parser('get_audio', help='获取音频文件')
    parser_get_audio.add_argument('--include', type=str, help='要包含的正则表达式模式')
    parser_get_audio.add_argument('--exclude', type=str, help='要排除的正则表达式模式')
    parser_get_audio.add_argument('--audio_format', type=str, help='音频格式，例如 wav, mp3')

    # hash_table 子命令
    subparsers.add_parser('hash_table', help='生成哈希表')

    args = parser.parse_args()

    # 根据 -v, -vv, -vvv 设置日志级别
    if args.verbose == 1:
        logger.remove()
        logger.add(sys.stderr, level="INFO")
    elif args.verbose == 2:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    elif args.verbose >= 3:
        logger.remove()
        logger.add(sys.stderr, level="TRACE")

    # 读取配置文件（如果有）
    config = {}
    if args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"从配置文件 {args.config} 中加载配置。")
        except FileNotFoundError:
            logger.error(f"配置文件 {args.config} 未找到。")
            sys.exit(1)

    # 检查命令行参数与配置文件的冲突
    cmd_args = {k: v for k, v in vars(args).items() if v is not None and k != 'config'}
    if args.config and any(k in config for k in cmd_args):
        logger.warning("命令行参数将覆盖配置文件中的设置。")

    # 合并配置文件和命令行参数，命令行参数优先
    final_args = {**config, **cmd_args}

    # 验证必要的参数
    if not args.config:
        if not final_args.get('GAME_PATH') or not final_args.get('OUTPUT_PATH'):
            logger.error("未提供配置文件时，必须指定 --GAME_PATH 和 --OUTPUT_PATH 参数。")
            sys.exit(1)

    if final_args.get('audio_format') and not final_args.get('VGMSTREAM_PATH'):
        logger.error("指定了音频格式时，必须提供 VGMStream 可执行文件路径 (--VGMSTREAM_PATH)。")
        sys.exit(1)

    return final_args


def hash_table() -> None:
    """
    生成哈希表的方法。
    """
    logger.info("正在生成哈希表...")
    # 在这里实现哈希表生成逻辑
    pass


def get_audio(include: Optional[str] = None, exclude: Optional[str] = None, audio_format: Optional[str] = None) -> None:
    """
    过滤并处理音频文件的方法。

    :param include: 包含的正则表达式模式
    :param exclude: 排除的正则表达式模式
    :param audio_format: 音频格式
    """
    if include:
        include_pattern = re.compile(include)
    if exclude:
        exclude_pattern = re.compile(exclude)

    # 示例实现：根据include/exclude模式过滤文件
    logger.info(f"根据包含模式: {include} 和排除模式: {exclude} 进行过滤。")
    if audio_format:
        logger.info(f"处理音频格式: {audio_format}")
    # 在这里实现文件处理逻辑
    pass


def main() -> None:
    """
    主函数，根据解析的参数调用相应的方法。
    """
    args = parse_arguments()

    if args['command'] == 'get_audio':
        get_audio(include=args.get('include'), exclude=args.get('exclude'), audio_format=args.get('audio_format'))
    elif args['command'] == 'hash_table':
        hash_table()


if __name__ == "__main__":
    main()
