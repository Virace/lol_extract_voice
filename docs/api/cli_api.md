# CLI API（命令行参数与执行语义）

当前入口：

- `unpack`：对应 `lol_audio_unpack.cli.cli:main`
- `mapping`：同样对应 `lol_audio_unpack.cli.cli:main`，但默认以 `mapping` 模式启动
- `python -m lol_audio_unpack`：薄壳转发到同一套 CLI 主入口

## 1. 基础命令

```bash
uv run unpack <ACTION...> [OPTIONS]
```

单独运行映射命令时，也可以直接使用：

```bash
uv run mapping [OPTIONS]
```

模块入口仍可用：

```bash
python -m lol_audio_unpack <ACTION...> [OPTIONS]
```

## 2. 配置来源语义

CLI 当前只有两种模式：

### 2.1 纯 CLI 模式

- 不带 `-c/--config-file`
- 仅使用内建默认值 + 本次命令显式参数
- 不再隐式读取 `.lol.env` 或系统 `LOL_*`

示例：

```bash
uv run unpack update extract \
  --champions Annie,Ahri \
  --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "./output"
```

### 2.2 配置文件模式

- 带 `-c` 或 `--config-file`
- `-c` 不带路径：读取默认配置文件 `lol-audio-unpack.ini`
- `-c <PATH>`：读取指定 INI 配置文件
- 启用 `-c` 后，除动作列表和配置文件路径外，不允许再手工追加任何其他参数
- 这条规则对全部 CLI 参数都生效，包括 `--dev`、`--force`、`--max-workers`
- 如果要切换到其他 profile（例如 `lol-audio-unpack.dev.ini`），请直接写显式 `-c <PATH>`

默认配置文件名：

- 默认：`lol-audio-unpack.ini`
- dev 配置：请显式传入 `-c ./lol-audio-unpack.dev.ini`

配置文件结构：

- `[app]`：共享配置
- `[targets]`：多个动作共享的实体范围
- `[runtime]`：多个动作共享的通用执行参数
- `[update]`：`update` 动作参数
- `[extract]`：`extract` 动作参数
- `[wav]`：WAV sidecar 细节参数
- `[mapping]`：`mapping` 动作参数

其中：

- `GUI` 只读取 `[app]`
- `[targets] / [runtime] / [update] / [extract] / [wav] / [mapping]` 仅在 CLI 的 `-c` 模式下生效

示例配置文件中的约定：

- 未注释的项：通常是必填或最重要的项
- 注释掉的项：表示默认值示例，不写就沿用默认值

示例：

```bash
uv run unpack extract -c
uv run unpack update extract mapping -c ./config/custom.ini
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

注意：

- `--max-workers` 在 `-c` 模式下应写入 `[runtime]`
- `-l, --log-level`、`--dev`、`--enable-league-tools-log` 仍然只支持纯 CLI 显式传入
- 一旦启用 `-c`，它们都不能再作为手工 CLI 参数追加

## 4. 动作与参数

### 4.1 动作列表

可以顺序提供多个动作：

```bash
uv run unpack update extract --champions Annie,Ahri --game-path "./game" --output-path "./output"
```

实际执行顺序固定为：

1. `update`
2. `extract`
3. `mapping`

因此只要同次命令里包含 `update`，运行时一定会先执行 `update`。

### 4.2 共享实体选择

- `--champions [IDs|ALIASES]`
- `--maps [IDs]`

它们会对本次命令中出现的所有动作同时生效。

在 `-c` 模式下，应写入 `[targets]`：

```ini
[targets]
champions = Annie,Ahri
maps =
```

### 4.3 通用执行参数

- `--max-workers N`

在 `-c` 模式下，应写入 `[runtime]`：

```ini
[runtime]
max_workers = 4
```

### 4.4 `update`

- `-f, --force`
- `--skip-events`

在 `-c` 模式下，上述参数应写入 `[update]`：

```ini
[update]
force = false
skip_events = false
```

### 4.5 `extract`

- `--wav`
- `--wav-workers N`
- `--wav-timeout SECONDS`
- `--wav-retries N`
- `--wav-format {auto,pcm16,pcm24,pcm32,float}`

在 `-c` 模式下：

- `[extract]` 负责 `wav` 开关
- `[wav]` 负责 `wav_workers`、`wav_timeout`、`wav_retries`、`wav_format`

示例：

```ini
[extract]
wav = true

[wav]
wav_workers = 2
wav_timeout = 5
wav_retries = 3
wav_format = pcm16
```

### 4.6 `mapping`

- `--integrate-data` / `--no-integrate-data`

在 `-c` 模式下，应写入 `[mapping]`：

```ini
[mapping]
integrate_data = true
```

## 5. 执行与校验规则

- 必须提供至少一个动作：`update` / `extract` / `mapping`
- `--wav*` 仅允许和 `extract` 一起使用
- `--integrate-data` 仅允许和 `mapping` 一起使用
- `local_path` 模式会校验 `game_path` 是否存在
- `remote_snapshot` 模式下：
  - 默认按 `remote_live_region` 自动解析最新 live 快照
  - 若显式指定 `remote_version` / `remote_lcu_manifest_url` / `remote_game_manifest_url`，三者必须同时提供

## 6. Remote 模式示例

纯 CLI 显式参数：

```bash
uv run unpack update extract \
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
