"""配置入口与共享 schema 导出。"""

from __future__ import annotations

from .ini import (
    CONFIG_SECTION,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_DEV_CONFIG_FILENAME,
    load_command_config,
    load_settings,
    resolve_default_path,
    write_command_config,
    write_settings,
)
from .schema import (
    COMMAND_CONFIG_FIELDS,
    CONTEXT_OPTION_ATTRS,
    DEFAULT_REMOTE_LIVE_REGION,
    DEFAULT_SHARED_SETTINGS,
    SHARED_FIELDS_BY_CLI_ATTR,
    SHARED_FIELDS_BY_INI_KEY,
    SHARED_FIELDS_BY_KEY,
    SHARED_SETTING_FIELDS,
    SUPPORTED_SETTING_KEYS,
    CommandConfigField,
    ConfigSection,
    SettingKey,
    SharedSettingField,
    build_settings,
)

__all__ = [
    "COMMAND_CONFIG_FIELDS",
    "CONFIG_SECTION",
    "CONTEXT_OPTION_ATTRS",
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_DEV_CONFIG_FILENAME",
    "DEFAULT_REMOTE_LIVE_REGION",
    "DEFAULT_SHARED_SETTINGS",
    "SHARED_FIELDS_BY_CLI_ATTR",
    "SHARED_FIELDS_BY_INI_KEY",
    "SHARED_FIELDS_BY_KEY",
    "SHARED_SETTING_FIELDS",
    "SUPPORTED_SETTING_KEYS",
    "CommandConfigField",
    "ConfigSection",
    "SettingKey",
    "SharedSettingField",
    "build_settings",
    "load_command_config",
    "load_settings",
    "resolve_default_path",
    "write_command_config",
    "write_settings",
]
