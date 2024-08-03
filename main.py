# -*- coding: utf-8 -*-
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2022/8/15 23:53
# @Update  : 2024/8/3 16:18
# @Detail  : 描述

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from league_tools import get_audio_files
from league_tools.formats import WAD
from loguru import logger

from Data.Manifest import compare_version
from Hashes import HashManager
from Utils.common import format_region, makedirs, capitalize_first_letter
from Utils.logs import log_result
from Utils.type_hints import StrPath
from config import config_instance

HASH_MANAGER = HashManager(
    game_path=config_instance.GAME_PATH,
    hash_path=config_instance.HASH_PATH,
    manifest_path=config_instance.MANIFEST_PATH,
    region=config_instance.GAME_REGION,
    log_path=config_instance.LOG_PATH,
)

AUDIO_PATH: StrPath = config_instance.AUDIO_PATH / HASH_MANAGER.game_version


def get_wad_file_name(kind, name, _type, region) -> StrPath:
    """
    根据条件拼接wad文件路径
    :param kind: 英雄 、地图
    :param name: 名字
    :param _type: 台词、音效
    :param region: 区域
    :return:
    """
    region2 = region[:3].lower() + region[3:].upper()
    if kind == "companions":
        name = "map22"

    path = (
        config_instance.GAME_CHAMPION_PATH
        if kind == "characters"
        else config_instance.GAME_MAPS_PATH
    )

    filename = f"{capitalize_first_letter(name)}.wad.client"
    if _type == "VO" and region2 != "en_US":
        filename = f"{capitalize_first_letter(name)}.{region2}.wad.client"

    return path / filename


def get_event_audio_hash_table(update=False, max_works=None) -> None:
    """
    给定游戏英雄以及公共文件目录和区域语言,
    获取出小小英雄外可获取的所有音频事件与音频资源ID对应哈希表
    :param update:
    :param max_works
    :return:
    """
    # 获取bnk\wpk文件哈希表
    logger.info(rf"开始获取bnk\wpk文件哈希表, 强制更新: {update}")
    bnk_hashes = HASH_MANAGER.get_bnk_hashes(update)
    logger.info(r"获取bnk\wpk文件哈希表完成")

    logger.info("开始提取音频哈希表.")
    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = {}
        for kind, sections in bnk_hashes.items():
            # 排除小小英雄
            if kind == "companions":
                continue

            # 循环英雄、和 皮肤
            for name, skins in sections.items():
                for skin, paths in skins.items():

                    event_hashes = HASH_MANAGER.get_event_hashes(kind, name)
                    for _type, value in paths.items():
                        # if not(kind == 'characters' and name == 'akali'
                        # and skin == 'skin61' and _type == 'SFX'):
                        #     continue

                        wad_file = get_wad_file_name(
                            kind, name, _type, config_instance.GAME_REGION
                        )
                        # HASH_MANAGER.get_audio_hashes(value, wad_file,
                        # event_hashes, _type, kind, name,
                        #                  skin, update)
                        # HASH_MANAGER.get_audio_hashes(
                        #     value, wad_file, event_hashes, _type, kind, name, skin, update
                        # )
                        fs.update(
                            {
                                e.submit(
                                    HASH_MANAGER.get_audio_hashes,
                                    value,
                                    wad_file,
                                    event_hashes,
                                    _type,
                                    kind,
                                    name,
                                    skin,
                                    update,
                                ): f"{kind}, {name}, {skin}, {_type}"
                            }
                        )

        log_result(
            fs,
            sys._getframe().f_code.co_name,
            config_instance.GAME_REGION,
            config_instance.LOG_PATH,
        )
        logger.info("提取音频哈希表完毕.")


def get_lcu_audio():
    """
    提取LCU ban 选以及效果 音频资源
    :return:
    """
    sfx = []
    vo = []

    def output_file_name(_r):
        def get_path(path: StrPath) -> StrPath:
            rep = f"plugins/rcp-be-lol-game-data/global/{_r}/v1/"
            new = path.replace(rep, "")
            return AUDIO_PATH / _r / "LCU" / Path(new)

        return get_path

    wad_sfx_file = config_instance.GAME_LCU_PATH / "default-assets.wad"
    wad_vo_file = (
            config_instance.GAME_LCU_PATH
            / f"{format_region(config_instance.GAME_REGION)}-assets.wad"
    )
    for cid in HASH_MANAGER.game_data.get_champions_id():
        sfx.append(
            f"plugins/rcp-be-lol-game-data/global/default/v1/champion-sfx-audios/{cid}.ogg"
        )
        vo.extend(
            [
                f"plugins/rcp-be-lol-game-data/global/{config_instance.GAME_REGION}/v1/champion-choose-vo/{cid}.ogg",
                f"plugins/rcp-be-lol-game-data/global/{config_instance.GAME_REGION}/v1/champion-ban-vo/{cid}.ogg",
            ]
        )

    WAD(wad_sfx_file).extract(sfx, out_dir=output_file_name("default"))
    WAD(wad_vo_file).extract(vo, out_dir=output_file_name(config_instance.GAME_REGION))


