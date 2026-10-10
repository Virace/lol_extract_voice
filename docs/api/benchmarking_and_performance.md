# 基准测试与性能参考

## 1. 定位

`scripts/benchmark_cli.py` 测量真实本地客户端的 `update -> extract` 链路，可分别走控制台、
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
- `--runner cli|api|both`：选择外部控制台、应用 API，或依次执行两种入口。

`--prepare-update` 默认启用。只有目标输出目录已具备匹配当前客户端版本的 manifest 时，
才应使用 `--no-prepare-update`。

### 源码树与 baseline

| 参数或入口 | 规则 |
| --- | --- |
| `--source-root` | 默认当前仓库，控制台子进程将 `<source-root>/src` 放在 `PYTHONPATH` 首位 |
| 外部 baseline | 可用 `git archive` 副本，继续使用当前解释器与依赖，无需切换分支 |
| `--source-label baseline` | 在 JSON 中标记比较对象 |
| runner 限制 | 外部源码树仅支持控制台；API 在当前进程导入，拒绝误标为外部 baseline |

## 3. 示例

### 单英雄 VO

```powershell
uv run python scripts/benchmark_cli.py `
  --mode single_vo `
  --runner cli `
  --game-path "<game-path>" `
  --output-path ".temp/benchmark-output"
```

### 全量解包并比较控制台与 API

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

### 报告字段

结果默认保存到 `.temp/benchmarks/latest.json`，`--output` 可指定其他位置。

| 字段 | 记录内容 |
| --- | --- |
| `results` | 每阶段 runner、scenario、step、状态、耗时、WEM 数量/字节、控制台 RSS 峰值与日志路径 |
| `summaries` | update、extract、end-to-end 耗时，最终 WEM 数量/字节与场景最高 RSS |
| meta 与 summary | 均包含 `source_label`、`source_root` |
| 无法读取的 RSS | 写入 `null`，不伪造为零 |

**RSS 口径：** Windows 通过标准库调用系统 API 采样工作集，聚合命令根进程及后代。
外层 `uv run python` 默认由当前 Python 直接启动生产子进程；改用 `--uv-entry` launcher
会扩大采样树与启动开销，不应混合比较。

### targeted 资源索引指标

| 来源 | 汇总规则 |
| --- | --- |
| v2 banks `diagnostics.index` | 读取 `candidateWads`、`cacheHits`、`cacheMisses`、`tocSeconds`，采用同一 update 进程的最大累计快照，不逐实体相加 |
| baseline v1 缺诊断 | 标记 `resource_index.status: unavailable`，仍可用同一脚本和目标参数比较 |
| current v2 | 额外记录 `uniqueTocLoads`、`duplicatePhysicalWadLoads`，核对单次运行同 WAD stat key 不重复构造 |

> `fail` 和 `timeout` 是基准执行失败，不表示测试跳过或通过。

## 4. 主要参数

- `--max-workers auto|N`：并发 worker 数。
- `--timeout SEC`：单个控制台子进程的超时。
- `--skip-events/--no-skip-events`：控制更新阶段是否处理事件。
- `--no-lobby-audio`：关闭默认附带的大厅音频。
- `--single-vo-exclude-type`：单英雄场景默认排除 `SFX,MUSIC`。
- `--full-extract-exclude-type`：全量场景默认不排除音频类型。
- `--target-champions`：targeted 英雄场景的逗号分隔 ID。
- `--target-maps`：targeted 地图场景的逗号分隔 ID；update 阶段自动补充地图 `0`。
- `--targeted-exclude-type`：targeted 场景默认不排除音频类型。
- `--source-root`：控制台子进程优先导入的源码树；其 `src` 目录必须存在，仅支持控制台 runner。
- `--source-label`：写入 JSON meta 与每条 summary 的源码标签。
- `--log-level`：benchmark 执行日志级别。

已安装客户端与外部准备目录都通过 `--game-path` 交给同一个 benchmark。脚本只消费本地资源，
不会下载缺失文件；外部准备器的下载耗时与缓存效率不属于本项目基准口径。

## 5. 历史数据

### 解包阶段的比较口径

1. 先准备并冻结同一份 manifest，在不同空输出目录中用相同客户端、音频类型、worker 配额运行 extract，排除首次准备与 WAV 转码。
2. 比较耗时、文件数、字节数及各相对路径的内容摘要，数量相同不能单独证明正确。
3. 单线程分段计时定位 WAD 提取、容器解析和 WEM 写出；多线程各文件时间存在重叠，累计值不能当墙钟耗时。未主动清空系统文件缓存时说明该边界。

| v2 解包执行 | 边界 |
| --- | --- |
| 读取与复用 | 整批读取目标 BNK/WPK，同实体复用物理容器解析结果，最后一次使用后释放 |
| 目录准备 | 按实际输出路径准备父目录一次 |
| WEM 写并发 | 少量实体可使用空余 worker 配额；容器顺序不变，重名 WEM 串行，保留首次成功写入与重试语义 |
| WAD 读取锁 | 上游无共享读取能力时使用每 WAD 独立兼容锁；声明 `thread_safe_reads=True` 后由上游负责，不额外锁住解压和输出 |

### 历史结果

仓库中的历史耗时只能作为旧机器、旧客户端版本与旧依赖组合下的参考，不构成 SLA。比较优化
前后结果时，应固定客户端版本、输出盘、runner、场景、worker 数和事件处理选项，并保留同一
口径的 JSON 报告。
