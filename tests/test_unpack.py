# 🐍 Errors should never pass silently.
# 🐼 错误绝不能悄悄忽略
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/25 2:54
# @Update  : 2025/7/25 23:25
# @Detail  : 


from loguru import logger

from lol_audio_unpack import DataReader, setup_app
from lol_audio_unpack.unpack import unpack_audio, unpack_audio_all

if __name__ == "__main__":
    # 一行代码完成所有初始化！
    # 在测试时，我们可以强制覆盖日志级别为INFO，即使配置文件中是DEBUG
    setup_app(dev_mode=True, log_level="INFO")
    logger.disable("league_tools")
    reader = DataReader()
    # unpack_audio_all(reader, max_workers=16)
    unpack_audio(555, reader)
