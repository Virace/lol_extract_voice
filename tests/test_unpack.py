# 🐍 Errors should never pass silently.
# 🐼 错误绝不能悄悄忽略
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/25 2:54
# @Update  : 2025/8/1 1:30
# @Detail  : 测试


from loguru import logger

from lol_audio_unpack import DataReader, setup_app
from lol_audio_unpack.unpack import unpack_audio_all, unpack_champion, unpack_map_audio

if __name__ == "__main__":
    setup_app(dev_mode=True, log_level="INFO")
    logger.disable("league_tools")
    reader = DataReader()
    # unpack_audio_all(reader, max_workers=4)
    unpack_champion(555, reader)
    # unpack_champion(62, reader)  # 孙悟空，皮肤62077 路径特殊
    # unpack_champion(19, reader)  # 狼人 部分皮肤名字后包含空格
    # unpack_map_audio(0, reader)
