# Python API

使用 Python 调用更新、解包、映射和转码。入口索引见 [API 总览](../API.md)，内部结构见 [模块与数据结构](README.md)。

<a id="root"></a>

## 根包入口

根包 `lol_audio_unpack` 当前只保留两个顶层入口：

- <a id="setup-app"></a>`setup_app`
- <a id="version"></a>`__version__`

```python
from lol_audio_unpack import setup_app
```

```python
def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> AppContext
```

用途：初始化日志，并基于传入的 `settings` / `runtime_cache` 构建 `AppContext`。

<a id="package-app"></a>

## 应用编排

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

<a id="create-app-context"></a>

### 构建上下文

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

<a id="types"></a>

### 参数与结果类型

- <a id="appcontextvalidationerror"></a>`AppContextValidationError`
  - 本地目录或上下文配置不符合要求时抛出的校验异常
- <a id="appconfig"></a>`AppConfig`
  - 环境级配置快照，包含 `game_path`、`output_path`、`game_region`、音频类型、分组、大厅音频、
    `wwiser_path` 与开发模式等字段
- <a id="apppaths"></a>`AppPaths`
  - 派生路径快照，包含 `audio_path`、`wav_path`、`cache_path`、`hash_path`、`report_path`、`manifest_path` 等字段
- <a id="appcontext"></a>`AppContext`
  - 运行时上下文对象，统一封装 `config`、`paths` 与 `runtime_cache`
- <a id="operationoptions"></a>`OperationOptions`
  - 单次操作参数，包含 `max_workers`、`force_update`、`process_events`、`integrate_data`、`champion_ids`、`map_ids`、`special_targets`、`resource_pack_wads`
- <a id="resourcepackwadref"></a>`ResourcePackWadRef`
  - 显式 selected-WAD 的相对 identity 与 `st_size` / `st_mtime_ns` 快照；使用
    `ResourcePackWadRef.from_path(game_root, path)` 创建。创建与执行均会验证路径仍在
    `Game/DATA/FINAL`、后缀为 `.wad.client` 且 stat 未变化，artifact 不保存绝对路径。
