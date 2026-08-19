"""本地与预处理游戏资源的 BIN 更新辅助逻辑。

该模块负责协调 BIN 来源选择、资源提取，以及更新流程中的
元数据刷新。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.app.game_version import resolve_game_version
from lol_audio_unpack.app.targets import should_hide_champion_by_default
from lol_audio_unpack.manager.bin_source import BinSource
from lol_audio_unpack.manager.champion_bin_processor import ChampionBinProcessor
from lol_audio_unpack.manager.files import read_data
from lol_audio_unpack.manager.map_bin_processor import MapBinProcessor
from lol_audio_unpack.utils.logging import performance_monitor
from lol_audio_unpack.utils.run_summary import record_runtime_note

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext


class BinUpdater:
    """
    负责从BIN文件提取音频数据并更新到数据文件中

    支持可选的事件处理：设置 process_events=False 可显著提升处理速度，但不会生成事件数据
    """

    def __init__(
        self,
        force_update: bool = False,
        process_events: bool = True,
        *,
        ctx: AppContext,
    ):
        """
        初始化BIN音频更新器

        :param force_update: 是否强制更新，忽略版本检查
        :param process_events: 是否处理事件数据（默认True，设置为False可大幅提升处理速度）
        :param ctx: 运行时上下文。
        """
        self.ctx = ctx
        self.game_path = Path(self.ctx.config.game_path)
        self.manifest_path = Path(self.ctx.paths.manifest_path)

        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.force_update = force_update
        self.process_events = process_events
        self.version: str = resolve_game_version(self.ctx)
        self.version_manifest_path: Path = self.manifest_path / self.version
        self.data_file_base: Path = self.version_manifest_path / "data"
        self.use_local_bin_flag_file: Path = self.version_manifest_path / ".use_local_bin"
        self.local_bin_input_dir: Path = self.version_manifest_path / "bin_input"
        self.champion_banks_dir: Path = self.version_manifest_path / "banks" / "champions"
        self.map_banks_dir: Path = self.version_manifest_path / "banks" / "maps"
        self.champion_events_dir: Path = self.version_manifest_path / "events" / "champions"
        self.map_events_dir: Path = self.version_manifest_path / "events" / "maps"
        self.languages: list[str] = []  # 在update()中初始化

        # 拆分后的协作对象：BIN 来源 + 英雄/地图处理器
        self.bin_source = BinSource(
            ctx=self.ctx,
            game_path=self.game_path,
            version=self.version,
            local_bin_input_dir=self.local_bin_input_dir,
            use_local_bin_flag_file=self.use_local_bin_flag_file,
            languages=self.languages,
        )
        self._champion_processor = ChampionBinProcessor(
            self.bin_source,
            ctx=self.ctx,
            version=self.version,
            force_update=self.force_update,
            process_events=self.process_events,
            game_path=self.game_path,
            champion_banks_dir=self.champion_banks_dir,
            champion_events_dir=self.champion_events_dir,
        )
        self._map_processor = MapBinProcessor(
            self.bin_source,
            ctx=self.ctx,
            version=self.version,
            force_update=self.force_update,
            process_events=self.process_events,
            map_banks_dir=self.map_banks_dir,
            map_events_dir=self.map_events_dir,
            languages=self.languages,
        )

    def _is_dev_mode(self) -> bool:
        """返回当前运行是否为开发模式。"""
        return bool(self.ctx.config.dev_mode)

    def _filter_default_champions(self, data: dict) -> dict:
        """过滤默认批量更新中应隐藏的特殊英雄。

        Args:
            data: 完整的聚合元数据。

        Returns:
            保留原元数据结构、仅替换英雄集合的新字典。
        """
        champions = data.get("champions", {})
        visible = {
            champion_id: champion
            for champion_id, champion in champions.items()
            if not should_hide_champion_by_default(champion)
        }
        return {**data, "champions": visible}

    @logger.catch
    @performance_monitor(level="INFO")
    def update(
        self,
        target: str = "all",
        champion_ids: list[str] | None = None,
        map_ids: list[str] | None = None,
    ) -> None:
        """
        处理BIN文件，提取皮肤和地图的音频路径和事件数据

        :param target: 处理目标，可选值：'all', 'skin', 'map'。当指定具体IDs时该参数被忽略
        :param champion_ids: 指定要处理的英雄ID列表，为None时处理所有英雄
        :param map_ids: 指定要处理的地图ID列表，为None时处理所有地图
        """
        data = read_data(self.data_file_base, dev_mode=self._is_dev_mode())
        if not data:
            logger.error(f"数据文件不存在，请先运行DataUpdater: {self.data_file_base}")
            raise FileNotFoundError(f"数据文件不存在: {self.data_file_base}")

        self.languages = data.get("metadata", {}).get("languages", [])
        # 将运行期解析出的语言列表同步给协作对象
        self.bin_source.languages = self.languages
        self._map_processor.languages = self.languages
        local_bin_mode_enabled = self.bin_source._is_local_bin_mode_enabled()

        # 根据传入的IDs构建筛选后的数据
        if champion_ids or map_ids:
            # 精确模式：根据具体ID筛选数据
            filtered_data = self._filter_data_by_ids(data, champion_ids, map_ids)
            champion_count = len(filtered_data.get("champions", {}))
            map_count = len(filtered_data.get("maps", {}))
            logger.info(
                f"开始更新 BIN 数据（精确模式）：英雄 {champion_count} 个，地图 {map_count} 个，"
                f"事件处理={'开启' if self.process_events else '关闭'}，"
                f"本地BIN模式={'开启' if local_bin_mode_enabled else '关闭'}"
            )
            if champion_ids and filtered_data.get("champions"):
                self._champion_processor._update_champions(filtered_data)
            if map_ids and filtered_data.get("maps"):
                self._record_map_event_scope_note(map_ids)
                self._map_processor._update_maps(filtered_data)
            logger.success(f"BinUpdater 更新完成（精确模式）：英雄 {champion_count} 个，地图 {map_count} 个")
        else:
            # 批量模式：使用target控制
            batch_data = self._filter_default_champions(data) if target in ["skin", "all"] else data
            champion_count = len(batch_data.get("champions", {})) if target in ["skin", "all"] else 0
            hidden_count = len(data.get("champions", {})) - champion_count if target in ["skin", "all"] else 0
            map_count = len(data.get("maps", {})) if target in ["map", "all"] else 0
            logger.info(
                f"开始更新 BIN 数据（批量模式）：target={target}，英雄 {champion_count} 个，地图 {map_count} 个，"
                f"事件处理={'开启' if self.process_events else '关闭'}，"
                f"本地BIN模式={'开启' if local_bin_mode_enabled else '关闭'}"
            )
            if hidden_count:
                logger.info(f"默认批量更新已排除 {hidden_count} 个隐藏英雄实体")
            if target in ["skin", "all"]:
                self._champion_processor._update_champions(batch_data)
            if target in ["map", "all"]:
                self._map_processor._update_maps(data)
            logger.success(f"BinUpdater 更新完成（批量模式）：英雄 {champion_count} 个，地图 {map_count} 个")

    def _record_map_event_scope_note(self, map_ids: list[str]) -> None:
        """记录精确地图更新在未包含 Common 地图时的事件差异说明。"""
        if not self.process_events or "0" in map_ids:
            return

        normalized_ids = [map_id for map_id in map_ids if map_id]
        if not normalized_ids:
            return

        message = "本次仅处理指定地图且未包含 Common 地图 0，地图事件不会应用公共事件去重；结果可能与全量更新不同。"
        detail = f"精确地图更新目标: {normalized_ids}；由于未包含地图 0，Common 事件差量规则不会参与本次运行。"
        record_runtime_note(self.ctx.runtime_cache, "update", message, label="数据更新", detail=detail)

    def _filter_data_by_ids(self, data: dict, champion_ids: list[str] | None, map_ids: list[str] | None) -> dict:
        """
        根据指定的ID列表筛选数据

        :param data: 完整的数据字典
        :param champion_ids: 要筛选的英雄ID列表
        :param map_ids: 要筛选的地图ID列表
        :returns: 筛选后的数据字典，保持原有结构
        """
        filtered_data: dict = {
            # 其他基础字段保持不变
        }

        # 筛选英雄数据
        if champion_ids:
            all_champions = data.get("champions", {})
            filtered_champions = {}
            for champion_id in champion_ids:
                if champion_id in all_champions:
                    filtered_champions[champion_id] = all_champions[champion_id]
                else:
                    logger.warning(f"指定的英雄ID {champion_id} 在数据中不存在")
            if filtered_champions:
                filtered_data["champions"] = filtered_champions

        # 筛选地图数据
        if map_ids:
            all_maps = data.get("maps", {})
            filtered_maps = {}
            for map_id in map_ids:
                if map_id in all_maps:
                    filtered_maps[map_id] = all_maps[map_id]
                else:
                    logger.warning(f"指定的地图ID {map_id} 在数据中不存在")
            if filtered_maps:
                filtered_data["maps"] = filtered_maps

        return filtered_data
