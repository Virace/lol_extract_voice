"""GUI preview models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResourcePreviewItem:
    """Preview data for a selectable GUI resource row.

    Args:
        entity_id: Stable resource identifier.
        name: Display name.
        subtitle: Secondary label shown under the name.
        entity_type: Resource type, such as ``champion`` or ``map``.
        categories: Supported audio categories.
        status: Current preview state.
    """

    entity_id: str
    name: str
    subtitle: str
    entity_type: str
    categories: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class MappingPreviewDocument:
    """Preview payload shown in the mapping pane.

    Args:
        title: Document title.
        content: Serialized mapping preview content.
    """

    title: str
    content: str


@dataclass(frozen=True)
class GuiPreviewState:
    """Static preview state used before business signals are wired.

    Args:
        champions: Preview champion rows.
        maps: Preview map rows.
        recent_logs: Recent log lines.
        mapping_document: Preview mapping document.
        hero_stats: Small summary card values.
    """

    champions: tuple[ResourcePreviewItem, ...] = ()
    maps: tuple[ResourcePreviewItem, ...] = ()
    recent_logs: tuple[str, ...] = ()
    mapping_document: MappingPreviewDocument = field(
        default_factory=lambda: MappingPreviewDocument(title="mapping-preview.json", content="{}")
    )
    hero_stats: tuple[tuple[str, str], ...] = ()
