# API 导航与模块视图

## 1. 当前包结构

- 根入口
  - `lol_audio_unpack/__init__.py`
  - `lol_audio_unpack/__main__.py`
- 应用编排
  - `app/context.py`
  - `app/facade.py`
  - `app/local_source.py`
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
  - `unpack/lobby_audio.py`
  - `unpack/stats.py`
- 映射
  - `mapping/entity.py`
  - `mapping/batch.py`
  - `mapping/session.py`
- 运行时支持
  - `runtime/wad_index.py`
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
7. CLI 顶层聚合各阶段 `StageResult`，并从 `RunResult` 映射统一结论与退出码

### 2.2 Python 主链

1. `ctx = setup_app(...)` 或 `ctx = create_app_context(...)`
2. `app = LolAudioUnpackApp(ctx)`
3. 构造 `OperationOptions`
4. 调用 `app.update(...)`、`app.extract(...)`、`app.mapping(...)`

## 3. 输出目录约定

- `manifest/<version>/<region>/data.msgpack`：基础聚合数据（英雄/地图元信息）
- `manifest/<version>/<region>/banks/**`：分类后的 bank 路径及 local v2 resource bindings；物理 WAD 只保存游戏根相对路径
- `manifest/<version>/<region>/events/**`：事件数据
- `audios/<version>/<region>/...`：保留原 ID 的可见 `.wem`
- `audios/_data/**` 与 `audios/_index/<version>/<region>.msgpack`：原始内容对象与归属索引
- `wavs/<version>/<region>/...`：固定位置的 WAV 输出；格式变化时替换同一文件，不保存隐藏派生对象
- `hashes/<version>/<region>/...`：映射结果或整合结果
- `reports/<version>/<region>/...`：解包、转码与汇总报告

管理目录可能通过硬链接共享内容；编辑前先复制到库外或导出独立副本。
搬迁、备份、旧目录一次性迁移和转换复用合同见[资源库说明](./library_api.md)。

## 4. 数据格式约定

`manager.utils.write_data(...)` 在正常和开发模式下均写入 `.msgpack`。
兼容参数 `dev_mode` 不再影响格式；开发模式的独立 INI 和调试日志保持原行为。

写入会先在目标同目录完成序列化与文件同步，再以原子替换发布正式文件，并返回实际目标路径。
序列化、同步或替换失败时抛出 `manager.errors.ArtifactWriteError`；已有正式文件保持原样，
本轮临时文件会尽力清理。
同一基础路径下的其他格式 sibling 不会被自动删除。
该保证只覆盖通过 `manager.utils.write_data(...)` 发布的结构化 artifact；WEM、报告等其他输出
仍遵循各自写入路径，不能据此推断为全项目原子写入。

`manager.utils.read_data(...)` 只读取同一基础路径的 `.msgpack`，不回退旧 YAML/JSON。
缺失返回空字典；损坏或顶层不是字典时抛出 `SharedDataCorruptError`，不当作空库覆盖。
`needs_update(...)` 仅用于可再生元数据，可把损坏识别为需要重新生成。

应用启动的一次性旧目录迁移会读取旧 JSON/YAML 元数据并转为 MessagePack；完成后移除旧位置，
不在正常读取器中增加旧格式或旧路径回退。

只有历史文件、没有游戏源时，可使用独立离线转换入口：

```powershell
uv run scripts/convert_data.py --input old.yml --output data.msgpack --from yml --to msgpack
uv run scripts/convert_data.py --input data.msgpack --output readable.yaml --from msgpack --to yaml
uv run scripts/convert_data.py --input data.msgpack --output readable.json --from msgpack --to json
```

输入、输出和格式必须显式指定。工具不覆盖已有文件，失败不发布正式半成品；YAML 使用安全解析，
保留整数/字符串键与二进制值。JSON 无法保留整数键或二进制值时明确拒绝，改用 YAML。
转换只改变容器格式，不升级 schema；转换完成后仍由正常读取入口验证结构。

当前 banks 文件顶层使用唯一的 `resourceSchemaVersion: 2` 合同。仅比较
`metadata.gameVersion` 不能证明旧 artifact 具备资源绑定；本地 update 会重建旧 schema。

## 5. 延伸文档

- [Python API（分域包与公开入口）](./python_api.md)
- [CLI API（命令行参数与执行语义）](./cli_api.md)
- [配置与上下文 API](./config_api.md)
- [解包与映射 API（核心流水线）](./pipeline_api.md)
- [已准备本地数据源合同](./prepared_source.md)
- [基准测试与性能参考](./benchmarking_and_performance.md)
