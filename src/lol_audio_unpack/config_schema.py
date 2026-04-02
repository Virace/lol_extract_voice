"""共享配置 schema 定义。

本模块集中维护运行时共享配置的字段定义，包括：

- 内部 settings key
- INI 文件中的小写 key
- CLI 对应的 argparse attr 名
- 默认值

后续若新增、删除或重命名共享配置字段，应优先修改本文件，
再由调用方复用这里的集中映射，避免同一语义散落在多处字符串字面量中。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SettingKey:
    """共享配置 key 常量。"""

    SOURCE_MODE = "SOURCE_MODE"
    GAME_PATH = "GAME_PATH"
    OUTPUT_PATH = "OUTPUT_PATH"
    GAME_REGION = "GAME_REGION"
    EXCLUDE_TYPE = "EXCLUDE_TYPE"
    CLEANUP_REMOTE = "CLEANUP_REMOTE"
    GROUP_BY_TYPE = "GROUP_BY_TYPE"
    REMOTE_LIVE_REGION = "REMOTE_LIVE_REGION"
    REMOTE_VERSION = "REMOTE_VERSION"
    REMOTE_LCU_MANIFEST_URL = "REMOTE_LCU_MANIFEST_URL"
    REMOTE_GAME_MANIFEST_URL = "REMOTE_GAME_MANIFEST_URL"
    WITH_BP_VO = "WITH_BP_VO"
    WWISER_PATH = "WWISER_PATH"


class ConfigSection:
    """标准 INI section 名。"""

    APP = "app"
    TARGETS = "targets"
    RUNTIME = "runtime"
    UPDATE = "update"
    EXTRACT = "extract"
    WAV = "wav"
    MAPPING = "mapping"


DEFAULT_REMOTE_LIVE_REGION = "EUW"


@dataclass(frozen=True)
class SharedSettingField:
    """单个共享配置字段定义。"""

    key: str
    ini_key: str
    cli_attr: str | None = None
    default: Any = None


@dataclass(frozen=True)
class CommandConfigField:
    """单个命令配置字段定义。"""

    attr: str
    ini_key: str
    value_kind: str


SHARED_SETTING_FIELDS: tuple[SharedSettingField, ...] = (
    SharedSettingField(SettingKey.SOURCE_MODE, "source_mode", "source_mode", "local_path"),
    SharedSettingField(SettingKey.GAME_PATH, "game_path", "game_path"),
    SharedSettingField(SettingKey.OUTPUT_PATH, "output_path", "output_path"),
    SharedSettingField(SettingKey.GAME_REGION, "game_region", "game_region", "zh_CN"),
    SharedSettingField(SettingKey.EXCLUDE_TYPE, "exclude_type", "exclude_type", "SFX,MUSIC"),
    SharedSettingField(SettingKey.CLEANUP_REMOTE, "cleanup_remote", "cleanup_remote", True),
    SharedSettingField(SettingKey.GROUP_BY_TYPE, "group_by_type", "group_by_type", False),
    SharedSettingField(
        SettingKey.REMOTE_LIVE_REGION,
        "remote_live_region",
        "remote_live_region",
        DEFAULT_REMOTE_LIVE_REGION,
    ),
    SharedSettingField(SettingKey.REMOTE_VERSION, "remote_version", "remote_version"),
    SharedSettingField(
        SettingKey.REMOTE_LCU_MANIFEST_URL,
        "remote_lcu_manifest_url",
        "remote_lcu_manifest_url",
    ),
    SharedSettingField(
        SettingKey.REMOTE_GAME_MANIFEST_URL,
        "remote_game_manifest_url",
        "remote_game_manifest_url",
    ),
    SharedSettingField(SettingKey.WITH_BP_VO, "with_bp_vo", "with_bp_vo", False),
    SharedSettingField(SettingKey.WWISER_PATH, "wwiser_path", "wwiser_path"),
)

SHARED_SETTING_FIELD_BY_KEY: dict[str, SharedSettingField] = {
    field.key: field for field in SHARED_SETTING_FIELDS
}
SHARED_SETTING_FIELD_BY_INI_KEY: dict[str, SharedSettingField] = {
    field.ini_key: field for field in SHARED_SETTING_FIELDS
}
SHARED_SETTING_FIELD_BY_CLI_ATTR: dict[str, SharedSettingField] = {
    field.cli_attr: field for field in SHARED_SETTING_FIELDS if field.cli_attr is not None
}

SUPPORTED_SETTING_KEYS: frozenset[str] = frozenset(SHARED_SETTING_FIELD_BY_KEY)
DEFAULT_SHARED_SETTINGS: dict[str, Any] = {
    field.key: field.default for field in SHARED_SETTING_FIELDS if field.default is not None
}
BASE_CONTEXT_OPTION_ATTRS: tuple[str, ...] = tuple(SHARED_SETTING_FIELD_BY_CLI_ATTR)

COMMAND_CONFIG_FIELDS: dict[str, tuple[CommandConfigField, ...]] = {
    ConfigSection.TARGETS: (
        CommandConfigField("champions", "champions", "text"),
        CommandConfigField("maps", "maps", "text"),
    ),
    ConfigSection.RUNTIME: (
        CommandConfigField("max_workers", "max_workers", "int"),
    ),
    ConfigSection.UPDATE: (
        CommandConfigField("force", "force", "bool"),
        CommandConfigField("skip_events", "skip_events", "bool"),
    ),
    ConfigSection.EXTRACT: (
        CommandConfigField("wav", "wav", "bool"),
    ),
    ConfigSection.WAV: (
        CommandConfigField("wav_workers", "wav_workers", "int"),
        CommandConfigField("wav_timeout", "wav_timeout", "int"),
        CommandConfigField("wav_retries", "wav_retries", "int"),
        CommandConfigField("wav_format", "wav_format", "text"),
    ),
    ConfigSection.MAPPING: (
        CommandConfigField("integrate_data", "integrate_data", "bool"),
    ),
}


def build_settings_from_namespace(args: Any) -> dict[str, Any]:
    """从 argparse namespace 构建显式共享配置。"""
    settings: dict[str, Any] = {}
    for attr_name, field in SHARED_SETTING_FIELD_BY_CLI_ATTR.items():
        value = getattr(args, attr_name, None)
        if value is not None:
            settings[field.key] = value
    return settings
