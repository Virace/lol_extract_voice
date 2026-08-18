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
- `--runner cli|api|both`：选择外部 CLI、应用 API，或依次执行两种入口。

`--prepare-update` 默认启用。只有目标输出目录已具备匹配当前客户端版本的 manifest 时，
才应使用 `--no-prepare-update`。

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

结果默认写入 `.temp/benchmarks/latest.json`；可通过 `--output` 覆盖。每个阶段记录 runner、
scenario、step、状态、耗时、产物统计及对应日志路径。`fail` 或 `timeout` 是基准执行失败，
不能解释为测试跳过或通过。

## 4. 主要参数

- `--max-workers auto|N`：并发 worker 数。
- `--timeout SEC`：单个 CLI 子进程的超时。
- `--skip-events/--no-skip-events`：控制更新阶段是否处理事件。
- `--with-bp-vo/--no-with-bp-vo`：显式覆盖 BP VO。
- `--single-vo-exclude-type`：单英雄场景默认排除 `SFX,MUSIC`。
- `--full-extract-exclude-type`：全量场景默认不排除音频类型。
- `--log-level`：benchmark 执行日志级别。

Remote 快照有独立的 `scripts/benchmark_remote_live.py`，默认会访问 Riot live manifest，
并可准备 wwiser；它同样不是 CI 或 pytest 门禁。remote 模式优化的是磁盘峰值，而非总耗时。

## 5. 历史数据

仓库中的历史耗时只能作为旧机器、旧客户端版本与旧依赖组合下的参考，不构成 SLA。比较优化
前后结果时，应固定客户端版本、输出盘、runner、场景、worker 数和事件处理选项，并保留同一
口径的 JSON 报告。
