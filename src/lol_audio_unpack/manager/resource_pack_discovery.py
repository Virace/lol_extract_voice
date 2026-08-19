"""显式 selected-WAD 的有界 resource-pack 发现与 artifact 写入。"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from league_tools.formats import BIN, WAD
from loguru import logger

from lol_audio_unpack.app.resource_pack import (
    RESOURCE_PACK_ENTITY_TYPE,
    RESOURCE_PACK_GROUP,
    DiscoveredResourcePack,
    ResourcePackWadRef,
    build_resource_pack_key_for_wad,
    resource_pack_path_component,
)
from lol_audio_unpack.manager.files import read_data, write_data
from lol_audio_unpack.model.binding import (
    BankBinding,
    BankReference,
    BinBinding,
    BindingRole,
    BindingStatus,
    ResourceBindings,
    build_diagnostics,
    format_entry_hash,
    normalize_logical_path,
    normalize_wad_identity,
)
from lol_audio_unpack.runtime.wad_index import ResolutionRequest, WadIndex

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext


MAX_CANDIDATE_COUNT = 4096
MAX_ENTRY_UNCOMPRESSED_BYTES = 4 * 1024 * 1024
MAX_SELECTED_COMPRESSED_BYTES = 64 * 1024 * 1024
_CANDIDATE_STORAGE_TYPES = frozenset({0, 1, 3})


@dataclass(frozen=True, slots=True)
class ResourcePackScan:
    """一条 selected-WAD 扫描的可读状态与成本。

    Args:
        wad: 相对于游戏根的 selected-WAD identity。
        status: ``complete``、``partial`` 或 ``failed``。
        reason: 失败或降级原因；成功时为 ``None``。
        candidate_count: 通过 storage predicate 的 TOC 条目数。
        payload_reads: 实际解压的 selected-WAD payload 数量。
        compressed_bytes: 候选条目的压缩字节总量。
        uncompressed_bytes: 实际成功解压的 payload 字节总量。
        elapsed_seconds: 当前 WAD 的扫描耗时。
        map_owned_entries_skipped: 因已有 Map 22 declaration/binding 归属而跳过的候选数。
    """

    wad: str
    status: str
    reason: str | None
    candidate_count: int
    payload_reads: int
    compressed_bytes: int
    uncompressed_bytes: int
    elapsed_seconds: float
    map_owned_entries_skipped: int = 0


@dataclass(frozen=True, slots=True)
class ResourcePackDiscoveryResult:
    """一批 selected-WAD 的发现结果。

    Args:
        packs: 可供后续 catalog/consumer 读取的 discovered rows。
        scans: 每个 selected-WAD 的状态与成本。
    """

    packs: tuple[DiscoveredResourcePack, ...]
    scans: tuple[ResourcePackScan, ...]

    @property
    def status(self) -> str:
        """返回整批发现的聚合状态。"""
        statuses = {scan.status for scan in self.scans}
        if not statuses or statuses == {"complete"}:
            return "complete"
        if statuses == {"failed"}:
            return "failed"
        return "partial"

    @property
    def cost(self) -> dict[str, int | float]:
        """返回可持久化或展示的累计扫描成本。"""
        return {
            "selectedWads": len(self.scans),
            "candidateEntries": sum(scan.candidate_count for scan in self.scans),
            "payloadReads": sum(scan.payload_reads for scan in self.scans),
            "candidateCompressedBytes": sum(scan.compressed_bytes for scan in self.scans),
            "payloadUncompressedBytes": sum(scan.uncompressed_bytes for scan in self.scans),
            "elapsedSeconds": sum(scan.elapsed_seconds for scan in self.scans),
            "mapOwnedEntriesSkipped": sum(scan.map_owned_entries_skipped for scan in self.scans),
        }


@dataclass(frozen=True, slots=True)
class _BankRecord:
    """同一 category/logical path 的合并 bank 声明。"""

    path: str
    normalized_path: str
    source_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MapOwnership:
    """Map 22 已声明或已绑定的 BIN entry ownership。"""

    declared_hashes: frozenset[int] = frozenset()
    bound_entries: frozenset[tuple[str, int]] = frozenset()

    def owns(self, ref: ResourcePackWadRef, entry_hash: int) -> bool:
        """判断 selected-WAD candidate 是否仍应属于 Map 22。"""
        return entry_hash in self.declared_hashes or (ref.identity.casefold(), entry_hash) in self.bound_entries


@dataclass
class _ScanState:
    """单个 selected-WAD 扫描期间的可变聚合状态。"""

    ref: ResourcePackWadRef
    started_at: float
    candidate_count: int = 0
    payload_reads: int = 0
    compressed_bytes: int = 0
    uncompressed_bytes: int = 0
    parsed_candidates: int = 0
    map_owned_entries_skipped: int = 0
    entry_errors: list[str] = field(default_factory=list)
    source_bindings: dict[str, BinBinding] = field(default_factory=dict)
    bank_paths: dict[str, dict[str, _BankRecord]] = field(default_factory=lambda: defaultdict(dict))
    bank_sources: dict[str, dict[str, set[str]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(set)))
    category_sources: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    events: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


class ResourcePackDiscovery:
    """只扫描显式 selected-WAD，并复用 P1 bank resolver 写入 v2 artifact。"""

    def __init__(  # noqa: PLR0913
        self,
        ctx: AppContext,
        *,
        reader: Any | None = None,
        wad_factory: Callable[[Path], Any] = WAD,
        bin_factory: Callable[[bytes], Any] = BIN,
        bank_resolver: Any | None = None,
        max_candidate_count: int = MAX_CANDIDATE_COUNT,
        max_entry_uncompressed_bytes: int = MAX_ENTRY_UNCOMPRESSED_BYTES,
        max_selected_compressed_bytes: int = MAX_SELECTED_COMPRESSED_BYTES,
    ):
        """初始化 discovery owner 的外部边界与预算。

        Args:
            ctx: 当前应用上下文。
            reader: 用于读取 Map 22 declaration/v2 binding ownership 的数据读取器。
            wad_factory: 仅为 selected-WAD 构造 TOC/读取器的注入边界。
            bin_factory: 从 candidate payload 创建 BIN 的注入边界。
            bank_resolver: P1 ``resolve_many`` 兼容对象；为空时使用 ``WadIndex``。
            max_candidate_count: 单个 WAD 允许解压前确认的候选上限。
            max_entry_uncompressed_bytes: 单个 candidate 的最大未压缩尺寸。
            max_selected_compressed_bytes: 单个 selected-WAD 的候选压缩字节总上限。
        """
        if min(max_candidate_count, max_entry_uncompressed_bytes, max_selected_compressed_bytes) <= 0:
            raise ValueError("resource pack discovery 预算必须为正数。")
        self.ctx = ctx
        self.reader = reader
        self.wad_factory = wad_factory
        self.bin_factory = bin_factory
        self.bank_resolver = bank_resolver
        self.max_candidate_count = max_candidate_count
        self.max_entry_uncompressed_bytes = max_entry_uncompressed_bytes
        self.max_selected_compressed_bytes = max_selected_compressed_bytes

    def discover(self, refs: Iterable[ResourcePackWadRef], *, version: str) -> ResourcePackDiscoveryResult:
        """扫描 selected-WAD，按成功 BANK_UNITS category 写入 resource-pack artifact。

        Args:
            refs: 选择阶段创建的 typed WAD refs。
            version: 当前 manifest 版本。

        Returns:
            含每个 WAD 状态、成本与 discovered pack rows 的结果。
        """
        packs: list[DiscoveredResourcePack] = []
        scans: list[ResourcePackScan] = []
        seen: set[tuple[str, int, int]] = set()
        map_ownership = self._load_map_ownership()
        for ref in refs:
            token = (ref.identity.casefold(), ref.size, ref.mtime_ns)
            if token in seen:
                continue
            seen.add(token)
            scan, rows = self._discover_wad(ref, version=version, map_ownership=map_ownership)
            scans.append(scan)
            packs.extend(rows)
        return ResourcePackDiscoveryResult(tuple(packs), tuple(scans))

    def _discover_wad(
        self,
        ref: ResourcePackWadRef,
        *,
        version: str,
        map_ownership: _MapOwnership,
    ) -> tuple[ResourcePackScan, list[DiscoveredResourcePack]]:
        """扫描一个已选择 WAD；该 WAD 失败不影响本批其它选择。"""
        started = time.perf_counter()
        state = _ScanState(ref=ref, started_at=started)
        try:
            path = ref.resolve(Path(self.ctx.config.game_path))
            wad = self.wad_factory(path)
            candidates, state.map_owned_entries_skipped = self._select_candidates(wad, ref, map_ownership)
            state.candidate_count = len(candidates)
            budget_error = self._validate_budget(candidates, state)
            if budget_error:
                return self._scan_result(state, "failed", budget_error, started), []

            for section in candidates:
                self._parse_candidate(wad, section, state)
            if state.parsed_candidates == 0:
                reason = "未找到可解析的 PROP/BIN candidate"
                if state.map_owned_entries_skipped:
                    reason += f"；已按 Map 22 declaration 排除 {state.map_owned_entries_skipped} 个候选"
                return self._scan_result(state, "failed", reason, started), []
            if not state.bank_paths:
                return self._scan_result(state, "failed", "可解析 BIN 未声明 BANK_UNITS bank path", started), []

            rows = self._write_discovered_packs(state, version=version)
            has_entry_failure = bool(state.entry_errors)
            failed_rows = [row for row in rows if row.status in {"conflict", "failed"}]
            incomplete_rows = [row for row in rows if row.status != "complete"]
            if failed_rows and len(failed_rows) == len(rows):
                status = "failed"
            elif has_entry_failure or incomplete_rows:
                status = "partial"
            else:
                status = "complete"

            reasons = list(state.entry_errors[:3])
            reasons.extend(f"{row.key}: {row.status}" for row in incomplete_rows[:3])
            reason = "; ".join(reasons) or None
            return self._scan_result(state, status, reason, started), rows
        except Exception as exc:
            logger.opt(exception=True).error(f"扫描资源包 WAD 失败: {ref.identity}")
            return self._scan_result(state, "failed", f"{type(exc).__name__}: {exc}", started), []

    def _select_candidates(
        self,
        wad: Any,
        ref: ResourcePackWadRef,
        map_ownership: _MapOwnership,
    ) -> tuple[list[Any], int]:
        """选择可扫描 candidate，并按结构化 ownership 排除 Map 22 declared BIN。"""
        candidates: list[Any] = []
        skipped = 0
        for section in getattr(wad, "files", ()):
            if not _is_candidate_section(section):
                continue
            path_hash = int(getattr(section, "path_hash", 0))
            if map_ownership.owns(ref, path_hash):
                skipped += 1
                continue
            candidates.append(section)
        return (
            sorted(
                candidates,
                key=lambda section: (int(getattr(section, "path_hash", 0)), int(getattr(section, "offset", 0))),
            ),
            skipped,
        )

    def _validate_budget(self, candidates: list[Any], state: _ScanState) -> str | None:
        """在解压前强制候选数、未压缩尺寸与压缩字节预算。"""
        if len(candidates) > self.max_candidate_count:
            return f"candidate 数量超出预算: {len(candidates)} > {self.max_candidate_count}"

        compressed_bytes = 0
        for section in candidates:
            size = _entry_size(section)
            compressed_size = _entry_compressed_size(section)
            if size > self.max_entry_uncompressed_bytes:
                return f"candidate 未压缩尺寸超出预算: {size} > {self.max_entry_uncompressed_bytes}"
            if compressed_size <= 0:
                return "candidate 压缩尺寸无效"
            compressed_bytes += compressed_size
        state.compressed_bytes = compressed_bytes
        if compressed_bytes > self.max_selected_compressed_bytes:
            return f"selected-WAD 压缩字节超出预算: {compressed_bytes} > {self.max_selected_compressed_bytes}"
        return None

    def _parse_candidate(self, wad: Any, section: Any, state: _ScanState) -> None:
        """独立读取并解析一个 candidate；失败只记录该 entry。"""
        entry_hash = format_entry_hash(int(getattr(section, "path_hash", 0)))
        source_bin = f"resource_pack/{entry_hash}.bin"
        state.payload_reads += 1
        try:
            payload = wad.extract_by_section(section, "", raw=True)
        except Exception as exc:
            state.entry_errors.append(f"{entry_hash}: WAD entry 解压失败: {type(exc).__name__}")
            return
        if payload is None:
            state.entry_errors.append(f"{entry_hash}: WAD entry 解压失败")
            return
        state.uncompressed_bytes += len(payload)
        if payload[:4] != b"PROP":
            # 保守 TOC predicate 会命中非 PROP false positive；它们已计入读取成本，但不是 BIN 解析失败。
            return
        try:
            bin_file = self.bin_factory(payload)
        except Exception as exc:
            state.entry_errors.append(f"{entry_hash}: BIN 内容解析失败: {type(exc).__name__}")
            return

        state.parsed_candidates += 1
        state.source_bindings[entry_hash] = self._bin_binding(
            state.ref,
            source_bin,
            entry_hash,
            BindingStatus.RESOLVED,
            None,
        )
        for group in getattr(bin_file, "data", ()):
            for unit in getattr(group, "bank_units", ()):
                category = str(getattr(unit, "category", "")).strip()
                paths = tuple(str(path).strip() for path in (getattr(unit, "bank_path", ()) or ()) if str(path).strip())
                if not category or not paths:
                    continue
                state.category_sources[category].add(entry_hash)
                for path in paths:
                    normalized_path = normalize_logical_path(path)
                    if normalized_path not in state.bank_paths[category]:
                        state.bank_paths[category][normalized_path] = _BankRecord(
                            path=path,
                            normalized_path=normalized_path,
                            source_hashes=(),
                        )
                    state.bank_sources[category][normalized_path].add(entry_hash)
                for event in getattr(unit, "events", ()) or ():
                    name = str(getattr(event, "string", "")).strip()
                    if name and name not in state.events[category]:
                        state.events[category].append(name)

    def _write_discovered_packs(
        self,
        state: _ScanState,
        *,
        version: str,
    ) -> list[DiscoveredResourcePack]:
        """按 category 独立解析 P1 bank bindings，并隔离单 pack 失败。"""
        rows: list[DiscoveredResourcePack] = []
        categories_by_key: dict[str, list[str]] = defaultdict(list)
        for category in sorted(state.bank_paths):
            categories_by_key[build_resource_pack_key_for_wad(state.ref, category)].append(category)

        for key, categories in sorted(categories_by_key.items()):
            if len(categories) > 1:
                # NFKC/casefold 会主动收敛 key；不同原始 namespace 不能在同一路径下顺序覆盖。
                rows.append(
                    DiscoveredResourcePack(
                        key=key,
                        wad=state.ref.identity,
                        namespace=" | ".join(categories),
                        status="conflict",
                        completeness=None,
                    )
                )
                continue
            category = categories[0]
            records = self._records_for_category(state, category)
            try:
                bindings = self._resolve_bank_bindings(state, category, records)
                row = self._write_pack_artifacts(
                    state,
                    key=key,
                    category=category,
                    records=records,
                    bank_bindings=bindings,
                    version=version,
                )
            except Exception:
                logger.opt(exception=True).error(f"写入资源包 artifact 失败: {key}")
                row = DiscoveredResourcePack(
                    key=key,
                    wad=state.ref.identity,
                    namespace=category,
                    status="failed",
                    completeness=None,
                )
            rows.append(row)
        return rows

    def _records_for_category(self, state: _ScanState, category: str) -> tuple[_BankRecord, ...]:
        """为 category 的逻辑 bank path 合并全部 source entry hashes。"""
        records: list[_BankRecord] = []
        for normalized_path, record in sorted(state.bank_paths[category].items()):
            records.append(
                _BankRecord(
                    path=record.path,
                    normalized_path=normalized_path,
                    source_hashes=tuple(sorted(state.bank_sources[category][normalized_path])),
                )
            )
        return tuple(records)

    def _resolve_bank_bindings(
        self,
        state: _ScanState,
        category: str,
        records: tuple[_BankRecord, ...],
    ) -> tuple[BankBinding, ...]:
        """复用 P1 resolver，为当前 resource pack 解析物理 bank WAD。"""
        resolver = self._get_bank_resolver()
        references = [
            BankReference(
                category=category,
                path=record.path,
                source_bin=f"resource_pack/{record.source_hashes[0]}.bin",
                sub_entity=None,
                group=None,
            )
            for record in records
        ]
        try:
            results = resolver.resolve_many(
                [ResolutionRequest(reference.path, reference.preferred_role) for reference in references]
            )
        except Exception as exc:
            return tuple(
                BankBinding(
                    category=category,
                    path=record.path,
                    normalized_path=record.normalized_path,
                    kind="",
                    wad=None,
                    entry_hash="",
                    source_bin=f"resource_pack/{record.source_hashes[0]}.bin",
                    role=None,
                    status=BindingStatus.PARSE_FAILED,
                    diagnostic=f"P1 bank resolver 失败: {type(exc).__name__}",
                )
                for record in records
            )
        return tuple(
            BankBinding(
                category=category,
                path=record.path,
                normalized_path=result.normalized_path,
                kind="",
                wad=result.wad,
                entry_hash=result.entry_hash,
                source_bin=reference.source_bin,
                role=result.role,
                status=result.status,
                candidates=result.candidates if len(result.candidates) > 1 else (),
                diagnostic=result.diagnostic,
            )
            for reference, record, result in zip(references, records, results, strict=True)
        )

    def _write_pack_artifacts(  # noqa: PLR0913
        self,
        state: _ScanState,
        *,
        key: str,
        category: str,
        records: tuple[_BankRecord, ...],
        bank_bindings: tuple[BankBinding, ...],
        version: str,
    ) -> DiscoveredResourcePack:
        """构造并安全写入单个 resource-pack banks/events artifact。"""
        source_bindings = tuple(
            state.source_bindings[source_hash]
            for source_hash in sorted(state.category_sources[category])
            if source_hash in state.source_bindings
        )
        index = self._index_diagnostics(state)
        diagnostics = build_diagnostics(
            list(source_bindings),
            list(bank_bindings),
            index=index,
            index_errors=state.entry_errors,
        )
        discovery_status = diagnostics.completeness.value
        if state.entry_errors and discovery_status == "complete":
            discovery_status = "partial"
        metadata = self._resource_metadata(
            state,
            key=key,
            category=category,
            records=records,
            discovery_status=discovery_status,
        )
        resource = ResourceBindings(
            entity_type=RESOURCE_PACK_ENTITY_TYPE,
            entity_id=key,
            bin_bindings=source_bindings,
            bank_bindings=bank_bindings,
            diagnostics=diagnostics,
        )
        banks_payload = resource.to_payload(
            metadata={"gameVersion": version},
            resourcePack=metadata,
            banks={category: [[record.path for record in records]]},
        )
        events_payload = {
            "metadata": {"gameVersion": version},
            "resourcePack": metadata,
            "events": {category: state.events[category]} if state.events[category] else {},
        }
        if not self._can_overwrite(key, metadata, version=version):
            return DiscoveredResourcePack(
                key=key,
                wad=state.ref.identity,
                namespace=category,
                status="conflict",
                completeness=diagnostics.completeness.value,
            )

        component = resource_pack_path_component(key)
        banks_base = self._artifact_dir(version, "banks") / component
        events_base = self._artifact_dir(version, "events") / component
        banks_base.parent.mkdir(parents=True, exist_ok=True)
        events_base.parent.mkdir(parents=True, exist_ok=True)
        # events 先落盘，banks 作为 catalog/consumer 的可见提交点最后写入；
        # 两次都必须回读一致；任一步失败时恢复精确字节快照，避免旧 banks 配上新 events。
        snapshots = (self._snapshot_artifact(events_base), self._snapshot_artifact(banks_base))
        try:
            self._persist_and_validate(events_payload, events_base, artifact_name="events")
            self._persist_and_validate(banks_payload, banks_base, artifact_name="banks")
        except Exception:
            self._restore_artifacts(snapshots)
            raise
        return DiscoveredResourcePack(
            key=key,
            wad=state.ref.identity,
            namespace=category,
            status=discovery_status,
            completeness=diagnostics.completeness.value,
        )

    def _persist_and_validate(self, payload: dict[str, Any], base: Path, *, artifact_name: str) -> None:
        """写入并回读单份 artifact，拒绝把静默 I/O 失败报告为成功。"""
        write_data(payload, base, dev_mode=self._is_dev_mode())
        persisted = read_data(base, dev_mode=self._is_dev_mode())
        if persisted != payload:
            raise OSError(f"resource-pack {artifact_name} artifact 写入后校验失败: {base.name}")

    def _snapshot_artifact(self, base: Path) -> tuple[Path, bytes | None]:
        """保存当前 serializer 会覆盖的精确文件字节；不存在时记录空快照。"""
        suffix = ".yml" if self._is_dev_mode() else ".msgpack"
        path = base.with_suffix(suffix)
        return path, path.read_bytes() if path.is_file() else None

    @staticmethod
    def _restore_artifacts(snapshots: tuple[tuple[Path, bytes | None], ...]) -> None:
        """尽力恢复写入前状态；恢复失败必须继续向上暴露。"""
        errors: list[OSError] = []
        for path, payload in snapshots:
            try:
                if payload is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise OSError(f"resource-pack artifact 回滚失败: {errors[0]}") from errors[0]

    def _can_overwrite(self, key: str, metadata: dict[str, Any], *, version: str) -> bool:
        """拒绝覆盖 source WAD identity 或 fingerprint 不同的同 key artifact。"""
        base = self._artifact_dir(version, "banks") / resource_pack_path_component(key)
        existing = read_data(base, dev_mode=self._is_dev_mode())
        if not existing:
            return True
        existing_pack = existing.get("resourcePack")
        if not isinstance(existing_pack, dict):
            return False
        try:
            existing_wad = normalize_wad_identity(str(existing_pack["wad"]))
        except (KeyError, ValueError):
            return False
        if existing_wad.casefold() != metadata["wad"].casefold():
            return False
        if existing_pack.get("source") != metadata["source"]:
            return False
        return existing_pack.get("sourceFingerprint") == metadata["sourceFingerprint"]

    def _artifact_dir(self, version: str, kind: str) -> Path:
        """返回当前版本 resource-pack artifact group 根目录。"""
        return Path(self.ctx.paths.manifest_path) / version / kind / RESOURCE_PACK_GROUP

    def _is_dev_mode(self) -> bool:
        """返回当前 artifact serializer 是否应使用开发格式。"""
        return bool(getattr(self.ctx.config, "dev_mode", False))

    def _resource_metadata(
        self,
        state: _ScanState,
        *,
        key: str,
        category: str,
        records: tuple[_BankRecord, ...],
        discovery_status: str,
    ) -> dict[str, Any]:
        """构造不含绝对路径的 resource-pack 来源与 dedupe 诊断字段。"""
        return {
            "key": key,
            "wad": state.ref.identity,
            "namespace": category,
            "source": {"wad": state.ref.identity, "size": state.ref.size, "mtimeNs": state.ref.mtime_ns},
            "sourceFingerprint": state.ref.fingerprint,
            "sourceEntryHashes": sorted(state.category_sources[category]),
            "bankSources": [
                {"normalizedPath": record.normalized_path, "entryHashes": list(record.source_hashes)}
                for record in records
            ],
            "discovery": {
                "status": discovery_status,
                "candidateEntries": state.candidate_count,
                "payloadReads": state.payload_reads,
                "candidateCompressedBytes": state.compressed_bytes,
                "payloadUncompressedBytes": state.uncompressed_bytes,
                "mapOwnedEntriesSkipped": state.map_owned_entries_skipped,
                "elapsedSeconds": time.perf_counter() - state.started_at,
            },
        }

    def _index_diagnostics(self, state: _ScanState) -> dict[str, int | float]:
        """汇总 selected-only 成本与 P1 resolver 的只读指标。"""
        index: dict[str, int | float] = {
            "candidateEntries": state.candidate_count,
            "payloadReads": state.payload_reads,
            "candidateCompressedBytes": state.compressed_bytes,
            "payloadUncompressedBytes": state.uncompressed_bytes,
            "mapOwnedEntriesSkipped": state.map_owned_entries_skipped,
        }
        resolver = self.bank_resolver
        if resolver is not None and hasattr(resolver, "snapshot_metrics"):
            index.update(resolver.snapshot_metrics())
        return index

    def _load_map_ownership(self) -> _MapOwnership:
        """从 Map 22 数据声明与 v2 BIN binding 构造候选排除集合。"""
        if self.reader is None:
            return _MapOwnership()

        declared_hashes: set[int] = set()
        bound_entries: set[tuple[str, int]] = set()
        get_map = getattr(self.reader, "get_map", None)
        if callable(get_map):
            try:
                map_data = get_map(22)
                bin_path = str(map_data.get("binPath", "")).strip() if isinstance(map_data, dict) else ""
                if bin_path:
                    declared_hashes.add(WAD.get_hash(normalize_logical_path(bin_path)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取 Map 22 declaration 失败，将继续检查 v2 binding ownership: {}", exc)

        get_bindings = getattr(self.reader, "get_map_resource_bindings", None)
        if callable(get_bindings):
            try:
                bindings = get_bindings(22)
                for binding in getattr(bindings, "bin_bindings", ()):
                    if not binding.wad or not binding.entry_hash:
                        continue
                    bound_entries.add(
                        (
                            normalize_wad_identity(binding.wad).casefold(),
                            int(binding.entry_hash, 16),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取 Map 22 v2 binding ownership 失败，将只使用数据声明: {}", exc)

        return _MapOwnership(frozenset(declared_hashes), frozenset(bound_entries))

    def _get_bank_resolver(self) -> Any:
        """延迟构造 P1 resolver，避免 zero selection 或无 BANK_UNITS 时枚举其它 WAD TOC。"""
        if self.bank_resolver is None:
            self.bank_resolver = WadIndex(Path(self.ctx.config.game_path), self.ctx.config.game_region)
        return self.bank_resolver

    @staticmethod
    def _bin_binding(
        ref: ResourcePackWadRef,
        source_bin: str,
        entry_hash: str,
        status: BindingStatus,
        diagnostic: str | None,
    ) -> BinBinding:
        """将 selected-WAD candidate 的 opaque hash 转为 v2 BIN binding。"""
        return BinBinding(
            path=source_bin,
            normalized_path=source_bin,
            wad=ref.identity,
            entry_hash=entry_hash,
            status=status,
            role=BindingRole.ROOT,
            diagnostic=diagnostic,
        )

    @staticmethod
    def _scan_result(
        state: _ScanState,
        status: str,
        reason: str | None,
        started: float,
    ) -> ResourcePackScan:
        """封装单 WAD 状态，确保失败同样报告候选与读取成本。"""
        return ResourcePackScan(
            wad=state.ref.identity,
            status=status,
            reason=reason,
            candidate_count=state.candidate_count,
            payload_reads=state.payload_reads,
            compressed_bytes=state.compressed_bytes,
            uncompressed_bytes=state.uncompressed_bytes,
            elapsed_seconds=time.perf_counter() - started,
            map_owned_entries_skipped=state.map_owned_entries_skipped,
        )


def _is_candidate_section(section: Any) -> bool:
    """执行 POC 冻结的 storage type + 非零未压缩尺寸 predicate。"""
    try:
        return int(section.type) in _CANDIDATE_STORAGE_TYPES and _entry_size(section) > 0
    except (TypeError, ValueError):
        return False


def _entry_size(section: Any) -> int:
    """返回 TOC 声明的未压缩 entry 尺寸。"""
    return int(getattr(section, "size", 0))


def _entry_compressed_size(section: Any) -> int:
    """返回预算用压缩尺寸；raw entry 缺字段时回退到未压缩尺寸。"""
    value = getattr(section, "compressed_size", None)
    return _entry_size(section) if value is None else int(value)


__all__ = [
    "MAX_CANDIDATE_COUNT",
    "MAX_ENTRY_UNCOMPRESSED_BYTES",
    "MAX_SELECTED_COMPRESSED_BYTES",
    "ResourcePackDiscovery",
    "ResourcePackDiscoveryResult",
    "ResourcePackScan",
]
