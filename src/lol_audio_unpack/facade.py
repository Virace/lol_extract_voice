"""模块化应用门面。

该模块为 CLI 与外部模块调用提供统一编排入口，避免直接操作底层
Manager 与流程函数。
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from lol_audio_unpack.app_context import AppContext, OperationOptions, SourceMode
from lol_audio_unpack.manager import BinUpdater, DataReader, DataUpdater
from lol_audio_unpack.mapping import build_champions_mapping, build_mapping_all, build_maps_mapping
from lol_audio_unpack.remote_preparer import RemoteSnapshotPreparer
from lol_audio_unpack.unpack import unpack_audio_all, unpack_champions, unpack_maps


class LolAudioUnpackApp:
    """统一业务编排门面。"""

    def __init__(self, ctx: AppContext):
        """初始化门面。

        Args:
            ctx: 应用运行上下文。
        """
        self.ctx = ctx

    @staticmethod
    def _to_str_ids(ids: tuple[int, ...] | None) -> list[str] | None:
        """将整数 ID 元组转换为字符串列表。"""
        if ids is None:
            return None
        return [str(item) for item in ids]

    def _create_reader(self) -> DataReader:
        """创建数据读取器实例。"""
        return DataReader(ctx=self.ctx)

    def _ensure_wwiser_path(self) -> None:
        """校验 Wwiser 路径可用性。

        Raises:
            ValueError: 路径未配置或不存在。
        """
        wwiser_path = self.ctx.config.wwiser_path
        if wwiser_path is None:
            raise ValueError("错误：未找到有效的 Wwiser 工具路径 (WWISER_PATH)。")
        if not Path(wwiser_path).exists():
            raise ValueError(f"错误：Wwiser 工具路径不存在: {wwiser_path}")

    def _prepare_remote_snapshot_for_update(self) -> RemoteSnapshotPreparer | None:
        """在远端快照模式下准备更新流程所需的远端资源。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return None

        logger.info("检测到 remote_snapshot 模式，开始准备 LCU 最小运行环境...")
        preparer = RemoteSnapshotPreparer(ctx=self.ctx)
        preparer.prepare_lcu_game_data()
        return preparer

    def _build_remote_preparer(self) -> RemoteSnapshotPreparer | None:
        """按需创建远端准备器。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return None
        return RemoteSnapshotPreparer(ctx=self.ctx)

    def update(self, opts: OperationOptions, *, target: str = "all") -> None:
        """执行更新流程。"""
        remote_preparer = self._prepare_remote_snapshot_for_update()
        DataUpdater(force_update=opts.force_update, ctx=self.ctx).check_and_update()
        if remote_preparer is not None:
            remote_preparer.prepare_bin_inputs(
                reader=self._create_reader(),
                target=target,
                champion_ids=opts.champion_ids,
                map_ids=opts.map_ids,
            )
        updater = BinUpdater(force_update=opts.force_update, process_events=opts.process_events, ctx=self.ctx)
        updater.update(
            target=target,
            champion_ids=self._to_str_ids(opts.champion_ids),
            map_ids=self._to_str_ids(opts.map_ids),
        )

    def extract(
        self,
        opts: OperationOptions,
        *,
        include_champions: bool = True,
        include_maps: bool = True,
    ) -> None:
        """执行解包流程。"""
        reader = self._create_reader()
        remote_preparer = self._build_remote_preparer()
        if remote_preparer is not None:
            remote_preparer.prepare_extract_wads(
                reader=reader,
                champion_ids=opts.champion_ids,
                map_ids=opts.map_ids,
                include_champions=include_champions,
                include_maps=include_maps,
            )
        logger.info(
            f"音频类型配置 - 包含: {list(self.ctx.config.include_types)}, "
            f"排除: {list(self.ctx.config.exclude_types)}"
        )
        logger.info(f"输出路径: {self.ctx.config.output_path}")
        logger.info(f"语言: {self.ctx.config.game_region}")

        if opts.champion_ids is not None:
            unpack_champions(reader=reader, champion_ids=list(opts.champion_ids), max_workers=opts.max_workers, ctx=self.ctx)
            return
        if opts.map_ids is not None:
            unpack_maps(reader=reader, map_ids=list(opts.map_ids), max_workers=opts.max_workers, ctx=self.ctx)
            return

        unpack_audio_all(
            reader=reader,
            max_workers=opts.max_workers,
            include_champions=include_champions,
            include_maps=include_maps,
            ctx=self.ctx,
        )

    def mapping(
        self,
        opts: OperationOptions,
        *,
        include_champions: bool = True,
        include_maps: bool = True,
    ) -> None:
        """执行映射流程。"""
        self._ensure_wwiser_path()
        reader = self._create_reader()
        remote_preparer = self._build_remote_preparer()
        if remote_preparer is not None:
            remote_preparer.prepare_mapping_wads(
                reader=reader,
                champion_ids=opts.champion_ids,
                map_ids=opts.map_ids,
                include_champions=include_champions,
                include_maps=include_maps,
            )

        logger.info(f"缓存路径: {self.ctx.paths.cache_path}")
        logger.info(f"哈希路径: {self.ctx.paths.hash_path}")
        logger.info(f"Wwiser 路径: {self.ctx.config.wwiser_path}")
        logger.info(f"语言: {self.ctx.config.game_region}")

        if opts.champion_ids is not None:
            build_champions_mapping(
                reader=reader,
                champion_ids=list(opts.champion_ids),
                max_workers=opts.max_workers,
                integrate_data=opts.integrate_data,
                ctx=self.ctx,
            )
            return
        if opts.map_ids is not None:
            build_maps_mapping(
                reader=reader,
                map_ids=list(opts.map_ids),
                max_workers=opts.max_workers,
                integrate_data=opts.integrate_data,
                ctx=self.ctx,
            )
            return

        build_mapping_all(
            reader=reader,
            max_workers=opts.max_workers,
            include_champions=include_champions,
            include_maps=include_maps,
            integrate_data=opts.integrate_data,
            ctx=self.ctx,
        )


__all__ = ["LolAudioUnpackApp"]
