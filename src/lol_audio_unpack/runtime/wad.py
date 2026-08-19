"""共享 WAD 运行时访问器。"""

from __future__ import annotations

import threading
from pathlib import Path

from league_tools import WAD

from lol_audio_unpack.model.binding import normalize_wad_identity


def resolve_bound_wad(game_path: Path, wad_identity: str) -> Path:
    """把 binding 的相对 WAD identity 解析为受游戏根约束的绝对路径。

    Args:
        game_path: 当前游戏根目录。
        wad_identity: P1 artifact 中保存的相对 WAD identity。

    Returns:
        已解析且不会越出游戏根目录的绝对路径。

    Raises:
        ValueError: identity 无效，或路径经 symlink 解析后越出游戏根目录。
    """
    game_root = Path(game_path).resolve()
    wad_path = (game_root / normalize_wad_identity(wad_identity)).resolve()
    try:
        wad_path.relative_to(game_root)
    except ValueError as exc:
        raise ValueError(f"WAD identity 解析后越出游戏根目录: {wad_identity}") from exc
    return wad_path


def get_wad(
    wad_path: Path,
    *,
    cache: dict[Path, WAD] | None,
    lock: threading.Lock | None,
) -> WAD:
    """返回可选缓存下的 WAD 实例。

    Args:
        wad_path: WAD 文件绝对路径。
        cache: 可复用的 WAD 实例缓存；为 ``None`` 时不缓存。
        lock: 多线程场景下的缓存锁。

    Returns:
        WAD: 对应路径的 ``WAD`` 实例。
    """
    # cache 和 lock 由调用方提供，这样 mapping / unpack 可以共享同一套复用语义，
    # 但又不用被迫依赖同一个 runtime cache 类型。
    if cache is None:
        return WAD(wad_path)

    if lock is None:
        if wad_path not in cache:
            cache[wad_path] = WAD(wad_path)
        return cache[wad_path]

    with lock:
        if wad_path not in cache:
            cache[wad_path] = WAD(wad_path)
        return cache[wad_path]
