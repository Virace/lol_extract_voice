# lol_audio_unpack
![](https://img.shields.io/badge/python-%3E%3D3.10-blue)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Virace/lol_extract_voice)

一个极简、高效的英雄联盟音频提取工具。

---

### **主要功能**

-   **全面支持**: 能够提取**英雄**和**地图**的所有音频类型（`VO`语音, `SFX`音效, `MUSIC`音乐）。
-   **大厅语音**: 默认不包含游戏大厅内的英雄选择/禁用语音；可通过 `--with-bp-vo` 在更新/解包流程中附带。
-   **数据纯粹**: 输出的音频文件为原始的 `.wem` 格式，文件名保留其在游戏数据中的ID，不进行重命名或分类。
-   **事件信息**: 数据更新时会包含音频事件信息，但目前解包功能**不支持**按事件对音频进行分类。

对于需要按事件分类或进行自动转码的用户，请关注后续版本或使用其他配套工具。

---

- [介绍](#介绍)
- [使用方法](#使用方法)
- [Remote 模式（无本地完整客户端）](#remote-模式无本地完整客户端)
- [基准测试](#基准测试)
- [设计哲学](#设计哲学)
- [性能参考](#性能参考)
- [后续处理：音频转码](#后续处理音频转码)
- [维护者](#维护者)
- [感谢](#感谢)
- [许可证](#许可证)


### 介绍
提取联盟客户端中的**英雄**和**地图**音频文件，专注于提供原始、未处理的音频数据。

### 使用方法
1.  **克隆仓库**:
    ```bash
    git clone https://github.com/Virace/lol_audio_unpack.git
    cd lol_audio_unpack
    ```

2.  **安装依赖**:
    *   **方式一: 使用 `uv` (推荐)**
        ```bash
        # uv 会自动创建虚拟环境
        uv sync

        # 如遇缓存目录权限问题，可使用仓库本地缓存目录
        UV_CACHE_DIR=.cache/uv uv sync
        ```
    *   **方式二: 使用 `pip`**
        ```bash
        pip install .
        ```

3.  **编写配置文件**:
    在项目根目录创建 `.lol.env` 文件。详见[配置（最简）](#配置最简)。

4.  **运行脚本**:
    所有命令都需要在项目根目录执行。

    *   **方式一: 使用 `uv` (推荐)**
        ```bash
        # --- 数据更新 ---
        # 首次运行或游戏更新后，需要更新数据

        # 更新所有数据 (英雄和地图)
        uv run unpack --update

        # 或，只更新所有英雄的数据
        uv run unpack --update-champions

        # 或，只更新指定ID的英雄 (例如：1,103,555)
        uv run unpack --update-champions 1,103,555
        
        # 或，只更新所有地图的数据
        uv run unpack --update-maps

        # 或，只更新指定ID的地图 (例如：11,12)
        uv run unpack --update-maps 11,12

        # 快速更新模式 (跳过事件数据处理，大幅提升速度)
        uv run unpack --update --skip-events

        # --- 音频解包 ---
        # 解包所有音频 (英雄和地图)，使用默认4线程
        uv run unpack --extract

        # 或，使用8个线程解包所有音频
        uv run unpack --extract --max-workers 8

        # 或，只解包所有英雄的音频
        uv run unpack --extract-champions

        # 或，只解包指定ID的英雄
        uv run unpack --extract-champions 555,222
        
        # 或，只解包所有地图的音频
        uv run unpack --extract-maps
        
        # 或，只解包指定ID的地图
        uv run unpack --extract-maps 11,12

        # update和extract可以一起使用
        uv run unpack --update --extract --skip-events
        ```

    *   **方式二: 使用 `python -m` (传统方式)**
        ```bash
        # --- 数据更新 ---
        python -m lol_audio_unpack --update
        python -m lol_audio_unpack --update-champions 1,103,555
        python -m lol_audio_unpack --update-maps 11,12
        python -m lol_audio_unpack --update --skip-events

        # --- 音频解包 ---
        python -m lol_audio_unpack --extract
        python -m lol_audio_unpack --extract-champions 555
        python -m lol_audio_unpack --extract-maps 11
        ```
    
    ##### 注意：在单独更新地图数据时候，如果使用了下列命令，则去重失效
    ```
    # 地图去重依赖于地图ID为0的Common数据，所以如果想正确处理地图数据，建议无论你单独处理哪个地图数据都带上 "0"
    lol_audio_unpack --update-maps 11,12
    ```
    

#### 配置（最简）
新手只需要做一件事：在项目根目录创建 `.lol.env`。

如果你使用 `--dev`，程序会优先读取 `.lol.env.dev`；不存在时回退到 `.lol.env`。

配置优先级（从高到低）：
1. 命令行显式参数（如 `--game-path`、`--output-path`）
2. 系统环境变量（`LOL_*`）
3. `.lol.env` / `.lol.env.dev`
4. 内置默认值

高级用户（CI、容器、远程环境）可直接用环境变量或 CLI 覆盖：

```bash
export LOL_GAME_PATH=/path/to/game
export LOL_OUTPUT_PATH=/path/to/output
uv run unpack --update

# 单次临时覆盖（优先级最高）
uv run unpack --update --game-path /tmp/game --output-path /tmp/out
```

```dotenv
# 游戏客户端根目录 (例如: D:\Games\League of Legends)
LOL_GAME_PATH=''

# 游戏语言区域 (例如: zh_CN, en_US, ko_KR)
LOL_GAME_REGION='zh_CN'

# 数据输出目录
LOL_OUTPUT_PATH=''

# 排除的音频类型 (VO: 语音, SFX: 特效, MUSIC: 音乐)
# 使用英文逗号分割, 留空则全部解包
LOL_EXCLUDE_TYPE='SFX,MUSIC'
```

### Remote 模式（无本地完整客户端）

当你没有本地完整游戏目录，或者运行环境磁盘受限（例如 CI、容器、临时服务器）时，可以使用 **remote 模式**。

remote 模式的核心思路是：
- 使用上游 `RiotManifest` 提供的一对 **已对齐** 的 LCU / GAME manifest
- 先最小化准备 `DataUpdater` 所需的 LCU 资源
- 再按英雄 / 地图单位准备 BIN 和 WAD
- `extract / mapping` 在 remote 模式下会按实体顺序执行，单实体完成后立即清理当前远端 WAD

#### 什么时候适合用
- 没有本地完整客户端，只想临时解包少量英雄 / 地图
- 想在 CI 或远程机器上做一次性更新、解包或映射
- 想把磁盘峰值控制在“单实体所需资源”级别，而不是整批资源总和

#### 什么时候不适合用
- 你已经有本地完整客户端，而且会频繁重复解包
- 你要做大量地图 / 大量 `mapping` 长测
- 你更关心总耗时，而不是磁盘峰值

#### remote 模式当前状态
- 英雄 `update / extract / mapping` 已完成真实远端验证
- 地图 `update` 已完成真实远端验证
- 地图 `mapping` 已确认可运行，但属于长耗时专项验收项
- `mapping` 当前不只处理 `VO`，也会处理 `SFX/MUSIC` 等有事件数据的类别

#### 最小配置

当前 remote 模式主要通过环境变量驱动：

```bash
export LOL_SOURCE_MODE=remote_snapshot
export LOL_REMOTE_VERSION=16.5
export LOL_REMOTE_LCU_MANIFEST_URL="https://..."
export LOL_REMOTE_GAME_MANIFEST_URL="https://..."
export LOL_OUTPUT_PATH="/tmp/lol-remote"
export LOL_GAME_REGION="zh_CN"
```

如果要运行 `mapping`，还需要：

```bash
export LOL_WWISER_PATH="/path/to/wwiser.pyz"
```

#### 常见示例

```bash
# 1. 远端更新指定英雄数据
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555
```

```bash
# 2. 远端更新并解包指定英雄 VO
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555
```

```bash
# 3. 远端更新、解包并构建指定英雄映射
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555 \
  --mapping-champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz"
```

```bash
# 4. 关闭自动清理，保留远端准备产物用于排查
UV_CACHE_DIR=.cache/uv uv run unpack \
  --update-champions 1,103,555 \
  --extract-champions 1,103,555 \
  --mapping-champions 1,103,555 \
  --wwiser-path "/path/to/wwiser.pyz" \
  --no-cleanup-remote
```

#### 清理策略

- 默认开启 `cleanup_remote`
- 全局 `update` 完成后会清理：
  - LCU assets.wad
  - `manifest/<version>/bin_input`
  - `.use_local_bin`
- `extract / mapping` 在 remote 模式下按实体顺序执行
  - 单实体完成后，会清理当前实体的 GAME WAD

如果你要保留现场，请显式使用：

```bash
--no-cleanup-remote
```

#### 磁盘与性能说明

- remote 模式主要优化的是 **磁盘峰值**，不是总耗时
- 当前大文件会优先使用 **硬链接** 进入 `_prepared_game`，失败时回退复制
- `mapping` 的耗时瓶颈主要在 `wwiser` 外部工具
- 地图 `mapping` 通常会明显慢于英雄 `mapping`

更详细的 remote 使用说明见：

- [docs/REMOTE.md](./docs/REMOTE.md)

### 基准测试
项目内置基准脚本：`scripts/benchmark_cli.py`，用于评估 CLI 外部调用的真实耗时与稳定性。

建议直接使用 `uv` 运行基准脚本：

```bash
uv run python scripts/benchmark_cli.py --help
```

#### 基准模式
- `--mode mock`：只跑轻量命令（`--version`、`--help`、无动作参数校验），不依赖本地游戏目录。
- `--mode local_game`：使用本地客户端与输出目录做真实小样本测试。
- `--mode both`：先跑 mock，再跑 local_game。

#### 常用参数
- `--sample-size N`：`local_game` 抽样数量（默认 10）。
- `--max-workers auto|N`：并发数，`auto` 使用 CPU 核心数。
- `--output PATH`：结果 JSON 输出路径。
- `--timeout SEC`：单条命令超时时间。
- `--prepare-update/--no-prepare-update`：
  - 默认 `--prepare-update`：`local_game` 前置执行 `unpack --update`，保证所需 `manifest/<version>/data.*` 可用。
  - 若已准备好数据，可使用 `--no-prepare-update` 跳过更新。
- `--game-path` / `--output-path` / `--wwiser-path`：显式覆盖运行路径，优先级高于环境变量。

#### 示例 1：仅做 mock 自检
```bash
uv run python scripts/benchmark_cli.py \
  --mode mock \
  --output /tmp/bench_mock.json
```

#### 示例 2：local_game 全流程（更新 + 解包 + 映射）
```bash
uv run python scripts/benchmark_cli.py \
  --mode local_game \
  --sample-size 10 \
  --max-workers auto \
  --game-path "/mnt/d/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "/mnt/e/Temp/Scratch/lol" \
  --wwiser-path "/path/to/wwiser.pyz" \
  --output /tmp/bench_local.json
```

#### 示例 3：仅解包音频（不做映射）
方式一（推荐）：直接使用 `unpack` 组合命令。
```bash
uv run unpack \
  --update --skip-events \
  --extract-champions 122,804,62 \
  --max-workers auto \
  --game-path "/mnt/d/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "/mnt/e/Temp/Scratch/lol"
```

方式二（使用 benchmark_cli）：不给有效 `WWISER_PATH`，映射阶段会 `skip`，仅统计解包阶段。
```bash
uv run python scripts/benchmark_cli.py \
  --mode local_game \
  --sample-size 3 \
  --no-prepare-update \
  --wwiser-path "/__not_exists__" \
  --game-path "/mnt/d/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "/mnt/e/Temp/Scratch/lol" \
  --output /tmp/bench_extract_only.json
```

#### 输出说明
结果为 JSON，核心结构：
- `meta`：生成时间、模式、样本规模、并发数。
- `results[]`：每个阶段的执行结果（`status`、`elapsed_sec`、`command`、`stdout_tail`、`stderr_tail`）。

`status` 含义：
- `ok`：阶段执行成功。
- `skip`：前置条件不满足（如缺少路径、缺少 `manifest data`、无有效 `WWISER_PATH`）。
- `fail`：返回码异常或命中关键错误标记。
- `timeout`：阶段超时。

### 设计哲学
-   **速度优先**: 通过简化的处理流程和优化的文件I/O，最大化解包效率。
-   **数据纯粹**: 不对文件进行任何形式的重命名或分类。文件名即ID，保留了数据的原始性，方便后续工具进行二次处理。
-   **责任分离**: 核心解包功能与音频转码等后处理步骤完全解耦。本工具只做一件事：快速解包。

### 性能参考
在典型的开发环境 (SSD, 多核CPU)下，测试数据如下：
- **解包**: 使用4线程解包全部英雄语音，耗时约 **15 秒**。
- **转码**: 将所有解包后的 `.wem` 文件转码为 `.wav`，耗时约 **15 分钟**。

### 后续处理：音频转码
本工具输出的音频文件为 `.wem` 格式。为了方便播放和使用，你可能需要将它们转换为 `.mp3` 或 `.wav` 等常见格式。

我们现在提供了一个**魔改版的 [vgmstream-cli](https://github.com/Virace/vgmstream-cli-build)** 工具，它支持以下增强功能：

1. **目录递归处理**：可以直接指定包含 `.wem` 文件的目录，工具会自动递归扫描并处理所有文件。
2. **增强的输出路径通配符**：
   * `?p`: 代表源文件的完整路径（包含最后的路径分隔符）。
   * `?b`: 代表源文件的基础名称（不含扩展名）。
3. **源文件删除选项**：通过 `-Y` 参数可以在转换成功后删除源文件。**⚠️ 注意：这是一个危险操作，请谨慎使用！**

#### 使用方法
- **命令行直接调用**:
  假设你的音频文件位于 `D:/audios` 目录下：
  ```bash
  # 将所有 .wem 文件转换为 .wav 格式，并保持原始目录结构
  .\vgmstream-cli.exe -o "?p?b.wav" "D:/audios"

  # 转换并删除原始的 .wem 文件（谨慎使用！）
  .\vgmstream-cli.exe -o "?p?b.wav" "D:/audios" -Y
  ```
- **使用测试脚本进行批量转码**:
  项目提供了一个测试脚本，可以方便地进行批量转码并验证结果。
  ```bash
  python tests/test_transcode.py
  ```
  > **注意**: 脚本中的 `vgmstream-cli.exe` 路径是硬编码的。如果你的路径不同，请直接修改 `tests/test_transcode.py` 文件中的路径。

你可以从 [Virace/vgmstream-cli-build](https://github.com/Virace/vgmstream-cli-build/releases) 下载最新版本的魔改工具。

**注意**: 如果你准备将所有提取的英雄语音转码为WAV格式，请确保有足够的硬盘空间。15.14版本所有VO相关WEM音频总共大小接近3G，转码后文件大小接近**40G**。

这种方式将转码与核心逻辑分离，让你可以自由选择是否需要以及如何进行格式转换。

### 维护者
**Virace**
- blog: [孤独的未知数](https://x-item.com)

### 感谢
- [@Morilli](https://github.com/Morilli/bnk-extract), **bnk-extract**
- [@Pupix](https://github.com/Pupix/lol-file-parser), **lol-file-parser**
- [@CommunityDragon](https://github.com/CommunityDragon/CDTB), **CDTB**
- [@vgmstream](https://github.com/vgmstream/vgmstream), **vgmstream**
- 以及**JetBrains**提供开发环境支持

  <a href="https://www.jetbrains.com/?from=kratos-pe" target="_blank"><img src="https://cdn.jsdelivr.net/gh/virace/kratos-pe@main/jetbrains.svg"></a>

### 许可证
[GPLv3](LICENSE)
