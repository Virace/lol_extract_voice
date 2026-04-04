# 配置与上下文 API

## 1. 当前配置主线

当前配置链路由三部分组成：

1. `settings`：传给 `create_app_context(...)` 的共享设置映射
2. 标准 INI：`lol_audio_unpack.config.ini` 负责读写
3. `AppContext`：只消费已经解析好的共享配置

## 2. `lol_audio_unpack.config`

### 2.1 schema 层

共享配置 schema 位于：

- `src/lol_audio_unpack/config/schema.py`

这里维护：

- `SettingKey`
- `ConfigSection`
- `SharedSettingField`
- `CommandConfigField`
- `SHARED_SETTING_FIELDS`
- `SHARED_FIELDS_BY_KEY`
- `SHARED_FIELDS_BY_INI_KEY`
- `SHARED_FIELDS_BY_CLI_ATTR`
- `SUPPORTED_SETTING_KEYS`
- `DEFAULT_SHARED_SETTINGS`
- `DEFAULT_REMOTE_LIVE_REGION`
- `COMMAND_CONFIG_FIELDS`
- `CONTEXT_OPTION_ATTRS`
- `build_settings(args)`

`build_settings(args)` 会从 argparse namespace 中提取共享配置字段，产出 `create_app_context(...)` 可直接消费的 `dict[str, Any]`。

### 2.2 INI 层

标准 INI 读写位于：

- `src/lol_audio_unpack/config/ini.py`

当前公开 helper：

```python
def resolve_default_path(
    *,
    dev_mode: bool = False,
    runtime_paths: RuntimePaths | None = None,
) -> Path


def load_settings(
    config_file: StrPath,
    *,
    require_exists: bool = True,
) -> dict[str, str]


def write_settings(
    config_file: StrPath,
    settings: dict[str, Any],
) -> None


def load_command_config(
    config_file: StrPath,
    *,
    command: str | None,
    require_exists: bool = True,
) -> dict[str, Any]


def write_command_config(
    config_file: StrPath,
    *,
    command: str,
    values: dict[str, Any],
) -> None
```

默认文件名：

- `lol-audio-unpack.ini`
- `lol-audio-unpack.dev.ini`

## 3. 运行时默认路径

`resolve_default_path(...)` 基于 `detect_runtime_paths()` 的 `config_root` 选择默认配置目录：

- 源码态：默认取当前工作目录
- 冻结态：默认取可执行文件所在目录

也就是说：

- 源码运行 GUI/CLI 时，默认配置文件落在当前启动目录
- 打包运行 GUI 时，默认配置文件落在可执行文件同目录

## 4. 标准 INI 结构

标准 section：

- `[app]`：共享配置
- `[targets]`：多个动作共享的实体范围
- `[runtime]`：多个动作共享的通用执行参数
- `[update]`：`update` 动作参数
- `[extract]`：`extract` 动作参数
- `[wav]`：WAV sidecar 细节参数
- `[mapping]`：`mapping` 动作参数

当前支持的命令字段：

- `[targets]`：`champions`、`maps`
- `[runtime]`：`max_workers`
- `[update]`：`force`、`skip_events`
- `[extract]`：`wav`
- `[wav]`：`wav_workers`、`wav_timeout`、`wav_retries`、`wav_format`
- `[mapping]`：`integrate_data`

GUI 只读取 `[app]`。其余 section 仅供 CLI 配置文件模式使用。

## 5. 共享设置字段

常用共享设置 key：

- `SOURCE_MODE`
- `GAME_PATH`
- `OUTPUT_PATH`
- `GAME_REGION`
- `EXCLUDE_TYPE`
- `GROUP_BY_TYPE`
- `WWISER_PATH`
- `WITH_BP_VO`
- `REMOTE_LIVE_REGION`
- `CLEANUP_REMOTE`
- `REMOTE_VERSION`
- `REMOTE_LCU_MANIFEST_URL`
- `REMOTE_GAME_MANIFEST_URL`

当前默认值：

- `GAME_REGION = "zh_CN"`
- `EXCLUDE_TYPE = "SFX,MUSIC"`
- `CLEANUP_REMOTE = True`
- `GROUP_BY_TYPE = False`
- `SOURCE_MODE = "local_path"`
- `REMOTE_LIVE_REGION = "EUW"`
- `WITH_BP_VO = False`

## 6. 上下文构建

```python
def create_app_context(
    *,
    settings: Mapping[str, Any] | None = None,
    force_reload: bool = False,
    dev_mode: bool = False,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext
```

```python
def setup_app(
    dev_mode: bool = False,
    log_level: str = "INFO",
    **kwargs,
) -> AppContext
```

- `create_app_context(...)` 负责：
  - 标准化共享配置
  - 构建 `AppConfig`
  - 派生 `AppPaths`
  - 产出 `AppContext`
- `setup_app(...)` 在此基础上额外完成日志初始化

## 7. 路径派生结果

`create_app_context(...)` 会派生以下路径根：

- `audios`
- `wavs`
- `temps`
- `logs`
- `cache`
- `hashes`
- `reports`
- `manifest`
- `game_version`
- `Game/DATA/FINAL/Champions`
- `Game/DATA/FINAL/Maps/Shipping`
- `LeagueClient/Plugins/rcp-be-lol-game-data`

在 `remote_snapshot` 模式下：

- `game_path` 默认落在 `OUTPUT_PATH/_prepared_game`
- `cache/remote/<version>/...` 用于缓存 manifest、LCU bundle 与 GAME WAD

## 8. 配置示例

### 8.1 本地模式

```python
from lol_audio_unpack.app import create_app_context

ctx = create_app_context(
    settings={
        "GAME_PATH": "/path/to/League of Legends",
        "OUTPUT_PATH": "./output",
        "GAME_REGION": "zh_CN",
    }
)
```

### 8.2 remote 模式

```python
from lol_audio_unpack.app import create_app_context

ctx = create_app_context(
    settings={
        "SOURCE_MODE": "remote_snapshot",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "REMOTE_LIVE_REGION": "EUW",
        "WWISER_PATH": "./wwiser.pyz",
    }
)
```

### 8.3 直接读写 INI

```python
from lol_audio_unpack.config import load_settings, resolve_default_path, write_settings

config_file = resolve_default_path()
write_settings(
    config_file,
    {
        "GAME_PATH": "/path/to/League of Legends",
        "OUTPUT_PATH": "./output",
        "GROUP_BY_TYPE": True,
    },
)
settings = load_settings(config_file)
```
