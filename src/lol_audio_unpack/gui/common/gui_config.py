"""GUI 配置持久化层。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from lol_audio_unpack.config import (
    DEFAULT_REMOTE_LIVE_REGION,
    ConfigSection,
    SettingKey,
    load_command_config,
    load_settings,
    remove_command_config_keys,
    resolve_default_path,
    write_command_config,
    write_settings,
)
from lol_audio_unpack.gui.common.packaged_remote_mode_policy import effective_source_mode
from lol_audio_unpack.gui.task_models import AppContextInputSnapshot
from lol_audio_unpack.gui.theme import (
    DEFAULT_ACCENT_PRESET_ID,
    get_accent_preset,
    resolve_accent_preset_id,
    resolve_legacy_accent_preset,
)
from lol_audio_unpack.utils.runtime_paths import (
    detect_runtime_paths,
    get_default_output_root,
    resolve_runtime_path,
)

# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------

_UNSET = object()  # distinguishes "not in file" from ""


class GuiConfig:
    """GUI 配置管理器。"""

    def __init__(self, dev_mode: bool = False) -> None:
        # 共享 runtime 层负责决定默认配置目录，GUI 仅消费结果。
        self._env_dir = detect_runtime_paths().config_root

        self._dev_mode = dev_mode
        self._config_file = resolve_default_path(dev_mode=dev_mode)

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
        self._wav_enabled: bool = False
        self._wav_workers: int = 2
        self._wav_timeout: int = 5
        self._wav_retries: int = 3
        self._wav_format: str = "pcm16"

        # GUI 专有配置
        self._theme_mode: str = "Auto"  # Light, Dark, Auto
        self._accent_preset_id: str = DEFAULT_ACCENT_PRESET_ID
        self._theme_color: str = get_accent_preset(self._accent_preset_id).primary_hex
        self._page_smooth_scroll_enabled: bool = False
        self._widget_smooth_scroll_enabled: bool = False
        self._log_drawer_auto_collapse_enabled: bool = True
        self._console_log_level: str = "INFO"
        self._file_log_level: str = "DEBUG"
        self._preview_audio_volume_percent: int = 10
        self._preview_audio_output_device_key: str = "default"

    def load(self) -> None:
        """从标准 INI 和 QSettings 加载配置。"""
        shared_settings = load_settings(self._config_file, require_exists=False)
        wav_settings = load_command_config(
            self._config_file,
            command=ConfigSection.WAV,
            require_exists=False,
        )

        def _shared_value(key: str, default: str) -> str:
            file_value = shared_settings.get(key)
            return default if file_value is None else str(file_value)

        # 1. 读取共享配置
        self._source_mode = _shared_value(SettingKey.SOURCE_MODE, "local_path")
        self._game_path = _shared_value(SettingKey.GAME_PATH, "")
        self._remote_live_region = _shared_value(SettingKey.REMOTE_LIVE_REGION, DEFAULT_REMOTE_LIVE_REGION)
        self._cleanup_remote = self._to_bool(_shared_value(SettingKey.CLEANUP_REMOTE, "true"))
        self._snapshot_version = _shared_value(SettingKey.REMOTE_VERSION, "")
        self._snapshot_lcu_url = _shared_value(SettingKey.REMOTE_LCU_MANIFEST_URL, "")
        self._snapshot_game_url = _shared_value(SettingKey.REMOTE_GAME_MANIFEST_URL, "")
        self._output_path = _shared_value(SettingKey.OUTPUT_PATH, "")
        self._game_region = _shared_value(SettingKey.GAME_REGION, "zh_CN")
        self._group_by_type = self._to_bool(_shared_value(SettingKey.GROUP_BY_TYPE, "false"))
        self._wwiser_path = _shared_value(SettingKey.WWISER_PATH, "")
        self._wav_enabled = bool(wav_settings.get("wav", False))
        self._wav_workers = int(wav_settings.get("wav_workers", 2))
        self._wav_timeout = int(wav_settings.get("wav_timeout", 5))
        self._wav_retries = int(wav_settings.get("wav_retries", 3))
        self._wav_format = str(wav_settings.get("wav_format", "pcm16") or "pcm16")

        # 2. GUI 专有配置只走 QSettings
        stored_vgmstream_path = self._qs.value("vgmstream_path", _UNSET)
        if stored_vgmstream_path is _UNSET:
            self._vgmstream_path = ""
        else:
            self._vgmstream_path = str(stored_vgmstream_path or "")

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
        self._theme_mode = str(self._qs.value("theme_mode", "Auto") or "Auto")
        stored_accent_preset = self._qs.value("accent_preset_id", _UNSET)
        stored_theme_color = str(self._qs.value("theme_color", self._theme_color) or self._theme_color)
        if stored_accent_preset is _UNSET:
            self._accent_preset_id = resolve_legacy_accent_preset(stored_theme_color)
        else:
            self._accent_preset_id = resolve_accent_preset_id(str(stored_accent_preset))
        self._theme_color = get_accent_preset(self._accent_preset_id).primary_hex

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
        """保存配置到标准 INI 与 QSettings。"""
        snapshot_overrides = self._snapshot_overrides()
        write_settings(
            self._config_file,
            {
                SettingKey.SOURCE_MODE: self._source_mode,
                SettingKey.GAME_PATH: self._game_path,
                SettingKey.REMOTE_LIVE_REGION: self._remote_live_region,
                SettingKey.CLEANUP_REMOTE: self._cleanup_remote,
                SettingKey.REMOTE_VERSION: snapshot_overrides[SettingKey.REMOTE_VERSION],
                SettingKey.REMOTE_LCU_MANIFEST_URL: snapshot_overrides[SettingKey.REMOTE_LCU_MANIFEST_URL],
                SettingKey.REMOTE_GAME_MANIFEST_URL: snapshot_overrides[SettingKey.REMOTE_GAME_MANIFEST_URL],
                SettingKey.OUTPUT_PATH: self._output_path,
                SettingKey.GAME_REGION: self._game_region,
                SettingKey.GROUP_BY_TYPE: self._group_by_type,
                SettingKey.WWISER_PATH: self._wwiser_path,
            },
        )
        write_command_config(
            self._config_file,
            command=ConfigSection.WAV,
            values={
                "wav": self._wav_enabled,
                "wav_workers": self._wav_workers,
                "wav_timeout": self._wav_timeout,
                "wav_retries": self._wav_retries,
                "wav_format": self._wav_format,
            },
        )
        remove_command_config_keys(
            self._config_file,
            command=ConfigSection.EXTRACT,
            ini_keys=("wav",),
        )

        # 保存 GUI 专有配置到 QSettings
        self._qs.setValue("vgmstream_path", self._vgmstream_path)
        self._qs.setValue("remote_snapshot_strategy", self._remote_snapshot_strategy)
        self._qs.setValue("remote_snapshot_version", self._snapshot_version)
        self._qs.setValue("remote_snapshot_lcu_url", self._snapshot_lcu_url)
        self._qs.setValue("remote_snapshot_game_url", self._snapshot_game_url)
        self._qs.setValue("theme_mode", self._theme_mode)
        self._qs.setValue("accent_preset_id", self._accent_preset_id)
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
        self._qs.setValue("accent_preset_id", self._accent_preset_id)

    def to_app_context_settings(self) -> dict[str, str | bool]:
        """构建供 ``create_app_context`` 使用的共享配置映射。"""
        snapshot_overrides = self._snapshot_overrides()
        return {
            SettingKey.SOURCE_MODE: self.effective_source_mode,
            SettingKey.GAME_PATH: self._game_path,
            SettingKey.OUTPUT_PATH: self._output_path,
            SettingKey.GAME_REGION: self._game_region,
            SettingKey.GROUP_BY_TYPE: self._group_by_type,
            SettingKey.REMOTE_LIVE_REGION: self._remote_live_region,
            SettingKey.CLEANUP_REMOTE: self._cleanup_remote,
            SettingKey.REMOTE_VERSION: snapshot_overrides[SettingKey.REMOTE_VERSION],
            SettingKey.REMOTE_LCU_MANIFEST_URL: snapshot_overrides[SettingKey.REMOTE_LCU_MANIFEST_URL],
            SettingKey.REMOTE_GAME_MANIFEST_URL: snapshot_overrides[SettingKey.REMOTE_GAME_MANIFEST_URL],
            SettingKey.WWISER_PATH: self._wwiser_path,
        }

    def to_app_context_input_snapshot(self) -> AppContextInputSnapshot:
        """构建执行中心可直接消费的共享上下文输入快照。"""
        return AppContextInputSnapshot(
            settings=tuple(self.to_app_context_settings().items()),
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

    @property
    def wav_enabled(self) -> bool:
        """返回执行中心默认是否启用音频转码。"""
        return self._wav_enabled

    @wav_enabled.setter
    def wav_enabled(self, value: bool) -> None:
        self._wav_enabled = bool(value)

    @property
    def wav_workers(self) -> int:
        """返回默认音频转码并发数。"""
        return self._wav_workers

    @wav_workers.setter
    def wav_workers(self, value: int) -> None:
        self._wav_workers = int(value)

    @property
    def wav_timeout(self) -> int:
        """返回默认单个音频转码任务超时时间。"""
        return self._wav_timeout

    @wav_timeout.setter
    def wav_timeout(self, value: int) -> None:
        self._wav_timeout = int(value)

    @property
    def wav_retries(self) -> int:
        """返回默认音频转码最大重试次数。"""
        return self._wav_retries

    @wav_retries.setter
    def wav_retries(self, value: int) -> None:
        self._wav_retries = int(value)

    @property
    def wav_format(self) -> str:
        """返回执行中心默认的 WAV 输出格式。"""
        return self._wav_format

    @wav_format.setter
    def wav_format(self, value: str) -> None:
        self._wav_format = str(value or "pcm16")

    # ------------------------------------------------------------------
    # Properties — GUI 专有
    # ------------------------------------------------------------------

    @property
    def theme_mode(self) -> str:
        """返回当前壳模式。"""
        return self._theme_mode

    @theme_mode.setter
    def theme_mode(self, v: str) -> None:
        self._theme_mode = str(v or "Auto")

    @property
    def accent_preset_id(self) -> str:
        """返回当前固定强调色预设标识。"""
        return self._accent_preset_id

    @accent_preset_id.setter
    def accent_preset_id(self, value: str) -> None:
        self._accent_preset_id = resolve_accent_preset_id(value)
        self._theme_color = get_accent_preset(self._accent_preset_id).primary_hex

    @property
    def theme_color(self) -> str:
        """返回当前强调色主值。"""
        return self._theme_color

    @theme_color.setter
    def theme_color(self, v: str) -> None:
        self._accent_preset_id = resolve_legacy_accent_preset(v)
        self._theme_color = get_accent_preset(self._accent_preset_id).primary_hex

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
                SettingKey.REMOTE_VERSION: "",
                SettingKey.REMOTE_LCU_MANIFEST_URL: "",
                SettingKey.REMOTE_GAME_MANIFEST_URL: "",
            }

        return {
            SettingKey.REMOTE_VERSION: self._snapshot_version,
            SettingKey.REMOTE_LCU_MANIFEST_URL: self._snapshot_lcu_url,
            SettingKey.REMOTE_GAME_MANIFEST_URL: self._snapshot_game_url,
        }
