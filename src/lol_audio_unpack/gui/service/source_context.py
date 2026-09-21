"""在共享上下文后台构建中生成目录快照，不在 GUI 线程访问游戏文件。"""

from lol_audio_unpack.app.context import create_app_context
from lol_audio_unpack.app.lobby import repair_lobby
from lol_audio_unpack.app.types import AppContext
from lol_audio_unpack.manager.source_inventory import scan_inventory
from lol_audio_unpack.model.progress import OperationProgress


def create_source_context(*, settings: dict, progress_callback=None) -> AppContext:
    """建立允许空语言的发现上下文，每次刷新重新检查物理文件。"""
    ctx = create_app_context(settings=settings, allow_empty_language=True, progress_callback=progress_callback)
    if progress_callback:
        progress_callback(OperationProgress("startup", "source_inventory", "started"))
    ctx.runtime_cache["source_inventory"] = scan_inventory(ctx.config.game_path)
    if ctx.game_region and ctx.runtime_cache["source_inventory"].get_language(ctx.game_region) is not None:
        repair_lobby(ctx)
    return ctx
