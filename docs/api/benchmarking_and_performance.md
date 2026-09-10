# 基准测试与性能参考

## 1. 定位

`scripts/benchmark_cli.py` 测量真实本地客户端的 `update -> extract` 链路，可分别走 CLI、
Python API，或在相同参数下依次执行两者。它是性能工具，不代替 pytest 正确性门禁。

```powershell
uv run python scripts/benchmark_cli.py --help
```

脚本要求显式传入游戏目录与输出目录，不提供不访问客户端的 mock 模式。

## 2. 模式与运行入口

- `--mode single_vo`：测量一个英雄的 VO 更新与解包；未传 `--single-vo-id` 时从 manifest
  选择代表英雄。
- `--mode full_extract`：测量当前配置范围内的全量更新与解包。
- `--mode both`：在同一个 runner 下依次执行以上两个场景。
- `--mode targeted`：分别测量显式英雄和显式地图范围的 `update -> extract`。至少传入
  `--target-champions` 或 `--target-maps` 之一；地图更新会自动加入公共地图 `0`，但解包只
  包含用户指定的地图。
- `--runner cli|api|both`：选择外部 CLI、应用 API，或依次执行两种入口。

`--prepare-update` 默认启用。只有目标输出目录已具备匹配当前客户端版本的 manifest 时，
才应使用 `--no-prepare-update`。

`--source-root` 默认当前仓库；CLI 子进程会将 `<source-root>/src` 放在 `PYTHONPATH` 首位。
这允许将 baseline 的 `git archive` 副本作为源码树、继续使用当前解释器与已安装依赖，而无需
切换分支。使用 `--source-label baseline` 等标签可在 JSON 中标识比较对象。外部源码树只支持
`--runner cli`；API runner 在当前进程导入代码，脚本会拒绝把它误标为外部 baseline。

## 3. 示例

### 单英雄 VO

```powershell
uv run python scripts/benchmark_cli.py `
  --mode single_vo `
  --runner cli `
  --game-path "<game-path>" `
  --output-path ".temp/benchmark-output"
```

### 全量解包并比较 CLI 与 API

```powershell
uv run python scripts/benchmark_cli.py `
  --mode full_extract `
  --runner both `
  --max-workers auto `
  --game-path "<game-path>" `
  --output-path ".temp/benchmark-output"
```

### 显式英雄与地图范围（用于 baseline/current 对比）

```powershell
uv run python scripts/benchmark_cli.py `
  --mode targeted `
  --runner cli `
  --target-champions "1,103" `
  --target-maps "11" `
  --max-workers 4 `
  --game-path "<game-path>" `
  --output-path ".temp/benchmark-output"
```

结果默认写入 `.temp/benchmarks/latest.json`；可通过 `--output` 覆盖。`results` 保留每个阶段的
runner、scenario、step、状态、耗时、WEM 数量/字节数、CLI 子进程采样 RSS 峰值及对应日志路径；
`summaries` 汇总 update、extract 和 end-to-end 耗时，以及最终 WEM 数量/字节数和场景最高 RSS。
Windows 使用标准库调用系统 API 采样工作集；无法读取的运行环境写入 `null`，不会伪造为零。
每份 meta 和 summary 均记录 `source_label` 与 `source_root`。
脚本在外层 `uv run python` 中默认直接使用当前 Python 启动生产子进程，
这是 RSS 对比的固定口径；Windows RSS 采样会聚合命令根进程及其后代。显式把
`--uv-entry` 改为 launcher 会扩大采样进程树与启动开销，不应与默认口径混合比较。

targeted 汇总还读取 local resource schema v2 的 banks `diagnostics.index`，记录
`candidateWads`、`cacheHits`、`cacheMisses`、`tocSeconds` 等指标。它们是同一 update 进程的
累计快照，汇总采用最大快照而非逐实体相加。baseline v1 artifact 没有该诊断时会标记
`resource_index.status: unavailable`，可与 current 使用同一脚本和目标参数驱动比较。
current v2 还记录 `uniqueTocLoads` 与 `duplicatePhysicalWadLoads`，以直接验证同一
WAD stat key 在单次运行中不被重复构造。
`fail` 或 `timeout` 是基准执行失败，不能解释为测试跳过或通过。

## 4. 主要参数

- `--max-workers auto|N`：并发 worker 数。
- `--timeout SEC`：单个 CLI 子进程的超时。
- `--skip-events/--no-skip-events`：控制更新阶段是否处理事件。
- `--with-bp-vo/--no-with-bp-vo`：显式覆盖 BP VO。
- `--single-vo-exclude-type`：单英雄场景默认排除 `SFX,MUSIC`。
- `--full-extract-exclude-type`：全量场景默认不排除音频类型。
- `--target-champions`：targeted 英雄场景的逗号分隔 ID。
- `--target-maps`：targeted 地图场景的逗号分隔 ID；update 阶段自动补充地图 `0`。
- `--targeted-exclude-type`：targeted 场景默认不排除音频类型。
- `--source-root`：CLI 子进程优先导入的源码树；其 `src` 目录必须存在，仅支持 CLI runner。
- `--source-label`：写入 JSON meta 与每条 summary 的源码标签。
- `--log-level`：benchmark 执行日志级别。

已安装客户端与外部准备目录都通过 `--game-path` 交给同一个 benchmark。脚本只消费本地资源，
不会下载缺失文件；外部准备器的下载耗时与缓存效率不属于本项目基准口径。

## 5. 历史数据

### 解包阶段的比较口径

比较纯解包优化时，先准备并冻结同一份 manifest，在不同空输出目录中使用相同客户端、
音频类型和 worker 配额运行 extract，排除首次资源准备和 WAV 转码。
除耗时、文件数和字节数外，应比较各相对路径对应的内容摘要，不能仅用数量相同证明正确。
单线程分段计时可以定位 WAD 提取、容器解析和 WEM 写出；多线程下各文件耗时相加包含重叠时间，
不能把这个累计值当成阶段墙钟耗时。系统文件缓存未主动清空时应说明该边界。

当前 v2 解包仍整批读取目标 BNK/WPK。同一物理容器在实体内复用解析结果，最后一次使用后释放；
父目录按实际输出路径准备一次。少量实体可以将空余 worker 配额用于容器内 WEM 并发写出，
容器之间保持原顺序，同容器重名 WEM 回到串行处理，保留首次成功写入与失败重试语义。
已发布上游不支持共享读取时，应用使用每个 WAD 对象独立的兼容锁；上游明确声明
`thread_safe_reads=True` 后由上游负责读取锁，避免再锁住其解压与输出。

### 历史结果

仓库中的历史耗时只能作为旧机器、旧客户端版本与旧依赖组合下的参考，不构成 SLA。比较优化
前后结果时，应固定客户端版本、输出盘、runner、场景、worker 数和事件处理选项，并保留同一
口径的 JSON 报告。
