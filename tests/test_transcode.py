# 🐍 Errors should never pass silently.
# 🐼 错误绝不能悄悄忽略
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/26 15:30
# @Update  : 2025/7/26 9:11
# @Detail  : 测试魔改版 vgmstream-cli 转码时间


import os
import subprocess
import time
from pathlib import Path

from loguru import logger

from lol_audio_unpack import setup_app
from lol_audio_unpack.Utils.config import config


def transcode_audio_files(vgmstream_path=None, delete_source=True):
    """
    使用魔改版 vgmstream-cli 转码所有解包的音频文件

    :param vgmstream_path: vgmstream-cli.exe 的路径，如果为 None，则从配置中读取
    :param delete_source: 是否删除源文件
    :return: 转码文件数量
    """
    # 如果未指定 vgmstream_path，则从配置中读取
    if vgmstream_path is None:
        vgmstream_path = config.get("VGMSTREAM_PATH")
        if not vgmstream_path:
            logger.error("未指定 vgmstream-cli.exe 路径，请在配置中设置 VGMSTREAM_PATH 或直接传入参数")
            return 0

    # 确保 vgmstream_path 是 Path 对象
    if isinstance(vgmstream_path, str):
        vgmstream_path = Path(vgmstream_path)

    # 检查 vgmstream-cli.exe 是否存在
    if not vgmstream_path.exists():
        logger.error(f"vgmstream-cli.exe 不存在: {vgmstream_path}")
        return 0

    # 获取音频目录
    audio_path = config.get("AUDIO_PATH")
    if not audio_path or not Path(audio_path).exists():
        logger.error(f"音频目录不存在: {audio_path}")
        return 0

    logger.info(f"开始转码音频文件，源目录: {audio_path}")
    logger.info(f"使用工具: {vgmstream_path}")

    # 步骤 1: 预先统计所有 .wem 文件数量
    logger.info("正在统计 .wem 文件总数...")
    wem_files = list(Path(audio_path).rglob("*.wem"))
    total_files = len(wem_files)

    if total_files == 0:
        logger.warning("在指定目录中未找到任何 .wem 文件，无需转码。")
        return 0

    logger.info(f"找到 {total_files} 个 .wem 文件准备转码。")

    # 构建命令行参数
    cmd = [
        str(vgmstream_path),
        "-o",
        "?p?b.wav",  # 输出文件格式，保持原目录结构和文件名，只改扩展名
        str(audio_path),  # 输入目录
    ]

    # 如果需要删除源文件，添加 -Y 参数
    if delete_source:
        cmd.append("-Y")
        logger.warning("已启用源文件删除选项 (-Y)，转码后将删除所有 .wem 文件")

    # 记录开始时间
    start_time = time.time()

    try:
        # 执行命令
        logger.info(f"执行命令: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace"
        )

        # 实时输出转码进度
        file_count = 0
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            line = line.strip().lower()

            # 检查是否有错误或警告信息
            if "error" in line or "not" in line:
                logger.warning(f"VGMStream output: {line.strip()}")
                continue  # 继续处理下一行

            # 根据 "decoding" 关键字更新进度
            if "decoding" in line:
                file_count += 1
                progress = (file_count / total_files) * 100
                # 每处理100个文件或处理完成时输出一次日志，避免刷屏
                if file_count % 100 == 0 or file_count == total_files:
                    logger.info(f"转码进度: {progress:.2f}% ({file_count}/{total_files})")

        # 等待进程完成
        process.wait()

        # 检查是否有错误
        if process.returncode != 0:
            stderr = process.stderr.read()
            logger.error(f"转码过程中出现错误，返回码: {process.returncode}")
            if stderr:
                logger.error(f"错误信息: {stderr.strip()}")
            return file_count

    except Exception as e:
        logger.error(f"执行转码命令时出错: {e}")
        return 0

    # 记录结束时间和总耗时
    end_time = time.time()
    total_time = end_time - start_time

    # 步骤 2: 验证转码结果
    logger.info("正在验证转码结果...")
    remaining_wems = list(Path(audio_path).rglob("*.wem"))
    created_wavs = list(Path(audio_path).rglob("*.wav"))
    logger.info(f"验证: 找到 {len(created_wavs)} 个 .wav 文件 (工具报告处理了 {file_count} 个)")
    logger.info(f"验证: 剩余 {len(remaining_wems)} 个 .wem 文件 (原始总数 {total_files} 个)")

    if delete_source:
        expected_remaining = total_files - file_count
        if len(remaining_wems) == expected_remaining:
            logger.success(f"源文件删除验证通过: 剩余 {len(remaining_wems)} 个, 符合预期。")
        else:
            logger.warning(f"源文件删除验证异常: 剩余 {len(remaining_wems)} 个, 预期应为 {expected_remaining} 个。")

    def format_duration(seconds_float: float) -> str:
        """格式化时长为易读的字符串"""
        seconds_int = int(seconds_float)
        if seconds_int < 100:
            return f"{seconds_float:.2f} 秒"

        minutes, sec = divmod(seconds_int, 60)
        if minutes < 100:
            return f"{minutes} 分钟 {sec} 秒"

        hours, min_rem = divmod(minutes, 60)
        return f"{hours} 小时 {min_rem} 分钟 {sec} 秒"

    # 输出统计信息
    # 确保最终进度是100%
    if file_count != total_files:
        logger.warning(f"处理的文件数 ({file_count}) 与找到的总数 ({total_files}) 不匹配。")

    formatted_time = format_duration(total_time)
    logger.success(f"转码完成！共处理 {file_count} 个文件，总耗时: {formatted_time}")
    if file_count > 0:
        logger.info(f"平均每个文件耗时: {total_time / file_count * 1000:.2f} 毫秒")

    return file_count


if __name__ == "__main__":
    # 初始化应用
    setup_app(dev_mode=True, log_level="INFO")

    # 设置 vgmstream-cli.exe 路径
    # 优先使用配置中的路径，如果没有则使用默认路径
    vgmstream_path = config.get("VGMSTREAM_PATH", r"C:\Users\Virace\Desktop\vgmstream-win64\vgmstream-cli.exe")

    # 执行转码
    transcode_audio_files(vgmstream_path, delete_source=True)
