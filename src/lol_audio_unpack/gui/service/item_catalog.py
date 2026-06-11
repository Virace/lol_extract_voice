"""装备资料查询的数据源适配。"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

TENCENT_ITEM_CATALOG_URL = "https://game.gtimg.cn/images/lol/act/img/js/items/items.js"
DEFAULT_FETCH_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class ItemRecord:
    """装备查询页展示的最小装备资料。

    Args:
        item_id: 腾讯官网装备 ID。
        name: 装备名称。
        icon_url: 装备图标 URL，可为空。
        keywords: 官网提供的搜索关键字，可为空。
    """

    item_id: str
    name: str
    icon_url: str = ""
    keywords: str = ""
    maps: tuple[str, ...] = ()

    def search_text(self) -> str:
        """返回用于本地搜索的合并文本。"""
        return " ".join((self.item_id, self.name, self.keywords)).lower()


@dataclass(frozen=True, slots=True)
class ItemCatalogPayload:
    """装备查询页消费的完整官网数据。

    Args:
        version: 官网装备数据版本，缺失时为空字符串。
        file_time: 官网装备数据更新时间，缺失时为空字符串。
        items: 已清洗和去重的装备行。
    """

    version: str = ""
    file_time: str = ""
    items: list[ItemRecord] = field(default_factory=list)


def _as_text(value: object) -> str:
    """把官网字段规整成去掉首尾空白的文本。"""
    if value is None:
        return ""
    return str(value).strip()


def _normalize_icon_url(value: object) -> str:
    """把官网图标地址规整为 HTTPS URL。"""
    icon_url = _as_text(value)
    if icon_url.startswith("//"):
        return f"https:{icon_url}"
    if icon_url.startswith("http://"):
        return f"https://{icon_url.removeprefix('http://')}"
    return icon_url


def _normalize_maps(value: object) -> tuple[str, ...]:
    """把官网地图字段规整成不可变文本序列。"""
    if not isinstance(value, list):
        return ()
    return tuple(text for item in value if (text := _as_text(item)))


def _extract_json_text(text: str) -> str:
    """从纯 JSON 或 JS 变量包装中提取 JSON 对象文本。"""
    raw = text.strip().removeprefix("\ufeff").strip()
    if raw.startswith("{"):
        return raw

    # 官网当前返回纯 JSON；保留 JS 包装兼容是为了字段外层形态轻微变化时不误判为无数据。
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("装备数据格式异常：未找到 JSON 对象")
    return raw[start : end + 1]


def parse_tencent_items_text(text: str) -> ItemCatalogPayload:
    """解析腾讯官网装备数据文本。

    Args:
        text: 官网返回的 ``items.js`` 文本。

    Returns:
        ItemCatalogPayload: 页面可直接消费的装备资料。

    Raises:
        ValueError: 文本不是 JSON 对象，或字段结构不符合预期。
    """
    try:
        payload = json.loads(_extract_json_text(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"装备数据格式异常：{exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("装备数据格式异常：根节点不是对象")
    return parse_tencent_items(payload)


def parse_tencent_items(payload: Mapping[str, Any]) -> ItemCatalogPayload:
    """解析腾讯官网装备数据对象。

    Args:
        payload: ``items.js`` 反序列化后的根对象。

    Returns:
        ItemCatalogPayload: 已清洗的装备资料。

    Raises:
        ValueError: ``items`` 字段不存在或不是列表。
    """
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("装备数据格式异常：缺少 items 列表")

    seen_ids: set[str] = set()
    items: list[ItemRecord] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            continue
        item_id = _as_text(raw_item.get("itemId"))
        name = _as_text(raw_item.get("name"))
        if not item_id or not name or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        items.append(
            ItemRecord(
                item_id=item_id,
                name=name,
                icon_url=_normalize_icon_url(raw_item.get("iconPath")),
                keywords=_as_text(raw_item.get("keywords")),
                maps=_normalize_maps(raw_item.get("maps")),
            )
        )

    return ItemCatalogPayload(
        version=_as_text(payload.get("version")),
        file_time=_as_text(payload.get("fileTime")),
        items=items,
    )


def fetch_tencent_items(
    *,
    url: str = TENCENT_ITEM_CATALOG_URL,
    timeout: int = DEFAULT_FETCH_TIMEOUT_SECONDS,
) -> ItemCatalogPayload:
    """下载并解析腾讯官网装备数据。

    Args:
        url: 装备数据 URL，默认使用腾讯官网公开 ``items.js``。
        timeout: 网络请求超时时间，单位为秒。

    Returns:
        ItemCatalogPayload: 已解析的装备资料。

    Raises:
        OSError: 网络请求失败。
        ValueError: 下载结果不是预期装备数据。
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "lol-audio-unpack-gui"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        text = response.read().decode(charset, errors="replace")
    return parse_tencent_items_text(text)


__all__ = [
    "DEFAULT_FETCH_TIMEOUT_SECONDS",
    "TENCENT_ITEM_CATALOG_URL",
    "ItemCatalogPayload",
    "ItemRecord",
    "fetch_tencent_items",
    "parse_tencent_items",
    "parse_tencent_items_text",
]
