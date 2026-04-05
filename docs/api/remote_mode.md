# Remote 模式（运行与接入）

本文档说明当前 `remote_snapshot` 模式的配置方式、CLI 用法与 Python 接入方式。

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

- 未显式固定快照时，按 `REMOTE_LIVE_REGION` 解析最新 live 快照
- 默认区服：`EUW`
- `update` 全局执行一次
- `extract / mapping` 通过 `LolAudioUnpackApp.run_workflow(...)` 按实体顺序执行
- 单实体完成后会清理当前远端 WAD（除非显式关闭）

若要固定某个快照，则需要同时提供：

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

```ini
[app]
source_mode = remote_snapshot
output_path = /tmp/lol-remote
game_region = zh_CN
remote_live_region = EUW

[targets]
champions = 1,103,555

[runtime]
max_workers = 4

[wav]
enable = false
```

调用方式：

```bash
uv run unpack extract -c ./config/lol-audio-unpack.remote.ini
```

### 3.3 若要执行 mapping

需要额外提供 `wwiser_path`：

```bash
uv run unpack mapping \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz"
```

## 4. CLI 执行语义

在 remote 模式下：

1. `update` 先完成全局数据准备
2. `extract` / `mapping` 再按实体逐个执行
3. 每个实体只准备当前所需的 WAD 与 BIN 输入
4. 单实体完成后会清理当前实体远端产物
5. 下载类错误默认重试 3 次
6. 单实体完整流程默认最多重试 3 次

保留现场、关闭自动清理：

```bash
uv run unpack extract \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555 \
  --no-cleanup-remote
```

## 5. Python API

### 5.1 `run_workflow(...)`

最常用的 Python 入口是：

```python
from lol_audio_unpack.app import LolAudioUnpackApp, OperationOptions, create_app_context

ctx = create_app_context(
    settings={
        "SOURCE_MODE": "remote_snapshot",
        "OUTPUT_PATH": "./out",
        "GAME_REGION": "zh_CN",
        "REMOTE_LIVE_REGION": "EUW",
        "WWISER_PATH": "./wwiser.pyz",
    }
)
app = LolAudioUnpackApp(ctx)

app.run_workflow(
    update_options=OperationOptions(champion_ids=(1, 103)),
    extract_options=OperationOptions(champion_ids=(1, 103), max_workers=4),
    mapping_options=OperationOptions(champion_ids=(1, 103), max_workers=1, integrate_data=True),
    extract_include_champions=True,
    mapping_include_champions=True,
)
```

### 5.2 `build_work_items(...)`

如果只想先看 remote 单位驱动会生成哪些实体队列，可以先调用：

```python
work_items = app.build_work_items(
    extract_options=OperationOptions(champion_ids=(1, 103)),
    mapping_options=OperationOptions(champion_ids=(1, 103), integrate_data=True),
    extract_include_champions=True,
    mapping_include_champions=True,
)
```

返回值是按实体类型与 ID 排序的 `RemoteEntityWorkItem` 列表。

### 5.3 低层准备入口

需要手动控制 LCU / BIN / GAME 资源准备时，可直接使用：

```python
from lol_audio_unpack.runtime.remote import RemotePreparer

preparer = RemotePreparer(ctx=ctx)
```

它提供：

- `prepare_lcu_data()`
- `prepare_bin_inputs(...)`
- `prepare_extract_wads(...)`
- `prepare_mapping_wads(...)`
- `cleanup_artifacts(...)`

## 6. 资源与清理

默认：

- `cleanup_remote = True`

清理范围包括：

- 全局 `update` 之后登记的 LCU bundle 与 BIN 输入
- 单实体 `extract / mapping` 之后登记的 GAME WAD
- `_prepared_game` 下的最小远端运行时产物

## 7. 验证与测试

真实远端 live 下载测试统一使用 `remote_live` marker。

默认全量测试已排除：

```bash
uv run pytest -q
```

显式运行远端长测：

```bash
uv run pytest -q -m remote_live
```
