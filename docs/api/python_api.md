# Python API（公开入口与管理器）

## 1. 包根公开 API

`lol_audio_unpack.__all__` 当前导出：

- `setup_app`
- `AppConfig`
- `AppPaths`
- `AppContext`
- `AppContextValidationError`
- `OperationOptions`
- `RemoteSnapshotConfig`
- `SourceMode`
- `LolAudioUnpackApp`
- `RemoteEntityCallbackPayload`
- `RemoteEntityWorkItem`
- `DataUpdater`
- `BinUpdater`
- `DataReader`

## 2. 推荐入口（Facade）

### 2.1 `setup_app`

```python
def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> AppContext
```

用途：初始化日志与上下文，并返回可注入的 `AppContext`。

补充说明：

- 当前环境若 `loguru enqueue=True` 因权限问题失败，会自动回退为非 `enqueue` 模式。

### 2.2 `LolAudioUnpackApp`

```python
class LolAudioUnpackApp:
    def __init__(self, ctx: AppContext)
    def update(self, opts: OperationOptions, *, target: str = "all") -> None
    def extract(
        self,
        opts: OperationOptions,
        *,
        include_champions: bool = True,
        include_maps: bool = True,
    ) -> None
    def mapping(
        self,
        opts: OperationOptions,
        *,
        include_champions: bool = True,
        include_maps: bool = True,
    ) -> None
    def cleanup_remote_artifacts(self) -> None
    def build_remote_entity_work_items(...) -> list[RemoteEntityWorkItem]
    def run_remote_entity_workflow(...) -> None
```

用途：统一编排更新、解包、映射流程，供 CLI 与模块调用共用。

补充说明：

- 在 `remote_snapshot` 模式下：
  - `update()` 会先准备 LCU 与 BIN 输入
  - `extract()` / `mapping()` 会先准备当前操作所需的实体 WAD
  - `cleanup_remote_artifacts()` 会在开启 `cleanup_remote` 时清理已登记的远端产物
  - `run_remote_entity_workflow()` 会复用 CLI 当前的“按实体拆批 + 每轮清理”策略

### 2.3 `run_remote_entity_workflow`

适用场景：

- 需要在纯 Python 中复用 CLI 现有 remote 单位驱动策略
- 希望在 `update` 后按实体逐个执行 `extract` / `mapping`
- 希望每个实体执行完成后立即清理已准备的远端 WAD，降低磁盘峰值

关键参数：

- `update_options` / `update_target`：可选的一次性 `update`
- `extract_options`：extract 阶段的批量配置
- `mapping_options`：mapping 阶段的批量配置
- `extract_include_*` / `mapping_include_*`：控制各阶段是否包含 champions / maps
- `download_retry_attempts`：单次实体尝试内，下载类错误的最大重试次数，默认 `3`
- `entity_retry_attempts`：单实体完整流程的最大重试次数，默认 `3`

说明：

- 该方法仅在 `remote_snapshot` 模式下可用
- 若 `extract_options` / `mapping_options` 未显式给 `champion_ids` 或 `map_ids`，会按 `include_*` 自动展开为全量实体
- 若同一实体同时命中 extract 与 mapping，会先一次性准备该实体所需 WAD，再依次执行两阶段，最后统一清理
- 可通过 `on_entity_complete(payload)` 接收当前实体完成后的产物路径回调
- 下载类错误（`DownloadError` / `DecompressError` / `DownloadBatchError`）默认会在当前实体尝试内重试 3 次
- 若单实体完整流程连续失败达到阈值（默认 3 次），会直接向上抛错，并提示当前解包脚本可能已不再适配最新二进制资源

### 2.4 `RemoteEntityCallbackPayload`

```python
@dataclass(frozen=True)
class RemoteEntityCallbackPayload:
    entity_type: str
    entity_id: int
    audio_output_paths: tuple[Path, ...] = ()
    mapping_output_path: Path | None = None
```

说明：

- `audio_output_paths`：当前实体解包后实际存在的输出目录列表
- `mapping_output_path`：当前实体 mapping 最终产物文件路径；若未产出则为 `None`
- 当 `group_by_type=False` 时，`audio_output_paths` 通常只有 1 个实体目录
- 当 `group_by_type=True` 且存在多种音频类型输出时，`audio_output_paths` 可能包含多个目录

### 2.5 `OperationOptions`

