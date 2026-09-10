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
    EntityResult,
    LolAudioUnpackApp,
    OperationProgress,
    OperationOptions,
    ResultStatus,
    ResourcePackWadRef,
    RunResult,
    StageResult,
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
  - 环境级配置快照，包含 `game_path`、`output_path`、`game_region`、音频类型、分组、BP VO、
    `wwiser_path` 与开发模式等字段
- `AppPaths`
  - 派生路径快照，包含 `audio_path`、`wav_path`、`cache_path`、`hash_path`、`report_path`、`manifest_path` 等字段
- `AppContext`
  - 运行时上下文对象，统一封装 `config`、`paths` 与 `runtime_cache`
- `OperationOptions`
  - 单次操作参数，包含 `max_workers`、`force_update`、`process_events`、`integrate_data`、`champion_ids`、`map_ids`、`special_targets`、`resource_pack_wads`
- `ResourcePackWadRef`
  - 显式 selected-WAD 的相对 identity 与 `st_size` / `st_mtime_ns` 快照；使用
    `ResourcePackWadRef.from_path(game_root, path)` 创建。创建与执行均会验证路径仍在
    `Game/DATA/FINAL`、后缀为 `.wad.client` 且 stat 未变化，artifact 不保存绝对路径。
- `WavOutputOptions`
  - 独立 WAV 转码 stage 配置，包含 `enabled`、`worker_count`、`timeout_seconds`、`max_retries`、`format`
- `ResultStatus` / `EntityResult` / `StageResult` / `RunResult`
  - 统一描述实体、阶段和整轮工作流的 `success`、`partial`、`failed`、`cancelled` 事实；
    状态与计数从子结果派生，异常对象和 traceback 不进入公共结果；`EntityResult.artifacts`
    仅保存本轮已确认写入的真实产物路径。extract 包含 WEM 与大厅音频路径，mapping 包含最终
    mapping 文件；实体落盘后再失败时仍保留已有路径。WAV 有处理结果时使用稳定的 `wav:batch`
    实体指向 `wav_root`
- `OperationProgress`
  - update 的可选结构化进度事件，稳定字段为 `operation_key`、`stage_key`、`event`、
    `current`、`total`、`entity_type`、`entity_id`；`event` 取值为 `started`、`advanced`、
    `finished`。进度只描述处理位置，最终业务成功与否仍以 `StageResult` 为准

`special_targets` 可包含 GUI 特殊内容的 `champion:<id>`，也可保留已发现的
`resource_pack:<wad-component>:<namespace-component>` key。应用门面只把前者归约为英雄数值 ID，
不会把 resource pack 交给数值 target 合并。`extract` / `mapping` 会把 resource-pack key 交给专用 consumer；
pack-only 选择不会回退到全量 champion/map 流程，混合选择会分别执行三类实体。WAV 转码当前明确
不支持 resource pack，并在应用边界报错，不影响 extract 或 mapping。

### 2.3 `LolAudioUnpackApp`

`LolAudioUnpackApp` 是应用编排入口，负责 update / extract / wav / mapping。

`update(...)`、`extract(...)`、`transcode_wav(...)`、`mapping(...)` 返回 `StageResult`。CLI 与 GUI
可按执行顺序把这些阶段聚合成 `RunResult`。调用方应检查返回状态，不能以“没有抛异常”或返回
`None` 推断成功。

已知共享数据和持久化错误会在常规阶段边界转换为 failed/partial 结果；参数与稳定合同错误
（例如不支持的 target）仍可能抛出 `ValueError`，未被阶段边界声明为可恢复的编程错误也会继续
上抛。

`update(OperationOptions(resource_pack_wads=(ref,)))` 在准备共享数据后只扫描 selected WAD，
不会因为英雄/地图 ID 为空而触发默认全量 `BinUpdater.update`。显式英雄或地图 target 与 selected WAD
同时存在时，两条 update 路径会各自执行。

显式地图 update 会自动把 Map 0 放在目标范围首位并去重，以保证 Common 音频事件参与去重；
调用方无需自行补齐。可通过 `progress_callback` 订阅 `data`、`champion_banks`、
`map_banks` 三类阶段事件：

```python
progress_events: list[OperationProgress] = []
result = app.update(
    OperationOptions(map_ids=(11,)),
    progress_callback=progress_events.append,
)
```

BIN 更新会保留每个英雄或地图的 `success` / `partial` / `failed` 事实并继续处理后续实体；
门面据此派生最终 `StageResult`，不会把部分完成误报为整体成功。

当前公开方法可按职责分为两组：

- 常规主链
  - `update(opts, *, target="all", progress_callback=None)`
  - `discover_resource_packs(opts)`
  - `extract(opts, *, include_champions=True, include_maps=True, progress_callback=None, persisted_wem_callback=None)`
  - `transcode_wav(opts, *, progress_callback=None, job_label=None)`
  - `mapping(opts, *, include_champions=True, include_maps=True, progress_callback=None)`
