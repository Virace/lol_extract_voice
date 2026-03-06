# CLI API（命令行参数与执行语义）

主入口：`unpack`（对应 `lol_audio_unpack.__main__:main`）

## 1. 基础命令

```bash
uv run unpack [OPTIONS]
```

```bash
python -m lol_audio_unpack [OPTIONS]
```

## 2. 参数总表

### 2.1 数据更新组

- `--update`：更新全部（英雄+地图）。
- `--update-champions [IDs]`：更新全部英雄或指定英雄（逗号分隔）。
- `--update-maps [IDs]`：更新全部地图或指定地图（逗号分隔）。
- `-f, --force`：强制更新，跳过版本命中判断。
- `--skip-events`：更新时跳过事件提取（更快）。

### 2.2 音频解包组

- `--extract`：解包全部（英雄+地图）。
- `--extract-champions [IDs]`：解包全部英雄或指定英雄。
- `--extract-maps [IDs]`：解包全部地图或指定地图。

### 2.3 映射组

- `--mapping`：构建全部事件映射。
- `--mapping-champions [IDs]`：构建全部英雄或指定英雄映射。
- `--mapping-maps [IDs]`：构建全部地图或指定地图映射。
- `--integrate-data`：输出整合数据（必须和映射参数同时出现）。

### 2.4 通用参数

- `--max-workers N`：并发线程数，默认 `4`。
- `-l, --log-level`：日志级别，默认 `INFO`。
- `--dev`：启用开发模式。
- `--with-bp-vo` / `--no-with-bp-vo`：显式覆盖大厅 BP 语音开关。
- `--enable-league-tools-log`：允许 `league_tools` 日志输出。
- `--cleanup-remote` / `--no-cleanup-remote`：remote 模式下是否在整轮命令成功后自动清理远端准备产物。

### 2.5 配置覆盖参数（优先级最高）

- `-g, --game-path PATH`
- `-o, --output-path PATH`
- `-r, --game-region REGION`
- `-t, --exclude-type TYPES`
- `-w, --wwiser-path PATH`
- `-b, --group-by-type` / `--no-group-by-type`

### 2.6 remote 模式相关配置

当前 remote 模式仍主要通过环境变量或 `cli_overrides` 驱动，常用项为：

- `LOL_SOURCE_MODE=remote_snapshot`
- `LOL_REMOTE_VERSION`
- `LOL_REMOTE_LCU_MANIFEST_URL`
- `LOL_REMOTE_GAME_MANIFEST_URL`
- `LOL_CLEANUP_REMOTE`

当前 CLI 还没有为这些 remote 字段单独提供一组正式参数。

## 3. 执行顺序与校验

### 3.1 顺序规则

当同次命令包含多个操作时：

### `local_path`

固定顺序为：

1. 更新（`execute_update_operations`）
2. 解包（`execute_extract_operations`）
3. 映射（`execute_mapping_operations`）

### `remote_snapshot`

执行语义为：

1. `update` 仍全局执行一次
2. 若存在 `extract` / `mapping`，则切换为 remote-only 单位驱动：
   - 构建实体 work item 队列
   - 单位顺序执行 `extract` / `mapping`
   - 单实体完成后立即清理当前实体远端 WAD

### 3.2 关键校验

- 未指定任何操作参数会直接报错并退出。
- `--integrate-data` 必须与任一 mapping 参数配合。
- 映射前会校验 `WWISER_PATH` 是否存在。
- `local_path` 初始化阶段会校验 `GAME_PATH` 是否存在。
- `remote_snapshot` 要求：
  - `REMOTE_VERSION`
  - `REMOTE_LCU_MANIFEST_URL`
  - `REMOTE_GAME_MANIFEST_URL`

## 4. 退出语义

- 参数/配置错误：`sys.exit(1)`。
- `KeyboardInterrupt`：`sys.exit(1)`。
- 正常完成：进程返回 `0`。

## 5. 备注：`mapping` 脚本入口

`pyproject.toml` 还定义了 `mapping = lol_audio_unpack.mapping:main`，该入口当前是示例用法（内部默认构建英雄 ID=1），不等价于完整 CLI。

## 6. 真实远端长测

真实远端 live 下载测试统一使用 `remote_live` marker。

默认全量测试已排除：

```bash
uv run pytest -q
```

显式运行远端长测：

```bash
UV_CACHE_DIR=.cache/uv uv run pytest -q -m remote_live
```
