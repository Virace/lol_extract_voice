# 🐍 Special cases aren't special enough to break the rules.
# 🐼 特例亦不可违背原则
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/24 8:46
# @Update  : 2025/8/1 1:31
# @Detail  : 测试数据


from loguru import logger

from lol_audio_unpack import BinUpdater, DataReader, DataUpdater, setup_app

if __name__ == "__main__":
    # 一行代码完成所有初始化！
    # 在测试时，我们可以强制覆盖日志级别为INFO，即使配置文件中是DEBUG
    setup_app(dev_mode=True, log_level="INFO")
    logger.disable("league_tools")

    # 示例：更新游戏数据
    # data_updater = DataUpdater()
    # bin_updater = BinUpdater()
    #
    # data_file = data_updater.check_and_update()
    # bin_updater.update()

    # 示例：使用数据读取器
    reader = DataReader()
    print(f"游戏版本: {reader.version}")
    print(f"支持语言: {reader.get_languages()}")

    print(reader.get_map_banks("11"))
