"""GUI 中与 AppContext 创建前置门禁相关的公共判断。"""

from __future__ import annotations


def get_app_context_block_reason(cfg: object | None) -> str | None:
    """返回当前配置是否应阻止创建 ``AppContext`` 的原因。

    Args:
        cfg: GUI 当前持有的运行配置对象，通常为 ``GuiConfig`` 或测试替身。

    Returns:
        若当前配置已经具备创建 ``AppContext`` 的最小前提，返回 ``None``；
        否则返回可直接反馈给用户的阻止原因文案。
    """
    if cfg is None:
        return None

    if getattr(cfg, "source_mode", "local_path") != "local_path":
        return None

    raw_game_path = str(getattr(cfg, "game_path", "") or "").strip()
    if not raw_game_path:
        return "请先在「全局设置」中配置游戏目录。"

    resolver = getattr(cfg, "resolve_game_path", None)
    resolved_game_path = resolver() if callable(resolver) else None
    if resolved_game_path is None:
        return "当前游戏目录不存在，请先在「全局设置」中修正路径。"
    if hasattr(resolved_game_path, "exists") and not resolved_game_path.exists():
        return "当前游戏目录不存在，请先在「全局设置」中修正路径。"
    return None
