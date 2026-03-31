"""跨页面复用的实体摘要缓存。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class EntityDataStore:
    """维护英雄/地图等实体摘要列表的共享缓存。"""

    def __init__(self, *, entity_types: tuple[str, ...]) -> None:
        """初始化实体缓存。

        Args:
            entity_types: 允许缓存的实体类型列表。
        """
        self._entity_types = entity_types
        self._rows_by_type: dict[str, list[dict[str, Any]]] = {
            entity_type: [] for entity_type in entity_types
        }

    def rows_for(self, entity_type: str) -> list[dict[str, Any]]:
        """返回指定实体类型的缓存行副本。"""
        return list(self._rows_by_type.get(entity_type, ()))

    def set_rows(self, entity_type: str, rows: list[dict[str, Any]]) -> bool:
        """整体替换指定实体类型的缓存行。"""
        if entity_type not in self._rows_by_type:
            return False
        self._rows_by_type[entity_type] = list(rows)
        return True

    def update_rows(self, entity_type: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """按实体 ID 增量合并指定实体类型的缓存行。"""
        if entity_type not in self._rows_by_type or not rows:
            return None

        row_by_id = {str(row["id"]): row for row in rows}
        merged_rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for row in self._rows_by_type[entity_type]:
            entity_id = str(row.get("id", ""))
            if entity_id in row_by_id:
                merged_rows.append(row_by_id[entity_id])
                seen_ids.add(entity_id)
            else:
                merged_rows.append(row)

        for row in rows:
            entity_id = str(row["id"])
            if entity_id not in seen_ids:
                merged_rows.append(row)

        self._rows_by_type[entity_type] = merged_rows
        return list(merged_rows)

    def clear(self) -> None:
        """清空所有实体类型缓存。"""
        for entity_type in self._entity_types:
            self._rows_by_type[entity_type] = []

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """返回当前缓存快照。"""
        return deepcopy(self._rows_by_type)
