# 开发文档

开发环境、代码风格和测试要求见 [PROJECT_STANDARD.md](../../PROJECT_STANDARD.md)。
产品说明、约束和架构分别见 [PRODUCT.md](../../PRODUCT.md)、
[PROJECT_CONSTRAINTS.md](../../PROJECT_CONSTRAINTS.md) 和 [PROJECT_DESIGN.md](../../PROJECT_DESIGN.md)。

## 常用命令

在仓库根目录执行：

```bash
uv sync --extra gui --group gui-test
uv run unpack-gui
uv run unpack --help
uv run ruff check
uv run pytest
```

GUI 行为测试通过 `uv run pytest tests/gui -q` 单独运行；涉及真实客户端的链路也需要显式运行，
不属于默认离线测试。具体范围和命令以项目规范为准。

## 代码结构


- 根包 `lol_audio_unpack`：保留 `setup_app` 与 `__version__` 两个顶层入口。
- 应用编排层：`src/lol_audio_unpack/app/`，负责本地源预检、`AppContext`、`OperationOptions` 与 `LolAudioUnpackApp`。
- 配置层：`src/lol_audio_unpack/config/`，集中维护共享设置 schema 与标准 INI 读写。
- CLI 入口：`src/lol_audio_unpack/cli/`，`unpack` / `mapping` console script 共用同一套动作式解析与调度实现。
- 核心流水线：`src/lol_audio_unpack/unpack/` 负责音频解包，`src/lol_audio_unpack/mapping/` 负责事件映射。
- 运行时支持：`src/lol_audio_unpack/runtime/` 负责 WAD 索引、缓存与独立 WAV 转码 stage。
- 共享模型与数据层：`src/lol_audio_unpack/model/`、`src/lol_audio_unpack/manager/`。
- GUI：`src/lol_audio_unpack/gui/`，当前围绕执行中心、总览与设置页展开。

## 打包与验证

- [CLI 本地打包与验收](cli-packaging.md)
- [基准测试与性能参考](../api/benchmarking_and_performance.md)
- [GUI 共享实体数据刷新](../gui/shared_entity_data_refresh.md)

正式可执行文件还需人工检查启动、路径、真实操作和使用体验；构建成功不能代替这些检查。
