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

## 2. 推荐入口

### 2.1 `setup_app`

```python
def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> AppContext
```

用途：初始化日志与上下文，并返回可注入的 `AppContext`。

### 2.2 `create_app_context`

```python
def create_app_context(
    *,
    settings: Mapping[str, Any] | None = None,
    force_reload: bool = False,
    dev_mode: bool = False,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext
```

用途：显式消费 `settings` 并构建 `AppContext`。

说明：

- 不再支持 `initialize_context_from_env(...)`
- 不再支持 `cli_overrides`
- 不再隐式读取 `.lol.env` 或 `LOL_*`

### 2.3 `LolAudioUnpackApp`

```python
class LolAudioUnpackApp:
    def __init__(self, ctx: AppContext)
    def update(self, opts: OperationOptions, *, target: str = "all") -> None
    def extract(self, opts: OperationOptions, *, include_champions: bool = True, include_maps: bool = True) -> None
    def mapping(self, opts: OperationOptions, *, include_champions: bool = True, include_maps: bool = True) -> None
    def cleanup_remote_artifacts(self) -> None
    def build_remote_entity_work_items(...) -> list[RemoteEntityWorkItem]
    def run_remote_entity_workflow(...) -> None
```

用途：统一编排更新、解包、映射流程。

## 3. `settings` 结构

常用字段：

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

本仓库的 key schema 集中定义在：

- `src/lol_audio_unpack/config_schema.py`

## 4. 快速示例

### 4.1 本地模式

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions, setup_app

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

### 4.2 Remote 模式

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions
from lol_audio_unpack.app_context import create_app_context

ctx = create_app_context(
    settings={
        "SOURCE_MODE": "remote_snapshot",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "REMOTE_LIVE_REGION": "EUW",
    }
)
app = LolAudioUnpackApp(ctx)
app.update(OperationOptions(champion_ids=(1, 103)), target="skin")
```

### 4.3 固定快照 + mapping

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions
from lol_audio_unpack.app_context import create_app_context

ctx = create_app_context(
    settings={
        "SOURCE_MODE": "remote_snapshot",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "REMOTE_VERSION": "16.5",
        "REMOTE_LCU_MANIFEST_URL": "https://...",
        "REMOTE_GAME_MANIFEST_URL": "https://...",
        "WWISER_PATH": "./wwiser.pyz",
    }
)
app = LolAudioUnpackApp(ctx)
app.mapping(OperationOptions(champion_ids=(1,), integrate_data=True), include_maps=False)
```

## 5. `OperationOptions`

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

用途：承载单次操作的运行级参数。

## 6. remote 单位驱动

`run_remote_entity_workflow(...)` 适合：

- 在 Python 中复用 CLI 当前的 remote 单位驱动策略
- 先 `update`，再按实体逐个执行 `extract` / `mapping`
- 每个实体完成后立即清理远端资源，降低磁盘峰值

下载类错误默认重试 3 次，单实体完整流程默认最多重试 3 次。

## 7. 管理器类

```python
class DataUpdater:
    def __init__(self, ctx: AppContext, languages: list[str] | None = None, force_update: bool = False) -> None


class BinUpdater:
    def __init__(self, force_update: bool = False, process_events: bool = True, *, ctx: AppContext) -> None


class DataReader(metaclass=Singleton):
    def __init__(self, ctx: AppContext)
```

说明：`ctx` 已为必填，不再支持任何全局配置回退。
