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
```

用途：统一编排更新、解包、映射流程，供 CLI 与模块调用共用。

补充说明：

- 在 `remote_snapshot` 模式下：
  - `update()` 会先准备 LCU 与 BIN 输入
  - `extract()` / `mapping()` 会先准备当前操作所需的实体 WAD
  - `cleanup_remote_artifacts()` 会在开启 `cleanup_remote` 时清理已登记的远端产物

### 2.3 `OperationOptions`

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

当前 remote 模式常用的 `cli_overrides` 包括：

- `SOURCE_MODE="remote_snapshot"`
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
        "REMOTE_VERSION": "16.5",
        "REMOTE_LCU_MANIFEST_URL": "...",
        "REMOTE_GAME_MANIFEST_URL": "...",
    }
)
app = LolAudioUnpackApp(ctx)
app.update(OperationOptions(champion_ids=(1, 103)), target="skin")
```
