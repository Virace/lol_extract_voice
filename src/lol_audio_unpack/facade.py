"""模块化应用门面。

该模块为 CLI 与外部模块调用提供统一编排入口，避免直接操作底层
Manager 与流程函数。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from loguru import logger
from riotmanifest import DecompressError, DownloadBatchError, DownloadError

from lol_audio_unpack.app_context import AppContext, OperationOptions, SourceMode
from lol_audio_unpack.manager import BinUpdater, DataReader, DataUpdater
from lol_audio_unpack.manager.data_reader import get_default_visible_champions
from lol_audio_unpack.mapping import (
    build_champions_mapping,
    build_mapping_all,
    build_maps_mapping,
    describe_hirc_backend,
)
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.runtime.remote import RemotePreparer
from lol_audio_unpack.unpack import unpack_all, unpack_champions, unpack_maps
from lol_audio_unpack.utils.path_constants import format_entity_folder_name, get_output_dir_name

DEFAULT_REMOTE_DOWNLOAD_RETRY_ATTEMPTS = 3
DEFAULT_REMOTE_ENTITY_RETRY_ATTEMPTS = 3
UPDATE_DATA_PREPARED_FORCE_CACHE_KEY = "update_data_prepared_force"


@dataclass(frozen=True)
class RemoteEntityWorkItem:
    """remote 模式下的最小实体工作项。"""

    entity_type: str
    entity_id: int
    need_extract: bool
    need_mapping: bool


@dataclass(frozen=True)
class RemoteEntityCallbackPayload:
    """remote 单位驱动完成后的回调载荷。"""

    entity_type: str
    entity_id: int
    audio_output_paths: tuple[Path, ...] = ()
    mapping_output_path: Path | None = None


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

    def _prepare_remote_snapshot_for_update(self) -> RemotePreparer | None:
        """在远端快照模式下准备更新流程所需的远端资源。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return None

        logger.info("检测到 remote_snapshot 模式，开始准备 LCU 最小运行环境...")
        preparer = RemotePreparer(ctx=self.ctx)
        preparer.prepare_lcu_data()
        return preparer

    def _is_update_data_prepared(self, *, force_update: bool) -> bool:
        """判断当前上下文是否已完成数据预热。"""
        cached_force_update = self.ctx.runtime_cache.get(UPDATE_DATA_PREPARED_FORCE_CACHE_KEY)
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
        remote_preparer = self._prepare_remote_snapshot_for_update()
        if not self._is_update_data_prepared(force_update=force_update):
            DataUpdater(force_update=force_update, ctx=self.ctx).check_and_update()
            self.ctx.runtime_cache[UPDATE_DATA_PREPARED_FORCE_CACHE_KEY] = force_update
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

    def _build_remote_preparer(self) -> RemotePreparer | None:
        """按需创建远端准备器。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return None
        return RemotePreparer(ctx=self.ctx)

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

        has_explicit_targets = False
        if opts.champion_ids is not None:
            has_explicit_targets = True
            if include_champions:
                for champion_id in opts.champion_ids:
                    self._merge_remote_work_item(
                        work_items,
                        entity_type="champion",
                        entity_id=champion_id,
                        need_extract=need_extract,
                        need_mapping=need_mapping,
                    )

        if opts.map_ids is not None:
            has_explicit_targets = True
            if include_maps:
                for map_id in opts.map_ids:
                    self._merge_remote_work_item(
                        work_items,
                        entity_type="map",
                        entity_id=map_id,
                        need_extract=need_extract,
                        need_mapping=need_mapping,
                    )

        if has_explicit_targets:
            return

        if include_champions:
            for champion in get_default_visible_champions(reader):
                champion_id = champion.get("id")
                if champion_id is None:
                    continue
                self._merge_remote_work_item(
                    work_items,
                    entity_type="champion",
                    entity_id=int(champion_id),
                    need_extract=need_extract,
                    need_mapping=need_mapping,
                )

        if include_maps:
            for map_data in reader.get_maps():
                map_id = map_data.get("id")
                if map_id is None:
                    continue
                self._merge_remote_work_item(
                    work_items,
                    entity_type="map",
                    entity_id=int(map_id),
                    need_extract=need_extract,
                    need_mapping=need_mapping,
                )

    @staticmethod
    def _build_entity_operation_options(
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

    def _build_entity_data(
        self,
        reader: DataReader,
        *,
        entity_type: str,
        entity_id: int,
        include_events: bool = False,
    ) -> AudioEntityData:
        """根据工作项构建实体数据。"""
        if entity_type == "champion":
            return AudioEntityData.from_champion(entity_id, reader, include_events=include_events, ctx=self.ctx)
        return AudioEntityData.from_map(entity_id, reader, include_events=include_events, ctx=self.ctx)

    def _resolve_extract_output_paths(self, entity_data: AudioEntityData) -> tuple[Path, ...]:
        """解析实体解包后的实际输出目录。"""
        audio_base = Path(self.ctx.paths.audio_path)
        entity_dir = get_output_dir_name(entity_data.entity_type)
        entity_folder_name = format_entity_folder_name(
            entity_data.entity_id,
            entity_data.entity_alias,
            entity_data.entity_name,
            entity_data.entity_title,
        )
        version_audio_root = audio_base / self._create_reader().version

        if self.ctx.config.group_by_type:
            paths = tuple(
                candidate
                for audio_type in self.ctx.config.include_types
                if (candidate := version_audio_root / audio_type / entity_dir / entity_folder_name).exists()
            )
            return paths

        candidate = version_audio_root / entity_dir / entity_folder_name
        if candidate.exists():
            return (candidate,)
        return ()

    def _resolve_mapping_output_path(self, *, entity_type: str, entity_id: int, integrate_data: bool) -> Path | None:
        """解析实体 mapping 的最终产物路径。"""
        version_hash_root = Path(self.ctx.paths.hash_path) / self._create_reader().version
        entity_dir = get_output_dir_name(entity_type)
        if integrate_data:
            base_path = version_hash_root / "integrated" / entity_dir / str(entity_id)
        else:
            base_path = version_hash_root / entity_dir / str(entity_id)

        suffix = ".yml" if self.ctx.config.dev_mode else ".msgpack"
        output_path = base_path.with_suffix(suffix)
        if output_path.exists():
            return output_path
        return None

    @staticmethod
    def _is_retryable_remote_download_error(exc: BaseException) -> bool:
        """判断是否属于可重试的远端下载错误。"""
        return isinstance(exc, (DownloadError, DecompressError, DownloadBatchError))

    def _prepare_remote_entity_wads_with_retries(  # noqa: PLR0913
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
                if not self._is_retryable_remote_download_error(exc):
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

    def _raise_remote_entity_failure(
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

    def cleanup_remote_artifacts(self) -> None:
        """在 remote 模式下按配置清理已登记的远端产物。"""
        if self.ctx.config.source_mode is not SourceMode.REMOTE_SNAPSHOT:
            return
        if not self.ctx.config.cleanup_remote:
            logger.info("remote_snapshot 模式已显式关闭自动清理，保留远端准备产物。")
            return

        preparer = self._build_remote_preparer()
        if preparer is None:
            return
        cleanup_result = preparer.cleanup_artifacts()
        if cleanup_result:
            logger.info(f"远端准备产物清理完成: {cleanup_result}")

    def build_remote_entity_work_items(  # noqa: PLR0913
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

    def run_remote_entity_workflow(  # noqa: PLR0913
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
        download_retry_attempts: int = DEFAULT_REMOTE_DOWNLOAD_RETRY_ATTEMPTS,
        entity_retry_attempts: int = DEFAULT_REMOTE_ENTITY_RETRY_ATTEMPTS,
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
            self.update(update_options, target=update_target)
            self.cleanup_remote_artifacts()

        if extract_options is None and mapping_options is None:
            return

        work_items = self.build_remote_entity_work_items(
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
        remote_preparer = RemotePreparer(ctx=self.ctx)

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
                    self._prepare_remote_entity_wads_with_retries(
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
                        remote_wav_handle = self.extract(
                            self._build_entity_operation_options(
                                extract_options,
                                entity_type=work_item.entity_type,
                                entity_id=work_item.entity_id,
                            ),
                            include_champions=is_champion,
                            include_maps=not is_champion,
                            prepare_remote=False,
                            detach_wav=bool(extract_options.wav_output.enabled),
                            wav_job_label=f"remote-{work_item.entity_type}-{work_item.entity_id}",
                        )
                        if remote_wav_handle is not None and remote_wav_handle.poll() is None:
                            logger.info(
                                "remote 实体 {} {} 的 WAV 转码已转入后台进程。",
                                work_item.entity_type,
                                work_item.entity_id,
                            )
                        extract_output_paths = self._resolve_extract_output_paths(entity_data)
                    if work_item.need_mapping and mapping_options is not None:
                        self.mapping(
                            self._build_entity_operation_options(
                                mapping_options,
                                entity_type=work_item.entity_type,
                                entity_id=work_item.entity_id,
                            ),
                            include_champions=is_champion,
                            include_maps=not is_champion,
                            prepare_remote=False,
                        )
                        mapping_output_path = self._resolve_mapping_output_path(
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
                        self._raise_remote_entity_failure(
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
                    self.cleanup_remote_artifacts()

        logger.success(f"remote 实体工作流完成：共处理 {total_work_items} 个实体工作项")

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

    def extract(  # noqa: PLR0913
        self,
        opts: OperationOptions,
        *,
        include_champions: bool = True,
        include_maps: bool = True,
        prepare_remote: bool = True,
        progress_callback: Callable[[str, int, int, str], None] | None = None,
        detach_wav: bool = False,
        wav_job_label: str | None = None,
        persisted_wem_callback: Callable[[Path], None] | None = None,
    ) -> object | None:
        """执行解包流程。

        Args:
            opts: 解包操作选项。
            include_champions: 是否包含英雄。
            include_maps: 是否包含地图。
            prepare_remote: 是否在 remote 模式下预准备所需资源。
            progress_callback: 每个实体处理结束后的可选进度回调。
        """
        reader = self._create_reader()
        remote_preparer = self._build_remote_preparer()
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
                wav_output=opts.wav_output,
                detach_wav=detach_wav,
                wav_job_label=wav_job_label,
                persisted_wem_callback=persisted_wem_callback,
            )
        if opts.map_ids is not None:
            return unpack_maps(
                reader=reader,
                map_ids=list(opts.map_ids),
                max_workers=opts.max_workers,
                ctx=self.ctx,
                progress_callback=progress_callback,
                wav_output=opts.wav_output,
                detach_wav=detach_wav,
                wav_job_label=wav_job_label,
                persisted_wem_callback=persisted_wem_callback,
            )

        return unpack_all(
            reader=reader,
            max_workers=opts.max_workers,
            include_champions=include_champions,
            include_maps=include_maps,
            ctx=self.ctx,
            progress_callback=progress_callback,
            wav_output=opts.wav_output,
            detach_wav=detach_wav,
            wav_job_label=wav_job_label,
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
        remote_preparer = self._build_remote_preparer()
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
            build_champions_mapping(
                reader=reader,
                champion_ids=list(opts.champion_ids),
                max_workers=opts.max_workers,
                integrate_data=opts.integrate_data,
                ctx=self.ctx,
                progress_callback=progress_callback,
            )
            return
        if opts.map_ids is not None:
            build_maps_mapping(
                reader=reader,
                map_ids=list(opts.map_ids),
                max_workers=opts.max_workers,
                integrate_data=opts.integrate_data,
                ctx=self.ctx,
                progress_callback=progress_callback,
            )
            return

        build_mapping_all(
            reader=reader,
            max_workers=opts.max_workers,
            include_champions=include_champions,
            include_maps=include_maps,
            integrate_data=opts.integrate_data,
            ctx=self.ctx,
            progress_callback=progress_callback,
        )


__all__ = ["LolAudioUnpackApp", "RemoteEntityCallbackPayload", "RemoteEntityWorkItem"]
