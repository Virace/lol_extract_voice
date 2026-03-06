# Remote 模式说明

本文档面向实际使用者，说明 `lol_audio_unpack` 当前的 remote 模式如何工作、适合什么场景、有哪些限制。

## 1. 适用场景

remote 模式适合：

- 没有本地完整游戏客户端
- 运行环境磁盘受限（CI、容器、临时服务器）
- 只想处理少量英雄 / 地图

remote 模式不适合：

- 你已经有稳定的本地完整客户端
- 你要频繁反复处理大量实体
- 你更关注总耗时而不是磁盘峰值

## 2. 核心前提

remote 模式依赖上游 `RiotManifest` 提供一对 **已经对齐** 的 LCU / GAME manifest。

当前仓库默认假设：

- `LOL_REMOTE_VERSION`
- `LOL_REMOTE_LCU_MANIFEST_URL`
- `LOL_REMOTE_GAME_MANIFEST_URL`

三者来自同一个已对齐快照。

推荐上游来源：

- `RiotGameData.resolve_live_manifest_pair(...)`

## 3. 当前能力边界

### 3.1 已完成真实验证

- 英雄：
  - `update`
  - `extract`
  - `mapping`
- 地图：
  - `update`

### 3.2 已确认可运行但仍属专项长测

- 地图 `mapping`

这条链路已确认：

- root / language WAD 准备正常
- `wwiser` 调用正常
- HIRC 缓存持续生成

但由于耗时很长，当前仍视为专项长测项。

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
export LOL_REMOTE_VERSION=16.5
export LOL_REMOTE_LCU_MANIFEST_URL="https://..."
export LOL_REMOTE_GAME_MANIFEST_URL="https://..."
export LOL_OUTPUT_PATH="/tmp/lol-remote"
export LOL_GAME_REGION="zh_CN"
```

若要执行 `mapping`：

```bash
export LOL_WWISER_PATH="/path/to/wwiser.pyz"
```

## 6. 执行语义

### 6.1 `update`

remote 模式下：

1. 先缓存并下载 `description.json`
2. 按区域下载 `rcp-be-lol-game-data` 所需 assets.wad
3. 运行 `DataUpdater`
4. 再从 GAME manifest 中按需提取 BIN，写入 `manifest/<version>/bin_input`
5. 运行 `BinUpdater`

### 6.2 `extract / mapping`

在 remote 模式下，CLI 不再简单地整批执行，而是采用 **单位驱动**：

1. `update` 先全局执行一次
2. 构建实体 work item 队列
3. 对每个英雄 / 地图：
   - 计算当前实体所需 WAD 并集
   - 先执行 `extract`
   - 再执行 `mapping`
   - 完成后清理当前实体远端 WAD

## 7. 资源规划规则

### 7.1 `extract`

- 只解 `VO`：
  - 只准备语言 WAD
- 含 `SFX/MUSIC`：
  - 准备 root WAD
- 同时命中两类：
  - root / language WAD 都准备

### 7.2 `mapping`

`mapping` 当前不是只处理 `VO`。

真实逻辑是：

1. 只要某个 `category` 在 `banks` 和 `events` 中都有数据，就处理
2. 再根据 `category` 是否包含 `VO` 决定 WAD 来源

因此：

- `mapping` 通常会同时需要 root + 语言 WAD
- 对地图尤其如此，因为地图往往卷入：
  - 环境音效
  - 音乐
  - NPC / VO 事件

## 8. 清理策略

默认：

- `cleanup_remote=True`

可显式关闭：

```bash
--no-cleanup-remote
```

### 8.1 全局 `update` 后清理

默认会清理：

- LCU assets.wad
- `manifest/<version>/bin_input/**`
- `.use_local_bin`

### 8.2 单实体清理

在 remote-only 单位驱动下：

- 单英雄 / 单地图完成后，会清理当前实体的 GAME WAD

## 9. 磁盘占用

当前已接入目录峰值占用监控，测试侧会写入：

- `space_usage_reports.json`

统计规则：

- 按 inode 去重
- 硬链接不会重复计算占用

已观测样例：

- 英雄 `extract`：峰值约 `11.66GiB`
- 地图 `update-map11`：峰值约 `5.49GiB`

## 10. 典型命令

```bash
# 远端更新指定英雄
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555
```

```bash
# 远端更新 + 解包指定英雄
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555
```

```bash
# 远端更新 + 解包 + 映射指定英雄
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555 \
  --mapping-champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz"
```

```bash
# 远端处理并保留现场
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555 \
  --mapping-champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz" \
  --no-cleanup-remote
```

## 11. 测试说明

真实远端 live 下载测试统一使用：

- `remote_live`

默认全量测试不会执行：

```bash
uv run pytest -q
```

显式执行：

```bash
UV_CACHE_DIR=.cache/uv uv run pytest -q -m remote_live
```

## 12. 当前未完全闭环的事项

- 地图 `mapping-map11` 最终落盘断言
- `mapping --integrate-data` 真实远端验收
- 更面向普通用户的 remote 命令示例与 FAQ 可继续补充
