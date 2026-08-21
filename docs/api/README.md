# API 导航与模块视图

## 1. 当前包结构

- 根入口
  - `lol_audio_unpack/__init__.py`
  - `lol_audio_unpack/__main__.py`
- 应用编排
  - `app/context.py`
  - `app/facade.py`
  - `app/remote.py`
  - `app/results.py`
  - `app/types.py`
- 配置与 INI
  - `config/schema.py`
  - `config/ini.py`
- CLI
  - `cli/cli.py`
  - `cli/parser.py`
  - `cli/runtime.py`
  - `cli/dispatch.py`
  - `cli/invocation.py`
- 数据准备与读取
  - `manager/data_updater.py`
  - `manager/bin_updater.py`
  - `manager/data_reader.py`
- 共享模型
  - `model/entity.py`
  - `model/binding.py`
- 解包
  - `unpack/entity.py`
  - `unpack/batch.py`
  - `unpack/bp_vo.py`
  - `unpack/stats.py`
- 映射
  - `mapping/entity.py`
  - `mapping/batch.py`
  - `mapping/session.py`
- 运行时支持
  - `runtime/wad_index.py`
  - `runtime/remote/preparer.py`
  - `runtime/wav/job.py`
  - `runtime/wav/transcode.py`
  - `runtime/wav/_runtime.py`
- GUI
  - `gui/`

## 2. 典型调用链

### 2.1 CLI 主链

1. `unpack` / `mapping` console script 进入 `lol_audio_unpack.cli.cli:main`
2. `cli.parser.create_parser(...)` 解析动作与共享参数
3. `cli.runtime._apply_config_profile(...)` 注入 `-c` 配置文件内容
4. `cli.runtime.validate_args(...)` 校验动作组合与参数边界
5. `cli.runtime.initialize_app(...)` 构建 `AppContext`
6. `LolAudioUnpackApp` 执行 `update / extract / wav / mapping`
7. remote 模式下，若存在 `extract` 或 `mapping`，改走 `LolAudioUnpackApp.run_workflow(...)`
8. CLI 顶层从 `RunResult` 映射统一结论与退出码

### 2.2 Python 主链

1. `ctx = setup_app(...)` 或 `ctx = create_app_context(...)`
2. `app = LolAudioUnpackApp(ctx)`
3. 构造 `OperationOptions`
4. 调用 `app.update(...)`、`app.extract(...)`、`app.mapping(...)`
5. remote 模式下按实体拆批时，调用 `app.build_work_items(...)` 或 `app.run_workflow(...)`

## 3. 输出目录约定

- `manifest/<version>/data.*`：基础聚合数据（英雄/地图元信息）
- `manifest/<version>/banks/**`：分类后的 bank 路径及 local v2 resource bindings；物理 WAD 只保存游戏根相对路径
- `manifest/<version>/events/**`：事件数据
- `manifest/<version>/bin_input/**`：remote 模式为 `BinUpdater` 准备的稀疏 BIN 输入
- `audios/<version>/...`：解包出的 `.wem`
- `wavs/<version>/...`：独立 `WAV 转码` stage 输出
- `hashes/<version>/...`：映射结果或整合结果
- `reports/<version>/...`：解包、转码与汇总报告
- `cache/remote/**`：remote 模式下载缓存
- `_prepared_game/**`：remote 模式最小运行环境

## 4. 数据格式约定

`manager.utils.write_data(...)` 会根据模式决定写入格式：

- 开发模式：优先写 `.yml`
- 非开发模式：优先写 `.msgpack`

写入会先在目标同目录完成序列化与文件同步，再以原子替换发布正式文件，并返回实际目标路径。
序列化、同步或替换失败时抛出 `manager.errors.ArtifactWriteError`；已有正式文件保持原样，
本轮临时文件会尽力清理。
同一基础路径下的其他格式 sibling 不会被自动删除。
该保证只覆盖通过 `manager.utils.write_data(...)` 发布的结构化 artifact；WEM、报告、远端下载
payload 等其他输出仍遵循各自写入路径，不能据此推断为全项目原子写入。

`manager.utils.read_data(...)` 会按优先级自动寻找可读文件。

`local_path` 的 banks 文件顶层使用 `resourceSchemaVersion: 2`。仅比较
`metadata.gameVersion` 不能证明旧 artifact 具备资源绑定；本地 update 会重建旧 schema。
`remote_snapshot` 暂时保留 v1 投影合同。

## 5. 延伸文档

- [Python API（分域包与公开入口）](./python_api.md)
- [CLI API（命令行参数与执行语义）](./cli_api.md)
- [配置与上下文 API](./config_api.md)
- [解包与映射 API（核心流水线）](./pipeline_api.md)
- [Remote 模式（运行与接入）](./remote_mode.md)
- [基准测试与性能参考](./benchmarking_and_performance.md)
