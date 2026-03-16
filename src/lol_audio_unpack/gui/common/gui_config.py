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

from PySide6.QtCore import QSettings


# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------

_UNSET = object()  # distinguishes "not in file" from ""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key


class GuiConfig:
    """Configuration manager for GUI, sharing CLI config via .lol.env."""

    def __init__(self, dev_mode: bool = False) -> None:
        # 确定配置文件路径
        if getattr(sys, 'frozen', False):
            # 打包模式：程序所在目录
            self._env_dir = Path(sys.executable).parent
        else:
            # 开发模式：cwd
            self._env_dir = Path.cwd()

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
        self._output_path: str = ""
        self._game_region: str = "zh_CN"
        self._group_by_type: bool = False
        self._wwiser_path: str = ""
        self._vgmstream_path: str = ""

        # GUI 专有配置
        self._theme_mode: str = "Auto"  # Light, Dark, Auto
        self._theme_color: str = "#009faa"

    def load(self) -> None:
        """从 .lol.env 和 QSettings 加载配置。"""
        # 1. 加载 .lol.env 文件到环境变量
        if self._env_file.exists():
            load_dotenv(self._env_file, override=False)

        # 2. 从环境变量读取 CLI 共享配置
        self._source_mode = os.getenv("LOL_SOURCE_MODE", "local_path")
        self._game_path = os.getenv("LOL_GAME_PATH", "")
        self._remote_live_region = os.getenv("LOL_REMOTE_LIVE_REGION", "EUW")
        self._cleanup_remote = self._to_bool(os.getenv("LOL_CLEANUP_REMOTE", "true"))
        self._snapshot_version = os.getenv("LOL_REMOTE_VERSION", "")
        self._snapshot_lcu_url = os.getenv("LOL_REMOTE_LCU_MANIFEST_URL", "")
        self._snapshot_game_url = os.getenv("LOL_REMOTE_GAME_MANIFEST_URL", "")
        self._output_path = os.getenv("LOL_OUTPUT_PATH", "")
        self._game_region = os.getenv("LOL_GAME_REGION", "zh_CN")
        self._group_by_type = self._to_bool(os.getenv("LOL_GROUP_BY_TYPE", "false"))
        self._wwiser_path = os.getenv("LOL_WWISER_PATH", "")
        self._vgmstream_path = os.getenv("LOL_VGMSTREAM_PATH", "")

        # 3. 从 QSettings 读取 GUI 专有配置
        self._theme_mode = self._qs.value("theme_mode", "Auto")
        self._theme_color = self._qs.value("theme_color", "#009faa")

    def save(self) -> None:
        """保存配置到 .lol.env。"""
        # 确保目录存在
        self._env_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入 CLI 共享配置到 .lol.env
        set_key(self._env_file, "LOL_SOURCE_MODE", self._source_mode)
        set_key(self._env_file, "LOL_GAME_PATH", self._game_path)
        set_key(self._env_file, "LOL_REMOTE_LIVE_REGION", self._remote_live_region)
        set_key(self._env_file, "LOL_CLEANUP_REMOTE", str(self._cleanup_remote).lower())
        set_key(self._env_file, "LOL_REMOTE_VERSION", self._snapshot_version)
        set_key(self._env_file, "LOL_REMOTE_LCU_MANIFEST_URL", self._snapshot_lcu_url)
        set_key(self._env_file, "LOL_REMOTE_GAME_MANIFEST_URL", self._snapshot_game_url)
        set_key(self._env_file, "LOL_OUTPUT_PATH", self._output_path)
        set_key(self._env_file, "LOL_GAME_REGION", self._game_region)
        set_key(self._env_file, "LOL_GROUP_BY_TYPE", str(self._group_by_type).lower())
        set_key(self._env_file, "LOL_WWISER_PATH", self._wwiser_path)
        set_key(self._env_file, "LOL_VGMSTREAM_PATH", self._vgmstream_path)

        # 保存 GUI 专有配置到 QSettings
        self._qs.setValue("theme_mode", self._theme_mode)
        self._qs.setValue("theme_color", self._theme_color)

    # ------------------------------------------------------------------
    # Properties — source
    # ------------------------------------------------------------------

    @property
    def source_mode(self) -> str:
        """``"local_path"`` or ``"remote_snapshot"``."""
        return self._source_mode

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
