# 配置与数据读写 API

## 1. 配置对象（`utils/config.py`）

全局入口：

```python
from lol_audio_unpack.utils.config import config
```

类型：`ConfigProxy`（延迟初始化代理）。

## 2. 初始化与优先级

### 2.1 初始化方法

```python
config.initialize(
    env_path=None,
    env_prefix=None,
    force_reload=False,
    dev_mode=None,
    cli_overrides=None,
)
```

### 2.2 配置优先级

从高到低：

1. CLI 显式覆盖（`cli_overrides`）
2. 系统环境变量（`LOL_*`）
3. `.lol.env.dev` / `.lol.env`
4. 内置默认值

## 3. 核心配置项

### 3.1 必填项

- `GAME_PATH`
- `OUTPUT_PATH`

缺失时抛出 `ConfigValidationError`。

### 3.2 常用项

- `GAME_REGION`（默认 `zh_CN`）
- `EXCLUDE_TYPE`（默认 `SFX,MUSIC`）
- `GROUP_BY_TYPE`（默认 `False`）
- `WWISER_PATH`

### 3.3 派生路径（自动生成）

- `AUDIO_PATH`：`<OUTPUT_PATH>/audios`
- `TEMP_PATH`：`<OUTPUT_PATH>/temps`
- `LOG_PATH`：`<OUTPUT_PATH>/logs`
- `CACHE_PATH`：`<OUTPUT_PATH>/cache`
- `HASH_PATH`：`<OUTPUT_PATH>/hashes`
- `REPORT_PATH`：`<OUTPUT_PATH>/reports`
- `MANIFEST_PATH`：`<OUTPUT_PATH>/manifest`

## 4. 数据读写辅助（`manager/utils.py`）

### 4.1 读取 API

```python
def find_data_file(path: Path) -> Path | None
def read_data(path: Path) -> dict
```

行为：

- 当 `path` 不带后缀时，按运行模式选择优先级自动查找 `.msgpack/.yml/.json`。
- 开发模式优先可读格式，非开发模式优先高效格式。

### 4.2 写入 API

```python
def write_data(data: dict, base_path: Path) -> None
```

行为：

- 开发模式写 `.yml`
- 非开发模式写 `.msgpack`

### 4.3 版本与元数据 API

```python
def get_game_version(game_path: Path) -> str
def create_metadata_object(game_version: str, languages: list[str]) -> dict
def needs_update(base_path: Path, current_version: str, force_update: bool) -> bool
```

## 5. 路径命名工具（`utils/path_constants.py`）

```python
def get_output_dir_name(entity_type: str) -> str
def get_game_dir_name(entity_type: str) -> str
def format_entity_folder_name(...) -> str
def format_sub_entity_folder_name(sub_id: str, sub_name: str) -> str
```

用途：统一生成 `champions/maps` 输出目录与实体文件夹命名，减少跨平台大小写与非法字符问题。
