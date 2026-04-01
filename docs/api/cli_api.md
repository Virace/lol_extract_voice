# CLI API（命令行参数与执行语义）

主入口：`unpack`（对应 `lol_audio_unpack.__main__:main`）

## 1. 基础命令

```bash
uv run unpack <update|extract|mapping> [OPTIONS]
```

兼容模块入口仍可用：

```bash
python -m lol_audio_unpack <update|extract|mapping> [OPTIONS]
```

## 2. 配置来源语义

CLI 当前只有两种模式：

### 2.1 纯 CLI 模式

- 不带 `-c/--config-file`
- 仅使用内建默认值 + 本次命令显式参数
- 不再隐式读取 `.lol.env` 或系统 `LOL_*`

示例：

```bash
uv run unpack update \
  --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "./output"
```

### 2.2 配置文件模式

- 带 `-c` 或 `--config-file`
- `-c` 不带路径：读取默认配置文件
- `-c <PATH>`：读取指定 INI 配置文件
- 启用 `-c` 后，除动作子命令和配置文件路径外，不能再手工追加任何其他参数

默认配置文件名：

- 源码运行：`lol-audio-unpack.ini`
- `--dev`：`lol-audio-unpack.dev.ini`

配置文件结构：

- `[app]`：共享配置
- `[update]`：`update` 子命令参数
- `[extract]`：`extract` 子命令参数
- `[mapping]`：`mapping` 子命令参数

其中：

- `GUI` 只读取 `[app]`
- 动作分组仅在 CLI 的 `-c` 模式下生效

示例配置文件中的约定：

- 未注释的项：通常是必填或最重要的项
- 注释掉的项：表示默认值示例，不写就沿用默认值

示例：

```bash
uv run unpack extract -c
uv run unpack mapping -c ./config/custom.ini
```

## 3. 共享配置参数

以下参数属于“共享配置”，只允许在纯 CLI 模式下显式传入：

- `--source-mode {local_path,remote_snapshot}`
- `--game-path PATH`
- `--output-path PATH`
- `--game-region REGION`
- `--exclude-type TYPES`
- `--wwiser-path PATH`
- `--group-by-type` / `--no-group-by-type`
- `--remote-live-region REGION`
- `--cleanup-remote` / `--no-cleanup-remote`
- `--remote-version VERSION`
- `--remote-lcu-manifest-url URL`
- `--remote-game-manifest-url URL`
- `--with-bp-vo` / `--no-with-bp-vo`

通用参数：

- `-c, --config-file [PATH]`
- `--max-workers N`
- `-l, --log-level`
- `--dev`
- `--enable-league-tools-log`

## 4. 子命令参数

### 4.1 `update`

- `--champions [IDs|ALIASES]`
- `--maps [IDs]`
- `-f, --force`
- `--skip-events`

在 `-c` 模式下，上述参数应写入 `[update]` section：

```ini
[update]
champions = Annie,Ahri
maps =
force = false
skip_events = false
```

示例：

```bash
uv run unpack update --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" --output-path "./output"
uv run unpack update -c
```

### 4.2 `extract`

- `--champions [IDs|ALIASES]`
- `--maps [IDs]`
- `--wav`
- `--wav-workers N`
- `--wav-timeout SECONDS`
- `--wav-retries N`
- `--wav-format {auto,pcm16,pcm24,pcm32,float}`

在 `-c` 模式下，上述参数应写入 `[extract]` section。

示例：

```bash
uv run unpack extract --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" --output-path "./output" --champions Annie,Ahri
uv run unpack extract -c
```

### 4.3 `mapping`

- `--champions [IDs|ALIASES]`
- `--maps [IDs]`
- `--integrate-data` / `--no-integrate-data`

在 `-c` 模式下，上述参数应写入 `[mapping]` section。

示例：

```bash
uv run unpack mapping --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" --output-path "./output" --champions Annie --wwiser-path "./tools/wwiser.pyz"
uv run unpack mapping -c
```

## 5. 执行与校验规则

- 必须提供一个动作子命令：`update` / `extract` / `mapping`
- `--wav*` 仅允许和 `extract` 一起使用
- `--integrate-data` 仅允许和 `mapping` 一起使用
- `local_path` 模式会校验 `game_path` 是否存在
- `remote_snapshot` 模式下：
  - 默认按 `remote_live_region` 自动解析最新 live 快照
  - 若显式指定 `remote_version` / `remote_lcu_manifest_url` / `remote_game_manifest_url`，三者必须同时提供

## 6. Remote 模式示例

纯 CLI 显式参数：

```bash
uv run unpack update \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555
```

配置文件模式：

```bash
uv run unpack extract -c ./config/lol-audio-unpack.remote.ini
```

## 7. 退出语义

- 参数或配置错误：`sys.exit(1)`
- `KeyboardInterrupt`：`sys.exit(1)`
- 正常完成：退出码 `0`
