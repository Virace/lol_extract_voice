"""在共享上下文后台构建中生成目录快照，不在 GUI 线程访问游戏文件。"""

from lol_audio_unpack.app.context import create_app_context
from lol_audio_unpack.app.types import AppContext
from lol_audio_unpack.manager.source_inventory import scan_inventory


def create_source_context(*, settings: dict) -> AppContext:
    """建立允许空语言的发现上下文，每次刷新重新检查物理文件。"""
    ctx = create_app_context(settings=settings, allow_empty_language=True)
    ctx.runtime_cache["source_inventory"] = scan_inventory(ctx.config.game_path)
    return ctx
