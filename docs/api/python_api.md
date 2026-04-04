# Python API（分域包与公开入口）

## 1. 根包入口

根包 `lol_audio_unpack` 当前只保留两个顶层入口：

- `setup_app`
- `__version__`

```python
from lol_audio_unpack import setup_app
```

```python
def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> AppContext
```

用途：初始化日志，并基于传入的 `settings` / `runtime_cache` 构建 `AppContext`。

## 2. `lol_audio_unpack.app`

推荐把应用级类型和编排能力都从 `lol_audio_unpack.app` 导入：

```python
from lol_audio_unpack.app import (
    AppConfig,
    AppContext,
    AppContextValidationError,
    AppPaths,
    LolAudioUnpackApp,
    OperationOptions,
    RemoteEntityCallbackPayload,
    RemoteEntityWorkItem,
    RemoteSnapshotConfig,
    SourceMode,
    WavOutputOptions,
    create_app_context,
)
```

### 2.1 `create_app_context`

```python
def create_app_context(
    *,
    settings: Mapping[str, Any] | None = None,
    force_reload: bool = False,
    dev_mode: bool = False,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext
```

用途：消费共享设置映射，构建 `AppConfig`、`AppPaths` 和 `AppContext`。

### 2.2 关键类型

- `AppConfig`
  - 环境级配置快照，包含 `game_path`、`output_path`、`source_mode`、`wwiser_path`、`remote_snapshot` 等字段
- `AppPaths`
  - 派生路径快照，包含 `audio_path`、`wav_path`、`cache_path`、`hash_path`、`report_path`、`manifest_path` 等字段
- `AppContext`
  - 运行时上下文对象，统一封装 `config`、`paths` 与 `runtime_cache`
- `OperationOptions`
  - 单次操作参数，包含 `max_workers`、`force_update`、`process_events`、`integrate_data`、`champion_ids`、`map_ids`
- `WavOutputOptions`
  - WAV sidecar 配置，包含 `enabled`、`worker_count`、`timeout_seconds`、`max_retries`、`format`
- `RemoteSnapshotConfig`
  - 固定快照配置，包含 `version`、`lcu_manifest_url`、`game_manifest_url`
- `SourceMode`
  - 当前支持 `local_path` 与 `remote_snapshot`

### 2.3 `LolAudioUnpackApp`

`LolAudioUnpackApp` 是应用编排入口，负责 update / extract / mapping 与 remote 单位驱动。

当前公开方法可按职责分为三组：

- 常规主链
  - `update(opts, *, target="all")`
  - `extract(opts, *, include_champions=True, include_maps=True, prepare_remote=True, ...)`
  - `mapping(opts, *, include_champions=True, include_maps=True, prepare_remote=True, ...)`
- remote 辅助
  - `prepare_update_data(*, force_update=False)`
  - `cleanup_remote_artifacts()`
  - `build_work_items(...)`
  - `run_workflow(...)`
- 目标解析
  - `resolve_champion_ids(selectors)`

`run_workflow(...)` 适合在 Python 中复用 CLI 当前的 remote 单位驱动策略：

- 可选先执行一次全局 `update`
- 再按实体顺序执行 `extract` / `mapping`
- 每个实体完成后立即清理远端资源
- 可挂接 `on_entity_complete` 与 `progress_callback`

## 3. 其他公开分域包

### 3.1 `lol_audio_unpack.config`

提供共享设置 schema 与标准 INI 读写能力：

- `SettingKey`、`ConfigSection`
- `SharedSettingField`、`CommandConfigField`
- `build_settings(args)`
- `load_settings(...)`、`write_settings(...)`
- `load_command_config(...)`、`write_command_config(...)`
- `resolve_default_path(...)`

### 3.2 `lol_audio_unpack.unpack`

提供解包入口：

- `generate_output_path`
- `unpack_all`
- `unpack_entity`
- `unpack_champion`
- `unpack_champions`
- `unpack_map`
- `unpack_maps`

### 3.3 `lol_audio_unpack.mapping`

提供映射入口：

- `RuntimeCache`
- `build_all`
- `build_entity`
- `build_champion`
- `build_champions`
- `build_map`
- `build_maps`
- `execute_tasks`
- `integrate_entity`
- `describe_hirc_backend`

### 3.4 `lol_audio_unpack.model`

提供共享实体模型与任务生成：

- `AudioEntityData`
- `generate_champion_tasks`
- `generate_map_tasks`

### 3.5 `lol_audio_unpack.runtime.remote`

提供 remote 资源准备能力：

- `RemotePreparer`
- `LcuResult`
- `BinInputResult`
- `GameWadResult`

### 3.6 `lol_audio_unpack.runtime.wav`

提供 WAV sidecar 作业与转码能力：

- `JobSpec`
- `JobHandle`
- `ManifestRecorder`
- `TranscodeCoordinator`
- `TranscodeProgress`
- `TranscodeSummary`
- `build_job_spec`
- `build_recorder`
- `launch_detached`
- `launch_job`
- `parse_job_spec`
- `run_job`
- `build_output_path`
- `resolve_decode_config`
- `run_worker`

### 3.7 `lol_audio_unpack.manager`

提供底层数据准备与读取类：

- `DataUpdater`
- `BinUpdater`
- `DataReader`

这些类都要求显式传入 `ctx: AppContext`。

## 4. 快速示例

### 4.1 本地模式

```python
from lol_audio_unpack import setup_app
from lol_audio_unpack.app import LolAudioUnpackApp, OperationOptions

ctx = setup_app(
    dev_mode=False,
    log_level="INFO",
    settings={
        "GAME_PATH": "/path/to/League of Legends",
        "OUTPUT_PATH": "./output",
        "GAME_REGION": "zh_CN",
    },
)
app = LolAudioUnpackApp(ctx)

app.update(OperationOptions(force_update=False), target="all")
app.extract(OperationOptions(max_workers=8, champion_ids=(1, 103)), include_maps=False)
app.mapping(OperationOptions(max_workers=8, integrate_data=True), include_maps=False)
```

### 4.2 remote 模式

```python
from lol_audio_unpack.app import LolAudioUnpackApp, OperationOptions, create_app_context

ctx = create_app_context(
    settings={
        "SOURCE_MODE": "remote_snapshot",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "REMOTE_LIVE_REGION": "EUW",
        "WWISER_PATH": "./wwiser.pyz",
    }
)
app = LolAudioUnpackApp(ctx)

app.run_workflow(
    update_options=OperationOptions(champion_ids=(1, 103)),
    extract_options=OperationOptions(champion_ids=(1, 103), max_workers=4),
    mapping_options=OperationOptions(champion_ids=(1, 103), max_workers=1, integrate_data=True),
    extract_include_champions=True,
    mapping_include_champions=True,
)
```

### 4.3 直接复用分域包

```python
from lol_audio_unpack.app import create_app_context
from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.mapping import build_champion

ctx = create_app_context(
    settings={
        "GAME_PATH": "/path/to/League of Legends",
        "OUTPUT_PATH": "./output",
        "GAME_REGION": "zh_CN",
        "WWISER_PATH": "./wwiser.pyz",
    }
)
reader = DataReader(ctx=ctx)
payload = build_champion(1, reader, ctx=ctx)
```
