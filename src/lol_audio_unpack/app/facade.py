"""模块化应用门面。

该模块为 CLI 与外部模块调用提供统一编排入口，避免直接操作底层
Manager 与流程函数。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from loguru import logger

from lol_audio_unpack.manager import BinUpdater, DataReader, DataUpdater
from lol_audio_unpack.mapping import (
    build_all,
    build_champions,
    build_maps,
    describe_hirc_backend,
)
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.runtime.remote import RemotePreparer
from lol_audio_unpack.runtime.wav import TranscodeTarget, run_tree
from lol_audio_unpack.unpack import unpack_all, unpack_champions, unpack_maps

from .artifacts import resolve_audio_paths, resolve_mapping_path
from .path_layout import get_output_dir_name
from .remote import RemoteEntityCallbackPayload, RemoteEntityWorkItem
from .remote_workflow import RemoteWorkflowOrchestrator
from .types import AppContext, OperationOptions, SourceMode

UPDATE_PREPARED_KEY = "update_data_prepared_force"


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

    def _describe_mapping_backend(self) -> str:
        """返回 mapping 流程使用的 HIRC 后端。"""
        return describe_hirc_backend(self.ctx)

    def _prepare_remote_update(self) -> RemotePreparer | None:
        """在远端快照模式下准备更新流程所需的远端资源。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return None

        logger.info("检测到 remote_snapshot 模式，开始准备 LCU 最小运行环境...")
        preparer = RemotePreparer(ctx=self.ctx)
        preparer.prepare_lcu_data()
        return preparer

    def _is_update_prepared(self, *, force_update: bool) -> bool:
        """判断当前上下文是否已完成数据预热。"""
        cached_force_update = self.ctx.runtime_cache.get(UPDATE_PREPARED_KEY)
        if cached_force_update is True:
            return True
        if cached_force_update is False and not force_update:
            return True
        return False

    def prepare_update_data(self, *, force_update: bool = False) -> RemotePreparer | None:
        """预热 update 所需结构化数据，并复用当前运行中的缓存状态。

        Args:
            force_update: 是否强制刷新数据文件。

        Returns:
            remote 模式下返回远端准备器，否则返回 ``None``。
        """
        remote_preparer = self._prepare_remote_update()
        if not self._is_update_prepared(force_update=force_update):
            DataUpdater(force_update=force_update, ctx=self.ctx).check_and_update()
            self.ctx.runtime_cache[UPDATE_PREPARED_KEY] = force_update
        return remote_preparer

    def resolve_champion_ids(self, selectors: Sequence[int | str] | None) -> tuple[int, ...] | None:
        """将英雄选择器解析为稳定的英雄 ID 元组。

        Args:
            selectors: 英雄选择器序列，支持整数 ID、数字字符串或英雄 alias。

        Returns:
            解析后的英雄 ID 元组；当 ``selectors`` 为 ``None`` 时返回 ``None``。

        Raises:
            ValueError: 当选择器为空、alias 不存在或类型不支持时抛出。
        """
        if selectors is None:
            return None

        normalized_selectors: list[str | int] = []
        has_numeric_selector = False
        has_alias_selector = False
        for selector in selectors:
            if isinstance(selector, int):
                normalized_selectors.append(selector)
                has_numeric_selector = True
                continue

            raw_selector = str(selector).strip()
            if not raw_selector:
                raise ValueError("英雄选择器不能为空。")
            normalized_selectors.append(raw_selector)
            if raw_selector.isdigit():
                has_numeric_selector = True
            else:
                has_alias_selector = True

        if has_numeric_selector and has_alias_selector:
            raise ValueError("暂不支持在同一次英雄选择中混用 ID 与 alias。")
        if has_numeric_selector:
            return tuple(int(selector) for selector in normalized_selectors)

        reader = self._create_reader()
        champions = reader.get_champions()
        alias_to_id = {
            str(champion.get("alias", "")).strip().casefold(): int(champion["id"])
            for champion in champions
            if champion.get("id") is not None and champion.get("alias")
        }

        resolved_ids: list[int] = []
        unresolved_aliases: list[str] = []
        for selector in normalized_selectors:
            champion_id = alias_to_id.get(str(selector).casefold())
            if champion_id is None:
                unresolved_aliases.append(str(selector))
                continue
            resolved_ids.append(champion_id)

        if unresolved_aliases:
            available_aliases = sorted(champion.get("alias", "") for champion in champions if champion.get("alias"))
            raise ValueError(f"未找到对应的英雄 alias: {unresolved_aliases}。可用 alias 示例: {available_aliases[:10]}")

        return tuple(resolved_ids)

    def _create_remote_preparer(self) -> RemotePreparer | None:
        """按需创建远端准备器。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return None
        return RemotePreparer(ctx=self.ctx)

    def _build_entity_data(
        self,
        reader: DataReader,
        *,
        entity_type: str,
        entity_id: int,
        include_events: bool = False,
    ) -> AudioEntityData:
        """根据工作项构建实体数据。"""
        return AudioEntityData.from_entity(
            entity_type,
            entity_id,
            reader,
            include_events=include_events,
            ctx=self.ctx,
        )

    def _resolve_audio_paths(self, entity_data: AudioEntityData) -> tuple[Path, ...]:
        """解析实体解包后的实际输出目录。"""
        return resolve_audio_paths(self.ctx, entity_data, self._create_reader().version)

    def _resolve_mapping_path(self, *, entity_type: str, entity_id: int, integrate_data: bool) -> Path | None:
        """解析实体 mapping 的最终产物路径。"""
        return resolve_mapping_path(
            self.ctx,
            entity_dir=get_output_dir_name(entity_type),
            entity_id=entity_id,
            version=self._create_reader().version,
            integrate_data=integrate_data,
        )

    @staticmethod
    def _build_entity_display_name(entity_data: AudioEntityData) -> str:
        """构造与实体列表一致的展示名称。"""
        if entity_data.entity_title:
            return f"{entity_data.entity_name}·{entity_data.entity_title}"
        return entity_data.entity_name

    def cleanup_remote_artifacts(self) -> None:
        """在 remote 模式下按配置清理已登记的远端产物。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return
        if not self.ctx.config.cleanup_remote:
            logger.info("remote_snapshot 模式已显式关闭自动清理，保留远端准备产物。")
            return

        preparer = self._create_remote_preparer()
        if preparer is None:
            return
        cleanup_result = preparer.cleanup_artifacts()
        if cleanup_result:
            logger.info(f"远端准备产物清理完成: {cleanup_result}")

    def _remote_orchestrator(self) -> RemoteWorkflowOrchestrator:
        """构造远端工作流编排器，注入标准操作与实体解析回调。"""
        return RemoteWorkflowOrchestrator(
            self.ctx,
            update_fn=self.update,
            extract_fn=self.extract,
            mapping_fn=self.mapping,
            cleanup_fn=self.cleanup_remote_artifacts,
            build_entity_data_fn=self._build_entity_data,
            resolve_audio_paths_fn=self._resolve_audio_paths,
            resolve_mapping_path_fn=self._resolve_mapping_path,
            create_reader_fn=self._create_reader,
            remote_preparer_factory=lambda: RemotePreparer(ctx=self.ctx),
        )

    def build_work_items(self, **kwargs) -> list[RemoteEntityWorkItem]:
        """构建 remote 模式下的实体工作项队列（委托 RemoteWorkflowOrchestrator）。"""
        return self._remote_orchestrator().build_work_items(**kwargs)

    def run_workflow(self, **kwargs) -> None:
        """按实体拆批执行 remote 流程（委托 RemoteWorkflowOrchestrator）。"""
        self._remote_orchestrator().run_workflow(**kwargs)

    def update(self, opts: OperationOptions, *, target: str = "all") -> None:
        """执行更新流程。"""
        logger.info(
            f"开始执行更新流程：target={target}，英雄 {len(opts.champion_ids or ())} 个，"
            f"地图 {len(opts.map_ids or ())} 个，事件处理={'开启' if opts.process_events else '关闭'}"
        )
        remote_preparer = self.prepare_update_data(force_update=opts.force_update)
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
        logger.success(
            f"更新流程完成：target={target}，英雄 {len(opts.champion_ids or ())} 个，地图 {len(opts.map_ids or ())} 个"
        )

    def transcode_wav(
        self,
        opts: OperationOptions,
        *,
        progress_callback: Callable[[str, int, int, str], None] | None = None,
        job_label: str | None = None,
    ) -> dict[str, object]:
        """执行独立的 WAV 转码 stage。

        Args:
            opts: 当前工作流的操作选项。
            progress_callback: 可选的统一进度回调。
            job_label: 可选报告标签。

        Returns:
            dict[str, object]: WAV 转码汇总结果。
        """
        reader = self._create_reader()
        audio_targets: tuple[TranscodeTarget, ...] | None = None
        if opts.champion_ids is not None or opts.map_ids is not None:
            resolved_targets: list[TranscodeTarget] = []
            seen_roots: set[Path] = set()

            def add_roots(entity_type: str, ids: tuple[int, ...] | None) -> None:
                if ids is None:
                    return
                for entity_id in ids:
                    entity_data = self._build_entity_data(
                        reader,
                        entity_type=entity_type,
                        entity_id=entity_id,
                    )
                    display_label = self._build_entity_display_name(entity_data)
                    for root in self._resolve_audio_paths(entity_data):
                        if root not in seen_roots:
                            seen_roots.add(root)
                            resolved_targets.append(
                                TranscodeTarget(root_path=root, display_label=display_label)
                            )

            add_roots("champion", opts.champion_ids)
            add_roots("map", opts.map_ids)
            audio_targets = tuple(resolved_targets)
            if audio_targets:
                logger.info("音频转码将按目标实体目录处理，共 {} 个目录。", len(audio_targets))
            else:
                logger.warning("音频转码未找到任何目标实体音频目录，将跳过本次执行。")
        return run_tree(
            ctx=self.ctx,
            version=reader.version,
            wav_output=opts.wav_output,
            audio_targets=audio_targets,
            progress_callback=progress_callback,
            job_label=job_label,
        )

    def extract(  # noqa: PLR0913
        self,
        opts: OperationOptions,
        *,
        include_champions: bool = True,
        include_maps: bool = True,
        prepare_remote: bool = True,
        progress_callback: Callable[[str, int, int, str], None] | None = None,
        persisted_wem_callback: Callable[[Path], None] | None = None,
    ) -> None:
        """执行解包流程。

        Args:
            opts: 解包操作选项。
            include_champions: 是否包含英雄。
            include_maps: 是否包含地图。
            prepare_remote: 是否在 remote 模式下预准备所需资源。
            progress_callback: 每个实体处理结束后的可选进度回调。
        """
        reader = self._create_reader()
        remote_preparer = self._create_remote_preparer()
        if prepare_remote and remote_preparer is not None:
            remote_preparer.prepare_extract_wads(
                reader=reader,
                champion_ids=opts.champion_ids,
                map_ids=opts.map_ids,
                include_champions=include_champions,
                include_maps=include_maps,
            )
        logger.info(
            f"音频类型配置 - 包含: {list(self.ctx.config.include_types)}, 排除: {list(self.ctx.config.exclude_types)}"
        )
        logger.info(f"输出路径: {self.ctx.config.output_path}")
        logger.info(f"语言: {self.ctx.config.game_region}")

        if opts.champion_ids is not None:
            return unpack_champions(
                reader=reader,
                champion_ids=list(opts.champion_ids),
                max_workers=opts.max_workers,
                ctx=self.ctx,
                progress_callback=progress_callback,
                persisted_wem_callback=persisted_wem_callback,
            )
        if opts.map_ids is not None:
            unpack_maps(
                reader=reader,
                map_ids=list(opts.map_ids),
                max_workers=opts.max_workers,
                ctx=self.ctx,
                progress_callback=progress_callback,
                persisted_wem_callback=persisted_wem_callback,
            )
            return

        unpack_all(
            reader=reader,
            max_workers=opts.max_workers,
            include_champions=include_champions,
            include_maps=include_maps,
            ctx=self.ctx,
            progress_callback=progress_callback,
            persisted_wem_callback=persisted_wem_callback,
        )

    def mapping(
        self,
        opts: OperationOptions,
        *,
        include_champions: bool = True,
        include_maps: bool = True,
        prepare_remote: bool = True,
        progress_callback: Callable[[str, int, int, str], None] | None = None,
    ) -> None:
        """执行映射流程。"""
        backend_label = self._describe_mapping_backend()
        reader = self._create_reader()
        remote_preparer = self._create_remote_preparer()
        if prepare_remote and remote_preparer is not None:
            remote_preparer.prepare_mapping_wads(
                reader=reader,
                champion_ids=opts.champion_ids,
                map_ids=opts.map_ids,
                include_champions=include_champions,
                include_maps=include_maps,
            )

        logger.info(f"缓存路径: {self.ctx.paths.cache_path}")
        logger.info(f"哈希路径: {self.ctx.paths.hash_path}")
        logger.info(f"HIRC 后端: {backend_label}")
        logger.info(f"语言: {self.ctx.config.game_region}")

        if opts.champion_ids is not None:
            build_champions(
                reader=reader,
                champion_ids=list(opts.champion_ids),
                max_workers=opts.max_workers,
                integrate_data=opts.integrate_data,
                ctx=self.ctx,
                progress_callback=progress_callback,
            )
            return
        if opts.map_ids is not None:
            build_maps(
                reader=reader,
                map_ids=list(opts.map_ids),
                max_workers=opts.max_workers,
                integrate_data=opts.integrate_data,
                ctx=self.ctx,
                progress_callback=progress_callback,
            )
            return

        build_all(
            reader=reader,
            max_workers=opts.max_workers,
            include_champions=include_champions,
            include_maps=include_maps,
            integrate_data=opts.integrate_data,
            ctx=self.ctx,
            progress_callback=progress_callback,
        )


__all__ = ["LolAudioUnpackApp", "RemoteEntityCallbackPayload", "RemoteEntityWorkItem"]
