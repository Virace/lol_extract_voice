"""GUI configuration persistence layer.

Uses QSettings (INI format, stored in the OS-default user config directory)
to save and restore all user-facing settings shown on SettingPage.

Key design decisions
--------------------
- **No coupling to CLI AppConfig**: The GUI config is its own source-of-truth
  for UI state.  When an unpack/mapping task is launched, the caller is
  responsible for reading these values and constructing the appropriate
  ``AppContext`` / ``OperationOptions``.
- **Flat, typed API**: Each setting is exposed as a typed Python property
  with a sensible default so call-sites never see raw QSettings strings.
- **Atomic save**: ``save()`` writes every known setting in one pass so
  partial-writes cannot leave the file inconsistent.
"""

from __future__ import annotations

import os
from pathlib import Path
from time import sleep

from dotenv import dotenv_values, set_key, unset_key
from PySide6.QtCore import QSettings

from lol_audio_unpack.gui.common.packaged_remote_mode_policy import effective_source_mode
from lol_audio_unpack.gui.task_models import AppContextInputSnapshot
from lol_audio_unpack.utils.runtime_paths import (
    detect_runtime_paths,
    get_default_output_root,
    resolve_runtime_path,
)

# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------

_UNSET = object()  # distinguishes "not in file" from ""


def _set_key_with_retry(env_file: Path, key: str, value: str) -> None:
    """在 Windows 瞬时文件锁场景下重试写入 env 配置。"""
    last_error: PermissionError | None = None
    for _ in range(3):
        try:
            set_key(env_file, key, value)
            return
        except PermissionError as exc:
            last_error = exc
            sleep(0.05)
    if last_error is not None:
        raise last_error


def _unset_key_with_retry(env_file: Path, key: str) -> None:
    """在 Windows 瞬时文件锁场景下重试删除 env 配置。"""
    last_error: PermissionError | None = None
    for _ in range(3):
        try:
            unset_key(env_file, key)
            return
        except PermissionError as exc:
            last_error = exc
            sleep(0.05)
    if last_error is not None:
        raise last_error


