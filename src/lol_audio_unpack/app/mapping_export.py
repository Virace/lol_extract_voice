"""根据实体 ID 读取已有映射，提供完整 JSON 导出。"""

from __future__ import annotations

import json
from pathlib import Path

from lol_audio_unpack.manager.files import read_data
from lol_audio_unpack.runtime.library.types import normalize_region, resolve_path

from .artifacts import find_mapping


def load_mapping(
    output_root: Path,
    *,
    entity_dir: str,
    entity_id: int,
    version: str | None = None,
    region: str = "zh_CN",
) -> tuple[Path, dict]:
    """按 ID 定位已有 mapping，版本不唯一时要求显式选择。

    Args:
        output_root: 主流程输出目录。
        entity_dir: ``champions`` 或 ``maps``。
        entity_id: 非负英雄或地图 ID。
        version: 指定已有版本；省略时只接受唯一匹配版本。
        region: 与生成映射时相同的语言区域。

    Returns:
        映射来源路径和完整数据，不生成或修复任何产物。

    Raises:
        ValueError: 选择无效、版本不唯一或未生成映射。
    """
    if entity_dir not in {"champions", "maps"} or entity_id < 0:
        raise ValueError("请提供非负的英雄或地图 ID")
    root = output_root.resolve() / "hashes"
    region = normalize_region(region)
    if version:
        versions = [resolve_path(root, version)]
    else:
        versions = sorted(root.iterdir()) if root.is_dir() else []
    candidates = []
    for folder in versions:
        if folder.is_dir():
            path = find_mapping(resolve_path(folder, region), entity_dir=entity_dir, entity_id=entity_id)
            if path is not None:
                candidates.append(path)
    if not candidates:
        flag = "--champions" if entity_dir == "champions" else "--maps"
        raise ValueError(
            f"未找到 {entity_dir}/{entity_id} 的映射；请先执行 update mapping {flag} {entity_id}，"
            "并使用相同的 --output-path 和 --game-region。"
        )
    if len(candidates) > 1:
        names = [path.relative_to(root).parts[0] for path in candidates]
        raise ValueError(f"存在多个版本：{', '.join(names)}；请使用 --game-version 选择")
    path = candidates[0]
    return path, read_data(path)


def mapping_json(data: dict) -> str:
    """生成完整可读 JSON；整数对象键转为字符串，拒绝同名键丢失。

    Args:
        data: 已读取的原始 mapping 数据。

    Returns:
        UTF-8 可表示的 JSON 文本，保留完整字段与数组顺序。
    """

    def validate(value: object) -> None:
        """递归检查对象键，避免 JSON 隐式转字符串后覆盖同名条目。"""
        if isinstance(value, dict):
            if any(type(key) not in (str, int) for key in value):
                raise ValueError("映射 JSON 仅支持字符串或整数对象键")
            if len({str(key) for key in value}) != len(value):
                raise ValueError("映射中存在 JSON 转换后同名的对象键")
            for child in value.values():
                validate(child)
        elif isinstance(value, list):
            for child in value:
                validate(child)

    validate(data)
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
