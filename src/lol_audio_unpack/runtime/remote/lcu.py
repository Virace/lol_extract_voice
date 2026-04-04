"""远端 LCU manifest 与 bundle 相关辅助函数。"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.request import Request

from loguru import logger


def ensure_manifest_cached(
    *,
    manifest_url: str,
    manifest_cache_dir: Path,
    headers: dict[str, str],
    request_open: Callable[[Request], Any],
) -> Path:
    """缓存远端 manifest 文件。

    Args:
        manifest_url: manifest 下载地址。
        manifest_cache_dir: manifest 缓存目录。
        headers: 下载请求头。
        request_open: 发送请求的可调用对象。

    Returns:
        本地 manifest 缓存路径。
    """
    manifest_id = manifest_url.rstrip("/").rsplit("/", maxsplit=1)[-1]
    manifest_path = manifest_cache_dir / manifest_id
    if manifest_path.exists():
        return manifest_path

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(manifest_url, headers=headers)
    with request_open(request) as response, manifest_path.open("wb") as target:  # noqa: S310
        shutil.copyfileobj(response, target)
    logger.debug(f"已缓存远端 manifest: {manifest_path}")
    return manifest_path


def collect_files(
    manifest: Any,
    *,
    get_relative_path: Callable[[str], PurePosixPath | None],
) -> dict[str, Any]:
    """收集 LCU 插件目录内的 manifest 文件条目。

    Args:
        manifest: `PatcherManifest` 实例。
        get_relative_path: 解析 LCU 相对路径的回调。

    Returns:
        以插件相对路径为键的文件条目映射。
    """
    lcu_files: dict[str, Any] = {}
    for file in manifest.files.values():
        relative_path = get_relative_path(file.name)
        if relative_path is None:
            continue
        lcu_files[relative_path.as_posix()] = file
    return lcu_files


def find_description(lcu_files: dict[str, Any], *, description_file_name: str) -> Any:
    """定位 `description.json` 文件。

    Args:
        lcu_files: LCU 文件条目映射。
        description_file_name: 目标描述文件名。

    Returns:
        对应的 manifest 文件条目。

    Raises:
        FileNotFoundError: 目标描述文件缺失时抛出。
    """
    description_file = lcu_files.get(description_file_name)
    if description_file is None:
        raise FileNotFoundError("远端 LCU manifest 中缺少 rcp-be-lol-game-data/description.json")
    return description_file


def resolve_bundle_names(description_cache_path: Path, *, region: str) -> list[str]:
    """根据区域与 `description.json` 解析所需 bundle 名称。

    Args:
        description_cache_path: 已缓存的描述文件路径。
        region: 当前游戏区域。

    Returns:
        去重后的 bundle 文件名列表。
    """
    description = json.loads(description_cache_path.read_text(encoding="utf-8"))
    riot_meta = description.get("riotMeta")
    if not isinstance(riot_meta, dict):
        raise ValueError(f"description.json 缺少 riotMeta 字段: {description_cache_path}")

    global_bundles = riot_meta.get("globalAssetBundles", [])
    if not isinstance(global_bundles, list):
        raise ValueError("description.json 的 globalAssetBundles 字段类型异常")

    bundle_names = [str(item).strip() for item in global_bundles if str(item).strip()]
    if region != "default":
        per_locale = riot_meta.get("perLocaleAssetBundles", {})
        if not isinstance(per_locale, dict):
            raise ValueError("description.json 的 perLocaleAssetBundles 字段类型异常")

        locale_bundles = (
            per_locale.get(region)
            or per_locale.get(region.lower())
            or per_locale.get(region.upper())
            or []
        )
        if not isinstance(locale_bundles, list):
            raise ValueError(f"description.json 中 {region} 的 bundle 列表类型异常")
        bundle_names.extend(str(item).strip() for item in locale_bundles if str(item).strip())

    deduplicated_names: list[str] = []
    for bundle_name in bundle_names:
        if bundle_name not in deduplicated_names:
            deduplicated_names.append(bundle_name)
    return deduplicated_names


def resolve_bundle_files(bundle_names: list[str], lcu_files: dict[str, Any]) -> list[Any]:
    """把 bundle 文件名映射为 manifest 文件条目。

    Args:
        bundle_names: 需要解析的 bundle 文件名。
        lcu_files: LCU 文件条目映射。

    Returns:
        已解析的 manifest 文件条目列表。

    Raises:
        FileNotFoundError: 任一 bundle 未找到时抛出。
    """
    resolved_files: list[Any] = []
    missing_names: list[str] = []
    for bundle_name in bundle_names:
        bundle_file = lcu_files.get(bundle_name)
        if bundle_file is None:
            missing_names.append(bundle_name)
            continue
        resolved_files.append(bundle_file)

    if missing_names:
        missing_text = ", ".join(missing_names)
        raise FileNotFoundError(f"远端 LCU manifest 中缺少以下 bundle 文件: {missing_text}")
    return resolved_files


def ensure_files_downloaded(
    manifest: Any,
    files: list[Any],
    *,
    run_coroutine_sync: Callable[[Any], Any],
) -> list[Path]:
    """确保目标文件已下载到缓存目录。

    Args:
        manifest: `PatcherManifest` 实例。
        files: 需要确保存在的文件条目。
        run_coroutine_sync: 同步执行 manifest 下载协程的回调。

    Returns:
        对应的缓存文件路径列表。
    """
    output_paths = [Path(manifest.file_output(file)) for file in files]
    missing_files = [file for file, output_path in zip(files, output_paths, strict=True) if not output_path.exists()]

    if missing_files:
        for output_path in output_paths:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        run_coroutine_sync(manifest.download_files_concurrently(missing_files, raise_on_error=True))

    return output_paths
