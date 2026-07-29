"""英雄 BIN 链路处理。

负责按英雄ID处理皮肤 BIN，提取 banks/events 数据并生成独立文件。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from league_tools.formats import BIN
from loguru import logger

from lol_audio_unpack.manager.bin_source import BinSource
from lol_audio_unpack.manager.files import needs_update, write_data
from lol_audio_unpack.utils.logging import performance_monitor

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext

# 类型别名定义
ChampionData = dict[str, Any]


class ChampionBinProcessor:
    """处理英雄皮肤 BIN，生成 banks/events 数据。"""

    def __init__(  # noqa: PLR0913
        self,
        bin_source: BinSource,
        *,
        ctx: AppContext,
        version: str,
        force_update: bool,
        process_events: bool,
        game_path: Path,
        champion_banks_dir: Path,
        champion_events_dir: Path,
    ):
        """初始化英雄 BIN 处理器。

        :param bin_source: BIN 来源辅助实例。
        :param ctx: 运行时上下文。
        :param version: 当前游戏版本。
        :param force_update: 是否强制更新，忽略版本检查。
        :param process_events: 是否处理事件数据。
        :param game_path: 游戏客户端根目录。
        :param champion_banks_dir: 英雄 banks 输出目录。
        :param champion_events_dir: 英雄 events 输出目录。
        """
        self.bin_source = bin_source
        self.ctx = ctx
        self.version = version
        self.force_update = force_update
        self.process_events = process_events
        self.game_path = game_path
        self.champion_banks_dir = champion_banks_dir
        self.champion_events_dir = champion_events_dir

    def _is_dev_mode(self) -> bool:
        """返回当前运行是否为开发模式。"""
        return bool(self.ctx.config.dev_mode)

    def _log_simple_progress(self, stage_name: str, index: int, total: int, entity_id: str) -> None:
        """输出简单的批量处理进度日志。"""
        logger.info(f"{stage_name}进度 {index}/{total}: {entity_id}")

    @performance_monitor(level="DEBUG")
    def _update_champions(self, data: dict) -> None:
        """
        处理英雄数据，按英雄ID分别生成文件

        :param data: 包含英雄数据的字典
        """
        logger.info("开始处理英雄音频数据...")
        self.champion_banks_dir.mkdir(parents=True, exist_ok=True)
        self.champion_events_dir.mkdir(parents=True, exist_ok=True)

        champions = data.get("champions", {})
        sorted_champion_ids = sorted(champions.keys(), key=int)

        total_champions = len(sorted_champion_ids)
        for index, champion_id in enumerate(sorted_champion_ids, start=1):
            champion_data = champions[champion_id]
            self._log_simple_progress("处理英雄", index, total_champions, champion_id)
            self._process_champion_skins(champion_data, champion_id)

        logger.success(f"英雄Banks数据更新完成，共处理 {total_champions} 个英雄")

    @performance_monitor(level="DEBUG")
    def _process_champion_skins(self, champion_data: ChampionData, champion_id: str) -> None:
        """
        处理单个英雄的所有皮肤，提取音频数据并生成独立文件

        :param champion_data: 英雄数据字典
        :param champion_id: 英雄ID
        """
        alias_raw = champion_data.get("alias", "")
        alias = alias_raw.lower()
        if not alias:
            return

        # 检查是否需要更新
        banks_file_base = self.champion_banks_dir / champion_id
        events_file_base = self.champion_events_dir / champion_id

        if not needs_update(
            banks_file_base, self.version, self.force_update, dev_mode=self._is_dev_mode()
        ) and not needs_update(events_file_base, self.version, self.force_update, dev_mode=self._is_dev_mode()):
            logger.trace(f"英雄 {champion_id} ({alias}) 的数据已是最新，跳过处理")
            return

        skin_id_by_path: dict[str, str] = {}
        skins_data = champion_data.get("skins", [])
        sorted_skins_data = sorted(skins_data, key=lambda s: int(s["id"]))

        base_skin_id = None
        for skin in sorted_skins_data:
            skin_id_str = str(skin["id"])
            if skin.get("isBase"):
                base_skin_id = skin_id_str

            if bin_path := skin.get("binPath"):
                skin_id_by_path[bin_path] = skin_id_str
            for chroma in skin.get("chromas", []):
                chroma_id_str = str(chroma["id"])
                if bin_path := chroma.get("binPath"):
                    skin_id_by_path[bin_path] = chroma_id_str

        if not skin_id_by_path:
            return

        bin_paths = list(skin_id_by_path)
        root_wad_path = champion_data.get("wad", {}).get("root")
        full_wad_path = self.game_path / root_wad_path if root_wad_path else None
        local_required_dir = Path("data") / "characters" / alias_raw
        try:
            logger.trace(f"从 {alias} 提取 {len(bin_paths)} 个BIN文件")
            bin_raws = self.bin_source._extract_bin_raws(
                wad_path=full_wad_path,
                bin_paths=bin_paths,
                entity_label=f"英雄 {champion_id} ({alias})",
                local_required_dir=local_required_dir,
            )
            if not bin_raws or not bin_raws[0]:
                logger.warning(f"英雄 {champion_id} ({alias}) 的首个BIN缺失或为空，跳过处理")
                return
            raw_data_map = dict(zip(bin_paths, bin_raws, strict=False))
        except (FileNotFoundError, ValueError):
            logger.opt(exception=True).error(f"处理英雄 {alias} 的本地BIN时出错")
            return
        except Exception:
            logger.opt(exception=True).error(f"处理英雄 {alias} 的WAD文件时出错")
            return

        sorted_skin_ids = sorted(skin_id_by_path.values(), key=int)
        path_by_skin_id = {skin_id: path for path, skin_id in skin_id_by_path.items()}

        # 初始化英雄的banks和events数据
        champion_banks_data = self.bin_source._create_base_data(
            champion_id, "champion", alias=alias, skinAudioMappings={}, skins={}
        )

        champion_skin_events = {}
        owner_by_fingerprint: dict[tuple, str] = {}

        for skin_id in sorted_skin_ids:
            path = path_by_skin_id[skin_id]
            if not (bin_raw := raw_data_map.get(path)):
                continue

            try:
                bin_file = BIN(bin_raw)
                is_new_skin_entry = True

                for group in bin_file.data:
                    for event_data in group.bank_units:
                        if event_data.bank_path:
                            bank_fingerprint = tuple(sorted(event_data.bank_path))
                            category = event_data.category

                            if owner_id := owner_by_fingerprint.get(bank_fingerprint):
                                if skin_id != owner_id and "_Base_" not in category:
                                    if skin_id not in champion_banks_data["skinAudioMappings"]:
                                        champion_banks_data["skinAudioMappings"][skin_id] = {}
                                    champion_banks_data["skinAudioMappings"][skin_id][category] = owner_id
                            else:
                                owner_by_fingerprint[bank_fingerprint] = skin_id
                                if skin_id not in champion_banks_data["skins"]:
                                    champion_banks_data["skins"][skin_id] = {}
                                if category not in champion_banks_data["skins"][skin_id]:
                                    champion_banks_data["skins"][skin_id][category] = []
                                champion_banks_data["skins"][skin_id][category].append(event_data.bank_path)

                                if is_new_skin_entry and self.process_events:
                                    if skin_events := self._extract_skin_events(bin_file, base_skin_id, skin_id):
                                        champion_skin_events[skin_id] = skin_events
                                    is_new_skin_entry = False

            except Exception:
                logger.opt(exception=True).error(f"解析皮肤BIN失败: {path}")
                if self._is_dev_mode():
                    raise

        # 优化映射关系
        self._optimize_champion_mappings(champion_banks_data)

        # 写入banks数据
        if needs_update(banks_file_base, self.version, self.force_update, dev_mode=self._is_dev_mode()):
            write_data(champion_banks_data, banks_file_base, dev_mode=self._is_dev_mode())

        # 写入events数据
        if champion_skin_events and needs_update(
            events_file_base,
            self.version,
            self.force_update,
            dev_mode=self._is_dev_mode(),
        ):
            final_event_data = self.bin_source._create_base_data(
                champion_id, "champion", alias=alias, skins=champion_skin_events
            )
            write_data(final_event_data, events_file_base, dev_mode=self._is_dev_mode())

    def _extract_skin_events(self, bin_file: BIN, base_skin_id: str | None, current_skin_id: str) -> dict | None:
        """
        提取一个皮肤BIN文件中的所有事件数据

        :param bin_file: BIN文件对象
        :param base_skin_id: 基础皮肤ID，用于过滤基础皮肤事件
        :param current_skin_id: 当前皮肤ID
        :returns: 皮肤事件数据字典，无数据时返回None
        """
        skin_events = {}
        if bin_file.theme_music:
            skin_events["theme_music"] = bin_file.theme_music

        events_by_category = {}
        for group in bin_file.data:
            if group.music:
                skin_events["music"] = group.music.to_dict()
            for event_data in group.bank_units:
                if base_skin_id and current_skin_id != base_skin_id and "_Base_" in event_data.category:
                    continue
                if event_data.events:
                    category = event_data.category
                    if category not in events_by_category:
                        events_by_category[category] = []
                    event_strings = [e.string for e in event_data.events]
                    # 添加到category，稍后统一去重
                    events_by_category[category].extend(event_strings)

        if events_by_category:
            # 对每个category的事件列表进行去重
            for category, events_list in events_by_category.items():
                events_by_category[category] = list(dict.fromkeys(events_list))  # 保持顺序的去重
            skin_events["events"] = events_by_category

        return skin_events if skin_events else None

    def _optimize_champion_mappings(self, champion_data: dict) -> None:
        """
        优化单个英雄的映射关系，将部分共享升级为完全共享

        :param champion_data: 英雄数据字典
        """
        for skin_id, mappings in champion_data["skinAudioMappings"].copy().items():
            if not isinstance(mappings, dict):
                continue

            owner_ids = set(mappings.values())
            if len(owner_ids) == 1:
                owner_id = owner_ids.pop()
                if skin_id not in champion_data["skins"]:
                    champion_data["skinAudioMappings"][skin_id] = owner_id
