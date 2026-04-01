# Remote 模式（运行与接入）

本文档说明 `lol_audio_unpack` 当前 `remote_snapshot` 模式的推荐配置方式、CLI 调用方式与 Python API 接入方式。

## 1. 适用场景

适合：

- 没有本地完整游戏客户端
- 运行环境磁盘受限
- 只处理少量英雄 / 地图

不适合：

- 已有稳定的本地完整客户端
- 需要频繁重复处理大量实体
- 更关注总耗时而不是磁盘峰值

## 2. 核心语义

`remote_snapshot` 模式依赖上游 `RiotManifest` 提供一对已对齐的 LCU / GAME manifest。

当前默认行为：

- 使用 `LeagueManifestResolver.resolve_manifest_pair(...)` 自动解析最新 live 快照
- 未显式固定快照时，按 `remote_live_region` 选择 live 区服，默认 `EUW`

若要固定某个快照，则必须同时提供：

- `REMOTE_VERSION`
- `REMOTE_LCU_MANIFEST_URL`
- `REMOTE_GAME_MANIFEST_URL`

## 3. 最小配置

### 3.1 纯 CLI 显式参数

```bash
uv run unpack update extract \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555
```

### 3.2 配置文件模式

示例配置：

```ini
[app]
source_mode = remote_snapshot
output_path = /tmp/lol-remote
game_region = zh_CN
remote_live_region = EUW

[targets]
champions = 1,103,555
```

调用方式：

```bash
uv run unpack extract -c ./config/lol-audio-unpack.remote.ini
```

### 3.3 若要执行 mapping

额外提供 `wwiser_path`：

```bash
uv run unpack mapping \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz"
```

## 4. CLI 执行方式

### 4.1 典型命令

```bash
uv run unpack update extract \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555
```

```bash
uv run unpack extract \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555
```

```bash
uv run unpack mapping \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz"
```

保留现场、关闭自动清理：

```bash
uv run unpack extract \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555 \
  --no-cleanup-remote
```

### 4.2 执行语义

在 remote 模式下：

1. `update` 仍全局执行一次
2. `extract` / `mapping` 会按实体逐个执行
3. 单实体完成后会清理当前实体远端 WAD（除非关闭清理）
4. 下载类错误默认重试 3 次
5. 单实体完整流程默认最多重试 3 次

## 5. Python API 调用方式

最小 `update -> extract` 示例：

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
app.run_remote_entity_workflow(
    update_options=OperationOptions(champion_ids=(1, 103)),
    update_target="skin",
    extract_options=OperationOptions(champion_ids=(1, 103), max_workers=4),
    extract_include_champions=True,
)
```

带 mapping 的示例：

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions
from lol_audio_unpack.app_context import create_app_context

ctx = create_app_context(
    settings={
        "SOURCE_MODE": "remote_snapshot",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "WWISER_PATH": "./wwiser.pyz",
    }
)

app = LolAudioUnpackApp(ctx)
app.run_remote_entity_workflow(
    update_options=OperationOptions(champion_ids=(1, 103)),
    update_target="skin",
    extract_options=OperationOptions(champion_ids=(1, 103), max_workers=4),
    mapping_options=OperationOptions(champion_ids=(103,), max_workers=1, integrate_data=True),
    extract_include_champions=True,
    mapping_include_champions=True,
)
```

## 6. 资源与清理规则

默认：

- `cleanup_remote = True`

全局 `update` 完成后会清理：

- LCU assets.wad
- `manifest/<version>/bin_input/**`
- `.use_local_bin`

实体级 `extract` / `mapping` 完成后会清理当前实体的 GAME WAD。

## 7. 真实长测

真实远端 live 下载测试统一使用 `remote_live` marker。

默认全量测试已排除：

```bash
uv run pytest -q
```

显式运行远端长测：

```bash
uv run pytest -q -m remote_live
```
