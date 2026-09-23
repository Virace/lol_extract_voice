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
- `[wav]`：独立 WAV 转码 stage 开关与细节参数
- `[mapping]`：`mapping` 动作参数

当前支持的命令字段：

- `[targets]`：`champions`、`maps`
- `[runtime]`：`max_workers`
- `[update]`：`enable`、`force`、`skip_events`
- `[extract]`：`enable`
- `[wav]`：`enable`、`wav_workers`、`wav_timeout`、`wav_retries`、`wav_format`
- `[mapping]`：`enable`、`integrate_data`

GUI 只读取 `[app]`。其余 section 仅供 CLI 配置文件模式使用；启用 `-c` 时，动作列表也由这些 section 的 `enable` 决定。

## 5. 共享设置字段

常用共享设置 key：

- `GAME_PATH`
- `OUTPUT_PATH`
- `GAME_REGION`
- `EXCLUDE_TYPE`
- `GROUP_BY_TYPE`
- `WWISER_PATH`
- `VGMSTREAM_PATH`
- `LOBBY_AUDIO`

当前默认值：

- `GAME_REGION = "zh_CN"`
- `EXCLUDE_TYPE = "SFX,MUSIC"`
- `GROUP_BY_TYPE = False`
- `LOBBY_AUDIO = True`：默认附带选人语音、禁用语音及选人音效；INI 使用 `[app] lobby_audio = false` 关闭，CLI 使用 `--no-lobby-audio`。

上述语言默认值用于未显式提供参数的 CLI/API。GUI 首次配置保持“请选择”，只在发现唯一
有效语言时自动选中；主动留空会持久化，刷新不重新填充。显式空语言不能执行源处理任务。

旧 `[app] with_bp_vo` 在配置加载时自动迁移为 `lobby_audio` 并保留原值。新旧键同时存在时保留新键；迁移无法写回时告警并继续兼容读取。Python 配置字段和设置键统一为 `lobby_audio` / `LOBBY_AUDIO`，旧 Python 名称不保留别名。

## 6. 上下文构建

```python
def create_app_context(
    *,
    settings: Mapping[str, Any] | None = None,
    force_reload: bool = False,
    dev_mode: bool = False,
    runtime_cache: dict[str, Any] | None = None,
    allow_empty_language: bool = False,
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
  - 在任何输出初始化前验证本地数据源基础结构
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

`game_path` 可以指向已安装客户端，也可以指向外部工具准备的等价目录。两者必须满足同一个
[已准备本地数据源合同](./prepared_source.md)，程序不提供下载或网络回退。

版本产物统一由 `ctx.version_path(kind, version)` 定位，在对应根下加入版本和规范化语言；
例如 `ctx.version_path("manifest", "16.18")` 返回 `manifest/16.18/zh_CN`。
`kind` 使用 `manifest`、`audio`、`wav`、`hash`、`report` 等 `AppPaths` 路径前缀。
`default` 英语规范化为 `en_US`；GUI 空语言使用只读占位 `_unselected`，不能执行源处理任务。
硬链接、完整搬迁及旧目录一次性迁移规则见[资源库说明](./library_api.md)。

## 8. 配置示例

GUI 的“提前准备数据”保存在独立偏好分组，默认关闭：

```ini
[gui]
prepare_data_on_startup = false
```

关闭时启动仅准备基础英雄/地图目录，解包或映射任务按所选目标补齐资源；开启后，在启动或游戏
版本、路径、区域变化时自动补齐普通英雄/地图的资源与事件缓存。普通准备复用同版本缓存，
显式“前置强制更新”才强制重建。该偏好不进入 `AppContext` 共享设置，也不改变 CLI 的显式动作
语义；运行任务期间开关与其他运行时配置一起锁定。

### 8.1 已安装客户端

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

### 8.2 外部准备目录

```python
from lol_audio_unpack.app import create_app_context

ctx = create_app_context(
    settings={
        "GAME_PATH": "/path/to/prepared/lol-client",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "WWISER_PATH": "./wwiser.pyz",
    }
)
```

旧版 `source_mode`、`remote_*` 与 `cleanup_remote` INI 项会作为未知配置记录警告并被忽略，
不会改变 `game_path` 的本地消费语义。

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

### 外部工具选择与启动预检

`[app] wwiser_path` 和 `vgmstream_path` 留空分别使用内置 NativeHIRC、pyvgmstream；
填写路径明确选择该外部工具。GUI 旧 `[gui] vgmstream_path` 在首次保存时写入共享字段，
新共享字段（包括空值）优先。清除仅移除配置，不删除文件；任务使用创建时的快照。

启动前只探测本次会调用的后端，使用随包提供的小 WEM/BNK 实际调用，失败不会静默回退。
GUI 可确认仅本次改用内置并复检，也可取消；CLI/API 直接返回失败。正式转换对失败文件自动重试
完整任务流程，默认最多尝试 3 次（含首次），保持原后端和参数，不重复工具预检；
耗尽次数后记录失败并继续其他文件。任务结束后 GUI 不提供失败项手动重试入口。
CLI `--wav-retries`、INI `[wav] wav_retries` 和 Python API `WavOutputOptions.max_retries`
使用相同语义：最大尝试次数包含首次，默认 3，至少 1。GUI 的“最大尝试次数”同步读写该 INI 字段，
创建任务与导出时冻结为任务参数；GUI 保存不会再移除该键。

Windows 打包程序运行外部 `wwiser.pyz` 时，需要 PATH 中有可启动的 `python`；
内置 NativeHIRC 不需要另装 Python。外部工具由用户自行准备，应用不自动下载。

发布包可在不启动界面、不加载用户配置的情况下执行真实样本自检：

```powershell
.\LolAudioUnpack.exe --check-tools .\check-results\report.json --check-cancel `
  --wwiser-path C:\Tools\wwiser.pyz --vgmstream-path C:\Tools\vgmstream-cli.exe
```

省略外部路径则只检查两项内置后端。报告包含实际样本调用结果、耗时和取消后的子进程情况；
所选检查全部成功（以及启用时取消成功）才返回退出码 0。该命令保留报告和探测材料，
不能替代正式界面的人工验收。
