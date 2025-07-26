# 🐍 Special cases aren't special enough to break the rules.
# 🐼 特例亦不可违背原则
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/24 8:46
# @Update  : 2025/7/25 4:58
# @Detail  : 


from loguru import logger

from lol_audio_unpack import BinUpdater, DataReader, DataUpdater, setup_app

if __name__ == "__main__":
    # 一行代码完成所有初始化！
    # 在测试时，我们可以强制覆盖日志级别为INFO，即使配置文件中是DEBUG
    setup_app(dev_mode=True, log_level="INFO")
    logger.disable("league_tools")

    # 示例：更新游戏数据
    data_updater = DataUpdater()
    bin_updater = BinUpdater()

    data_file = data_updater.check_and_update()
    bin_updater.update()

    # 示例：使用数据读取器
    reader = DataReader(data_file)
    print(f"游戏版本: {reader.version}")
    print(f"支持语言: {reader.get_languages()}")

    # 获取一个英雄的信息
    ahri = reader.find_champion("ahri")
    if ahri:
        print(f"英雄ID: {ahri['id']}")
        print(f"英雄名称: {ahri['names'].get('zh_CN', ahri['names'].get('default'))}")
        print(f"皮肤数量: {len(ahri.get('skins', []))}")

    # 循环所有英雄的所有皮肤，包括炫彩
    for champion in reader.get_champions():
        # 判段所有 audioData 下的所有类型，每个类型下数据量，如果大于1，则打印出来
        for skin in champion.get("skins", []):
            for audio_type, paths in reader.get_skin_bank(skin.get("id")).items():
                if len(paths) > 1:
                    print(
                        f"英雄: {champion.get('alias')},"
                        f"皮肤: {skin.get('skinNames').get('zh_CN')},"
                        f"类型: {audio_type},"
                        f"数据量: {len(paths)},"
                        f"数据是否相同: {paths[0] == paths[1]}"
                    )

            for chroma in skin.get("chromas", []):
                for audio_type, paths in reader.get_skin_bank(chroma.get("id")).items():
                    if len(paths) > 1:
                        print(
                            f"英雄: {champion.get('alias')},"
                            f"皮肤: {skin.get('skinNames').get('zh_CN')},"
                            f"炫彩: {chroma.get('chromaNames').get('zh_CN')},"
                            f"类型: {audio_type},"
                            f"数据量: {len(paths)},"
                            f"数据是否相同: {paths[0] == paths[1]}"
                        )
