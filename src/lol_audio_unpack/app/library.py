"""把实体归属和可见布局投影到内容库，不承担 WAD 或转码解析。"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING

from lol_audio_unpack.runtime.library import Library, MediaRef

if TYPE_CHECKING:
    from lol_audio_unpack.model.entity import AudioBank, AudioEntityData

    from .types import AppContext


def with_library(function: Callable) -> Callable:
    """为入口持有一个库写锁，内部实体线程共用该实例。"""

    @wraps(function)
    def run(*args, ctx: AppContext, **kwargs):
        with library_session(ctx):
            return function(*args, ctx=ctx, **kwargs)

    return run


@contextmanager
def library_session(ctx: AppContext):
    """共享数据更新与媒体写入共用一个库门禁，内部子步骤复用当前会话。"""
    if writer := ctx.runtime_cache.get("library_writer"):
        yield writer
        return
    with Library(ctx.config.output_path) as writer:
        ctx.runtime_cache["library_writer"] = writer
        try:
            yield writer
        finally:
            ctx.runtime_cache.pop("library_writer", None)


def make_media(entity: AudioEntityData, bank: AudioBank, media_id: int, obj) -> MediaRef:
    """用实体、英雄皮肤与原 ID 构造内容引用。"""
    skin_id = bank.sub_id if entity.entity_type == "champion" else None
    return MediaRef(entity.entity_type, str(entity.entity_id), media_id, obj, skin_id)
