# 配置与数据读写 API

## 1. 配置模型（`app_context.py`）

核心数据结构：

```python
class SourceMode(str, Enum):
    LOCAL_PATH = "local_path"
    REMOTE_SNAPSHOT = "remote_snapshot"


@dataclass(frozen=True)
class RemoteSnapshotConfig:
    version: str
    lcu_manifest_url: str
    game_manifest_url: str


@dataclass(frozen=True)
class AppConfig:
    game_path: Path
    output_path: Path
    game_region: str
    exclude_types: tuple[str, ...]
    include_types: tuple[str, ...]
    cleanup_remote: bool
    source_mode: SourceMode
    remote_snapshot: RemoteSnapshotConfig | None
    group_by_type: bool
    with_bp_vo: bool
    wwiser_path: Path | None
    dev_mode: bool


@dataclass(frozen=True)
class AppPaths:
    audio_path: Path
    temp_path: Path
    log_path: Path
    cache_path: Path
    hash_path: Path
    report_path: Path
    manifest_path: Path
    local_version_file: Path
    game_champion_path: Path
    game_maps_path: Path
    game_lcu_path: Path


@dataclass
class AppContext:
    config: AppConfig
    paths: AppPaths
    logger: Any
    runtime_cache: dict[str, Any]
```

## 2. 上下文构建入口

```python
def create_app_context(
    env_path: StrPath | None = None,
    env_prefix: str = "LOL_",
    force_reload: bool = False,
    dev_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext
```

```python
def initialize_context_from_env(
    env_path: StrPath | None = None,
    env_prefix: str = "LOL_",
    force_reload: bool = False,
    dev_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
) -> AppContext
```

`setup_app(...)` 为对外便捷入口：在构建 `AppContext` 的同时完成日志初始化。

## 3. 配置优先级

从高到低：

1. CLI 显式覆盖（`cli_overrides`）
2. 系统环境变量（`LOL_*`）
3. `.lol.env.dev` / `.lol.env`
4. 内置默认值（`GAME_REGION`、`EXCLUDE_TYPE`、`CLEANUP_REMOTE`、`GROUP_BY_TYPE`、`SOURCE_MODE`、`WITH_BP_VO`）

## 4. 必填项与校验

### 4.1 必填项

- `GAME_PATH`
- `OUTPUT_PATH`

缺失时抛出 `AppContextValidationError`。

补充说明：

- `local_path` 模式下：
  - `GAME_PATH` 必须显式存在
- `remote_snapshot` 模式下：
  - 若未显式给出 `GAME_PATH`，会默认派生为 `OUTPUT_PATH/_prepared_game`
  - 必须额外提供：
    - `REMOTE_VERSION`
    - `REMOTE_LCU_MANIFEST_URL`
    - `REMOTE_GAME_MANIFEST_URL`

### 4.2 关键归一化规则

- `GAME_REGION=en_us` 会归一化为 `default`。
- `EXCLUDE_TYPE` 支持字符串或可迭代输入，内部统一转为大写元组。
- `include_types` 由 `KNOWN_AUDIO_TYPES - exclude_types` 自动推导。
- `SOURCE_MODE` 目前支持：
  - `local_path`
  - `remote_snapshot`
- `REMOTE_VERSION` 会标准化为 `major.minor`。

## 5. 运行目录派生

`create_app_context` 仅负责派生路径，不会在初始化阶段统一创建目录。
目录按流程懒创建（例如更新阶段创建 `manifest/temps`，解包阶段创建 `audios/reports`，映射阶段创建 `cache/hashes`）：

- `audios`
- `temps`（每次初始化会清空后重建）
- `logs`
- `cache`
- `hashes`
- `reports`
- `manifest`

在 `remote_snapshot` 模式下，还会按需派生：

- `_prepared_game`
- `cache/remote/<version>/lcu`
- `cache/remote/<version>/game`

## 6. 数据读写辅助（`manager/utils.py`）

### 6.1 读取 API

```python
def find_data_file(path: Path, *, dev_mode: bool) -> Path | None
def read_data(path: Path, *, dev_mode: bool = False) -> dict
```

行为：

- 当 `path` 不带后缀时，按运行模式选择优先级自动查找 `.msgpack/.yml/.json`。
- 开发模式优先可读格式，非开发模式优先高效格式。

### 6.2 写入 API

```python
def write_data(data: dict, base_path: Path, *, dev_mode: bool) -> None
```

行为：

- 开发模式写 `.yml`
- 非开发模式写 `.msgpack`

### 6.3 版本与元数据 API

```python
def get_game_version(game_path: Path) -> str
def get_lcu_version(game_path: Path) -> str | None
def validate_local_path_version(game_path: Path, game_version: str) -> None
def resolve_context_version(ctx: AppContext) -> str
def create_metadata_object(game_version: str, languages: list[str]) -> dict
def needs_update(base_path: Path, current_version: str, force_update: bool, *, dev_mode: bool) -> bool
```

说明：

- `get_game_version`：
  - 仅用于 `local_path`
  - 主版本来源仍为 `Game/content-metadata.json`
- `get_lcu_version`：
  - 从 `LeagueClient.exe` 提取 `major.minor`
  - 仅作为本地一致性辅助校验
- `resolve_context_version`：
  - `local_path`：走本地版本
  - `remote_snapshot`：直接使用 `RemoteSnapshotConfig.version`

## 7. 路径命名工具（`utils/path_constants.py`）

```python
def get_output_dir_name(entity_type: str) -> str
def get_game_dir_name(entity_type: str) -> str
def format_entity_folder_name(...) -> str
def format_sub_entity_folder_name(sub_id: str, sub_name: str) -> str
```

用途：统一生成 `champions/maps` 输出目录与实体文件夹命名，减少跨平台大小写与非法字符问题。

## 8. 迁移说明

旧的 `utils.config` 全局依赖路径已从主链路移除；
当前 API 文档以 `AppContext` 显式注入模型为唯一基线。

## 9. remote 相关说明

当前 remote 主要通过 `create_app_context(..., cli_overrides=...)` 或环境变量驱动，推荐最小集合：

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
```

`cleanup_remote=True` 时：

- 全局 `update` 后会清理：
  - LCU WAD
  - `bin_input`
- 单实体 `extract / mapping` 完成后会清理当前实体的 GAME WAD
