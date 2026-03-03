# Python API（公开入口与管理器）

## 1. 包根公开 API

`lol_audio_unpack.__all__` 当前导出：

- `setup_app`
- `BinUpdater`
- `config`
- `DataUpdater`
- `DataReader`

### 1.1 `setup_app`

```python
def setup_app(dev_mode: bool = False, log_level: str = "INFO", **kwargs) -> None
```

用途：统一初始化日志与配置系统，推荐作为所有 Python 调用入口。

参数说明：

- `dev_mode`：是否启用开发模式（影响 `.lol.env.dev` 与数据写入格式）。
- `log_level`：日志级别，传入如 `"INFO"`、`"DEBUG"`。
- `**kwargs`：透传给 `config.initialize(...)`，常见为 `cli_overrides`。

副作用：

- 重新配置 loguru handler。
- 初始化并校验配置（缺失必填项会抛出 `ConfigValidationError`）。
- 创建输出相关目录。

## 2. 管理器 API

### 2.1 `DataUpdater`

```python
class DataUpdater:
    def __init__(self, languages: list[str] | None = None, force_update: bool = False) -> None
    def check_and_update(self) -> Path
```

用途：从客户端 WAD 提取并聚合基础数据（英雄、地图、多语言）。

关键行为：

- 自动解析当前游戏版本（`content-metadata.json`）。
- 根据 `needs_update(...)` 判断是否需要重建。
- 输出 `manifest/<version>/data.*`。
- 非开发模式会自动清理临时目录。

### 2.2 `BinUpdater`

```python
class BinUpdater:
    def __init__(self, force_update: bool = False, process_events: bool = True)
    def update(
        self,
        target: str = "all",
        champion_ids: list[str] | None = None,
        map_ids: list[str] | None = None,
    ) -> None
```

用途：基于 BIN 数据生成 `banks` / `events`。

`update` 参数语义：

- `target`：`"all" | "skin" | "map"`，仅在未传具体 ID 时生效。
- `champion_ids`：指定仅处理的英雄 ID（字符串列表）。
- `map_ids`：指定仅处理的地图 ID（字符串列表）。

本地 BIN 回退机制：

- 当 `manifest/<version>/.use_local_bin` 存在时，会优先读取 `manifest/<version>/bin_input` 中的手动 BIN。
- 若本地存在缺失项且 WAD 可用，仅对缺失项走 WAD 补齐。
- 读取过程具备路径越界防护与缺失容忍。

### 2.3 `DataReader`

```python
class DataReader(metaclass=Singleton):
    def get_audio_type(self, category: str) -> str
    def get_languages(self) -> list[str]
    def get_champion_banks(self, champion_id: int) -> dict | None
    def get_champion_events(self, champion_id: int) -> dict | None
    def get_map_banks(self, map_id: int) -> dict | None
    def get_map_events(self, map_id: int) -> dict | None
    def get_champion(self, champion_id: int) -> dict
    def get_champions(self) -> list[dict]
    def get_map(self, map_id: int) -> dict
    def get_maps(self) -> list[dict]
    def write_unknown_categories_to_file(self) -> None
```

用途：读取 `manifest/<version>` 下的数据，并提供缓存。

关键行为：

- 初始化时验证数据版本与游戏版本兼容性（大版本不一致会抛错）。
- `get_audio_type` 会把未知分类记录到 `unknown_categories`，最终可写入 `unknown-category.txt`。

## 3. 数据模型 API（`model.py`）

### 3.1 `AudioEntityData`

```python
@dataclass
class AudioEntityData:
    entity_id: str
    entity_name: str
    entity_alias: str
    entity_title: str
    entity_type: str
    sub_entities: dict[str, dict[str, Any]]
    wad_root: str
    wad_language: str | None = None
    events: dict[str, dict[str, Any]] | None = None
```

核心方法：

```python
def get_sub_entity_info(self, sub_id: str) -> dict[str, Any] | None

def get_wad_path(self, audio_type: str) -> Path | None

@classmethod
def from_champion(cls, champion_id: int, reader: DataReader, include_events: bool = False) -> AudioEntityData

@classmethod
def from_map(cls, map_id: int, reader: DataReader, include_events: bool = False) -> AudioEntityData
```

### 3.2 任务生成器

```python
def generate_champion_tasks(
    reader: DataReader,
    champion_ids: list[int] | None = None,
) -> list[tuple[str, int, str]]


def generate_map_tasks(
    reader: DataReader,
    map_ids: list[int] | None = None,
) -> list[tuple[str, int, str]]
```

用途：统一生成 `(entity_type, id, description)` 任务元组；传入非法 ID 时会抛 `ValueError`。