- <a id="wavoutputoptions"></a>`WavOutputOptions`
  - 独立 WAV 转码 stage 配置，包含 `enabled`、`worker_count`、`timeout_seconds`、`max_retries`、`format`
  - `format` 设置采样格式，转码统一输出 WAV；支持 `auto`、`pcm16`（默认）、`pcm24`、`pcm32`、`float`，
    各值含义见 [控制台采样格式说明](./cli_api.md#wav-options)
  - `max_retries` 沿用历史语义，表示单文件任务最大尝试次数（含首次，默认 3）；内外后端共用，不自动切换后端。
- <a id="resultstatus"></a>`ResultStatus` / <a id="entityresult"></a>`EntityResult` / <a id="stageresult"></a>`StageResult` / <a id="runresult"></a>`RunResult`
  - 统一描述实体、阶段和整轮工作流的 `success`、`partial`、`failed`、`cancelled` 事实；
    状态与计数从子结果派生，异常对象和 traceback 不进入公共结果；`EntityResult.artifacts`
    仅保存本轮已确认写入的真实产物路径。extract 包含 WEM 与大厅音频路径，mapping 包含最终
    mapping 文件；实体落盘后再失败时仍保留已有路径。WAV 有处理结果时使用稳定的 `wav:batch`
    实体指向 `wav_root`
- <a id="operationprogress"></a>`OperationProgress`
  - update 的可选结构化进度事件，稳定字段为 `operation_key`、`stage_key`、`event`、
    `current`、`total`、`entity_type`、`entity_id`；`event` 取值为 `started`、`advanced`、
    `finished`。进度只描述处理位置，最终业务成功与否仍以 `StageResult` 为准

| `special_targets` 内容 | 处理方式 |
| --- | --- |
| `champion:<id>` | 归约为英雄数值 ID |
| `resource_pack:<wad-component>:<namespace-component>` | 保留已发现的完整 key，不交给数值 target 合并 |
| pack-only 选择 | extract/mapping 使用专用 consumer，不回退全量 champion/map |
| 混合选择 | 分别执行英雄、地图与资源包 |
| resource pack WAV | 当前不支持，在应用边界报错，不影响 extract/mapping |

<a id="lolaudiounpackapp"></a>

### 应用门面

`LolAudioUnpackApp` 是应用编排入口，负责 update / extract / wav / mapping。

`update(...)`、`extract(...)`、`transcode_wav(...)`、`mapping(...)` 返回 `StageResult`。控制台与界面
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
  - <a id="update"></a>

    ```python
    update(opts, *, target="all", progress_callback=None)
    ```
  - <a id="discover-resource-packs"></a>

    ```python
    discover_resource_packs(opts)
    ```
  - <a id="extract"></a>

    ```python
    extract(opts, *, include_champions=True, include_maps=True, progress_callback=None, persisted_wem_callback=None)
    ```
  - <a id="transcode-wav"></a>

    ```python
    transcode_wav(opts, *, progress_callback=None, job_label=None)
    ```
  - <a id="app-mapping"></a>

    ```python
    mapping(opts, *, include_champions=True, include_maps=True, progress_callback=None)
    ```
- 数据与目标辅助
  - <a id="prepare-update-data"></a>

    ```python
    prepare_update_data(*, force_update=False)
    ```
  - <a id="check-targets"></a>

    ```python
    check_targets(opts)
    ```
  - <a id="resolve-champion-ids"></a>

    ```python
    resolve_champion_ids(selectors)
    ```

#### 目标检查

| 入口或阶段 | 规则 |
| --- | --- |
| `check_targets(opts)` | 用 `data.msgpack` 检查英雄、地图及显式 `champion:<id>`；未知 ID 抛 `app.targets.TargetSelectionError`，不读 GAME WAD |
| `app.targets.check_ids(ids, rows)` | 返回 `valid` 与 `unknown` 清单 |
| update | 基础 game data 准备后、BIN 更新前检查 |
| extract / mapping / transcode_wav | 消费资源前复检已有目录 |
| 阶段内未知 ID | 返回 failed `StageResult`，`error_type = TargetSelectionError`，不静默处理有效子集 |

资源存在性与 WAD/BIN 内容仍由各自阶段判断。控制台的本地源检查可能在写入前发现错误目标，
缺失文件和未知 ID 分别报告。

界面的确认窗口允许用户明确接受有效子集：确认后只提交有效 ID，排除项保留在任务详情中；若没有
有效目标则不能提交。英雄和地图都使用显式元组，空元组表示不处理该类；过滤成空集合不会回退全量。

所有方法只消费 `AppContext.config.game_path` 指向的本地目录。`create_app_context(...)` 会在任何
输出初始化前验证共享结构；目标级 WAD/BIN/bank 完整性继续由 update 与 v2 bindings 证明。

<a id="packages"></a>

## 其他模块

<a id="config"></a>

### 配置与 INI

导入包：`lol_audio_unpack.config`。

提供共享设置 schema 与标准 INI 读写能力：

- <a id="settingkey"></a>`SettingKey`、<a id="configsection"></a>`ConfigSection`
- <a id="sharedsettingfield"></a>`SharedSettingField`、<a id="commandconfigfield"></a>`CommandConfigField`
- <a id="build-settings"></a>`build_settings(args)`
- <a id="load-settings"></a>`load_settings(...)`、<a id="write-settings"></a>`write_settings(...)`
- <a id="load-command-config"></a>`load_command_config(...)`、<a id="write-command-config"></a>`write_command_config(...)`
- <a id="resolve-default-path"></a>`resolve_default_path(...)`

<a id="unpack"></a>

### 音频解包

导入包：`lol_audio_unpack.unpack`。

提供解包入口：

- <a id="generate-output-path"></a>`generate_output_path`
- <a id="unpack-all"></a>`unpack_all`
- <a id="unpack-entity"></a>`unpack_entity`
- <a id="unpack-champion"></a>`unpack_champion`
- <a id="unpack-champions"></a>`unpack_champions`
- <a id="unpack-map"></a>`unpack_map`
- <a id="unpack-maps"></a>`unpack_maps`
- <a id="unpack-resource-pack"></a>`unpack_resource_pack`
- <a id="unpack-resource-packs"></a>`unpack_resource_packs`

- **实体内并发**：`unpack_entity`、`unpack_champion`、`unpack_map`、`unpack_resource_pack` 支持 `max_workers=1`，控制 v2 binding 路径中的 WEM 写出。
- **直接回调**：并发时 `persisted_wem_callback` 从写线程触发，调用方需保证线程安全。
- **批处理配额**：应用协调回调，从 `OperationOptions.max_workers` 总配额分配实体与写并发，不为每个实体额外启动同规模线程。
- **默认行为**：保持整实体解包、原始 ID 与既有目录布局。

<a id="mapping"></a>

### 事件映射

导入包：`lol_audio_unpack.mapping`。

提供映射入口：

- <a id="runtimecache"></a>`RuntimeCache`
- <a id="build-all"></a>`build_all`
- <a id="build-entity"></a>`build_entity`
- <a id="build-champion"></a>`build_champion`
- <a id="build-champions"></a>`build_champions`
- <a id="build-map"></a>`build_map`
- <a id="build-maps"></a>`build_maps`
- <a id="build-resource-pack"></a>`build_resource_pack`
- <a id="build-resource-packs"></a>`build_resource_packs`
- <a id="execute-tasks"></a>`execute_tasks`
- <a id="integrate-entity"></a>`integrate_entity`
- <a id="describe-hirc-backend"></a>`describe_hirc_backend`

<a id="model"></a>

### 数据模型

导入包：`lol_audio_unpack.model`。

提供共享实体模型与任务生成：

- <a id="audioentitydata"></a>`AudioEntityData`
- <a id="generate-champion-tasks"></a>`generate_champion_tasks`
- <a id="generate-map-tasks"></a>`generate_map_tasks`

<a id="wav"></a>

### WAV 转码

导入包：`lol_audio_unpack.runtime.wav`。

提供独立 WAV 转码 stage 的路径装配与批处理能力：

- <a id="transcodecoordinator"></a>`TranscodeCoordinator`
- <a id="transcodepaths"></a>`TranscodePaths`
- <a id="transcodeprogress"></a>`TranscodeProgress`
- <a id="transcodesummary"></a>`TranscodeSummary`
- <a id="build-output-path"></a>`build_output_path`
- <a id="build-transcode-paths"></a>`build_transcode_paths`
- <a id="resolve-decode-config"></a>`resolve_decode_config`
- <a id="run-tree"></a>`run_tree`
- <a id="run-worker"></a>`run_worker`

<a id="manager"></a>

### 数据准备与读取

导入包：`lol_audio_unpack.manager`。

提供底层数据准备与读取类：

- <a id="dataupdater"></a>`DataUpdater`
- <a id="binupdater"></a>`BinUpdater`
- <a id="datareader"></a>`DataReader`
- <a id="resourcepackdiscovery"></a>`ResourcePackDiscovery`

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

#### reader 生命周期

- 所有类要求显式 `ctx: AppContext`。每次 `DataReader(ctx)` 都构造独立实例，无进程级单例或跨 context registry。
- `LolAudioUnpackApp` 为自己的 context 懒加载并复用 reader；`prepare_update_data()`、`update()` 或 selected-WAD discovery 可能改写 artifact 后，使 reader 整体失效，下次重新加载。
- 直接写入 artifact 的调用方应丢弃旧 `DataReader` 并重新构造。

<a id="examples"></a>

## 调用示例

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
