"""远端来源配置的草稿与运行时生效控制器。"""

from __future__ import annotations

from dataclasses import dataclass

from lol_audio_unpack.gui.common.gui_config import GuiConfig


@dataclass(slots=True)
class RemoteSourceDraft:
    """描述远端来源配置草稿。"""

    source_mode: str
    strategy: str
    live_region: str
    cleanup_remote: bool
    snapshot_version: str
    snapshot_lcu_url: str
    snapshot_game_url: str

    @property
    def uses_latest(self) -> bool:
        """返回当前草稿是否使用 latest live 解析。"""
        return self.strategy == "latest"

    @property
    def uses_custom_snapshot(self) -> bool:
        """返回当前草稿是否使用固定快照。"""
        return self.strategy == "custom"

    @property
    def custom_snapshot_complete(self) -> bool:
        """返回固定快照三元组是否已完整填写。"""
        return bool(self.snapshot_version and self.snapshot_lcu_url and self.snapshot_game_url)

    @property
    def is_remote_mode(self) -> bool:
        """返回当前草稿是否处于远端模式。"""
        return self.source_mode == "remote_snapshot"


class RemoteSourceController:
    """负责 latest/custom 草稿态与远端运行时摘要计算。"""

    def draft_from_config(self, cfg: GuiConfig) -> RemoteSourceDraft:
        """从当前配置构建一份远端来源草稿。"""
        return RemoteSourceDraft(
            source_mode=cfg.source_mode,
            strategy=cfg.remote_snapshot_strategy,
            live_region=cfg.remote_live_region,
            cleanup_remote=cfg.cleanup_remote,
            snapshot_version=cfg.snapshot_version,
            snapshot_lcu_url=cfg.snapshot_lcu_url,
            snapshot_game_url=cfg.snapshot_game_url,
        )

    def build_draft(  # noqa: PLR0913
        self,
        *,
        source_mode: str,
        strategy: str,
        live_region: str,
        cleanup_remote: bool,
        snapshot_version: str,
        snapshot_lcu_url: str,
        snapshot_game_url: str,
    ) -> RemoteSourceDraft:
        """根据当前界面值构建一份远端来源草稿。"""
        return RemoteSourceDraft(
            source_mode=source_mode,
            strategy=strategy,
            live_region=live_region,
            cleanup_remote=cleanup_remote,
            snapshot_version=snapshot_version.strip(),
            snapshot_lcu_url=snapshot_lcu_url.strip(),
            snapshot_game_url=snapshot_game_url.strip(),
        )

    def apply_draft_to_config(
        self,
        cfg: GuiConfig,
        draft: RemoteSourceDraft,
        *,
        persist_remote_source_mode: bool,
    ) -> None:
        """把远端来源草稿写回配置对象。"""
        if persist_remote_source_mode:
            cfg.source_mode = draft.source_mode
        elif draft.source_mode == "local_path":
            cfg.source_mode = "local_path"

        cfg.remote_snapshot_strategy = draft.strategy
        cfg.remote_live_region = draft.live_region
        cfg.cleanup_remote = draft.cleanup_remote
        cfg.snapshot_version = draft.snapshot_version
        cfg.snapshot_lcu_url = draft.snapshot_lcu_url
        cfg.snapshot_game_url = draft.snapshot_game_url

    def build_runtime_summary(self, draft: RemoteSourceDraft) -> tuple[str, str, bool]:
        """根据草稿生成提示文案与确认按钮状态。"""
        if draft.uses_latest:
            return (
                f"当前将使用：确认后按 {draft.live_region} 解析最新快照",
                "确认当前区服后，才会开始解析并重建共享实体数据。",
                draft.is_remote_mode,
            )

        if draft.custom_snapshot_complete:
            return (
                f"当前将使用：固定快照 {draft.snapshot_version}",
                "确认当前固定快照后，才会开始重建共享实体数据。",
                draft.is_remote_mode,
            )

        return (
            "当前将使用：自定义固定快照（待补全版本号与 Manifest URL）",
            "需要先填写完整的固定快照三元组，才能开始重建共享实体数据。",
            False,
        )