def get_game_audio(
        hash_path: StrPath = HASH_MANAGER.e2a_hash_path, audio_format="wav", max_works=None
):
    """
    根据提供的哈希表, 提取游戏音频资源
    如果默认则为全部哈希表
    如果只需要更新部分英雄，则将部分哈希表放在指定目录，传入即可
    :param hash_path: 哈希表路径, 默认为E2A_HASH_PATH
    :param audio_format: 音频转码格式
    :param max_works: 最大进程数
    :return:
    """
    logger.info(
        f"开始提取游戏内音频. hash_path:{hash_path}, audio_format:{audio_format}"
    )

    # 当前游戏版本
    current_version = HASH_MANAGER.game_data.get_game_version()

    with ProcessPoolExecutor(max_workers=max_works) as e:
        fs = dict()
        for file in Path(hash_path).rglob("*.json"):

            # 排除不需要的文件夹
            _tt = file.parent.parent.parent.name
            if _tt in config_instance.EXCLUDE_TYPE:
                logger.debug(f"排除: {_tt}")
                continue

            with file.open(encoding="utf-8") as f:
                data = json.load(f)
                _type = data["info"]["type"]
                kind = data["info"]["kind"]
                name = data["info"]["name"]
                detail = data["info"]["detail"]

                if "version" in data["info"]:
                    # 比较版本号, 如果大版本号不同直接报错， 小版本号不同则警告
                    compare_version(current_version, data["info"]["version"])

                logger.info(f"获取{kind} {name} {detail} {_type}音频")
                # 拼接wad文件名字
                wad_file = (
                        Path(config_instance.GAME_PATH)
                        / Path(data["info"]["wad"]).as_posix()
                )

                # 取出bnk音频文件 字节类型
                audio_raws = WAD(wad_file).extract(list(data["data"].keys()), raw=True)

                ids = []
                for raw in audio_raws:
                    if raw:
                        # 解析bnk文件
                        audio_files = get_audio_files(raw)
                        del raw
                        for i in audio_files:

                            # 处理不同事件下的重复文件
                            if i.id in ids:
                                continue
                            else:
                                ids.append(i.id)

                            thisname = i.filename if i.filename else f"{i.id}.wem"
                            filename = (
                                    Path(AUDIO_PATH)
                                    / (
                                        config_instance.GAME_REGION
                                        if _type == "VO"
                                        else "default"
                                    )
                                    / _type
                                    / kind
                                    / name
                                    / detail
                                    / thisname.replace("wem", audio_format)
                            )

                            filename.parent.mkdir(parents=True, exist_ok=True)
                            # i.static_save_file(i.data,
                            # filename, False, vgmstream_cli)
                            # i.static_save_file(
                            #     i.data,
                            #     filename,
                            #     False,
                            #     config_instance.VGMSTREAM_PATH,
                            # )
                            fs[
                                e.submit(
                                    i.static_save_file,
                                    i.data,
                                    filename,
                                    False,
                                    config_instance.VGMSTREAM_PATH,
                                )
                            ] = (_type, kind, name, detail, wad_file)

        log_result(
            fs,
            sys._getframe().f_code.co_name,
            config_instance.GAME_REGION,
            config_instance.LOG_PATH,
        )
        logger.info("提取游戏内音频完毕.")


def main(audio_format="wem", max_works=None):
    """
    获取游戏内 音频文件
    :param audio_format: 音频格式
    :param max_works: 最大线程数
    :return:
    """
    # 更新英雄列表等数据
    HASH_MANAGER.game_data.update_data()
    HASH_MANAGER.game_data_default.update_data()
    # 当前游戏版本号
    logger.info(f"当前游戏版本: {HASH_MANAGER.game_version}")
    # 获取英雄相关图片
    # HASH_MANAGER.game_data.get_images()

    # 更新哈希表
    get_event_audio_hash_table(False)

    get_lcu_audio()
    get_game_audio(audio_format=audio_format, max_works=max_works)


def init():
    # 初始化目录
    makedirs(config_instance.TEMP_PATH)
    makedirs(config_instance.LOG_PATH, True)
    makedirs(config_instance.HASH_PATH)
    makedirs(config_instance.MANIFEST_PATH)


if __name__ == "__main__":
    logger.configure(handlers=[
        dict(sink=sys.stdout, level="INFO")
    ])
    logger.enable("league_tools")

    init()
    main(audio_format="wav")