class GuiConfig:
    """Configuration manager for GUI, sharing CLI config via .lol.env."""

    def __init__(self, dev_mode: bool = False) -> None:
        # 共享 runtime 层负责决定默认配置目录，GUI 仅消费结果。
        self._env_dir = detect_runtime_paths().config_root

        self._dev_mode = dev_mode
        self._env_file = self._env_dir / (".lol.env.dev" if dev_mode else ".lol.env")

        # QSettings 用于 GUI 独有配置
        self._qs = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "ViraceLab", "LolAudioUnpack")

        # 内部缓存 — CLI 共享配置
        self._source_mode: str = "local_path"
        self._game_path: str = ""
        self._remote_live_region: str = "EUW"
        self._cleanup_remote: bool = True
        self._snapshot_version: str = ""
        self._snapshot_lcu_url: str = ""
        self._snapshot_game_url: str = ""
        self._remote_snapshot_strategy: str = "latest"
        self._output_path: str = ""
        self._game_region: str = "zh_CN"
        self._group_by_type: bool = False
        self._wwiser_path: str = ""
        self._vgmstream_path: str = ""

        # GUI 专有配置
        self._theme_mode: str = "Auto"  # Light, Dark, Auto
        self._theme_color: str = "#009faa"
        self._page_smooth_scroll_enabled: bool = False
        self._widget_smooth_scroll_enabled: bool = False
        self._log_drawer_auto_collapse_enabled: bool = True
        self._console_log_level: str = "INFO"
        self._file_log_level: str = "DEBUG"
        self._preview_audio_volume_percent: int = 10
        self._preview_audio_output_device_key: str = "default"

    def load(self) -> None:
        """从 .lol.env 和 QSettings 加载配置。"""
        env_values = dotenv_values(self._env_file) if self._env_file.exists() else {}

        def _shared_value(key: str, default: str) -> str:
            system_value = os.getenv(key)
            if system_value is not None:
                return system_value
            file_value = env_values.get(key)
            return default if file_value is None else str(file_value)

        # 1. 读取 CLI 共享配置，保持系统环境变量优先于 .lol.env
        self._source_mode = _shared_value("LOL_SOURCE_MODE", "local_path")
        self._game_path = _shared_value("LOL_GAME_PATH", "")
        self._remote_live_region = _shared_value("LOL_REMOTE_LIVE_REGION", "EUW")
        self._cleanup_remote = self._to_bool(_shared_value("LOL_CLEANUP_REMOTE", "true"))
        self._snapshot_version = _shared_value("LOL_REMOTE_VERSION", "")
        self._snapshot_lcu_url = _shared_value("LOL_REMOTE_LCU_MANIFEST_URL", "")
        self._snapshot_game_url = _shared_value("LOL_REMOTE_GAME_MANIFEST_URL", "")
        self._output_path = _shared_value("LOL_OUTPUT_PATH", "")
        self._game_region = _shared_value("LOL_GAME_REGION", "zh_CN")
        self._group_by_type = self._to_bool(_shared_value("LOL_GROUP_BY_TYPE", "false"))
        self._wwiser_path = _shared_value("LOL_WWISER_PATH", "")

        # 2. GUI 专有配置优先走 QSettings，兼容一次性迁移旧的 .lol.env 值
        stored_vgmstream_path = self._qs.value("vgmstream_path", _UNSET)
        if stored_vgmstream_path is _UNSET:
            self._vgmstream_path = _shared_value("LOL_VGMSTREAM_PATH", "")
        else:
            self._vgmstream_path = str(stored_vgmstream_path or "")

        if env_values.get("LOL_VGMSTREAM_PATH") is not None:
            self._qs.setValue("vgmstream_path", self._vgmstream_path)
            unset_key(self._env_file, "LOL_VGMSTREAM_PATH")

        inferred_snapshot_strategy = (
            "custom"
            if self._snapshot_version and self._snapshot_lcu_url and self._snapshot_game_url
            else "latest"
        )
        self._remote_snapshot_strategy = str(
            self._qs.value("remote_snapshot_strategy", inferred_snapshot_strategy) or inferred_snapshot_strategy
        )
        stored_snapshot_version = self._qs.value("remote_snapshot_version", _UNSET)
        if stored_snapshot_version is not _UNSET:
            self._snapshot_version = str(stored_snapshot_version or "")
        stored_snapshot_lcu_url = self._qs.value("remote_snapshot_lcu_url", _UNSET)
        if stored_snapshot_lcu_url is not _UNSET:
            self._snapshot_lcu_url = str(stored_snapshot_lcu_url or "")
        stored_snapshot_game_url = self._qs.value("remote_snapshot_game_url", _UNSET)
        if stored_snapshot_game_url is not _UNSET:
            self._snapshot_game_url = str(stored_snapshot_game_url or "")

        # 3. 从 QSettings 读取 GUI 主题配置
        self._theme_mode = self._qs.value("theme_mode", "Auto")
        self._theme_color = self._qs.value("theme_color", "#009faa")

        legacy_smooth_scroll = self._qs.value("smooth_scroll_enabled", _UNSET)
        stored_page_smooth_scroll = self._qs.value("page_smooth_scroll_enabled", _UNSET)
        stored_widget_smooth_scroll = self._qs.value("widget_smooth_scroll_enabled", _UNSET)
        legacy_smooth_scroll_enabled = (
            False if legacy_smooth_scroll is _UNSET else self._to_bool(legacy_smooth_scroll)
        )
        self._page_smooth_scroll_enabled = (
            legacy_smooth_scroll_enabled
            if stored_page_smooth_scroll is _UNSET
            else self._to_bool(stored_page_smooth_scroll)
        )
        self._widget_smooth_scroll_enabled = (
            legacy_smooth_scroll_enabled
            if stored_widget_smooth_scroll is _UNSET
            else self._to_bool(stored_widget_smooth_scroll)
        )
        self._log_drawer_auto_collapse_enabled = self._to_bool(
            self._qs.value("log_drawer_auto_collapse_enabled", True)
        )
        self._console_log_level = str(self._qs.value("console_log_level", "INFO") or "INFO").upper()
        self._file_log_level = str(self._qs.value("file_log_level", "DEBUG") or "DEBUG").upper()
        self._preview_audio_volume_percent = self._clamp_percentage(
            self._qs.value("preview_audio_volume_percent", 10)
        )
        self._preview_audio_output_device_key = str(
            self._qs.value("preview_audio_output_device_key", "default") or "default"
        )

    def save(self) -> None:
        """保存配置到 .lol.env。"""
        # 确保目录存在
        self._env_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入 CLI 共享配置到 .lol.env
        _set_key_with_retry(self._env_file, "LOL_SOURCE_MODE", self._source_mode)
        _set_key_with_retry(self._env_file, "LOL_GAME_PATH", self._game_path)
        _set_key_with_retry(self._env_file, "LOL_REMOTE_LIVE_REGION", self._remote_live_region)
        _set_key_with_retry(self._env_file, "LOL_CLEANUP_REMOTE", str(self._cleanup_remote).lower())
        snapshot_overrides = self._snapshot_overrides()
        _set_key_with_retry(self._env_file, "LOL_REMOTE_VERSION", str(snapshot_overrides["REMOTE_VERSION"]))
        _set_key_with_retry(
            self._env_file,
            "LOL_REMOTE_LCU_MANIFEST_URL",
            str(snapshot_overrides["REMOTE_LCU_MANIFEST_URL"]),
        )
        _set_key_with_retry(
            self._env_file,
            "LOL_REMOTE_GAME_MANIFEST_URL",
            str(snapshot_overrides["REMOTE_GAME_MANIFEST_URL"]),
        )
        _set_key_with_retry(self._env_file, "LOL_OUTPUT_PATH", self._output_path)
        _set_key_with_retry(self._env_file, "LOL_GAME_REGION", self._game_region)
        _set_key_with_retry(self._env_file, "LOL_GROUP_BY_TYPE", str(self._group_by_type).lower())
        _set_key_with_retry(self._env_file, "LOL_WWISER_PATH", self._wwiser_path)

        # 保存 GUI 专有配置到 QSettings
        if dotenv_values(self._env_file).get("LOL_VGMSTREAM_PATH") is not None:
            _unset_key_with_retry(self._env_file, "LOL_VGMSTREAM_PATH")
        self._qs.setValue("vgmstream_path", self._vgmstream_path)
        self._qs.setValue("remote_snapshot_strategy", self._remote_snapshot_strategy)
        self._qs.setValue("remote_snapshot_version", self._snapshot_version)
        self._qs.setValue("remote_snapshot_lcu_url", self._snapshot_lcu_url)
        self._qs.setValue("remote_snapshot_game_url", self._snapshot_game_url)
        self._qs.setValue("theme_mode", self._theme_mode)
        self._qs.setValue("theme_color", self._theme_color)
        self._qs.setValue("page_smooth_scroll_enabled", self._page_smooth_scroll_enabled)
        self._qs.setValue("widget_smooth_scroll_enabled", self._widget_smooth_scroll_enabled)
        self._qs.setValue("log_drawer_auto_collapse_enabled", self._log_drawer_auto_collapse_enabled)
        self._qs.setValue("console_log_level", self._console_log_level)
        self._qs.setValue("file_log_level", self._file_log_level)
        self._qs.setValue("preview_audio_volume_percent", self._preview_audio_volume_percent)
        self._qs.setValue("preview_audio_output_device_key", self._preview_audio_output_device_key)
        self._qs.setValue("smooth_scroll_enabled", self.smooth_scroll_enabled)

    def save_theme_preferences(self) -> None:
        """仅保存主题相关的 GUI 偏好，不触碰共享 runtime 配置。"""
        self._qs.setValue("theme_mode", self._theme_mode)
        self._qs.setValue("theme_color", self._theme_color)

    def to_app_context_overrides(self) -> dict[str, str | bool]:
        """构建供 ``create_app_context`` 使用的配置映射。"""
        snapshot_overrides = self._snapshot_overrides()
        return {
            "SOURCE_MODE": self.effective_source_mode,
            "GAME_PATH": self._game_path,
            "OUTPUT_PATH": self._output_path,
            "GAME_REGION": self._game_region,
            "GROUP_BY_TYPE": self._group_by_type,
            "REMOTE_LIVE_REGION": self._remote_live_region,
            "CLEANUP_REMOTE": self._cleanup_remote,
            "REMOTE_VERSION": snapshot_overrides["REMOTE_VERSION"],
            "REMOTE_LCU_MANIFEST_URL": snapshot_overrides["REMOTE_LCU_MANIFEST_URL"],
            "REMOTE_GAME_MANIFEST_URL": snapshot_overrides["REMOTE_GAME_MANIFEST_URL"],
            "WWISER_PATH": self._wwiser_path,
        }

    def to_app_context_input_snapshot(self) -> AppContextInputSnapshot:
        """构建执行中心可直接消费的共享上下文输入快照。"""
        return AppContextInputSnapshot(
            overrides=tuple(self.to_app_context_overrides().items()),
        )

    def _resolve_optional_runtime_path(self, raw: str) -> Path | None:
        """按共享 runtime 语义解析可选路径。"""
        text = raw.strip()
        if not text:
            return None
        return resolve_runtime_path(text, runtime_paths=detect_runtime_paths())

    def resolve_game_path(self) -> Path | None:
        """解析当前 GUI 配置对应的有效游戏目录。"""
        return self._resolve_optional_runtime_path(self._game_path)

    def resolve_output_path(self) -> Path:
        """解析当前 GUI 配置对应的有效输出目录。

        Returns:
            Path: 已解析的绝对输出目录。若用户未显式配置，则回退到共享
                runtime 语义下的默认 ``output`` 目录。
        """
        runtime_paths = detect_runtime_paths()
        raw = self._output_path.strip()
        if not raw:
            return get_default_output_root(runtime_paths)

        return resolve_runtime_path(raw, runtime_paths=runtime_paths)

    def resolve_log_dir(self) -> Path:
        """解析当前 GUI 配置对应的有效日志目录。

        Returns:
            Path: 当前 GUI 启动期与运行期都应写入的日志目录。
        """
        return self.resolve_output_path() / "logs"

    def resolve_wwiser_path(self) -> Path | None:
        """解析当前 GUI 配置对应的有效 wwiser 工具路径。"""
        return self._resolve_optional_runtime_path(self._wwiser_path)

    def resolve_vgmstream_path(self) -> Path | None:
        """解析当前 GUI 配置对应的有效 vgmstream 工具路径。"""
        return self._resolve_optional_runtime_path(self._vgmstream_path)

    # ------------------------------------------------------------------
    # Properties — source
    # ------------------------------------------------------------------

    @property
    def source_mode(self) -> str:
        """``"local_path"`` or ``"remote_snapshot"``."""
        return self._source_mode

    @property
    def effective_source_mode(self) -> str:
        """返回 GUI 当前运行时应使用的来源模式。"""
        return effective_source_mode(self._source_mode)

    @source_mode.setter
    def source_mode(self, v: str) -> None:
        self._source_mode = v

    @property
    def game_path(self) -> str:
        """Absolute path to the local LoL game root directory."""
        return self._game_path

    @game_path.setter
    def game_path(self, v: str) -> None:
        self._game_path = v

    # ------------------------------------------------------------------
    # Properties — remote
    # ------------------------------------------------------------------

    @property
    def remote_live_region(self) -> str:
        """Riot live-region code for snapshot resolution (e.g. ``"EUW"``)."""
        return self._remote_live_region

    @remote_live_region.setter
    def remote_live_region(self, v: str) -> None:
        self._remote_live_region = v

    @property
    def cleanup_remote(self) -> bool:
        """Whether to clean up temporary remote files after extraction."""
        return self._cleanup_remote

    @cleanup_remote.setter
    def cleanup_remote(self, v: bool) -> None:
        self._cleanup_remote = v

    @property
    def remote_snapshot_strategy(self) -> str:
        """返回远端快照来源策略。"""
        return self._remote_snapshot_strategy

    @remote_snapshot_strategy.setter
    def remote_snapshot_strategy(self, value: str) -> None:
        normalized = str(value or "latest").strip().lower()
        self._remote_snapshot_strategy = "custom" if normalized == "custom" else "latest"

    @property
    def snapshot_version(self) -> str:
        return self._snapshot_version

    @snapshot_version.setter
    def snapshot_version(self, v: str) -> None:
        self._snapshot_version = v

    @property
    def snapshot_lcu_url(self) -> str:
        return self._snapshot_lcu_url

    @snapshot_lcu_url.setter
    def snapshot_lcu_url(self, v: str) -> None:
        self._snapshot_lcu_url = v

    @property
    def snapshot_game_url(self) -> str:
        return self._snapshot_game_url

    @snapshot_game_url.setter
    def snapshot_game_url(self, v: str) -> None:
        self._snapshot_game_url = v

    # ------------------------------------------------------------------
    # Properties — base
    # ------------------------------------------------------------------

    @property
    def output_path(self) -> str:
        """Absolute path where extracted audio files are written."""
        return self._output_path

    @output_path.setter
    def output_path(self, v: str) -> None:
        self._output_path = v

    @property
    def game_region(self) -> str:
        """Language / region tag, e.g. ``"zh_CN"``."""
        return self._game_region

    @game_region.setter
    def game_region(self, v: str) -> None:
        self._game_region = v

    @property
    def group_by_type(self) -> bool:
        """If ``True``: ``audios/type/hero/…``; else ``audios/hero/type/…``."""
        return self._group_by_type

    @group_by_type.setter
    def group_by_type(self, v: bool) -> None:
        self._group_by_type = v

    # ------------------------------------------------------------------
    # Properties — tools
    # ------------------------------------------------------------------

    @property
    def wwiser_path(self) -> str:
        """Absolute path to ``wwiser.py``."""
        return self._wwiser_path

    @wwiser_path.setter
    def wwiser_path(self, v: str) -> None:
        self._wwiser_path = v

    @property
    def vgmstream_path(self) -> str:
        """Absolute path to ``vgmstream-cli.exe``."""
        return self._vgmstream_path

    @vgmstream_path.setter
    def vgmstream_path(self, v: str) -> None:
        self._vgmstream_path = v

    # ------------------------------------------------------------------
    # Properties — GUI 专有
    # ------------------------------------------------------------------

    @property
    def theme_mode(self) -> str:
        """主题模式: Light, Dark, Auto"""
        return self._theme_mode

    @theme_mode.setter
    def theme_mode(self, v: str) -> None:
        self._theme_mode = v

    @property
    def theme_color(self) -> str:
        """主题颜色 (hex 格式，如 #009faa)"""
        return self._theme_color

    @theme_color.setter
    def theme_color(self, v: str) -> None:
        self._theme_color = v

    @property
    def page_smooth_scroll_enabled(self) -> bool:
        """是否启用页面级平滑滚动。"""
        return self._page_smooth_scroll_enabled

    @page_smooth_scroll_enabled.setter
    def page_smooth_scroll_enabled(self, v: bool) -> None:
        self._page_smooth_scroll_enabled = bool(v)

    @property
    def widget_smooth_scroll_enabled(self) -> bool:
        """是否启用控件级平滑滚动。"""
        return self._widget_smooth_scroll_enabled

    @widget_smooth_scroll_enabled.setter
    def widget_smooth_scroll_enabled(self, v: bool) -> None:
        self._widget_smooth_scroll_enabled = bool(v)

    @property
    def smooth_scroll_enabled(self) -> bool:
        """兼容旧配置的聚合平滑滚动开关。"""
        return self._page_smooth_scroll_enabled and self._widget_smooth_scroll_enabled

    @smooth_scroll_enabled.setter
    def smooth_scroll_enabled(self, v: bool) -> None:
        enabled = bool(v)
        self._page_smooth_scroll_enabled = enabled
        self._widget_smooth_scroll_enabled = enabled

    @property
    def log_drawer_auto_collapse_enabled(self) -> bool:
        """点击日志抽屉外部区域时是否自动收起。"""
        return self._log_drawer_auto_collapse_enabled

    @log_drawer_auto_collapse_enabled.setter
    def log_drawer_auto_collapse_enabled(self, v: bool) -> None:
        self._log_drawer_auto_collapse_enabled = bool(v)

    @property
    def console_log_level(self) -> str:
        """控制台与窗口日志级别。"""
        return self._console_log_level

    @console_log_level.setter
    def console_log_level(self, v: str) -> None:
        self._console_log_level = str(v).upper()

    @property
    def file_log_level(self) -> str:
        """文件日志级别。"""
        return self._file_log_level

    @file_log_level.setter
    def file_log_level(self, v: str) -> None:
        self._file_log_level = str(v).upper()

    @property
    def preview_audio_volume_percent(self) -> int:
        """试听音量百分比。"""
        return self._preview_audio_volume_percent

    @preview_audio_volume_percent.setter
    def preview_audio_volume_percent(self, value: int) -> None:
        self._preview_audio_volume_percent = self._clamp_percentage(value)

    @property
    def preview_audio_output_device_key(self) -> str:
        """试听输出设备键值。"""
        return self._preview_audio_output_device_key

    @preview_audio_output_device_key.setter
    def preview_audio_output_device_key(self, value: str) -> None:
        text = str(value or "").strip()
        self._preview_audio_output_device_key = text or "default"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_bool(v: str | bool) -> bool:
        """Coerce env var string to Python bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    @staticmethod
    def _clamp_percentage(value) -> int:
        """将任意输入约束到 0~100 的整数百分比。"""
        try:
            normalized = int(round(float(value)))
        except (TypeError, ValueError):
            normalized = 10
        return max(0, min(100, normalized))

    def _snapshot_overrides(self) -> dict[str, str]:
        """根据当前远端快照策略构建实际生效的快照覆盖项。"""
        if self._source_mode != "remote_snapshot" or self._remote_snapshot_strategy != "custom":
            return {
                "REMOTE_VERSION": "",
                "REMOTE_LCU_MANIFEST_URL": "",
                "REMOTE_GAME_MANIFEST_URL": "",
            }

        return {
            "REMOTE_VERSION": self._snapshot_version,
            "REMOTE_LCU_MANIFEST_URL": self._snapshot_lcu_url,
            "REMOTE_GAME_MANIFEST_URL": self._snapshot_game_url,
        }
