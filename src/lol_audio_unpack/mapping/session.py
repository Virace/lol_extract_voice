"""映射流程会话缓存与后端辅助。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from league_tools import WAD, NativeHIRC, WwiserHIRC, WwiserManager

from lol_audio_unpack.runtime.wad import get_wad

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


ParsedHIRC = NativeHIRC | WwiserHIRC


def _resolve_wwiser_path(ctx: AppContext) -> Path | None:
    """解析并校验 wwiser 可执行路径。

    Args:
        ctx: 运行时上下文。

    Returns:
        Path | None: 可用的 wwiser 文件路径；未配置时返回 ``None``。

    Raises:
        ValueError: 配置了路径但文件不存在时抛出。
    """

    wwiser_path = ctx.wwiser_path
    if wwiser_path is None:
        return None

    path = Path(wwiser_path)
    if not path.is_file():
        raise ValueError(f"错误：Wwiser 工具路径不存在或不是文件: {path}")
    return path


def describe_hirc_backend(ctx: AppContext) -> str:
    """返回当前 mapping 流程的 HIRC 后端描述。

    Args:
        ctx: 运行时上下文。

    Returns:
        str: 当前使用的 HIRC 后端说明。
    """

    wwiser_path = _resolve_wwiser_path(ctx)
    if wwiser_path is None:
        return "NativeHIRC（默认）"
    return f"WwiserHIRC ({wwiser_path})"


def _create_wwiser_manager(ctx: AppContext) -> WwiserManager | None:
    """按上下文创建可选的 wwiser 管理器。

    Args:
        ctx: 运行时上下文。

    Returns:
        WwiserManager | None: 可复用的 wwiser 管理器。
    """

    wwiser_path = _resolve_wwiser_path(ctx)
    if wwiser_path is None:
        return None
    return WwiserManager(wwiser_path)


@dataclass
class RuntimeCache:
    """映射流程中的运行时缓存。

    Attributes:
        wad_cache: 已创建的 WAD 实例缓存。
        extract_cache: 本轮已提取的 ``(wad_path, bnk_rel_path)`` 集合。
        hirc_cache: 已解析的 HIRC 缓存。
        cache_lock: 多线程模式下的缓存互斥锁。
    """

    wad_cache: dict[Path, WAD] = field(default_factory=dict)
    extract_cache: set[tuple[Path, str]] = field(default_factory=set)
    hirc_cache: dict[tuple[Path, str], ParsedHIRC] = field(default_factory=dict)
    cache_lock: threading.Lock | None = None


def _get_wad(
    wad_path: Path,
    runtime_cache: RuntimeCache | None,
) -> WAD:
    """获取 WAD 实例并复用缓存。

    Args:
        wad_path: WAD 文件绝对路径。
        runtime_cache: 映射过程共享缓存；为 ``None`` 时不使用缓存。

    Returns:
        WAD: 对应路径的 ``WAD`` 实例。
    """

    wad_cache = None if runtime_cache is None else runtime_cache.wad_cache
    cache_lock = None if runtime_cache is None else runtime_cache.cache_lock
    return get_wad(wad_path, cache=wad_cache, lock=cache_lock)


def _is_bnk_extracted(
    key: tuple[Path, str],
    runtime_cache: RuntimeCache | None,
) -> bool:
    """检查 bnk 文件是否已在本轮执行中提取过。

    Args:
        key: 提取去重键，格式为 ``(wad_path, bnk_rel_path)``。
        runtime_cache: 映射过程共享缓存。

    Returns:
        bool: ``True`` 表示已提取过。
    """

    if runtime_cache is None:
        return False
    extract_cache = runtime_cache.extract_cache
    cache_lock = runtime_cache.cache_lock

    # 提取去重必须同时看 wad_path 和 bnk 相对路径，
    # 否则不同 WAD 中同名 bnk 会被错误地视为已提取。
    if cache_lock is None:
        return key in extract_cache
    with cache_lock:
        return key in extract_cache


def _mark_bnk_extracted(
    key: tuple[Path, str],
    runtime_cache: RuntimeCache | None,
) -> None:
    """标记 bnk 文件已提取。

    Args:
        key: 提取去重键，格式为 ``(wad_path, bnk_rel_path)``。
        runtime_cache: 映射过程共享缓存。
    """

    if runtime_cache is None:
        return
    extract_cache = runtime_cache.extract_cache
    cache_lock = runtime_cache.cache_lock

    if cache_lock is None:
        extract_cache.add(key)
        return
    with cache_lock:
        extract_cache.add(key)


def _get_cached_hirc(
    bnk_path: Path,
    hirc_cache_dir: Path,
    wwiser_manager: WwiserManager | None,
    runtime_cache: RuntimeCache | None,
) -> ParsedHIRC:
    """获取 HIRC 对象并复用缓存。

    Args:
        bnk_path: bnk 文件路径。
        hirc_cache_dir: hirc 缓存目录。
        wwiser_manager: 可选的 wwiser 管理器；为 ``None`` 时走 ``NativeHIRC``。
        runtime_cache: 映射过程共享缓存。

    Returns:
        ParsedHIRC: 解析后的 HIRC 对象。
    """

    backend_key = "wwiser" if wwiser_manager is not None else "native"
    cache_key = (bnk_path, backend_key)

    def parse_hirc() -> ParsedHIRC:
        if wwiser_manager is None:
            return NativeHIRC.from_bnk(bnk_path, cache_dir=hirc_cache_dir)
        return WwiserHIRC.from_bnk(
            bnk_path,
            cache_dir=hirc_cache_dir,
            wwiser_manager=wwiser_manager,
        )

    if runtime_cache is None:
        return parse_hirc()

    hirc_cache = runtime_cache.hirc_cache
    cache_lock = runtime_cache.cache_lock

    if cache_lock is None:
        cached = hirc_cache.get(cache_key)
        if cached is not None:
            return cached
        parsed = parse_hirc()
        hirc_cache[cache_key] = parsed
        return parsed

    # 这里刻意不用“持锁解析”：
    # HIRC 解析本身可能较慢，若全程占锁会把其他类别处理全部阻塞住。
    with cache_lock:
        cached = hirc_cache.get(cache_key)
    if cached is not None:
        return cached

    parsed = parse_hirc()
    with cache_lock:
        # 二次确认是为了兼容并发场景：
        # 可能在当前线程解析期间，其他线程已经把同一个 cache_key 填进缓存。
        existing = hirc_cache.get(cache_key)
        if existing is not None:
            return existing
        hirc_cache[cache_key] = parsed
        return parsed
