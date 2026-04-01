# 配置与数据读写 API

## 1. 当前配置主线

当前仓库的共享配置已经收口为：

1. `settings`：显式传入的共享配置映射
2. 标准 INI 配置文件：由外部显式读取，再转成 `settings`
3. `AppContext`：只消费 `settings`，不再负责来源解析

已移除的主线：

- `.lol.env` / `.lol.env.dev`
- 系统环境变量 `LOL_*`
- `initialize_context_from_env(...)`
- `cli_overrides`

## 2. 共享配置 schema

集中定义位于：

- `src/lol_audio_unpack/config_schema.py`

这里维护：

- 内部 settings key
- INI 文件中的小写 key
- CLI 对应的 argparse attr 名
- 默认值

新增、删除或重命名共享配置字段时，应优先修改这个 schema 文件。

## 3. 上下文构建入口

```python
def create_app_context(
    *,
    settings: Mapping[str, Any] | None = None,
    force_reload: bool = False,
    dev_mode: bool = False,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext
```

```python
def setup_app(
    dev_mode: bool = False,
    log_level: str = "INFO",
    **kwargs,
) -> AppContext
```

`setup_app(...)` 是对外便捷入口：会在构建 `AppContext` 的同时完成日志初始化。

## 4. 配置文件 API

标准 INI 配置加载位于：

- `src/lol_audio_unpack/config_loading.py`

当前公开的核心 helper：

```python
def resolve_default_config_file_path(
    *,
    dev_mode: bool = False,
    runtime_paths: RuntimePaths | None = None,
) -> Path


def load_settings_from_config_file(
    config_file: StrPath,
    *,
    require_exists: bool = True,
) -> dict[str, str]


def load_command_config_from_file(
    config_file: StrPath,
    *,
    command: str,
    require_exists: bool = True,
) -> dict[str, Any]


def write_settings_to_config_file(
    config_file: StrPath,
    settings: dict[str, Any],
) -> None
```

默认配置文件名：

- `lol-audio-unpack.ini`
- `lol-audio-unpack.dev.ini`

标准 section：

- `[app]`：共享配置
- `[targets]`：多个动作共享的实体范围
- `[update]`：`update` 动作参数
- `[extract]`：`extract` 动作参数
- `[mapping]`：`mapping` 动作参数

GUI 语义：

- GUI 只读取 `[app]`
- `[targets] / [update] / [extract] / [mapping]` 仅供 CLI 的配置文件模式使用

建议示例风格：

- 必填或关键项保持未注释
- 只是默认值说明的项保留为注释，用户按需取消注释覆盖

## 5. `settings` 结构

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

示例：

```python
settings = {
    "GAME_PATH": "/path/to/League of Legends",
    "OUTPUT_PATH": "./output",
    "GAME_REGION": "zh_CN",
}

ctx = create_app_context(settings=settings)
```

Remote 模式最小示例：

```python
settings = {
    "SOURCE_MODE": "remote_snapshot",
    "OUTPUT_PATH": "./out",
    "GAME_REGION": "zh_CN",
    "REMOTE_LIVE_REGION": "EUW",
}

ctx = create_app_context(settings=settings)
```

固定快照示例：

```python
settings = {
    "SOURCE_MODE": "remote_snapshot",
    "OUTPUT_PATH": "./out",
    "GAME_REGION": "zh_CN",
    "REMOTE_VERSION": "16.5",
    "REMOTE_LCU_MANIFEST_URL": "https://...",
    "REMOTE_GAME_MANIFEST_URL": "https://...",
}

ctx = create_app_context(settings=settings)
```

## 6. 默认值与校验

默认值来自 `config_schema.py`，当前包括：

- `GAME_REGION = "zh_CN"`
- `EXCLUDE_TYPE = "SFX,MUSIC"`
- `CLEANUP_REMOTE = True`
- `GROUP_BY_TYPE = False`
- `SOURCE_MODE = "local_path"`
- `REMOTE_LIVE_REGION = "EUW"`
- `WITH_BP_VO = False`

关键校验规则：

- `local_path` 模式必须能解析到有效 `GAME_PATH`
- `remote_snapshot` 模式下，若未显式提供 `GAME_PATH`，会默认派生为 `OUTPUT_PATH/_prepared_game`
- `remote_snapshot` 模式下，若显式指定固定快照，则 `REMOTE_VERSION` / `REMOTE_LCU_MANIFEST_URL` / `REMOTE_GAME_MANIFEST_URL` 必须同时提供

关键归一化规则：

- `GAME_REGION=en_us` 会归一化为 `default`
- `EXCLUDE_TYPE` 支持字符串或可迭代输入，内部统一转为大写元组
- `REMOTE_LIVE_REGION` 统一转为大写 live 区服代码
- `REMOTE_VERSION` 统一转为 `major.minor`

## 7. 路径派生

`create_app_context(...)` 只负责派生路径，不会在初始化阶段统一创建目录。

派生结果包括：

- `audios`
- `wavs`
- `temps`
- `logs`
- `cache`
- `hashes`
- `reports`
- `manifest`

在 `remote_snapshot` 模式下，还会按需派生：

- `_prepared_game`
- `cache/remote/<version>/lcu`
- `cache/remote/<version>/game`

## 8. 数据读写辅助

`manager/utils.py` 中的读写 helper 仍保持不变：

- `find_data_file(...)`
- `read_data(...)`
- `write_data(...)`
- `resolve_context_version(...)`
- `needs_update(...)`

这些 helper 依赖 `AppContext` 的显式配置与派生路径，不再依赖外部全局配置。
