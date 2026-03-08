# Remote 模式（运行与接入）

本文档面向实际使用者与接入方，说明 `lol_audio_unpack` 当前的 remote 模式如何工作、适合什么场景，以及 CLI / Python API 的推荐调用方式。

## 1. 适用场景

remote 模式适合：

- 没有本地完整游戏客户端
- 运行环境磁盘受限（CI、容器、临时服务器）
- 只想处理少量英雄 / 地图

remote 模式不适合：

- 已经有稳定的本地完整客户端
- 需要频繁重复处理大量实体
- 更关注总耗时而不是磁盘峰值

## 2. 核心前提

remote 模式依赖上游 `RiotManifest` 提供一对已经对齐的 LCU / GAME manifest。

当前仓库的默认行为是：

- 使用 `LeagueManifestResolver.resolve_manifest_pair(...)` 自动解析最新 live 快照
- 未显式覆盖时，按 `LOL_REMOTE_LIVE_REGION` 选择 live 区服（默认 `EUW`）

如果需要固定某个快照，也可以手动提供：

- `LOL_REMOTE_VERSION`
- `LOL_REMOTE_LCU_MANIFEST_URL`
- `LOL_REMOTE_GAME_MANIFEST_URL`

这三个字段必须来自同一个已对齐快照，且需要同时提供。

## 3. 当前能力边界

### 3.1 已完成真实验证

- 英雄：
  - `update`
  - `extract`
  - `mapping`
  - `mapping --integrate-data`
- 地图：
  - `update`
  - `mapping`

### 3.2 当前定位

- 地图 `mapping` 已通过真实 remote benchmark 验证
- `mapping --integrate-data` 已完成真实远端验收
- 地图链路整体耗时仍较长，相关回归继续保留为专项长测项

## 4. 运行模式

### 4.1 `local_path`

- 使用本地完整客户端
- 版本来源：`Game/content-metadata.json`
- 如存在 `LeagueClient.exe`，会补做主版本一致性校验

### 4.2 `remote_snapshot`

- 不依赖本地完整客户端
- 版本、LCU manifest、GAME manifest 都来自上游
- 当前仓库不负责双清单对账

## 5. 最小配置

```bash
export LOL_SOURCE_MODE=remote_snapshot
export LOL_OUTPUT_PATH="/tmp/lol-remote"
export LOL_GAME_REGION="zh_CN"

# 可选：切换 live 区服，默认 EUW
export LOL_REMOTE_LIVE_REGION="EUW"
```

若要固定某个快照、复现问题或调试指定 manifest，可额外显式提供：

```bash
export LOL_REMOTE_VERSION="16.5"
export LOL_REMOTE_LCU_MANIFEST_URL="https://..."
export LOL_REMOTE_GAME_MANIFEST_URL="https://..."
```

这三个高级覆盖项需要同时提供；不提供时会自动解析最新 live 快照。

若要执行 `mapping`：

```bash
export LOL_WWISER_PATH="/path/to/wwiser.pyz"
```

## 6. CLI 调用方式

### 6.1 执行语义

remote 模式下：

1. `update` 仍全局执行一次
2. 若存在 `extract` / `mapping`，则切换为单位驱动：
   - 构建实体 work item 队列
   - 按实体顺序执行 `extract` / `mapping`
   - 单实体完成后立即清理当前实体远端 WAD
3. 下载类错误（`DownloadError` / `DecompressError` / `DownloadBatchError`）默认重试 3 次
4. 单实体完整流程默认最多重试 3 次；超过阈值会直接向上抛错

### 6.2 典型命令

```bash
# 远端更新指定英雄
uv run unpack --update-champions 1,103,555
```

```bash
# 远端更新 + 解包指定英雄
uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555
```

```bash
# 远端更新 + 解包 + 映射指定英雄
uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555 \
  --mapping-champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz"
```

```bash
# 保留现场，关闭自动清理
uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555 \
  --mapping-champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz" \
  --no-cleanup-remote
```

## 7. Python API 调用方式

> 说明：英雄筛选除稳定 `ID` 外，也支持稳定 `alias`。推荐做法是先调用 `prepare_update_data()`，再用 `resolve_champion_ids(...)` 将 alias 解析为稳定 ID；两者都能准确定位到同一个英雄。

### 7.1 最小 `update -> extract`

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions
from lol_audio_unpack.app_context import create_app_context

ctx = create_app_context(
    cli_overrides={
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

若上游只提供英雄 alias，可先这样处理：

```python
app.prepare_update_data()
champion_ids = app.resolve_champion_ids(["Annie", "Ahri"])
```

随后再把 `champion_ids` 填入 `OperationOptions(...)` 即可。

### 7.2 `update -> extract -> mapping` + 回调

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions, RemoteEntityCallbackPayload
from lol_audio_unpack.app_context import create_app_context


def on_entity_complete(payload: RemoteEntityCallbackPayload) -> None:
    print(
        payload.entity_type,
        payload.entity_id,
        payload.audio_output_paths,
        payload.mapping_output_path,
    )


ctx = create_app_context(
    cli_overrides={
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
    on_entity_complete=on_entity_complete,
)
```

### 7.3 回调与重试语义

- `on_entity_complete(payload)` 在当前实体成功完成后触发
- `payload.audio_output_paths` 返回当前实体实际存在的解包输出目录列表
- `payload.mapping_output_path` 返回当前实体 mapping 最终产物文件路径
- `download_retry_attempts` 默认 `3`
- `entity_retry_attempts` 默认 `3`
- 若单实体完整流程连续失败达到阈值，会直接向上抛出异常，并提示当前解包脚本可能已无法适配最新二进制资源

## 8. 资源规划规则

### 8.1 `extract`

- 只解 `VO`：只准备语言 WAD
- 含 `SFX/MUSIC`：准备 root WAD
- 同时命中两类：root / language WAD 都准备

### 8.2 `mapping`

`mapping` 当前不是只处理 `VO`。

真实逻辑是：

1. 只要某个 `category` 在 `banks` 和 `events` 中都有数据，就处理
2. 再根据 `category` 是否包含 `VO` 决定 WAD 来源

因此：

- `mapping` 通常会同时需要 root + 语言 WAD
- 地图 `mapping` 往往还会卷入环境音效、音乐和 NPC / VO 事件

## 9. 清理策略

默认：

- `cleanup_remote=True`

全局 `update` 完成后默认会清理：

- LCU assets.wad
- `manifest/<version>/bin_input/**`
- `.use_local_bin`

在 remote 单位驱动下：

- 单英雄 / 单地图完成后，会清理当前实体的 GAME WAD

如果需要保留现场，请显式关闭 `cleanup_remote`：

- CLI：`--no-cleanup-remote`
- Python API：在 `create_app_context(..., cli_overrides={"CLEANUP_REMOTE": False})` 中覆盖

## 10. 测试说明

真实远端 live 下载测试统一使用 `remote_live` marker。

默认全量测试不会执行：

```bash
uv run pytest -q
```

显式执行：

```bash
uv run pytest -q -m remote_live
```
