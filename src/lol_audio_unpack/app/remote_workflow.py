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
from .results import EntityResult, ResultStatus, RunResult, StageResult
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
        update_fn: Callable[..., StageResult],
        extract_fn: Callable[..., StageResult],
        mapping_fn: Callable[..., StageResult],
        cleanup_fn: Callable[[], None],
        build_entity_data_fn: Callable[..., AudioEntityData],
        resolve_audio_paths_fn: Callable[[AudioEntityData], tuple[Path, ...]],
        get_reader_fn: Callable[[], DataReader],
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
            get_reader_fn: 获取当前 app-owned 数据读取器的回调。
            remote_preparer_factory: 构造远端准备器的回调。
        """
        self.ctx = ctx
        self._update = update_fn
        self._extract = extract_fn
        self._mapping = mapping_fn
        self._cleanup = cleanup_fn
        self._build_entity_data = build_entity_data_fn
        self._resolve_audio_paths = resolve_audio_paths_fn
        self._get_reader = get_reader_fn
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

    @staticmethod
    def _cleanup_result(*, scope: str, error: Exception) -> StageResult:
        """将清理异常保留为独立结果，避免覆盖触发清理的原始失败。"""
        logger.error("remote {} 清理失败：{}", scope, error)
        return StageResult.from_error("cleanup", error, note=f"{scope}后的远端产物清理失败。")

    def _cleanup_after(self, *, scope: str) -> StageResult | None:
        """执行一次清理，并把普通运行时失败转成可聚合结果。"""
        try:
            self._cleanup()
        except Exception as exc:  # noqa: BLE001
            return self._cleanup_result(scope=scope, error=exc)
        return None

    @staticmethod
    def _entity_name(entity_data: AudioEntityData | None, work_item: RemoteEntityWorkItem) -> str:
        """返回可用于结果和进度展示的实体名称。"""
        if entity_data is not None:
            return entity_data.entity_name
        return f"{work_item.entity_type} {work_item.entity_id}"

    @staticmethod
    def _entity_result_from_stage(
        result: StageResult,
        *,
        work_item: RemoteEntityWorkItem,
        entity_name: str,
    ) -> EntityResult:
        """将单实体 facade 结果规范为远端工作项结果。"""
        source = next(
            (
                entity
                for entity in result.entities
                if entity.entity_type == work_item.entity_type and entity.entity_id == work_item.entity_id
            ),
            None,
        )
        status = source.status if source is not None else result.status or ResultStatus.FAILED
        return EntityResult(
            entity_type=work_item.entity_type,
            entity_id=work_item.entity_id,
            entity_name=entity_name,
            status=status,
            error_type=(source.error_type if source is not None else result.error_type),
            error_message=(source.error_message if source is not None else result.error_message),
            artifacts=source.artifacts if source is not None else (),
        )

    @staticmethod
    def _merge_entity_artifacts(
        entity: EntityResult | None,
        confirmed: tuple[str, ...],
    ) -> tuple[EntityResult | None, tuple[str, ...]]:
        """合并当前与此前 attempt 已确认的实体产物证据。"""
        if entity is None:
            return None, confirmed
        artifacts = tuple(dict.fromkeys((*confirmed, *entity.artifacts)))
        return replace(entity, artifacts=artifacts), artifacts

    def _notify_entity_completion(  # noqa: PLR0913
        self,
        *,
        work_item: RemoteEntityWorkItem,
        entity_data: AudioEntityData,
        status: ResultStatus,
        audio_output_paths: tuple[Path, ...],
        mapping_output_path: Path | None,
        index: int,
        total: int,
        on_entity_complete: Callable[[RemoteEntityCallbackPayload], None] | None,
        progress_callback: Callable[[int, int, str], None] | None,
    ) -> None:
        """报告含已确认产物的成功或部分成功实体。"""
        has_artifact = bool(audio_output_paths or mapping_output_path is not None)
        is_completed = status is ResultStatus.SUCCESS or (status is ResultStatus.PARTIAL and has_artifact)
        if progress_callback is not None and is_completed:
            progress_callback(
                index,
                total,
                f"{self._entity_name(entity_data, work_item)} {self._operation_name(work_item)}完成",
            )
        if on_entity_complete is not None and is_completed and (audio_output_paths or mapping_output_path is not None):
            on_entity_complete(
                RemoteEntityCallbackPayload(
                    entity_type=work_item.entity_type,
                    entity_id=work_item.entity_id,
                    audio_output_paths=audio_output_paths,
                    mapping_output_path=mapping_output_path,
                )
            )

    @staticmethod
    def _operation_name(work_item: RemoteEntityWorkItem) -> str:
        """返回当前实体工作项的用户可见操作名称。"""
        if work_item.need_extract and work_item.need_mapping:
            return "解包/映射"
        if work_item.need_extract:
            return "解包"
        return "映射"

    def _resolve_completed_artifacts(  # noqa: PLR0913
        self,
        *,
        entity_data: AudioEntityData,
        extract_entity: EntityResult | None,
        mapping_entity: EntityResult | None,
    ) -> tuple[tuple[Path, ...], Path | None]:
        """只从 typed entity result 的落盘证据解析完成回调路径。"""

        def is_within(path: Path, root: Path) -> bool:
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                return False
            return True

        confirmed_audio_files = (
            tuple(path for raw_path in extract_entity.artifacts if (path := Path(raw_path)).is_file())
            if extract_entity is not None
            else ()
        )
        audio_paths = tuple(
            root
            for root in self._resolve_audio_paths(entity_data)
            if any(is_within(path, root) for path in confirmed_audio_files)
        )
        mapping_path = (
            next(
                (path for raw_path in mapping_entity.artifacts if (path := Path(raw_path)).is_file()),
                None,
            )
            if mapping_entity is not None
            else None
        )
        return audio_paths, mapping_path

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

        reader = self._get_reader()
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
    ) -> RunResult:
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

        Returns:
            包含 update、extract、mapping 与失败 cleanup 阶段的整轮结果。
        """
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            raise ValueError("仅 remote_snapshot 模式支持按实体拆批执行。")
        if download_retry_attempts < 1:
            raise ValueError("download_retry_attempts 必须大于等于 1。")
        if entity_retry_attempts < 1:
            raise ValueError("entity_retry_attempts 必须大于等于 1。")

        stages: list[StageResult] = []
        cleanup_results: list[StageResult] = []
        if update_options is not None:
            try:
                update_result = self._update(update_options, target=update_target)
            except Exception as exc:  # noqa: BLE001
                update_result = StageResult.from_error("update", exc)
            finally:
                cleanup_result = self._cleanup_after(scope="update")
                if cleanup_result is not None:
                    cleanup_results.append(cleanup_result)
            stages.append(update_result)
            if update_result.status is not ResultStatus.SUCCESS:
                if cleanup_results:
                    stages.append(StageResult.combine("cleanup", cleanup_results))
                return RunResult(tuple(stages))

        if extract_options is None and mapping_options is None:
            if cleanup_results:
                stages.append(StageResult.combine("cleanup", cleanup_results))
            return RunResult(tuple(stages))

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
            if extract_options is not None:
                stages.append(StageResult("extract", note="没有待处理的远端实体。"))
            if mapping_options is not None:
                stages.append(StageResult("mapping", note="没有待处理的远端实体。"))
            if cleanup_results:
                stages.append(StageResult.combine("cleanup", cleanup_results))
            return RunResult(tuple(stages))

        total_work_items = len(work_items)
        logger.info(f"remote 模式启用单位驱动执行，共 {total_work_items} 个实体工作项。")
        reader = self._get_reader()
        remote_preparer = self._remote_preparer_factory()
        extract_entities: list[EntityResult] = []
        mapping_entities: list[EntityResult] = []
        workflow_cancelled = False

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

            entity_data: AudioEntityData | None = None
            extract_artifacts: tuple[str, ...] = ()
            mapping_artifacts: tuple[str, ...] = ()
            last_extract_entity: EntityResult | None = None
            last_mapping_entity: EntityResult | None = None
            for entity_attempt in range(1, entity_retry_attempts + 1):
                extract_entity: EntityResult | None = None
                mapping_entity: EntityResult | None = None
                try:
                    is_champion = work_item.entity_type == "champion"
                    entity_data = self._build_entity_data(
                        reader,
                        entity_type=work_item.entity_type,
                        entity_id=work_item.entity_id,
                    )
                    champion_ids = (work_item.entity_id,) if is_champion else None
                    map_ids = (work_item.entity_id,) if not is_champion else None
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

                    extract_result: StageResult | None = None
                    mapping_result: StageResult | None = None
                    if work_item.need_extract and extract_options is not None:
                        extract_result = self._extract(
                            self._build_entity_options(
                                extract_options,
                                entity_type=work_item.entity_type,
                                entity_id=work_item.entity_id,
                            ),
                            include_champions=is_champion,
                            include_maps=not is_champion,
                            prepare_remote=False,
                        )
                        extract_entity = self._entity_result_from_stage(
                            extract_result,
                            work_item=work_item,
                            entity_name=self._entity_name(entity_data, work_item),
                        )
                        extract_entity, extract_artifacts = self._merge_entity_artifacts(
                            extract_entity,
                            extract_artifacts,
                        )
                        last_extract_entity = extract_entity
                    if (
                        work_item.need_mapping
                        and mapping_options is not None
                        and (extract_entity is None or extract_entity.status is not ResultStatus.CANCELLED)
                    ):
                        mapping_result = self._mapping(
                            self._build_entity_options(
                                mapping_options,
                                entity_type=work_item.entity_type,
                                entity_id=work_item.entity_id,
                            ),
                            include_champions=is_champion,
                            include_maps=not is_champion,
                            prepare_remote=False,
                        )
                        mapping_entity = self._entity_result_from_stage(
                            mapping_result,
                            work_item=work_item,
                            entity_name=self._entity_name(entity_data, work_item),
                        )
                        mapping_entity, mapping_artifacts = self._merge_entity_artifacts(
                            mapping_entity,
                            mapping_artifacts,
                        )
                        last_mapping_entity = mapping_entity

                    try:
                        extract_output_paths, mapping_output_path = self._resolve_completed_artifacts(
                            entity_data=entity_data,
                            extract_entity=extract_entity,
                            mapping_entity=mapping_entity,
                        )
                    except Exception as exc:  # noqa: BLE001
                        # 产物定位只服务于 GUI/进度回调，不能把已完成的解包或映射误判为失败。
                        logger.warning(
                            "remote 实体 {} {} 无法解析完成产物，将跳过完成回调：{}",
                            work_item.entity_type,
                            work_item.entity_id,
                            exc,
                        )
                        extract_output_paths, mapping_output_path = (), None
                    entity_results = tuple(
                        result
                        for result in (
                            extract_entity,
                            mapping_entity,
                        )
                        if result is not None
                    )
                    entity_status = StageResult.from_entities("remote", entity_results).status
                    if entity_status is ResultStatus.CANCELLED:
                        terminal_extract_entity = extract_entity or last_extract_entity
                        terminal_mapping_entity = mapping_entity or last_mapping_entity
                        if terminal_extract_entity is not None:
                            extract_entities.append(terminal_extract_entity)
                        if terminal_mapping_entity is not None:
                            mapping_entities.append(terminal_mapping_entity)
                        workflow_cancelled = True
                        logger.warning(
                            "remote 实体 {} {} 已取消，将停止后续实体与阶段",
                            work_item.entity_type,
                            work_item.entity_id,
                        )
                        break
                    if entity_status is not ResultStatus.SUCCESS:
                        if entity_attempt < entity_retry_attempts:
                            logger.warning(
                                "remote 实体 {} {} 返回非成功结果，准备重试 {}/{}",
                                work_item.entity_type,
                                work_item.entity_id,
                                entity_attempt + 1,
                                entity_retry_attempts,
                            )
                            continue
                        self._notify_entity_completion(
                            work_item=work_item,
                            entity_data=entity_data,
                            status=entity_status,
                            audio_output_paths=extract_output_paths,
                            mapping_output_path=mapping_output_path,
                            index=index,
                            total=total_work_items,
                            on_entity_complete=on_entity_complete,
                            progress_callback=progress_callback,
                        )
                        if extract_entity is not None:
                            extract_entities.append(extract_entity)
                        if mapping_entity is not None:
                            mapping_entities.append(mapping_entity)
                        logger.warning(
                            "remote 实体 {} {} 返回非成功结果，已超过重试阈值，将继续后续实体",
                            work_item.entity_type,
                            work_item.entity_id,
                        )
                        break
                    self._notify_entity_completion(
                        work_item=work_item,
                        entity_data=entity_data,
                        status=entity_status,
                        audio_output_paths=extract_output_paths,
                        mapping_output_path=mapping_output_path,
                        index=index,
                        total=total_work_items,
                        on_entity_complete=on_entity_complete,
                        progress_callback=progress_callback,
                    )
                    if extract_entity is not None:
                        extract_entities.append(extract_entity)
                    if mapping_entity is not None:
                        mapping_entities.append(mapping_entity)
                    break
                except Exception as exc:
                    if entity_attempt >= entity_retry_attempts:
                        entity_name = self._entity_name(entity_data, work_item)
                        if work_item.need_extract:
                            if extract_entity is None:
                                extract_entity = EntityResult.from_error(
                                    work_item.entity_type,
                                    work_item.entity_id,
                                    exc,
                                    entity_name=entity_name,
                                    artifacts=extract_artifacts,
                                )
                            extract_entities.append(extract_entity)
                        if work_item.need_mapping:
                            if mapping_entity is None:
                                mapping_entity = EntityResult.from_error(
                                    work_item.entity_type,
                                    work_item.entity_id,
                                    exc,
                                    entity_name=entity_name,
                                    artifacts=mapping_artifacts,
                                )
                            mapping_entities.append(mapping_entity)
                        if entity_data is not None:
                            try:
                                extract_output_paths, mapping_output_path = self._resolve_completed_artifacts(
                                    entity_data=entity_data,
                                    extract_entity=extract_entity,
                                    mapping_entity=mapping_entity,
                                )
                            except Exception as artifact_exc:  # noqa: BLE001
                                logger.warning(
                                    "remote 实体 {} {} 无法解析完成产物，将跳过完成回调：{}",
                                    work_item.entity_type,
                                    work_item.entity_id,
                                    artifact_exc,
                                )
                            else:
                                terminal_status = StageResult.from_entities(
                                    "remote",
                                    tuple(result for result in (extract_entity, mapping_entity) if result is not None),
                                ).status
                                self._notify_entity_completion(
                                    work_item=work_item,
                                    entity_data=entity_data,
                                    status=terminal_status,
                                    audio_output_paths=extract_output_paths,
                                    mapping_output_path=mapping_output_path,
                                    index=index,
                                    total=total_work_items,
                                    on_entity_complete=on_entity_complete,
                                    progress_callback=progress_callback,
                                )
                        logger.warning(
                            "remote 实体 {} {} 执行失败，已超过重试阈值，将继续后续实体：{}",
                            work_item.entity_type,
                            work_item.entity_id,
                            exc,
                        )
                        break
                    logger.warning(
                        "remote 实体 {} {} 执行失败，准备重试 {}/{}：{}",
                        work_item.entity_type,
                        work_item.entity_id,
                        entity_attempt + 1,
                        entity_retry_attempts,
                        exc,
                    )
                finally:
                    cleanup_result = self._cleanup_after(
                        scope=(f"实体 {work_item.entity_type} {work_item.entity_id} 第 {entity_attempt} 次尝试")
                    )
                    if cleanup_result is not None:
                        cleanup_results.append(cleanup_result)
            if workflow_cancelled:
                break

        if extract_options is not None and (extract_entities or not workflow_cancelled):
            stages.append(StageResult.from_entities("extract", extract_entities))
        if mapping_options is not None and (mapping_entities or not workflow_cancelled):
            stages.append(StageResult.from_entities("mapping", mapping_entities))
        if cleanup_results:
            stages.append(StageResult.combine("cleanup", cleanup_results))
        result = RunResult(tuple(stages))
        if result.status is ResultStatus.SUCCESS:
            logger.success(f"remote 实体工作流完成：共处理 {total_work_items} 个实体工作项")
        elif result.status is ResultStatus.PARTIAL:
            logger.warning(f"remote 实体工作流部分完成：共处理 {total_work_items} 个实体工作项")
        else:
            logger.error(f"remote 实体工作流失败：共处理 {total_work_items} 个实体工作项")
        return result


__all__ = [
    "DEFAULT_DOWNLOAD_RETRIES",
    "DEFAULT_ENTITY_RETRIES",
    "RemoteWorkflowOrchestrator",
]
