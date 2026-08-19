"""本地 WAD 资源绑定的数据合同与序列化辅助。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

RESOURCE_SCHEMA_VERSION = 2
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[a-zA-Z]:/")


class BindingStatus(str, Enum):
    """资源路径解析状态。"""

    RESOLVED = "resolved"
    MISSING = "missing"
    AMBIGUOUS_IDENTICAL = "ambiguous_identical"
    AMBIGUOUS_CONFLICT = "ambiguous_conflict"
    PARSE_FAILED = "parse_failed"


class BindingRole(str, Enum):
    """资源容器在解析选择中的解释角色。"""

    ROOT = "root"
    LOCALIZED = "localized"
    FALLBACK = "fallback"


class Completeness(str, Enum):
    """实体资源绑定的完整程度。"""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


SUCCESS_STATUSES = frozenset({BindingStatus.RESOLVED, BindingStatus.AMBIGUOUS_IDENTICAL})


def normalize_logical_path(path: str) -> str:
    """规范化 WAD 内部逻辑路径以供比较和哈希。

    Args:
        path: 原始逻辑路径。

    Returns:
        使用正斜杠、无多余前导分隔符并完成大小写折叠的路径。
    """
    parts = (part for part in path.replace("\\", "/").split("/") if part not in {"", "."})
    return "/".join(parts).casefold()


def normalize_wad_identity(path: str | PurePosixPath) -> str:
    """规范化可持久化的相对 WAD identity。

    Args:
        path: 相对于游戏根目录的 WAD 路径。

    Returns:
        保留发现时大小写的正斜杠相对路径。

    Raises:
        ValueError: 路径为绝对路径或可能逃逸游戏根时抛出。
    """
    text = str(path).replace("\\", "/")
    if text.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(text):
        raise ValueError(f"WAD identity 必须相对于游戏根目录: {path}")

    parts = tuple(part for part in text.split("/") if part not in {"", "."})
    if not parts or ".." in parts or ":" in parts[0]:
        raise ValueError(f"WAD identity 无效或可能逃逸游戏根目录: {path}")
    return "/".join(parts)


def format_entry_hash(path_hash: int) -> str:
    """把 WAD 路径 hash 格式化为稳定的 16 位十六进制字符串。"""
    return f"{path_hash:016x}"


def infer_resource_kind(path: str) -> str:
    """从 bank 逻辑路径推断资源种类。"""
    suffix = PurePosixPath(normalize_logical_path(path)).suffix.casefold()
    return suffix.removeprefix(".").upper() or "UNKNOWN"


@dataclass(frozen=True)
class BindingCandidate:
    """同一逻辑资源的一个物理 WAD 候选。"""

    wad: str
    entry_hash: str
    role: BindingRole
    size: int
    checksum: str | None = None
    offset: int | None = None

    def __post_init__(self) -> None:
        """校验候选不会持久化本机绝对路径。"""
        object.__setattr__(self, "wad", normalize_wad_identity(self.wad))

    def to_dict(self) -> dict[str, Any]:
        """序列化为 artifact 字段。"""
        payload: dict[str, Any] = {
            "wad": self.wad,
            "entryHash": self.entry_hash,
            "role": self.role.value,
            "size": self.size,
        }
        if self.checksum is not None:
            payload["checksum"] = self.checksum
        if self.offset is not None:
            payload["offset"] = self.offset
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BindingCandidate:
        """从 artifact 字段恢复候选。"""
        return cls(
            wad=str(payload["wad"]),
            entry_hash=str(payload["entryHash"]),
            role=BindingRole(payload["role"]),
            size=int(payload.get("size", 0)),
            checksum=payload.get("checksum"),
            offset=payload.get("offset"),
        )


@dataclass(frozen=True)
class BinBinding:
    """Declared BIN 到物理 WAD entry 的解析结果。"""

    path: str
    normalized_path: str
    wad: str | None
    entry_hash: str
    status: BindingStatus
    role: BindingRole | None = None
    candidates: tuple[BindingCandidate, ...] = ()
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        """统一路径并校验相对 WAD identity。"""
        object.__setattr__(self, "normalized_path", normalize_logical_path(self.normalized_path or self.path))
        if self.wad is not None:
            object.__setattr__(self, "wad", normalize_wad_identity(self.wad))

    def to_dict(self) -> dict[str, Any]:
        """序列化为 SPEC 固定字段及附加诊断。"""
        payload: dict[str, Any] = {
            "path": self.path,
            "normalizedPath": self.normalized_path,
            "wad": self.wad,
            "entryHash": self.entry_hash,
            "status": self.status.value,
        }
        if self.role is not None:
            payload["role"] = self.role.value
        if self.candidates:
            payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        if self.diagnostic:
            payload["diagnostic"] = self.diagnostic
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BinBinding:
        """从 artifact 字段恢复 BIN binding。"""
        role = payload.get("role")
        return cls(
            path=str(payload["path"]),
            normalized_path=str(payload.get("normalizedPath", payload["path"])),
            wad=payload.get("wad"),
            entry_hash=str(payload["entryHash"]),
            status=BindingStatus(payload["status"]),
            role=BindingRole(role) if role else None,
            candidates=tuple(BindingCandidate.from_dict(item) for item in payload.get("candidates", [])),
            diagnostic=payload.get("diagnostic"),
        )


@dataclass(frozen=True)
class BankBinding:
    """Bank reference 到物理 WAD entry 的解析结果。"""

    category: str
    path: str
    normalized_path: str
    kind: str
    wad: str | None
    entry_hash: str
    source_bin: str
    role: BindingRole | None
    status: BindingStatus
    sub_entity: str | None = None
    group: int | None = None
    candidates: tuple[BindingCandidate, ...] = ()
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        """统一逻辑路径、来源 BIN 与相对 WAD identity。"""
        object.__setattr__(self, "normalized_path", normalize_logical_path(self.normalized_path or self.path))
        object.__setattr__(self, "source_bin", normalize_logical_path(self.source_bin))
        object.__setattr__(self, "kind", (self.kind or infer_resource_kind(self.path)).upper())
        if self.wad is not None:
            object.__setattr__(self, "wad", normalize_wad_identity(self.wad))

    @property
    def key(self) -> tuple[str, str]:
        """返回 SPEC 规定的 category + normalized path 语义主键。"""
        return self.category, self.normalized_path

    def to_dict(self) -> dict[str, Any]:
        """序列化为 SPEC 固定字段及旧投影所需的归属信息。"""
        payload: dict[str, Any] = {
            "category": self.category,
            "path": self.path,
            "normalizedPath": self.normalized_path,
            "kind": self.kind,
            "wad": self.wad,
            "entryHash": self.entry_hash,
            "sourceBin": self.source_bin,
            "role": self.role.value if self.role else None,
            "status": self.status.value,
        }
        if self.sub_entity is not None:
            payload["subEntity"] = self.sub_entity
        if self.group is not None:
            payload["group"] = self.group
        if self.candidates:
            payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        if self.diagnostic:
            payload["diagnostic"] = self.diagnostic
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BankBinding:
        """从 artifact 字段恢复 bank binding。"""
        role = payload.get("role")
        return cls(
            category=str(payload["category"]),
            path=str(payload["path"]),
            normalized_path=str(payload.get("normalizedPath", payload["path"])),
            kind=str(payload.get("kind", infer_resource_kind(str(payload["path"])))),
            wad=payload.get("wad"),
            entry_hash=str(payload["entryHash"]),
            source_bin=str(payload["sourceBin"]),
            role=BindingRole(role) if role else None,
            status=BindingStatus(payload["status"]),
            sub_entity=payload.get("subEntity"),
            group=payload.get("group"),
            candidates=tuple(BindingCandidate.from_dict(item) for item in payload.get("candidates", [])),
            diagnostic=payload.get("diagnostic"),
        )


@dataclass(frozen=True)
class BankReference:
    """从已解析 BIN 收集、等待物理 WAD 解析的 bank 声明。"""

    category: str
    path: str
    source_bin: str
    sub_entity: str | None = None
    group: int | None = None

    @property
    def preferred_role(self) -> BindingRole:
        """根据分类语义返回首选容器层。"""
        category = self.category.upper()
        segments = category.replace("_", "/").split("/")
        if "VO" in segments or "ANNOUNCER" in category:
            return BindingRole.LOCALIZED
        return BindingRole.ROOT


@dataclass(frozen=True)
class BindingDiagnostics:
    """实体绑定完整度、未解析项与索引指标。"""

    completeness: Completeness
    unresolved_bins: tuple[dict[str, str], ...] = ()
    unresolved_banks: tuple[dict[str, str], ...] = ()
    index: dict[str, Any] = field(default_factory=dict)
    index_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """序列化诊断字段。"""
        payload: dict[str, Any] = {
            "completeness": self.completeness.value,
            "unresolvedBins": list(self.unresolved_bins),
            "unresolvedBanks": list(self.unresolved_banks),
        }
        if self.index:
            payload["index"] = self.index
        if self.index_errors:
            payload["indexErrors"] = list(self.index_errors)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BindingDiagnostics:
        """从 artifact 字段恢复 diagnostics。"""
        return cls(
            completeness=Completeness(payload["completeness"]),
            unresolved_bins=tuple(payload.get("unresolvedBins", [])),
            unresolved_banks=tuple(payload.get("unresolvedBanks", [])),
            index=dict(payload.get("index", {})),
            index_errors=tuple(payload.get("indexErrors", [])),
        )


def build_diagnostics(
    bins: list[BinBinding],
    banks: list[BankBinding],
    *,
    index: dict[str, Any] | None = None,
    index_errors: list[str] | None = None,
) -> BindingDiagnostics:
    """从 binding 单一事实源派生实体完整度与未解析项。"""
    unresolved_bins = tuple(
        {"path": binding.path, "status": binding.status.value}
        for binding in bins
        if binding.status not in SUCCESS_STATUSES
    )
    unresolved_banks = tuple(
        {"category": binding.category, "path": binding.path, "status": binding.status.value}
        for binding in banks
        if binding.status not in SUCCESS_STATUSES
    )

    resolved_banks = sum(binding.status in SUCCESS_STATUSES for binding in banks)
    if resolved_banks == 0:
        completeness = Completeness.FAILED
    elif unresolved_bins or unresolved_banks:
        completeness = Completeness.PARTIAL
    else:
        completeness = Completeness.COMPLETE

    return BindingDiagnostics(
        completeness=completeness,
        unresolved_bins=unresolved_bins,
        unresolved_banks=unresolved_banks,
        index=index or {},
        index_errors=tuple(index_errors or []),
    )


@dataclass(frozen=True)
class ResourceBindings:
    """单个逻辑实体的 v2 resource binding artifact。"""

    entity_type: str
    entity_id: str
    bin_bindings: tuple[BinBinding, ...]
    bank_bindings: tuple[BankBinding, ...]
    diagnostics: BindingDiagnostics

    def to_payload(self, **legacy_projection: Any) -> dict[str, Any]:
        """生成顶层 v2 artifact，并按需附加旧消费者投影。"""
        return {
            **legacy_projection,
            "resourceSchemaVersion": RESOURCE_SCHEMA_VERSION,
            "entity": {"type": self.entity_type, "id": self.entity_id},
            "binBindings": [binding.to_dict() for binding in self.bin_bindings],
            "bankBindings": [binding.to_dict() for binding in self.bank_bindings],
            "diagnostics": self.diagnostics.to_dict(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ResourceBindings:
        """从 v2 artifact 恢复 typed bindings。

        Raises:
            ValueError: artifact 不是受支持的 resource schema 时抛出。
        """
        if payload.get("resourceSchemaVersion") != RESOURCE_SCHEMA_VERSION:
            raise ValueError("banks artifact 缺少 resource schema v2，请先重新运行 update。")
        entity = payload.get("entity", {})
        return cls(
            entity_type=str(entity["type"]),
            entity_id=str(entity["id"]),
            bin_bindings=tuple(BinBinding.from_dict(item) for item in payload.get("binBindings", [])),
            bank_bindings=tuple(BankBinding.from_dict(item) for item in payload.get("bankBindings", [])),
            diagnostics=BindingDiagnostics.from_dict(payload["diagnostics"]),
        )


__all__ = [
    "RESOURCE_SCHEMA_VERSION",
    "SUCCESS_STATUSES",
    "BankBinding",
    "BankReference",
    "BinBinding",
    "BindingCandidate",
    "BindingDiagnostics",
    "BindingRole",
    "BindingStatus",
    "Completeness",
    "ResourceBindings",
    "build_diagnostics",
    "format_entry_hash",
    "infer_resource_kind",
    "normalize_logical_path",
    "normalize_wad_identity",
]
