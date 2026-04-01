# 基准测试与性能参考

本文档承接 `README.md` 中下沉的详细内容，集中说明 `scripts/benchmark_cli.py` 的使用方式，以及当前仓库对 remote 模式和整体性能的参考口径。

## 1. 基准脚本定位

项目内置基准脚本：`scripts/benchmark_cli.py`。

建议直接使用 `uv` 运行：

```bash
uv run scripts/benchmark_cli.py --help
```

它适用于：

- 评估 CLI 外部调用的真实耗时与稳定性
- 做轻量 mock 自检
- 在本地完整客户端环境下做小样本链路测量

## 2. 基准模式

- `--mode mock`
  - 只跑轻量命令（`--version`、`--help`、无动作参数校验）
  - 不依赖本地游戏目录
- `--mode local_game`
  - 使用本地客户端与输出目录做真实小样本测试
- `--mode both`
  - 先跑 mock，再跑 local_game

## 3. 常用参数

- `--sample-size N`
  - `local_game` 抽样数量，默认 `10`
- `--max-workers auto|N`
  - 并发数；`auto` 使用 CPU 核心数
- `--output PATH`
  - 结果 JSON 输出路径
- `--timeout SEC`
  - 单条命令超时时间
- `--prepare-update/--no-prepare-update`
  - 默认 `--prepare-update`
  - `local_game` 前置执行 `unpack --update`，保证所需 `manifest/<version>/data.*` 可用
  - 若已准备好数据，可使用 `--no-prepare-update` 跳过更新
- `--game-path` / `--output-path` / `--wwiser-path`
  - 显式覆盖运行路径，优先级高于环境变量

## 4. 常见示例

### 4.1 仅做 mock 自检

```bash
uv run scripts/benchmark_cli.py \
  --mode mock \
  --output /tmp/bench_mock.json
```

### 4.2 local_game 全流程（更新 + 解包 + 映射）

```bash
uv run scripts/benchmark_cli.py \
  --mode local_game \
  --sample-size 10 \
  --max-workers auto \
  --game-path "/mnt/d/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "/mnt/e/Temp/Scratch/lol" \
  --wwiser-path "/path/to/wwiser.pyz" \
  --output /tmp/bench_local.json
```

### 4.3 仅解包音频（不做映射）

方式一：直接使用动作式 CLI。

```bash
uv run unpack update \
  --skip-events \
  --max-workers auto \
  --game-path "/mnt/d/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "/mnt/e/Temp/Scratch/lol"

uv run unpack extract \
  --champions 122,804,62 \
  --max-workers auto \
  --game-path "/mnt/d/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "/mnt/e/Temp/Scratch/lol"
```

方式二：使用 `benchmark_cli`，不给有效 `WWISER_PATH`，让映射阶段 `skip`。

```bash
uv run scripts/benchmark_cli.py \
  --mode local_game \
  --sample-size 3 \
  --no-prepare-update \
  --wwiser-path "/__not_exists__" \
  --game-path "/mnt/d/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "/mnt/e/Temp/Scratch/lol" \
  --output /tmp/bench_extract_only.json
```

## 5. 输出说明

结果为 JSON，核心结构：

- `meta`
  - 生成时间、模式、样本规模、并发数
- `results[]`
  - 每个阶段的执行结果
  - 关键字段包括 `status`、`elapsed_sec`、`command`、`stdout_tail`、`stderr_tail`

`status` 含义：

- `ok`
  - 阶段执行成功
- `skip`
  - 前置条件不满足，例如缺少路径、缺少 `manifest data`、无有效 `WWISER_PATH`
- `fail`
  - 返回码异常或命中关键错误标记
- `timeout`
  - 阶段超时

## 6. Remote 模式性能口径

remote 模式当前的性能解释应按下面这组原则理解：

- remote 模式主要优化的是 **磁盘峰值**，不是总耗时
- 大文件会优先使用 **硬链接** 进入 `_prepared_game`，失败时回退复制
- `mapping` 的主要耗时瓶颈通常在 `wwiser` 外部工具
- 地图 `mapping` 往往会比英雄 `mapping` 更慢
- 地图链路中的长耗时回归，当前仍作为专项验收项保留

remote 模式的详细运行语义、最小配置和 Python API 调用方式见：

- [Remote 模式（运行与接入）](./remote_mode.md)

## 7. 历史性能参考

以下数据仅作为历史参考，不应视为固定 SLA：

- 在典型开发环境（SSD、多核 CPU）下
  - 使用 4 线程解包全部英雄语音，耗时约 **15 秒**
- 若将所有解包后的 `.wem` 文件进一步转码为 `.wav`
  - 整体耗时约 **15 分钟**

对转码链路还需要额外注意：

- 若准备将全部英雄语音转码为 WAV，请预留足够磁盘空间
- 15.14 版本全部 VO 相关 WEM 体积接近 `3G`
- 转码后总体积接近 **40G**