```python
@dataclass(frozen=True)
class OperationOptions:
    max_workers: int = 4
    force_update: bool = False
    process_events: bool = True
    integrate_data: bool = False
    champion_ids: tuple[int, ...] | None = None
    map_ids: tuple[int, ...] | None = None
```

用途：承载一次操作的可变参数，替代散装参数穿透。

## 3. 上下文工厂（`app_context.py`）

```python
def create_app_context(
    env_path: StrPath | None = None,
    env_prefix: str = "LOL_",
    force_reload: bool = False,
    dev_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext


def initialize_context_from_env(
    env_path: StrPath | None = None,
    env_prefix: str = "LOL_",
    force_reload: bool = False,
    dev_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
) -> AppContext
```

用途：构建 `AppConfig + AppPaths + AppContext` 组合对象。

当前 remote 模式常用的 `cli_overrides` 分两层：

- 默认入口：
  - `SOURCE_MODE="remote_snapshot"`
  - `OUTPUT_PATH`
  - `GAME_REGION`
  - `REMOTE_LIVE_REGION`（可选，默认 `EUW`）
- 高级覆盖：
  - `REMOTE_VERSION`
  - `REMOTE_LCU_MANIFEST_URL`
  - `REMOTE_GAME_MANIFEST_URL`
  - `CLEANUP_REMOTE`

## 4. 管理器类（显式上下文）

```python
class DataUpdater:
    def __init__(
        self,
        ctx: AppContext,
        languages: list[str] | None = None,
        force_update: bool = False,
    ) -> None


class BinUpdater:
    def __init__(
        self,
        force_update: bool = False,
        process_events: bool = True,
        *,
        ctx: AppContext,
    ) -> None


class DataReader(metaclass=Singleton):
    def __init__(self, ctx: AppContext)
```

说明：`ctx` 已为必填，且不再支持全局 `config` 回退路径。

## 5. remote 内部准备器（内部实现）

`remote_preparer.py` 当前提供：

- `RemoteSnapshotPreparer`
- `LcuPrepareResult`
- `BinInputPrepareResult`
- `GameWadPrepareResult`

说明：

- 这些对象已经在主链路中使用，但仍归类为内部实现。
- 当前不建议外部业务代码直接依赖其细节。

## 6. 模块级流水线函数

`model` / `unpack` / `mapping` 相关核心函数均要求显式 `ctx: AppContext`，包括但不限于：

- `AudioEntityData.from_champion(..., ctx=ctx)` / `AudioEntityData.from_map(..., ctx=ctx)`
- `unpack_audio_all(..., ctx=ctx)` / `unpack_champions(..., ctx=ctx)` / `unpack_maps(..., ctx=ctx)`
- `build_mapping_all(..., ctx=ctx)` / `build_champions_mapping(..., ctx=ctx)` / `build_maps_mapping(..., ctx=ctx)`

## 7. 快速示例

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions, setup_app

ctx = setup_app(dev_mode=False, log_level="INFO")
app = LolAudioUnpackApp(ctx)

app.update(OperationOptions(force_update=False), target="all")
app.extract(OperationOptions(max_workers=8, champion_ids=(1, 103)), include_maps=False)
app.mapping(OperationOptions(max_workers=8, integrate_data=True), include_maps=False)
```

```python
ctx = create_app_context(
    cli_overrides={
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "SOURCE_MODE": "remote_snapshot",
    }
)
app = LolAudioUnpackApp(ctx)
app.update(OperationOptions(champion_ids=(1, 103)), target="skin")
```

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions
from lol_audio_unpack.app_context import create_app_context

ctx = create_app_context(
    cli_overrides={
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "SOURCE_MODE": "remote_snapshot",
        "WWISER_PATH": "./wwiser.pyz",
    }
)
app = LolAudioUnpackApp(ctx)

def on_entity_complete(payload):
    print(payload.entity_id, payload.audio_output_paths, payload.mapping_output_path)

app.run_remote_entity_workflow(
    update_options=OperationOptions(champion_ids=(1, 103)),
    update_target="skin",
    extract_options=OperationOptions(max_workers=4, champion_ids=(1, 103)),
    mapping_options=OperationOptions(max_workers=1, champion_ids=(103,), integrate_data=True),
    extract_include_champions=True,
    mapping_include_champions=True,
    on_entity_complete=on_entity_complete,
)
```
