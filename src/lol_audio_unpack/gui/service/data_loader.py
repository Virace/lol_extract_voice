"""GUI 实体列表与映射文件的数据加载工具。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

from loguru import logger

from lol_audio_unpack.app.artifacts import (
    AudioIndexProgress,
    AudioRef,
    enumerate_audio_refs,
    resolve_audio_refs,
)
from lol_audio_unpack.app.artifacts import (
    resolve_audio_paths as resolve_artifact_audio_paths,
)
from lol_audio_unpack.app.artifacts import (
    resolve_mapping_path as resolve_artifact_mapping_path,
)
from lol_audio_unpack.app.path_layout import get_output_dir_name
from lol_audio_unpack.app.resource_pack import (
    ResourcePackSelectionError,
    ResourcePackWadRef,
    partition_special_targets,
)
from lol_audio_unpack.app.special_content import (
    DOOM_BOTS_PROFILE,
    HISTORICAL_RESOURCE_PACKS_PROFILE,
    SWARM_PROFILE,
    build_special_content_item,
    is_structured_special_champion,
)
from lol_audio_unpack.app.targets import (
    get_default_visible_champions,
    should_hide_champion_by_default,
)
from lol_audio_unpack.gui.shared_data import (
    SharedDataFailure,
    SharedDataProblem,
    SharedDataProblemCode,
    SharedDataProgress,
    SharedDataReadiness,
    SharedDataScanResult,
    SharedDataSectionResult,
)
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.manager.errors import (
    DataVersionMismatchError,
    ResourceSchemaMismatchError,
    SharedDataCorruptError,
    SharedDataMissingError,
)
from lol_audio_unpack.manager.files import find_data_file, read_data
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.model.binding import RESOURCE_SCHEMA_VERSION
from lol_audio_unpack.utils.common import sanitize_filename

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext

GuiEntityType = Literal["champions", "maps", "resource_packs"]


class _ArtifactCorruptError(ValueError):
    """表示已存在的共享 artifact 无法形成有效数据。"""


class _ResourceBindingIncompleteError(ValueError):
    """表示 v2 artifact 的 binding diagnostics 尚未完整。"""


_PROBLEM_MESSAGES = {
    SharedDataProblemCode.DATASET_MISSING: "当前版本的实体基础数据不存在。",
    SharedDataProblemCode.DATASET_STALE: "实体基础数据与当前版本不兼容。",
    SharedDataProblemCode.DATASET_EMPTY: "实体基础数据没有形成必需目录。",
    SharedDataProblemCode.BANK_ARTIFACT_MISSING: "共享 banks artifact 缺失或尚未生成。",
    SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH: "共享 banks artifact 仍使用旧版资源结构。",
    SharedDataProblemCode.RESOURCE_BINDING_INCOMPLETE: "共享 banks artifact 的资源绑定尚未完整。",
    SharedDataProblemCode.MAP_COMMON_MISSING: "地图目录缺少 Common 地图 0。",
    SharedDataProblemCode.ARTIFACT_CORRUPT: "共享 artifact 无法读取或缺少必要字段。",
    SharedDataProblemCode.OUTPUT_NOT_WRITABLE: "输出目录不可访问。",
    SharedDataProblemCode.SOURCE_UNAVAILABLE: "当前数据来源不可用。",
    SharedDataProblemCode.UNEXPECTED: "扫描共享实体数据时发生未分类错误。",
}


def _classify_scan_error(error: BaseException, *, dataset: bool = False) -> tuple[SharedDataProblemCode, str]:
    """把扫描异常映射为不依赖文案的稳定问题分类。"""
    if isinstance(error, ResourceSchemaMismatchError):
        code = SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH
    elif isinstance(error, _ResourceBindingIncompleteError):
        code = SharedDataProblemCode.RESOURCE_BINDING_INCOMPLETE
    elif isinstance(error, DataVersionMismatchError):
        code = SharedDataProblemCode.DATASET_STALE
    elif isinstance(error, SharedDataMissingError | FileNotFoundError):
        code = SharedDataProblemCode.DATASET_MISSING if dataset else SharedDataProblemCode.BANK_ARTIFACT_MISSING
    elif isinstance(error, PermissionError):
        code = SharedDataProblemCode.OUTPUT_NOT_WRITABLE
    elif isinstance(
        error, SharedDataCorruptError | _ArtifactCorruptError | KeyError | AttributeError | TypeError | ValueError
    ):
        code = SharedDataProblemCode.ARTIFACT_CORRUPT
    elif isinstance(error, OSError):
        code = SharedDataProblemCode.SOURCE_UNAVAILABLE
    else:
        code = SharedDataProblemCode.UNEXPECTED
    return code, _PROBLEM_MESSAGES[code]


def build_scan_failure_result(
    generation: int,
    error: BaseException,
) -> SharedDataScanResult:
    """把 reader 初始化阶段的预期失败转换为 typed 扫描结果。

    Args:
        generation: 扫描所属上下文代数。
        error: reader 初始化失败。

    Returns:
        不包含任何可信目录行的失败扫描结果。
    """
    code, message = _classify_scan_error(error, dataset=True)
    empty_champions = SharedDataSectionResult("champions", ())
    empty_maps = SharedDataSectionResult("maps", ())
    empty_special = SharedDataSectionResult("special", (), required=False)
    return SharedDataScanResult(
        generation=generation,
        version="",
        champions=empty_champions,
        maps=empty_maps,
        special=empty_special,
        problems=(SharedDataProblem(code, "dataset", message),),
    )


def _mapping_audio_paths(mapping_data: dict | None) -> tuple[str, ...]:
    """提取标准化 mapping 中事件明确引用的唯一 WEM 路径。"""
    paths: set[str] = set()
    if not isinstance(mapping_data, dict):
        return ()

    for root_key in ("skins", "map", "resourcePacks"):
        groups = mapping_data.get(root_key)
        if not isinstance(groups, dict):
            continue
        for group in groups.values():
            if not isinstance(group, dict):
                continue
            paths_by_type = group.get("audioPaths")
            if not isinstance(paths_by_type, dict):
                continue
            for paths_by_event in paths_by_type.values():
                if not isinstance(paths_by_event, dict):
                    continue
                for event_paths in paths_by_event.values():
                    if not isinstance(event_paths, list | tuple):
                        continue
                    paths.update(
                        normalized for path in event_paths if (normalized := str(path).replace("\\", "/").strip("/"))
                    )
    return tuple(sorted(paths))


def _build_mapping_preview_base(metadata: dict[str, object] | None) -> dict[str, object]:
    """构造预览适配后的基础映射数据。"""
    return {"metadata": dict(metadata) if isinstance(metadata, dict) else {}}


def _normalize_integrated_events(events_payload: object) -> dict[str, dict[str, list[object]]]:
    """把整合版事件节点还原成预览树可消费的 mapping 结构。

    Args:
        events_payload: 整合版 ``events`` 原始节点。

    Returns:
        与普通 mapping 对齐的 ``{category: {event_name: [audio_ids]}}`` 结构。
    """
    normalized_events: dict[str, dict[str, list[object]]] = {}
    if not isinstance(events_payload, dict):
        return normalized_events

    for category, category_payload in events_payload.items():
        if not isinstance(category_payload, dict):
            continue
        mapping_payload = category_payload.get("mapping")
        if not isinstance(mapping_payload, dict):
            continue
        normalized_events[str(category)] = {
            str(event_name): list(audio_ids)
            for event_name, audio_ids in mapping_payload.items()
            if isinstance(audio_ids, list | tuple)
        }

    return normalized_events


def _normalize_integrated_audio_paths(events_payload: object) -> dict[str, dict[str, list[str]]]:
    """保留整合版事件节点中的精确 WEM 相对路径。

    Args:
        events_payload: 整合版 ``audioPaths`` 原始节点。

    Returns:
        与普通 mapping 对齐的 ``{category: {event_name: [relative_path]}}`` 结构。
    """
    normalized_paths: dict[str, dict[str, list[str]]] = {}
    if not isinstance(events_payload, dict):
        return normalized_paths

    for category, event_payload in events_payload.items():
        if not isinstance(event_payload, dict):
            continue
        paths_by_event: dict[str, list[str]] = {}
        for event_name, paths in event_payload.items():
            if not isinstance(paths, list | tuple):
                continue
            normalized = [str(path).strip() for path in paths if str(path).strip()]
            if normalized:
                paths_by_event[str(event_name)] = normalized
        if paths_by_event:
            normalized_paths[str(category)] = paths_by_event

    return normalized_paths


def _normalize_integrated_mapping_data(  # noqa: PLR0911
    mapping_data: dict[str, object] | None,
    *,
    entity_type: GuiEntityType,
    entity_id: str,
) -> dict[str, object] | None:
    """把整合版 mapping 数据投影成当前预览页使用的普通视图。

    Args:
        mapping_data: 原始 mapping 数据。
        entity_type: GUI 实体类型目录名。
        entity_id: 当前实体 ID。

    Returns:
        若输入是整合版结构，则返回适配后的普通 mapping 视图；否则原样返回。
    """
    if not isinstance(mapping_data, dict):
        return mapping_data

    data_payload = mapping_data.get("data")
    if not isinstance(data_payload, dict):
        return mapping_data

    normalized = _build_mapping_preview_base(mapping_data.get("metadata"))

    if entity_type == "champions":
        skins_payload = data_payload.get("skins")
        if not isinstance(skins_payload, list):
            return mapping_data

        normalized["championId"] = data_payload.get("championId", entity_id)
        normalized["alias"] = data_payload.get("alias", "")
        normalized_skins: dict[str, dict[str, object]] = {}
        for skin_payload in skins_payload:
            if not isinstance(skin_payload, dict):
                continue
            skin_id = str(skin_payload.get("id", "")).strip()
            if not skin_id:
                continue

            normalized_events = _normalize_integrated_events(skin_payload.get("events"))
            normalized_paths = _normalize_integrated_audio_paths(skin_payload.get("audioPaths"))
            if normalized_events or normalized_paths:
                normalized_skin: dict[str, object] = {"events": normalized_events}
                if normalized_paths:
                    normalized_skin["audioPaths"] = normalized_paths
                normalized_skins[skin_id] = normalized_skin

        normalized["skins"] = normalized_skins
        return normalized

    if entity_type == "resource_packs":
        resource_pack = data_payload.get("resourcePack")
        if not isinstance(resource_pack, dict):
            return mapping_data
        key = str(resource_pack.get("key", entity_id)).strip()
        if not key:
            return mapping_data
        normalized_events = _normalize_integrated_events(resource_pack.get("events"))
        normalized_paths = _normalize_integrated_audio_paths(resource_pack.get("audioPaths"))
        normalized_pack: dict[str, object] = {"events": normalized_events}
        if normalized_paths:
            normalized_pack["audioPaths"] = normalized_paths
        normalized["resourcePackKey"] = key
        normalized["resourcePacks"] = {key: normalized_pack}
        return normalized

    map_payload = data_payload.get("map")
    if not isinstance(map_payload, dict):
        return mapping_data

    normalized["mapId"] = data_payload.get("mapId", entity_id)
    normalized["name"] = data_payload.get("name", "")
    normalized_events = _normalize_integrated_events(map_payload.get("events"))
    normalized_map: dict[str, object] = {"events": normalized_events}
    normalized_paths = _normalize_integrated_audio_paths(map_payload.get("audioPaths"))
    if normalized_paths:
        normalized_map["audioPaths"] = normalized_paths
    normalized["map"] = {str(data_payload.get("mapId", entity_id)): normalized_map}
    return normalized


def resolve_entity_audio_paths(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
) -> tuple[Path, ...]:
    """解析实体解包后的实际输出目录。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。

    Returns:
        实际存在的音频输出目录列表。
    """
    return resolve_artifact_audio_paths(ctx, entity_data, version)


def resolve_mapping_file_path(
    ctx: AppContext,
    entity_type: GuiEntityType,
    entity_id: str,
    version: str,
) -> Path | None:
    """解析实体映射文件的实际路径。

    Args:
        ctx: 当前应用上下文。
        entity_type: GUI 使用的实体类型目录名。
        entity_id: 实体 ID。
        version: 当前数据版本号。

    Returns:
        映射文件的实际路径；不存在时返回 ``None``。
    """
    return resolve_artifact_mapping_path(
        ctx,
        entity_dir=entity_type,
        entity_id=entity_id,
        version=version,
    )


def check_entity_status(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
) -> tuple[str, str]:
    """检查实体的解包和映射状态。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。

    Returns:
        音频状态与映射状态组成的二元组。
    """
    audio_paths = resolve_entity_audio_paths(ctx, entity_data, version)
    audio_exists = any(path.exists() and any(path.iterdir()) for path in audio_paths)

    mapping_path = resolve_mapping_file_path(
        ctx,
        get_output_dir_name(entity_data.entity_type),
        str(entity_data.entity_id),
        version,
    )
    mapping_exists = mapping_path is not None

    return (
        "已存在" if audio_exists else "未存在",
        "已存在" if mapping_exists else "未存在",
    )


class EntityDataLoader:
    """负责从解包目录加载实体数据和映射预览。"""

    def __init__(self, app_context: AppContext):
        """初始化 GUI 数据加载器。

        Args:
            app_context: 当前应用上下文。
        """
        self.ctx = app_context
        self.data_reader = DataReader(app_context)

    def _build_entity_data(self, entity_type: GuiEntityType, entity_id: str) -> AudioEntityData:
        """按 GUI 实体类型构造对应的实体数据对象。

        Args:
            entity_type: GUI 使用的实体类型目录名。
            entity_id: 实体 ID。

        Returns:
            对应实体的数据对象。
        """
        normalized_type = {
            "champions": "champion",
            "maps": "map",
            "resource_packs": "resource_pack",
        }[entity_type]
        return AudioEntityData.from_entity(
            normalized_type,
            entity_id if normalized_type == "resource_pack" else int(entity_id),
            self.data_reader,
            ctx=self.ctx,
        )

    def _load_raw_entities(self, entity_type: GuiEntityType) -> tuple[str, list[dict]]:
        """读取指定实体类型对应的原始实体列表与版本号。"""
        version = self.data_reader.version
        raw_data = (
            get_default_visible_champions(self.data_reader)
            if entity_type == "champions"
            else self.data_reader.get_maps()
        )
        return version, raw_data

    def _ensure_bank_dataset_ready(self, entity_type: GuiEntityType) -> None:
        """在按实体扫描前，先确认对应 bank 数据集根目录已经就绪。"""
        bank_root = {
            "champions": self.data_reader.champion_banks_dir,
            "maps": self.data_reader.map_banks_dir,
            "resource_packs": self.data_reader.resource_pack_banks_dir,
        }[entity_type]
        if bank_root.is_dir():
            return

        raise SharedDataMissingError(f"{entity_type} 共享 bank 数据目录不存在，请先运行更新程序。path={bank_root}")

    def _preload_bank_artifact(self, entity_type: Literal["champions", "maps"], entity_id: str) -> None:
        """静默校验并缓存扫描所需的单实体 banks artifact。

        预期的缺失、旧 schema 与损坏由完整扫描统一聚合；这里不在逐实体边界打印 traceback。
        """
        is_champion = entity_type == "champions"
        bank_root = self.data_reader.champion_banks_dir if is_champion else self.data_reader.map_banks_dir
        cache = self.data_reader._champion_banks_cache if is_champion else self.data_reader._map_banks_cache
        numeric_id = int(entity_id)
        if numeric_id in cache:
            payload = cache[numeric_id]
        else:
            base_path = bank_root / entity_id
            dev_mode = bool(getattr(self.ctx.config, "dev_mode", False))
            if find_data_file(base_path, dev_mode=dev_mode) is None:
                raise SharedDataMissingError(f"{entity_type} {entity_id} 缺少 banks artifact")
            payload = read_data(base_path, dev_mode=dev_mode, log_errors=False)
            if not isinstance(payload, dict) or not payload:
                raise _ArtifactCorruptError(f"{entity_type} {entity_id} banks artifact 无法读取")
            cache[numeric_id] = payload

        if payload.get("resourceSchemaVersion") != RESOURCE_SCHEMA_VERSION:
            raise ResourceSchemaMismatchError(f"{entity_type} {entity_id} banks artifact 缺少 resource schema v2")
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            raise _ArtifactCorruptError(f"{entity_type} {entity_id} banks artifact 缺少 diagnostics")
        if diagnostics.get("completeness") != "complete":
            raise _ResourceBindingIncompleteError(f"{entity_type} {entity_id} resource bindings 未完整")

    @staticmethod
    def _emit_scan_progress(  # noqa: PLR0913
        callback: Callable[[SharedDataProgress], None] | None,
        *,
        generation: int,
        stage_key: str,
        event: Literal["started", "advanced", "finished"],
        current: int,
        total: int | None,
        entity_id: str | None = None,
    ) -> None:
        """向调用方发送单调的目录扫描进度。"""
        if callback is None:
            return
        callback(
            SharedDataProgress(
                generation=generation,
                stage_key=stage_key,
                event=event,
                current=current,
                total=total,
                entity_type=stage_key if entity_id is not None else None,
                entity_id=entity_id,
            )
        )

    def _failure_from_error(self, entity_id: str, error: BaseException) -> SharedDataFailure:
        """把逐实体错误转换为稳定失败条目，并保留首个未预期根因。"""
        code, message = _classify_scan_error(error)
        if code is SharedDataProblemCode.UNEXPECTED and self._first_scan_unexpected is None:
            self._first_scan_unexpected = error
        return SharedDataFailure(entity_id, code, message)

    def _scan_required_section(
        self,
        entity_type: Literal["champions", "maps"],
        raw_entities: list[dict],
        *,
        version: str,
        generation: int,
        progress: Callable[[SharedDataProgress], None] | None,
    ) -> SharedDataSectionResult:
        """扫描一个必需普通目录并保留全部成功与失败事实。"""
        entities_by_id: dict[str, dict] = {}
        duplicate_ids: list[str] = []
        missing_id_markers: list[str] = []
        for raw_index, entity in enumerate(raw_entities, start=1):
            entity_id = str(entity.get("id", "")).strip()
            if not entity_id:
                missing_id_markers.append(f"unknown:{raw_index}")
                continue
            if entity_id in entities_by_id:
                duplicate_ids.append(entity_id)
                continue
            entities_by_id[entity_id] = entity

        expected_ids = tuple(entities_by_id)
        total = len(expected_ids)
        self._emit_scan_progress(
            progress,
            generation=generation,
            stage_key=entity_type,
            event="started",
            current=0,
            total=total,
        )
        rows: list[dict] = []
        failures = [
            SharedDataFailure(entity_id, SharedDataProblemCode.ARTIFACT_CORRUPT, "基础数据中存在重复实体 ID。")
            for entity_id in duplicate_ids
        ]
        failures.extend(
            SharedDataFailure(marker, SharedDataProblemCode.ARTIFACT_CORRUPT, "基础数据条目缺少实体 ID。")
            for marker in missing_id_markers
        )

        root_error: BaseException | None = None
        try:
            self._ensure_bank_dataset_ready(entity_type)
        except Exception as exc:  # noqa: BLE001
            root_error = exc

        for index, (entity_id, entity) in enumerate(entities_by_id.items(), start=1):
            try:
                if root_error is not None:
                    raise root_error
                self._preload_bank_artifact(entity_type, entity_id)
                row = self._build_entity_row(entity_type, entity, version)
                if str(row.get("id", "")) != entity_id:
                    raise _ArtifactCorruptError(f"{entity_type} {entity_id} 行身份不一致")
                rows.append(row)
            except Exception as exc:  # noqa: BLE001
                failures.append(self._failure_from_error(entity_id, exc))
            self._emit_scan_progress(
                progress,
                generation=generation,
                stage_key=entity_type,
                event="advanced",
                current=index,
                total=total,
                entity_id=entity_id,
            )

        self._emit_scan_progress(
            progress,
            generation=generation,
            stage_key=entity_type,
            event="finished",
            current=total,
            total=total,
        )
        return SharedDataSectionResult(
            section=entity_type,
            expected_ids=expected_ids,
            rows=tuple(rows),
            failures=tuple(failures),
        )

    def _scan_special_section(
        self,
        champions: list[dict],
        *,
        version: str,
        generation: int,
        progress: Callable[[SharedDataProgress], None] | None,
    ) -> SharedDataSectionResult:
        """扫描可选特殊内容，并把未准备状态与阻断失败分开。"""
        ordinary_names = self._localized_ordinary_names(champions)
        candidates = []
        for champion in champions:
            if not is_structured_special_champion(champion):
                continue
            item = build_special_content_item(champion)
            if item is not None:
                candidates.append((champion, item))

        self._emit_scan_progress(
            progress,
            generation=generation,
            stage_key="special",
            event="started",
            current=0,
            total=None,
        )
        rows: list[dict] = []
        failures: list[SharedDataFailure] = []
        expected_ids: list[str] = []
        processed_count = 0
        for champion, item in candidates:
            expected_ids.append(item.key)
            try:
                display_name = ordinary_names.get(item.base_alias.casefold(), "")
                row = self._build_special_row(champion, version, display_name=display_name)
                if row is None:
                    raise _ArtifactCorruptError(f"特殊内容 {item.key} 无法构造目录行")
                rows.append(row)
            except Exception as exc:  # noqa: BLE001
                failures.append(self._failure_from_error(item.key, exc))
            processed_count += 1
            self._emit_scan_progress(
                progress,
                generation=generation,
                stage_key="special",
                event="advanced",
                current=processed_count,
                total=None,
                entity_id=item.key,
            )

        try:
            resource_pack_rows = self.load_resource_pack_rows(ordinary_names=ordinary_names)
        except Exception as exc:  # noqa: BLE001
            failures.append(self._failure_from_error("resource_packs", exc))
            resource_pack_rows = []
        for row in resource_pack_rows:
            identity = str(row.get("key", "")).strip()
            if identity and identity not in expected_ids:
                expected_ids.append(identity)
                rows.append(row)
                processed_count += 1
                self._emit_scan_progress(
                    progress,
                    generation=generation,
                    stage_key="special",
                    event="advanced",
                    current=processed_count,
                    total=None,
                    entity_id=identity,
                )

        total = len(expected_ids)
        unprepared_ids = tuple(
            str(row.get("key") or row.get("id"))
            for row in rows
            if row.get("audio") == "未准备" or row.get("mapping") == "未准备"
        )
        self._emit_scan_progress(
            progress,
            generation=generation,
            stage_key="special",
            event="finished",
            current=total,
            total=total,
        )
        return SharedDataSectionResult(
            section="special",
            expected_ids=tuple(expected_ids),
            rows=tuple(rows),
            failures=tuple(failures),
            unprepared_ids=unprepared_ids,
            required=False,
        )

    @staticmethod
    def _group_section_problems(section: SharedDataSectionResult) -> tuple[SharedDataProblem, ...]:
        """把逐实体失败按稳定问题码聚合为页面诊断。"""
        grouped: dict[tuple[SharedDataProblemCode, str], list[str]] = {}
        for failure in section.failures:
            grouped.setdefault((failure.code, failure.message), []).append(failure.entity_id)
        return tuple(
            SharedDataProblem(
                code=code,
                scope=section.section,
                message=message,
                entity_ids=tuple(dict.fromkeys(entity_ids)),
                blocking=section.required,
            )
            for (code, message), entity_ids in grouped.items()
        )

    def scan_catalog(
        self,
        generation: int,
        *,
        progress: Callable[[SharedDataProgress], None] | None = None,
    ) -> SharedDataScanResult:
        """在一个 generation 内完整扫描普通与可选实体目录。

        Args:
            generation: 当前共享上下文代数。
            progress: 可选结构化扫描进度回调。

        Returns:
            同时包含英雄、地图、特殊内容和聚合问题的原子快照。
        """
        self._first_scan_unexpected: BaseException | None = None
        version = self.data_reader.version
        champions = self.data_reader.get_champions()
        maps = self.data_reader.get_maps()
        ordinary_champions = [
            champion
            for champion in champions
            if not is_structured_special_champion(champion) and not should_hide_champion_by_default(champion)
        ]
        champion_result = self._scan_required_section(
            "champions",
            ordinary_champions,
            version=version,
            generation=generation,
            progress=progress,
        )
        special_result = self._scan_special_section(
            champions,
            version=version,
            generation=generation,
            progress=progress,
        )
        map_result = self._scan_required_section(
            "maps",
            maps,
            version=version,
            generation=generation,
            progress=progress,
        )

        problems: list[SharedDataProblem] = []
        if not champion_result.expected_ids or not map_result.expected_ids:
            problems.append(
                SharedDataProblem(
                    SharedDataProblemCode.DATASET_EMPTY,
                    "dataset",
                    _PROBLEM_MESSAGES[SharedDataProblemCode.DATASET_EMPTY],
                )
            )
        if "0" not in map_result.expected_ids:
            problems.append(
                SharedDataProblem(
                    SharedDataProblemCode.MAP_COMMON_MISSING,
                    "maps",
                    _PROBLEM_MESSAGES[SharedDataProblemCode.MAP_COMMON_MISSING],
                )
            )
        problems.extend(self._group_section_problems(champion_result))
        problems.extend(self._group_section_problems(map_result))
        problems.extend(self._group_section_problems(special_result))
        result = SharedDataScanResult(
            generation=generation,
            version=version,
            champions=champion_result,
            maps=map_result,
            special=special_result,
            problems=tuple(problems),
        )
        summary = result.summary
        log_message = (
            f"共享实体目录扫描完成: readiness={result.readiness.value}; "
            f"champions expected={summary.champion_expected} loaded={summary.champion_loaded} "
            f"failed={summary.champion_failed}; maps expected={summary.map_expected} "
            f"loaded={summary.map_loaded} failed={summary.map_failed}; "
            f"special discovered={summary.special_discovered} unprepared={summary.special_unprepared}"
        )
        if self._first_scan_unexpected is not None:
            logger.opt(exception=self._first_scan_unexpected).error(log_message)
        elif result.readiness is SharedDataReadiness.COMPLETE or result.all_blocking_problems_repairable:
            logger.info(log_message)
        else:
            logger.warning(log_message)
        return result

    def _build_row_from_entity_data(
        self,
        entity_type: GuiEntityType,
        entity_data: AudioEntityData,
        version: str,
    ) -> dict:
        """把已验证实体投影成 GUI 目录行。"""
        entity_id = str(entity_data.entity_id)
        audio_status, mapping_status = check_entity_status(self.ctx, entity_data, version)
        mapping_path = resolve_mapping_file_path(
            self.ctx,
            entity_type,
            entity_id,
            version,
        )

        if entity_data.entity_title:
            display_name = f"{entity_data.entity_name}·{entity_data.entity_title}"
        else:
            display_name = entity_data.entity_name

        return {
            "id": entity_id,
            "name": display_name,
            "alias": entity_data.entity_alias or "",
            "audio": audio_status,
            "mapping": mapping_status,
            "entity_type": entity_type,
            "mapping_file": str(mapping_path) if mapping_path else "",
        }

    def _build_entity_row(self, entity_type: GuiEntityType, entity_dict: dict, version: str) -> dict:
        """将单个原始实体字典转换为 GUI 行数据。"""
        entity_data = self._build_entity_data(entity_type, str(entity_dict["id"]))
        return self._build_row_from_entity_data(entity_type, entity_data, version)

    def _localized_champion_name(self, champion: dict) -> str:
        """读取当前区域的英雄名，缺失时交由 special profile 回退基础 alias。"""
        names = champion.get("names", {})
        if not isinstance(names, dict):
            return ""
        return str(names.get(self.ctx.game_region, names.get("default", ""))).strip()

    def _localized_ordinary_names(self, champions: list[dict]) -> dict[str, str]:
        """建立普通英雄 alias 到本地化展示名的轻量索引。"""
        return {
            str(champion.get("alias", "")).casefold(): self._localized_champion_name(champion)
            for champion in champions
            if not is_structured_special_champion(champion)
        }

    def _build_special_row(self, champion: dict, version: str, *, display_name: str) -> dict | None:
        """构造特殊内容行；缺少 banks 时保留可解释的未准备状态。"""
        item = build_special_content_item(
            champion,
            display_name=display_name,
        )
        if item is None:
            return None

        audio_status = "未准备"
        mapping_status = "未准备"
        mapping_file = ""
        try:
            entity_data = self._build_entity_data("champions", str(item.champion_id))
            audio_status, mapping_status = check_entity_status(self.ctx, entity_data, version)
            mapping_path = resolve_mapping_file_path(self.ctx, "champions", str(item.champion_id), version)
            mapping_file = str(mapping_path) if mapping_path else ""
        except Exception:  # noqa: BLE001
            # 特殊内容按需准备；目录扫描只保留未准备状态，不逐项制造异常日志。
            pass

        return {
            "id": str(item.champion_id),
            "key": item.key,
            "name": item.display_name,
            "display_name": item.standalone_name,
            "alias": item.internal_alias,
            "base_alias": item.base_alias,
            "mode_key": item.profile.mode_key,
            "mode_display_name": item.profile.display_name,
            "mode_english_name": item.profile.english_name,
            "search_text": item.search_text,
            "tooltip": (
                f"{item.standalone_name}\n"
                f"ID: {item.champion_id}\n"
                f"资源键: {item.key}\n"
                f"内部标识: {item.internal_alias}\n"
                f"音频: {audio_status}\n"
                f"映射: {mapping_status}\n"
                f"文件: {mapping_file or '当前还没有 mapping 文件'}"
            ),
            "audio": audio_status,
            "mapping": mapping_status,
            "entity_type": "champions",
            "mapping_file": mapping_file,
        }

    @staticmethod
    def _resource_pack_profile(wad: str):
        """按来源 WAD 的已知模式命名投影 resource-pack 分组。"""
        name = PurePosixPath(wad).name.casefold()
        if name.startswith("ruby_"):
            return DOOM_BOTS_PROFILE
        if name.startswith("strawberry_"):
            return SWARM_PROFILE
        return HISTORICAL_RESOURCE_PACKS_PROFILE

    @staticmethod
    def _resource_pack_display_name(
        wad: str,
        *,
        profile,
        ordinary_names: Mapping[str, str] | None,
    ) -> str:
        """从 WAD 名恢复不含技术前缀的资源包主展示名。"""
        wad_name = PurePosixPath(wad).name
        wad_stem = wad_name[: -len(".wad.client")] if wad_name.casefold().endswith(".wad.client") else wad_name
        prefix = profile.prefix
        base_alias = (
            wad_stem[len(prefix) :] if prefix and wad_stem.casefold().startswith(prefix.casefold()) else wad_stem
        )
        return (ordinary_names or {}).get(base_alias.casefold(), base_alias)

    @staticmethod
    def _resource_pack_namespace_label(namespace: str, *, profile) -> str:
        """压缩 BIN category，保证同 WAD 的多个资源包仍可区分。"""
        normalized = namespace.removeprefix("MODE_")
        parts = tuple(part for part in normalized.split("_") if part)
        if profile in {DOOM_BOTS_PROFILE, SWARM_PROFILE} and parts:
            return parts[-1]
        return " ".join(parts)

    def _build_resource_pack_row(
        self,
        payload: dict,
        version: str,
        *,
        ordinary_names: Mapping[str, str] | None = None,
    ) -> dict | None:
        """把已持久化 resource-pack artifact 投影为特殊目录行。"""
        metadata = payload.get("resourcePack")
        if not isinstance(metadata, dict):
            return None
        key = str(metadata.get("key", "")).strip()
        wad = str(metadata.get("wad", "")).strip()
        namespace = str(metadata.get("namespace", "")).strip()
        if not key or not wad or not namespace:
            return None

        source = metadata.get("source")
        wad_ref = None
        if isinstance(source, dict):
            try:
                wad_ref = ResourcePackWadRef(
                    identity=str(source.get("wad", wad)),
                    size=int(source["size"]),
                    mtime_ns=int(source["mtimeNs"]),
                )
                # artifact 可能来自更早的客户端快照；目录重载同样属于选择阶段，
                # 必须先确认来源仍在当前 FINAL 且 stat 未变化，才能允许发送到执行中心。
                wad_ref.resolve(Path(self.ctx.config.game_path))
            except (KeyError, TypeError, ValueError, ResourcePackSelectionError):
                logger.warning("资源包 {} 的 source snapshot 无效，将仅作为已发现 artifact 展示", key)
                wad_ref = None

        diagnostics = payload.get("diagnostics")
        completeness = str(diagnostics.get("completeness", "")) if isinstance(diagnostics, dict) else ""
        discovery = metadata.get("discovery")
        status = str(discovery.get("status", "")).strip() if isinstance(discovery, dict) else ""
        status = status or completeness or "unknown"
        profile = self._resource_pack_profile(wad)
        display_base = self._resource_pack_display_name(wad, profile=profile, ordinary_names=ordinary_names)
        namespace_label = self._resource_pack_namespace_label(namespace, profile=profile)
        name = f"{display_base} · {namespace_label}" if namespace_label else display_base
        display_name = f"{profile.display_name} · {name}"

        audio_status = "未准备"
        mapping_status = "未准备"
        mapping_file = ""
        try:
            entity_data = self._build_entity_data("resource_packs", key)
            audio_status, mapping_status = check_entity_status(self.ctx, entity_data, version)
            mapping_path = resolve_mapping_file_path(self.ctx, "resource_packs", key, version)
            mapping_file = str(mapping_path) if mapping_path else ""
        except Exception:  # noqa: BLE001
            # 可选 resource pack 缺少 consumer artifact 不影响普通目录就绪。
            pass

        cost_text = ""
        if isinstance(discovery, dict):
            candidates = discovery.get("candidateEntries")
            reads = discovery.get("payloadReads")
            elapsed = discovery.get("elapsedSeconds")
            if candidates is not None or reads is not None or elapsed is not None:
                elapsed_seconds = elapsed if isinstance(elapsed, int | float) else 0
                cost_text = (
                    f"\n扫描成本: candidate {candidates or 0}，payload {reads or 0}，耗时 {elapsed_seconds:.1f}s"
                )
        selection_notice = "\n选择快照无效，请重新选择并扫描该 WAD。" if wad_ref is None else ""

        return {
            "id": key,
            "key": key,
            "name": name,
            "display_name": display_name,
            "alias": name,
            "source_wad": wad,
            "namespace": namespace,
            "mode_key": profile.mode_key,
            "mode_display_name": profile.display_name,
            "mode_english_name": profile.english_name,
            "search_text": " ".join(
                (profile.display_name, profile.english_name, display_name, wad, namespace, key)
            ).casefold(),
            "tooltip": (
                f"{display_name}\n"
                f"来源 WAD: {wad}\n"
                f"命名空间: {namespace}\n"
                f"状态: {status}\n"
                f"完整度: {completeness or '未知'}\n"
                f"资源键: {key}\n"
                f"音频: {audio_status}\n"
                f"映射: {mapping_status}\n"
                f"文件: {mapping_file or '当前还没有 mapping 文件'}"
                f"{cost_text}"
                f"{selection_notice}"
            ),
            "status": status,
            "completeness": completeness,
            "audio": audio_status,
            "mapping": mapping_status,
            "entity_type": "resource_packs",
            "mapping_file": mapping_file,
            "resource_pack_wad": wad_ref,
            "selectable": wad_ref is not None,
        }

    def load_resource_pack_rows(
        self,
        keys: tuple[str, ...] = (),
        *,
        ordinary_names: Mapping[str, str] | None = None,
    ) -> list[dict]:
        """读取已持久化 resource-pack artifact，不触碰来源 WAD payload。"""
        if keys:
            payloads = [
                payload
                for key in dict.fromkeys(keys)
                if (payload := self.data_reader.get_resource_pack_banks(key, require_bindings=False))
            ]
        else:
            list_packs = getattr(self.data_reader, "list_resource_pack_banks", None)
            payloads = list_packs() if callable(list_packs) else []

        rows = [
            row
            for payload in payloads
            if (row := self._build_resource_pack_row(payload, self.data_reader.version, ordinary_names=ordinary_names))
        ]
        return sorted(rows, key=lambda row: (str(row["mode_key"]), str(row["name"]).casefold()))

    def load_champion_catalog(self) -> dict[str, list[dict]]:
        """一次读取并扫描完整英雄数据，分区返回普通与特殊目录。"""
        try:
            version = self.data_reader.version
            champions = self.data_reader.get_champions()
            self._ensure_bank_dataset_ready("champions")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"Error initializing data for champions: {exc}")
            raise

        ordinary_rows: list[dict] = []
        special_rows: list[dict] = []
        ordinary_names = self._localized_ordinary_names(champions)
        for champion in champions:
            if is_structured_special_champion(champion):
                profile_item = build_special_content_item(champion)
                display_name = ordinary_names.get(profile_item.base_alias.casefold(), "") if profile_item else ""
                row = self._build_special_row(champion, version, display_name=display_name)
                if row is not None:
                    special_rows.append(row)
                continue
            if should_hide_champion_by_default(champion):
                continue
            try:
                ordinary_rows.append(self._build_entity_row("champions", champion, version))
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"Error loading entity {champion.get('id', 'unknown')}: {exc}")

        special_rows.extend(self.load_resource_pack_rows(ordinary_names=ordinary_names))
        return {"champions": ordinary_rows, "special": special_rows}

    def load_champion_rows_by_targets(
        self,
        *,
        champion_ids: tuple[str, ...] = (),
        special_targets: tuple[str, ...] = (),
    ) -> dict[str, list[dict]]:
        """一次读取冠军元数据，仅重建指定普通与特殊条目的输出状态。

        Args:
            champion_ids: 要增量更新的普通英雄数值 ID。
            special_targets: 要增量更新的 ``champion:<id>`` 特殊内容 key。

        Returns:
            包含 ``champions`` 与 ``special`` 两个分区的增量行。
        """
        ordinary_targets = set(champion_ids)
        partition = partition_special_targets(special_targets)
        special_target_keys = set(partition.champion_targets)
        champions: list[dict] | None = None
        ordinary_names: dict[str, str] = {}
        if partition.resource_pack_targets:
            try:
                champions = self.data_reader.get_champions()
                ordinary_names = self._localized_ordinary_names(champions)
            except Exception as exc:  # noqa: BLE001
                logger.warning("资源包增量刷新未能读取英雄本地化元数据，将使用 WAD 名回退: {}", exc)
        resource_pack_rows = self.load_resource_pack_rows(
            partition.resource_pack_targets,
            ordinary_names=ordinary_names,
        )
        if not ordinary_targets and not special_target_keys:
            return {"champions": [], "special": resource_pack_rows}

        try:
            version = self.data_reader.version
            champions = champions if champions is not None else self.data_reader.get_champions()
            self._ensure_bank_dataset_ready("champions")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"Error initializing data for champions: {exc}")
            raise

        ordinary_names = self._localized_ordinary_names(champions)
        ordinary_rows: list[dict] = []
        special_rows: list[dict] = []
        for champion in champions:
            entity_id = str(champion.get("id", ""))
            if is_structured_special_champion(champion):
                profile_item = build_special_content_item(champion)
                if profile_item is None or profile_item.key not in special_target_keys:
                    continue
                display_name = ordinary_names.get(profile_item.base_alias.casefold(), "")
                row = self._build_special_row(champion, version, display_name=display_name)
                if row is not None:
                    special_rows.append(row)
                continue

            if entity_id not in ordinary_targets or should_hide_champion_by_default(champion):
                continue
            try:
                ordinary_rows.append(self._build_entity_row("champions", champion, version))
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"Error loading entity {champion.get('id', 'unknown')}: {exc}")

        special_rows.extend(resource_pack_rows)
        return {"champions": ordinary_rows, "special": special_rows}

    def load_entities(self, entity_type: Literal["champions", "maps"]) -> list[dict]:
        """加载指定类型的实体数据。

        Args:
            entity_type: 实体类型。

        Returns:
            供 GUI 直接展示的实体列表。
        """
        if entity_type == "champions":
            return self.load_champion_catalog()["champions"]

        try:
            version, raw_data = self._load_raw_entities(entity_type)
            self._ensure_bank_dataset_ready(entity_type)
        except Exception as e:
            logger.opt(exception=True).warning(f"Error initializing data for {entity_type}: {e}")
            raise

        result = []
        for entity_dict in raw_data:
            try:
                result.append(self._build_entity_row(entity_type, entity_dict, version))
            except Exception as e:
                logger.opt(exception=True).warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                continue

        return result

    def load_entities_by_ids(self, entity_type: GuiEntityType, entity_ids: tuple[str, ...]) -> list[dict]:
        """按实体 ID 增量加载指定类型的 GUI 行数据。"""
        if not entity_ids:
            return []

        target_ids = set(entity_ids)
        try:
            version, raw_data = self._load_raw_entities(entity_type)
            self._ensure_bank_dataset_ready(entity_type)
        except Exception as e:
            logger.opt(exception=True).warning(f"Error initializing data for {entity_type}: {e}")
            raise

        result = []
        for entity_dict in raw_data:
            entity_id = str(entity_dict.get("id", ""))
            if entity_id not in target_ids:
                continue
            try:
                result.append(self._build_entity_row(entity_type, entity_dict, version))
            except Exception as e:
                logger.opt(exception=True).warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                continue

        return result

    def load_mapping_preview(self, entity_type: GuiEntityType, entity_id: str) -> tuple[Path | None, dict | None, str]:
        """读取实体映射文件并序列化为可预览文本。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。

        Returns:
            映射文件路径、原始映射数据与序列化后的文本内容；未找到文件时返回 ``(None, None, "")``。
        """
        mapping_path = resolve_mapping_file_path(
            self.ctx,
            entity_type,
            str(entity_id),
            self.data_reader.version,
        )
        if mapping_path is None:
            return None, None, ""

        raw_mapping_data = read_data(mapping_path, dev_mode=getattr(self.ctx.config, "dev_mode", False))
        mapping_data = _normalize_integrated_mapping_data(
            raw_mapping_data,
            entity_type=entity_type,
            entity_id=str(entity_id),
        )
        return mapping_path, mapping_data, json.dumps(raw_mapping_data, ensure_ascii=False, indent=2)

    def load_audio_refs(
        self,
        entity_type: GuiEntityType,
        entity_id: str,
        *,
        progress: Callable[[AudioIndexProgress], None] | None = None,
    ) -> tuple[AudioRef, ...]:
        """加载当前实体全部已解包 WEM 的路径级稳定引用。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。
            progress: 可选的音频索引计数进度回调。

        Returns:
            按相对路径排序的 WEM 引用；同一 ID 的不同路径会保留为独立项。
        """
        entity_data = self._build_entity_data(entity_type, str(entity_id))
        return enumerate_audio_refs(
            self.ctx,
            entity_data,
            self.data_reader.version,
            progress=progress,
        )

    def load_event_audio_refs(
        self,
        entity_type: GuiEntityType,
        entity_id: str,
        mapping_data: dict | None,
    ) -> tuple[AudioRef, ...]:
        """只加载事件 mapping 明确引用且已落盘的 WEM。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。
            mapping_data: 标准化事件 mapping。

        Returns:
            按相对路径排序的事件级稳定引用；不会递归枚举全部音频。
        """
        paths = _mapping_audio_paths(mapping_data)
        if not paths:
            return ()
        entity_data = self._build_entity_data(entity_type, str(entity_id))
        return resolve_audio_refs(self.ctx, entity_data, self.data_reader.version, paths)

    def load_audio_roots(
        self,
        entity_type: GuiEntityType,
        entity_id: str,
        *,
        audio_refs: tuple[AudioRef, ...] = (),
    ) -> tuple[Path, ...]:
        """加载当前实体实际存在的音频输出目录。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。
            audio_refs: 已枚举的路径级引用；提供时用于覆盖全部实际音频根。

        Returns:
            当前实体已存在的音频输出目录。
        """
        if audio_refs:
            roots = {root for ref in audio_refs if (root := self._resolve_audio_ref_root(ref)) is not None}
            return tuple(sorted(roots, key=lambda path: str(path).casefold()))

        entity_data = self._build_entity_data(entity_type, str(entity_id))
        return resolve_entity_audio_paths(self.ctx, entity_data, self.data_reader.version)

    def _resolve_audio_ref_root(self, ref: AudioRef) -> Path | None:
        """从路径级引用恢复其所属的实体音频根目录。"""
        parts = PurePosixPath(ref.relative_path).parts
        physical_part_count = len(parts) - (1 if self.ctx.config.group_by_type else 0)
        if physical_part_count <= 0:
            return None
        try:
            return ref.path.parents[physical_part_count - 1]
        except IndexError:
            return None