- 数据与目标辅助
  - `prepare_update_data(*, force_update=False)`
  - `resolve_champion_ids(selectors)`

所有方法只消费 `AppContext.config.game_path` 指向的本地目录。`create_app_context(...)` 会在任何
输出初始化前验证共享结构；目标级 WAD/BIN/bank 完整性继续由 update 与 v2 bindings 证明。

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
- `unpack_resource_pack`
- `unpack_resource_packs`

`unpack_entity`、`unpack_champion`、`unpack_map` 和 `unpack_resource_pack` 支持
关键字参数 `max_workers=1`，用于 v2 binding 路径中实体内部的 WEM 写出并发。
直接调用并启用并发时，`persisted_wem_callback` 会从写出线程触发，调用方需保证回调线程安全。
应用批处理入口会协调回调，并从 `OperationOptions.max_workers` 的总配额中分配实体与写出并发，
不会为每个实体额外启动一整套同规模写线程。默认保持整实体解包、原始 ID 与现有目录布局。

### 3.3 `lol_audio_unpack.mapping`

提供映射入口：

- `RuntimeCache`
- `build_all`
- `build_entity`
- `build_champion`
- `build_champions`
- `build_map`
- `build_maps`
- `build_resource_pack`
- `build_resource_packs`
- `execute_tasks`
- `integrate_entity`
- `describe_hirc_backend`

### 3.4 `lol_audio_unpack.model`

提供共享实体模型与任务生成：

- `AudioEntityData`
- `generate_champion_tasks`
- `generate_map_tasks`

### 3.5 `lol_audio_unpack.runtime.wav`

提供独立 WAV 转码 stage 的路径装配与批处理能力：

- `TranscodeCoordinator`
- `TranscodePaths`
- `TranscodeProgress`
- `TranscodeSummary`
- `build_output_path`
- `build_transcode_paths`
- `resolve_decode_config`
- `run_tree`
- `run_worker`

### 3.6 `lol_audio_unpack.manager`

提供底层数据准备与读取类：

- `DataUpdater`
- `BinUpdater`
- `DataReader`
- `ResourcePackDiscovery`

`DataReader` 的 banks 读取边界：

- `get_champion_banks(id, require_bindings=False)` / `get_map_banks(id, require_bindings=False)`
  默认允许读取旧投影以便检查；调用方显式要求 bindings 时，v1 artifact 会提示重新 update。
- `get_champion_resource_bindings(id)` / `get_map_resource_bindings(id)` 返回 typed
  `ResourceBindings`，并始终要求 v2 artifact。
- `get_resource_pack_banks(key, require_bindings=False)`、
  `get_resource_pack_resource_bindings(key)` 与 `get_resource_pack_events(key)` 读取
  `resource_pack` string identity 的独立 artifact group；本地 v2 缺失时会提示重新运行 update。
- `AudioEntityData.from_resource_pack(key, reader, include_events=..., ctx=...)` 构造唯一 logical
  sub-entity，完整 key 保留在 payload/诊断中；输出、mapping hash 与 report 路径使用该 key 的
  Windows-safe component。

这些类都要求显式传入 `ctx: AppContext`。`DataReader(ctx)` 每次构造都会得到独立实例，不存在
进程级单例或跨 context registry。`LolAudioUnpackApp` 会为自己的 context 懒加载并复用一个 reader；
`prepare_update_data()`、`update()` 或 selected-WAD discovery 可能改写结构化 artifact 后，门面会使
该 reader 整体失效，下一次读取重新加载。直接使用 `DataReader` 的调用方若自行写入 artifact，也应
丢弃旧实例并重新构造。

## 4. 快速示例

### 4.1 已安装客户端

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

update_result = app.update(OperationOptions(force_update=False), target="all")
extract_result = app.extract(OperationOptions(max_workers=8, champion_ids=(1, 103)), include_maps=False)
mapping_result = app.mapping(OperationOptions(max_workers=8, integrate_data=True), include_maps=False)
```

### 4.2 外部准备目录

```python
from lol_audio_unpack.app import LolAudioUnpackApp, OperationOptions, create_app_context

ctx = create_app_context(
    settings={
        "GAME_PATH": "/path/to/prepared/lol-client",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
    }
)
app = LolAudioUnpackApp(ctx)

update_result = app.update(OperationOptions(champion_ids=(1, 103)))
extract_result = app.extract(OperationOptions(champion_ids=(1, 103), max_workers=4), include_maps=False)
mapping_result = app.mapping(
    OperationOptions(champion_ids=(1, 103), max_workers=1, integrate_data=True),
    include_maps=False,
)
```

该目录必须符合 [已准备本地数据源合同](./prepared_source.md)。外部工具负责准备资源；本应用不会
下载缺失文件或切换来源。

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
    }
)
reader = DataReader(ctx=ctx)
payload = build_champion(1, reader, ctx=ctx)
```

上述 mapping 默认使用 NativeHIRC；只有显式选择 WwiserHIRC 回退路径时才配置 `WWISER_PATH`。
