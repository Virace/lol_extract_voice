# Python API（公开入口与管理器）

## 1. 包根公开 API

`lol_audio_unpack.__all__` 当前导出：

- `setup_app`
- `AppConfig`
- `AppPaths`
- `AppContext`
- `OperationOptions`
- `LolAudioUnpackApp`
- `DataUpdater`
- `BinUpdater`
- `DataReader`
- `config`（兼容待弃用）

## 2. 推荐入口（Facade）

### 2.1 `setup_app`

```python
def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> AppContext
```

用途：初始化日志与配置，并返回可注入的 `AppContext`。

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
```

用途：统一编排更新、解包、映射流程，供 CLI 与模块调用共用。

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

## 3. 兼容 API（仍可用）

### 3.1 管理器类

```python
class DataUpdater:
    def __init__(
        self,
        languages: list[str] | None = None,
        force_update: bool = False,
        ctx: AppContext | None = None,
    ) -> None

class BinUpdater:
    def __init__(
        self,
        force_update: bool = False,
        process_events: bool = True,
        ctx: AppContext | None = None,
    ) -> None

class DataReader(metaclass=Singleton):
    def __init__(self, ctx: AppContext | None = None)
```

说明：

- 传入 `ctx` 时走显式注入模式（推荐）。
- 不传 `ctx` 时走全局 `config` 回退（兼容模式）。

### 3.2 `model/unpack/mapping` 模块函数

这些模块函数已支持 `ctx` 可选注入；未传 `ctx` 时仍可回退到全局 `config`。

## 4. 弃用策略

以下能力已标注为“兼容待弃用”并发出 `DeprecationWarning`（一次性告警）：

- Manager 构造不传 `ctx`。
- `model/unpack/mapping` 链路不传 `ctx` 导致读取全局 `config`。

目标移除版本：`4.0.0`。

建议迁移：

1. 使用 `ctx = setup_app(...)` 获取上下文。
2. 使用 `app = LolAudioUnpackApp(ctx)`。
3. 使用 `OperationOptions(...)` 调用 `app.update/extract/mapping`。

## 5. 快速示例

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions, setup_app

ctx = setup_app(dev_mode=False, log_level="INFO")
app = LolAudioUnpackApp(ctx)

app.update(OperationOptions(force_update=False), target="all")
app.extract(OperationOptions(max_workers=4, champion_ids=(1, 103)), include_maps=False)
app.mapping(OperationOptions(max_workers=4, integrate_data=True), include_maps=False)
```
