# 🐍 Although that way may not be obvious at first unless you're Dutch.
# 🐼 尽管这方法一开始并非如此直观，除非你是荷兰人
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:38
# @Update  : 2025/7/30 9:22
# @Detail  : Manager模块的通用函数


import json
import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from lol_audio_unpack.utils.common import dump_json, dump_msgpack, dump_yaml, load_json, load_msgpack, load_yaml
from lol_audio_unpack.utils.config import config


def read_data(path: Path) -> dict:
    """
    智能读取数据文件。
    如果路径包含后缀，则直接读取该文件。
    如果路径不含后缀，则按优先级顺序查找并读取第一个存在的文件。

    开发模式下，优先使用人类可读的格式。

    :param path: 文件路径（可带或不带后缀）
    :return: 读取的数据字典
    """
    result = {}
    files_to_check = []

    # 1. 确定要检查的文件列表
    if path.suffix:
        # 如果指定了后缀，只检查这一个文件
        files_to_check.append(path)
    else:
        # 如果未指定后缀，按优先级生成待检查文件列表
        formats_priority = [".yml", ".json", ".msgpack"] if config.is_dev_mode() else [".msgpack", ".yml", ".json"]
        files_to_check = [path.with_suffix(s) for s in formats_priority]

    # 2. 遍历并加载第一个存在的文件
    for file_to_try in files_to_check:
        if not file_to_try.exists():
            continue

        suffix = file_to_try.suffix
        loader = None
        if suffix == ".json":
            loader = load_json
        elif suffix == ".msgpack":
            loader = load_msgpack
        elif suffix in [".yaml", ".yml"]:
            loader = load_yaml

        if loader:
            logger.debug(f"找到并读取数据文件: {file_to_try}")
            try:
                result = loader(file_to_try)
                break  # 成功加载后立即退出循环
            except Exception as e:
                logger.error(f"读取文件时出错: {file_to_try}, 错误: {e}")
                # 如果一个文件损坏，可以继续尝试下一个
                continue
        else:
            logger.error(f"不支持的文件格式: {suffix} (来自: {file_to_try})")

    # 3. 如果循环结束后仍未加载任何文件，记录警告
    if not result and not path.suffix:
        logger.warning(f"在 {path.parent} 未找到任何格式的数据文件 (base: {path.name})")
    elif not result and path.suffix and not path.exists():
        logger.warning(f"指定的数据文件不存在: {path}，将返回空字典")

    return result


def write_data(data: dict, base_path: Path) -> None:
    """
    根据环境自动选择最佳格式写入数据文件。
    开发模式下写入YAML，生产模式下写入MessagePack。

    :param data: 要写入的数据
    :param base_path: 不带后缀的基础文件路径
    """
    fmt = "yml" if config.is_dev_mode() else "msgpack"
    path = base_path.with_suffix(f".{fmt}")
    try:
        if fmt == "yml":
            dump_yaml(data, path)
        elif fmt == "json":
            dump_json(data, path)
        else:
            dump_msgpack(data, path)
        logger.debug(f"成功写入数据到: {path}")
    except Exception as e:
        logger.error(f"写入文件失败: {path}, 错误: {e}")


def get_game_version(game_path: Path) -> str:
    """
    获取游戏版本

    :param game_path: 游戏根目录路径
    :return: 游戏版本号
    """
    meta = game_path / "Game" / "content-metadata.json"
    if not meta.exists():
        raise FileNotFoundError("content-metadata.json 文件不存在，无法判断版本信息")

    with open(meta, encoding="utf-8") as f:
        data = json.load(f)

    version_v = data["version"]

    if m := re.match(r"^(\d+\.\d+)\.", version_v):
        return m.group(1)

    raise ValueError(f"无法解析版本号: {version_v}")


def needs_update(base_path: Path, current_version: str, force_update: bool) -> bool:
    """
    检查文件是否需要更新的通用函数

    :param base_path: 要检查的文件的基础路径（不带后缀）
    :param current_version: 当前游戏版本
    :param force_update: 是否强制更新
    :return: 如果需要更新，则返回True
    """
    if force_update:
        return True

    data = read_data(base_path)
    if not data:
        return True  # 文件不存在，需要更新

    if data.get("gameVersion") == current_version:
        logger.debug(f"文件已是最新版本 ({current_version})，跳过更新: {base_path.name}")
        return False

    return True


class ProgressTracker:
    """
    进度跟踪器，用于记录和显示处理进度
    """

    def __init__(self, total: int, description: str, log_interval: int = 10):
        """
        初始化进度跟踪器

        :param total: 总项目数
        :param description: 进度描述
        :param log_interval: 日志记录间隔
        """
        self.total = total
        self.current = 0
        self.description = description
        self.log_interval = log_interval
        self.start_time = datetime.now()
        logger.info(f"开始{description}，总计 {total} 项")

    def update(self, increment: int = 1) -> None:
        """
        更新进度

        :param increment: 增量，默认为1
        """
        self.current += increment
        if self.current % self.log_interval == 0 or self.current == self.total:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            percentage = (self.current / self.total) * 100
            logger.info(
                f"{self.description}进度: {self.current}/{self.total} ({percentage:.1f}%)，已用时 {elapsed:.1f}秒"
            )

    def finish(self) -> None:
        """
        完成进度跟踪，显示最终结果
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        logger.success(f"{self.description}完成，共 {self.current}/{self.total} 项，用时 {elapsed:.1f}秒")
