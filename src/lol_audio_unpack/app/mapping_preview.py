"""普通与整合版事件映射的统一投影，供预览与范围解析复用。"""

from __future__ import annotations


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


def normalize_mapping(  # noqa: PLR0911
    mapping_data: dict[str, object] | None,
    *,
    entity_type: str,
    entity_id: str,
) -> dict[str, object] | None:
    """把整合版 mapping 数据投影成当前预览页使用的普通视图。

    Args:
        mapping_data: 原始 mapping 数据。
        entity_type: 实体类型目录名。
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
