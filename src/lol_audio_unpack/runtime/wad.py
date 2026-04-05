"""共享 WAD 运行时访问器。"""

from __future__ import annotations

import threading
from pathlib import Path

from league_tools import WAD


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
