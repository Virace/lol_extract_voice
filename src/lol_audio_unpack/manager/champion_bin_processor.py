"""英雄 BIN 链路处理。

负责按英雄ID处理皮肤 BIN，提取 banks/events 数据并生成独立文件。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from league_tools.formats import BIN
from loguru import logger

from lol_audio_unpack.manager.bin_source import BinBatch, BinSource
from lol_audio_unpack.manager.files import needs_update, write_data
from lol_audio_unpack.manager.update_result import UpdateEntityResult
from lol_audio_unpack.model.binding import (
    RESOURCE_SCHEMA_VERSION,
    SUCCESS_STATUSES,
    BankBinding,
    BankReference,
    Completeness,
    ResourceBindings,
    build_diagnostics,
)
from lol_audio_unpack.model.progress import OperationProgress, ProgressEvent
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
        progress_callback: Callable[[OperationProgress], None] | None = None,
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
        self._progress_callback = progress_callback

    def _is_dev_mode(self) -> bool:
        """返回当前运行是否为开发模式。"""
        return bool(self.ctx.config.dev_mode)

    def _log_simple_progress(self, stage_name: str, index: int, total: int, entity_id: str) -> None:
        """输出简单的批量处理进度日志。"""
        logger.info(f"{stage_name}进度 {index}/{total}: {entity_id}")

    @performance_monitor(level="DEBUG")
    def _update_champions(self, data: dict) -> tuple[UpdateEntityResult, ...]:
        """按英雄 ID 更新 banks/events，并返回逐实体结果。"""
        logger.info("开始处理英雄音频数据...")
        self.champion_banks_dir.mkdir(parents=True, exist_ok=True)
        self.champion_events_dir.mkdir(parents=True, exist_ok=True)

        champions = data.get("champions", {})
        sorted_champion_ids = sorted(champions.keys(), key=int)

        total_champions = len(sorted_champion_ids)
        self._emit_progress("started", current=0, total=total_champions)
        results: list[UpdateEntityResult] = []
        first_error: BaseException | None = None
        for index, champion_id in enumerate(sorted_champion_ids, start=1):
            champion_data = champions[champion_id]
            self._log_simple_progress("处理英雄", index, total_champions, champion_id)
            try:
                result = self._process_champion_skins(champion_data, champion_id)
            except Exception as exc:  # noqa: BLE001
                first_error = first_error or exc
                result = UpdateEntityResult.from_error(
                    "champion",
                    champion_id,
                    exc,
                    entity_name=str(champion_data.get("alias", "")),
                )
            results.append(result)
            self._emit_progress(
                "advanced",
                current=index,
                total=total_champions,
                entity_id=champion_id,
            )

        self._emit_progress("finished", current=total_champions, total=total_champions)
        failed_count = sum(result.status.value == "failed" for result in results)
        partial_count = sum(result.status.value == "partial" for result in results)
        if first_error is not None:
            logger.opt(exception=first_error).error(
                "英雄 Banks 更新出现未预期异常：总计 {}，失败 {}，部分成功 {}",
                total_champions,
                failed_count,
                partial_count,
            )
        elif failed_count or partial_count:
            logger.warning(
                "英雄 Banks 更新未完整：总计 {}，失败 {}，部分成功 {}",
                total_champions,
                failed_count,
                partial_count,
            )
        else:
            logger.success(f"英雄Banks数据更新完成，共处理 {total_champions} 个英雄")
        return tuple(results)

    def _emit_progress(
        self,
        event: ProgressEvent,
        *,
        current: int,
        total: int,
        entity_id: str | None = None,
    ) -> None:
        """发送英雄 banks 阶段的结构化进度。"""
        if self._progress_callback is None:
            return
        self._progress_callback(
            OperationProgress(
                operation_key="update",
                stage_key="champion_banks",
                event=event,
                current=current,
                total=total,
                entity_type="champion" if entity_id is not None else None,
                entity_id=entity_id,
            )
        )

    @performance_monitor(level="DEBUG")
    def _process_champion_skins(self, champion_data: ChampionData, champion_id: str) -> UpdateEntityResult:
        """
        处理单个英雄的所有皮肤，提取音频数据并生成独立文件

        :param champion_data: 英雄数据字典
        :param champion_id: 英雄ID
        """
        alias_raw = champion_data.get("alias", "")
        alias = alias_raw.lower()
        if not alias:
            raise ValueError(f"英雄 {champion_id} 缺少 alias，无法准备 banks artifact")

        # 检查是否需要更新
        banks_file_base = self.champion_banks_dir / champion_id
        events_file_base = self.champion_events_dir / champion_id

        resource_v2 = getattr(self.bin_source, "_uses_resource_v2", lambda: False)()
        resource_schema = RESOURCE_SCHEMA_VERSION if resource_v2 else None
        banks_need_update = needs_update(
            banks_file_base,
            self.version,
            self.force_update,
            dev_mode=self._is_dev_mode(),
            resource_schema=resource_schema,
        )
        events_need_update = self.process_events and needs_update(
            events_file_base,
            self.version,
            self.force_update,
            dev_mode=self._is_dev_mode(),
        )
        if not banks_need_update and not events_need_update:
            logger.trace(f"英雄 {champion_id} ({alias}) 的数据已是最新，跳过处理")
            return UpdateEntityResult.success("champion", champion_id, entity_name=alias_raw)

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
            raise ValueError(f"英雄 {champion_id} 没有可处理的皮肤 BIN 路径")

        bin_paths = list(skin_id_by_path)
        local_required_dir = Path("data") / "characters" / alias_raw
        logger.trace(f"从 {alias} 提取 {len(bin_paths)} 个BIN文件")
        batch = self._read_bin_batch(
            champion_data,
            bin_paths,
            f"英雄 {champion_id} ({alias})",
            local_required_dir=local_required_dir,
        )

        sorted_skin_ids = sorted(skin_id_by_path.values(), key=int)
        path_by_skin_id = {skin_id: path for path, skin_id in skin_id_by_path.items()}

        champion_skin_events = {}
        references: list[BankReference] = []
        parse_failed = False

        for skin_id in sorted_skin_ids:
            path = path_by_skin_id[skin_id]
            if not (bin_raw := batch.raws.get(path)):
                continue

            try:
                bin_file = BIN(bin_raw)
                references.extend(self._collect_bank_references(bin_file, path, skin_id))
                if events_need_update and (skin_events := self._extract_skin_events(bin_file, base_skin_id, skin_id)):
                    champion_skin_events[skin_id] = skin_events

            except Exception:
                batch.mark_parse_failed(path, "BIN 内容解析失败")
                parse_failed = True
                if self._is_dev_mode():
                    raise

        bank_bindings = self.bin_source._resolve_bank_bindings(references) if batch.resource_v2 else []
        legacy_groups = self._binding_groups(bank_bindings) if batch.resource_v2 else self._reference_groups(references)
        if not batch.resource_v2 and not references:
            raise ValueError(f"英雄 {champion_id} 未提取到可用 bank 引用")
        champion_banks_data = self.bin_source._create_base_data(
            champion_id,
            "champion",
            alias=alias,
            **self._build_legacy_projection(legacy_groups),
        )

        completeness = Completeness.COMPLETE
        if batch.resource_v2:
            index_metrics, index_errors = self.bin_source._resource_index_diagnostics()
            diagnostics = build_diagnostics(
                batch.bindings,
                bank_bindings,
                index=index_metrics,
                index_errors=index_errors,
            )
            resource = ResourceBindings(
                entity_type="champion",
                entity_id=champion_id,
                bin_bindings=tuple(batch.bindings),
                bank_bindings=tuple(bank_bindings),
                diagnostics=diagnostics,
            )
            champion_banks_data.update(resource.to_payload())
            self._log_binding_summary(f"英雄 {champion_id} ({alias})", diagnostics.completeness, diagnostics.to_dict())
            completeness = diagnostics.completeness
        self._optimize_champion_mappings(champion_banks_data)

        # 写入banks数据
        artifacts: list[Path] = []
        if banks_need_update:
            artifacts.append(write_data(champion_banks_data, banks_file_base, dev_mode=self._is_dev_mode()))

        # 写入events数据
        if champion_skin_events and events_need_update:
            final_event_data = self.bin_source._create_base_data(
                champion_id, "champion", alias=alias, skins=champion_skin_events
            )
            artifacts.append(write_data(final_event_data, events_file_base, dev_mode=self._is_dev_mode()))

        if completeness is Completeness.FAILED:
            return UpdateEntityResult.incomplete(
                "champion",
                champion_id,
                entity_name=alias_raw,
                message="resource bindings 未形成可用结果",
                failed=True,
                artifacts=tuple(artifacts),
            )
        if completeness is Completeness.PARTIAL or parse_failed:
            return UpdateEntityResult.incomplete(
                "champion",
                champion_id,
                entity_name=alias_raw,
                message="部分 BIN 或 bank binding 未能解析",
                artifacts=tuple(artifacts),
            )
        return UpdateEntityResult.success(
            "champion",
            champion_id,
            entity_name=alias_raw,
            artifacts=tuple(artifacts),
        )

    def _read_bin_batch(
        self,
        champion_data: ChampionData,
        bin_paths: list[str],
        entity_label: str,
        *,
        local_required_dir: Path,
    ) -> BinBatch:
        """读取 declared BIN，并兼容只提供旧测试边界的调用方。"""
        if hasattr(self.bin_source, "_resolve_bin_resources"):
            return self.bin_source._resolve_bin_resources(
                bin_paths,
                entity_label,
                local_required_dir=local_required_dir,
            )

        root_wad_path = champion_data.get("wad", {}).get("root")
        wad_path = self.game_path / root_wad_path if root_wad_path else None
        values = self.bin_source._extract_bin_raws(
            wad_path=wad_path,
            bin_paths=bin_paths,
            entity_label=entity_label,
            local_required_dir=local_required_dir,
        )
        raws = {path: raw for path, raw in zip(bin_paths, values, strict=False) if raw is not None}
        return BinBatch(raws=raws, bindings=[], resource_v2=False)

    @staticmethod
    def _collect_bank_references(bin_file: BIN, source_bin: str, skin_id: str) -> list[BankReference]:
        """从一个皮肤 BIN 收集带分组与皮肤归属的 bank 声明。"""
        references: list[BankReference] = []
        group_index = 0
        for group in bin_file.data:
            for event_data in group.bank_units:
                if not event_data.bank_path:
                    continue
                references.extend(
                    BankReference(
                        category=event_data.category,
                        path=path,
                        source_bin=source_bin,
                        sub_entity=skin_id,
                        group=group_index,
                    )
                    for path in event_data.bank_path
                )
                group_index += 1
        return references

    @staticmethod
    def _reference_groups(references: list[BankReference]) -> list[tuple[str, str, list[str]]]:
        """把 remote 旧合同的声明恢复为皮肤/category/path group。"""
        groups: dict[tuple[str, str, str, int | None], list[str]] = {}
        for reference in references:
            key = (reference.sub_entity or "", reference.category, reference.source_bin, reference.group)
            groups.setdefault(key, []).append(reference.path)
        return [(skin_id, category, paths) for (skin_id, category, _source, _group), paths in groups.items()]

    @staticmethod
    def _binding_groups(bindings: list[BankBinding]) -> list[tuple[str, str, list[str]]]:
        """只从成功 bank bindings 派生 local v2 旧消费者投影。"""
        groups: dict[tuple[str, str, str, int | None], list[str]] = {}
        for binding in bindings:
            if binding.status not in SUCCESS_STATUSES:
                continue
            key = (binding.sub_entity or "", binding.category, binding.source_bin, binding.group)
            groups.setdefault(key, []).append(binding.path)
        return [(skin_id, category, paths) for (skin_id, category, _source, _group), paths in groups.items()]

    @staticmethod
    def _build_legacy_projection(groups: list[tuple[str, str, list[str]]]) -> dict[str, dict]:
        """按既有共享皮肤语义，从一组 binding groups 派生旧投影。"""
        projection: dict[str, dict] = {"skinAudioMappings": {}, "skins": {}}
        owner_by_fingerprint: dict[tuple[str, ...], str] = {}
        for skin_id, category, paths in groups:
            fingerprint = tuple(sorted(paths))
            if owner_id := owner_by_fingerprint.get(fingerprint):
                if skin_id != owner_id and "_Base_" not in category:
                    projection["skinAudioMappings"].setdefault(skin_id, {})[category] = owner_id
                continue

            owner_by_fingerprint[fingerprint] = skin_id
            projection["skins"].setdefault(skin_id, {}).setdefault(category, []).append(paths)
        return projection

    @staticmethod
    def _log_binding_summary(label: str, completeness: Completeness, diagnostics: dict) -> None:
        """为 partial/failed binding artifact 输出可观察摘要。"""
        if completeness is Completeness.COMPLETE:
            return
        message = (
            f"{label} 资源绑定结果为 {completeness.value}: "
            f"unresolved BIN={len(diagnostics['unresolvedBins'])}, "
            f"unresolved bank={len(diagnostics['unresolvedBanks'])}"
        )
        if completeness is Completeness.FAILED:
            logger.error(message)
        else:
            logger.warning(message)

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
