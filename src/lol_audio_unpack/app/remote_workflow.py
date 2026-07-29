"""远端快照模式的按实体拆批执行编排。

从 ``LolAudioUnpackApp`` 抽出，专责 ``remote_snapshot`` 模式下的实体工作项构建、
逐实体下载/解包/映射、失败重试与每轮清理。标准操作（update/extract/mapping/cleanup）、
实体解析（构建实体数据、解析输出路径）以及读取器/远端准备器的构造均通过回调注入，
避免反向依赖 facade，也让远端工作流可独立单测。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from riotmanifest import DecompressError, DownloadBatchError, DownloadError

from .remote import RemoteEntityCallbackPayload, RemoteEntityWorkItem
from .targets import iter_entity_refs
from .types import AppContext, OperationOptions, SourceMode

if TYPE_CHECKING:
    from lol_audio_unpack.manager import DataReader
    from lol_audio_unpack.model import AudioEntityData
    from lol_audio_unpack.runtime.remote import RemotePreparer

DEFAULT_DOWNLOAD_RETRIES = 3
DEFAULT_ENTITY_RETRIES = 3


class RemoteWorkflowOrchestrator:
    """remote_snapshot 模式下按实体拆批执行的工作流编排器。"""

    def __init__(  # noqa: PLR0913
        self,
        ctx: AppContext,
        *,
        update_fn: Callable[..., None],
        extract_fn: Callable[..., None],
        mapping_fn: Callable[..., None],
        cleanup_fn: Callable[[], None],
        build_entity_data_fn: Callable[..., AudioEntityData],
        resolve_audio_paths_fn: Callable[[AudioEntityData], tuple[Path, ...]],
        resolve_mapping_path_fn: Callable[..., Path | None],
        create_reader_fn: Callable[[], DataReader],
        remote_preparer_factory: Callable[[], RemotePreparer],
    ) -> None:
        """初始化编排器。

        Args:
            ctx: 应用运行上下文。
            update_fn: 标准 update 操作（签名同 ``LolAudioUnpackApp.update``）。
            extract_fn: 标准 extract 操作（签名同 ``LolAudioUnpackApp.extract``）。
            mapping_fn: 标准 mapping 操作（签名同 ``LolAudioUnpackApp.mapping``）。
            cleanup_fn: 远端产物清理（签名同 ``cleanup_remote_artifacts``）。
            build_entity_data_fn: 构建实体数据的回调。
            resolve_audio_paths_fn: 解析实体解包输出目录的回调。
            resolve_mapping_path_fn: 解析实体 mapping 产物路径的回调。
            create_reader_fn: 构造数据读取器的回调。
            remote_preparer_factory: 构造远端准备器的回调。
        """
        self.ctx = ctx
        self._update = update_fn
        self._extract = extract_fn
        self._mapping = mapping_fn
        self._cleanup = cleanup_fn
        self._build_entity_data = build_entity_data_fn
        self._resolve_audio_paths = resolve_audio_paths_fn
        self._resolve_mapping_path = resolve_mapping_path_fn
        self._create_reader = create_reader_fn
        self._remote_preparer_factory = remote_preparer_factory

    @staticmethod
    def _merge_remote_work_item(
        work_items: dict[tuple[str, int], RemoteEntityWorkItem],
        *,
        entity_type: str,
        entity_id: int,
        need_extract: bool,
        need_mapping: bool,
    ) -> None:
        """注册或合并远端实体工作项。"""
        key = (entity_type, entity_id)
        existing = work_items.get(key)
        if existing is None:
            work_items[key] = RemoteEntityWorkItem(
                entity_type=entity_type,
                entity_id=entity_id,
                need_extract=need_extract,
                need_mapping=need_mapping,
            )
            return

        work_items[key] = RemoteEntityWorkItem(
            entity_type=entity_type,
            entity_id=entity_id,
            need_extract=existing.need_extract or need_extract,
            need_mapping=existing.need_mapping or need_mapping,
        )

    def _register_remote_work_items(  # noqa: PLR0913
        self,
        work_items: dict[tuple[str, int], RemoteEntityWorkItem],
        *,
        reader: DataReader,
        opts: OperationOptions | None,
        need_extract: bool,
        need_mapping: bool,
        include_champions: bool,
        include_maps: bool,
    ) -> None:
        """根据操作范围生成远端实体工作项。"""
        if opts is None:
            return

        for entity_type, entity_id in iter_entity_refs(
            reader,
            champion_ids=opts.champion_ids,
            map_ids=opts.map_ids,
            include_champions=include_champions,
            include_maps=include_maps,
        ):
            self._merge_remote_work_item(
                work_items,
                entity_type=entity_type,
                entity_id=entity_id,
                need_extract=need_extract,
                need_mapping=need_mapping,
            )

    @staticmethod
    def _build_entity_options(
        opts: OperationOptions,
        *,
        entity_type: str,
        entity_id: int,
    ) -> OperationOptions:
        """将批量操作选项收窄为单实体选项。"""
        is_champion = entity_type == "champion"
        return replace(
            opts,
            champion_ids=(entity_id,) if is_champion else None,
            map_ids=(entity_id,) if not is_champion else None,
        )

    @staticmethod
    def _is_retryable_download_error(exc: BaseException) -> bool:
        """判断是否属于可重试的远端下载错误。"""
        return isinstance(exc, (DownloadError, DecompressError, DownloadBatchError))

    def _prepare_entity_wads(  # noqa: PLR0913
        self,
        remote_preparer: RemotePreparer,
        *,
        reader: DataReader,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
        include_champions: bool,
        include_maps: bool,
        need_extract: bool,
        need_mapping: bool,
        download_retry_attempts: int,
        work_item: RemoteEntityWorkItem,
        entity_attempt: int,
        entity_retry_attempts: int,
    ) -> None:
        """按下载错误重试准备单实体所需 WAD。"""
        for download_attempt in range(1, download_retry_attempts + 1):
            try:
                remote_preparer.prepare_entity_wads(
                    reader=reader,
                    champion_ids=champion_ids,
                    map_ids=map_ids,
                    include_champions=include_champions,
                    include_maps=include_maps,
                    need_extract=need_extract,
                    need_mapping=need_mapping,
                )
                return
            except Exception as exc:
                if not self._is_retryable_download_error(exc):
                    raise
                if download_attempt >= download_retry_attempts:
                    raise
                logger.warning(
                    "remote 实体 {} {} 下载 WAD 失败，准备重试 {}/{}（实体重试 {}/{}）：{}",
                    work_item.entity_type,
                    work_item.entity_id,
                    download_attempt + 1,
                    download_retry_attempts,
                    entity_attempt,
                    entity_retry_attempts,
                    exc,
                )

    def _raise_entity_failure(
        self,
        *,
        work_item: RemoteEntityWorkItem,
        entity_retry_attempts: int,
        exc: Exception,
    ) -> None:
        """在实体重试耗尽后抛出带上下文的错误。"""
        raise RuntimeError(
            "remote 实体执行失败且已超过重试阈值："
            f"{work_item.entity_type} {work_item.entity_id} 已尝试 {entity_retry_attempts} 次；"
            "当前解包脚本可能无法正常解包，可能是网络持续异常、二进制文件版本更新或上游资源结构变化导致。"
        ) from exc

    def build_work_items(  # noqa: PLR0913
        self,
        *,
        extract_options: OperationOptions | None = None,
        mapping_options: OperationOptions | None = None,
        extract_include_champions: bool = True,
        extract_include_maps: bool = True,
        mapping_include_champions: bool = True,
        mapping_include_maps: bool = True,
    ) -> list[RemoteEntityWorkItem]:
        """构建 remote 模式下的实体工作项队列。

        Args:
            extract_options: extract 阶段的操作选项；为 ``None`` 表示不执行 extract。
            mapping_options: mapping 阶段的操作选项；为 ``None`` 表示不执行 mapping。
            extract_include_champions: extract 阶段是否包含英雄。
            extract_include_maps: extract 阶段是否包含地图。
            mapping_include_champions: mapping 阶段是否包含英雄。
            mapping_include_maps: mapping 阶段是否包含地图。

        Returns:
            已按实体类型与 ID 排序的工作项列表。

        Raises:
            ValueError: 当前不是 ``remote_snapshot`` 模式。
        """
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            raise ValueError("仅 remote_snapshot 模式支持按实体拆批执行。")

        reader = self._create_reader()
        work_items: dict[tuple[str, int], RemoteEntityWorkItem] = {}
        self._register_remote_work_items(
            work_items,
            reader=reader,
            opts=extract_options,
            need_extract=True,
            need_mapping=False,
            include_champions=extract_include_champions,
            include_maps=extract_include_maps,
        )
        self._register_remote_work_items(
            work_items,
            reader=reader,
            opts=mapping_options,
            need_extract=False,
            need_mapping=True,
            include_champions=mapping_include_champions,
            include_maps=mapping_include_maps,
        )
        return sorted(
            work_items.values(),
            key=lambda item: (item.entity_type != "champion", item.entity_id),
        )

    def run_workflow(  # noqa: PLR0913
        self,
        *,
        update_options: OperationOptions | None = None,
        update_target: str = "all",
        extract_options: OperationOptions | None = None,
        mapping_options: OperationOptions | None = None,
        extract_include_champions: bool = True,
        extract_include_maps: bool = True,
        mapping_include_champions: bool = True,
        mapping_include_maps: bool = True,
        on_entity_complete: Callable[[RemoteEntityCallbackPayload], None] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        download_retry_attempts: int = DEFAULT_DOWNLOAD_RETRIES,
        entity_retry_attempts: int = DEFAULT_ENTITY_RETRIES,
    ) -> None:
        """按实体拆批执行 remote 流程，并在每轮后清理远端产物。

        Args:
            update_options: 可选的 update 选项；提供时会先执行一次全局 update。
            update_target: update 阶段目标，语义与 ``update(..., target=...)`` 相同。
            extract_options: extract 阶段的操作选项；为 ``None`` 表示跳过。
            mapping_options: mapping 阶段的操作选项；为 ``None`` 表示跳过。
            extract_include_champions: extract 阶段是否包含英雄。
            extract_include_maps: extract 阶段是否包含地图。
            mapping_include_champions: mapping 阶段是否包含英雄。
            mapping_include_maps: mapping 阶段是否包含地图。
            on_entity_complete: 当前实体执行完成后的可选回调。
            progress_callback: 每个实体处理结束后的可选进度回调。
            download_retry_attempts: 单次实体尝试内，WAD 下载类错误的最大重试次数。
            entity_retry_attempts: 单实体完整流程失败时的最大重试次数。

        Raises:
            ValueError: 当前不是 ``remote_snapshot`` 模式。
        """
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            raise ValueError("仅 remote_snapshot 模式支持按实体拆批执行。")
        if download_retry_attempts < 1:
            raise ValueError("download_retry_attempts 必须大于等于 1。")
        if entity_retry_attempts < 1:
            raise ValueError("entity_retry_attempts 必须大于等于 1。")

        if update_options is not None:
            self._update(update_options, target=update_target)
            self._cleanup()

        if extract_options is None and mapping_options is None:
            return

        work_items = self.build_work_items(
            extract_options=extract_options,
            mapping_options=mapping_options,
            extract_include_champions=extract_include_champions,
            extract_include_maps=extract_include_maps,
            mapping_include_champions=mapping_include_champions,
            mapping_include_maps=mapping_include_maps,
        )
        if not work_items:
            logger.warning("remote 模式未生成任何实体工作项。")
            return

        total_work_items = len(work_items)
        logger.info(f"remote 模式启用单位驱动执行，共 {total_work_items} 个实体工作项。")
        reader = self._create_reader()
        remote_preparer = self._remote_preparer_factory()

        for index, work_item in enumerate(work_items, start=1):
            logger.info(
                "remote 单位进度 {}/{}: {} {} (extract={}, mapping={})",
                index,
                total_work_items,
                work_item.entity_type,
                work_item.entity_id,
                work_item.need_extract,
                work_item.need_mapping,
            )

            for entity_attempt in range(1, entity_retry_attempts + 1):
                is_champion = work_item.entity_type == "champion"
                entity_data = self._build_entity_data(
                    reader,
                    entity_type=work_item.entity_type,
                    entity_id=work_item.entity_id,
                )
                champion_ids = (work_item.entity_id,) if is_champion else None
                map_ids = (work_item.entity_id,) if not is_champion else None
                try:
                    self._prepare_entity_wads(
                        remote_preparer,
                        reader=reader,
                        champion_ids=champion_ids,
                        map_ids=map_ids,
                        include_champions=is_champion,
                        include_maps=not is_champion,
                        need_extract=work_item.need_extract,
                        need_mapping=work_item.need_mapping,
                        download_retry_attempts=download_retry_attempts,
                        work_item=work_item,
                        entity_attempt=entity_attempt,
                        entity_retry_attempts=entity_retry_attempts,
                    )

                    extract_output_paths: tuple[Path, ...] = ()
                    mapping_output_path: Path | None = None
                    if work_item.need_extract and extract_options is not None:
                        self._extract(
                            self._build_entity_options(
                                extract_options,
                                entity_type=work_item.entity_type,
                                entity_id=work_item.entity_id,
                            ),
                            include_champions=is_champion,
                            include_maps=not is_champion,
                            prepare_remote=False,
                        )
                        extract_output_paths = self._resolve_audio_paths(entity_data)
                    if work_item.need_mapping and mapping_options is not None:
                        self._mapping(
                            self._build_entity_options(
                                mapping_options,
                                entity_type=work_item.entity_type,
                                entity_id=work_item.entity_id,
                            ),
                            include_champions=is_champion,
                            include_maps=not is_champion,
                            prepare_remote=False,
                        )
                        mapping_output_path = self._resolve_mapping_path(
                            entity_type=work_item.entity_type,
                            entity_id=work_item.entity_id,
                            integrate_data=mapping_options.integrate_data,
                        )
                    if progress_callback is not None:
                        operation_name = "解包/映射"
                        if work_item.need_extract and not work_item.need_mapping:
                            operation_name = "解包"
                        elif work_item.need_mapping and not work_item.need_extract:
                            operation_name = "映射"
                        progress_callback(
                            index,
                            total_work_items,
                            f"{entity_data.entity_name} {operation_name}完成",
                        )
                    if on_entity_complete is not None and (extract_output_paths or mapping_output_path is not None):
                        on_entity_complete(
                            RemoteEntityCallbackPayload(
                                entity_type=work_item.entity_type,
                                entity_id=work_item.entity_id,
                                audio_output_paths=extract_output_paths,
                                mapping_output_path=mapping_output_path,
                            )
                        )
                    break
                except Exception as exc:
                    if entity_attempt >= entity_retry_attempts:
                        self._raise_entity_failure(
                            work_item=work_item,
                            entity_retry_attempts=entity_retry_attempts,
                            exc=exc,
                        )
                    logger.warning(
                        "remote 实体 {} {} 执行失败，准备重试 {}/{}：{}",
                        work_item.entity_type,
                        work_item.entity_id,
                        entity_attempt + 1,
                        entity_retry_attempts,
                        exc,
                    )
                finally:
                    self._cleanup()

        logger.success(f"remote 实体工作流完成：共处理 {total_work_items} 个实体工作项")


__all__ = [
    "DEFAULT_DOWNLOAD_RETRIES",
    "DEFAULT_ENTITY_RETRIES",
    "RemoteWorkflowOrchestrator",
]
