# 开发文档

| 内容 | 权威文档 |
| --- | --- |
| 环境、代码风格与测试要求 | [项目规范](../../PROJECT_STANDARD.md) |
| 产品定位 | [产品说明](../../PRODUCT.md) |
| 约束 | [项目约束](../../PROJECT_CONSTRAINTS.md) |
| 架构与页面设计 | [设计说明](../../PROJECT_DESIGN.md) |

## 常用命令

在仓库根目录执行：

```bash
uv sync --extra gui --group gui-test
uv run unpack-gui
uv run unpack --help
uv run ruff check
uv run pytest
```

界面行为测试通过 `uv run pytest tests/gui -q` 单独运行；涉及真实客户端的链路也需要显式运行，
不属于默认离线测试。具体范围和命令以项目规范为准。

## 代码结构


- 根包 `lol_audio_unpack`：保留 `setup_app` 与 `__version__` 两个顶层入口。
- 应用编排层：`src/lol_audio_unpack/app/`，负责本地源预检、`AppContext`、`OperationOptions` 与 `LolAudioUnpackApp`。
- 配置层：`src/lol_audio_unpack/config/`，集中维护共享设置 schema 与标准 INI 读写。
- 控制台入口：`src/lol_audio_unpack/cli/`，`unpack` / `mapping` console script 共用同一套动作式解析与调度实现。
- 核心流水线：`src/lol_audio_unpack/unpack/` 负责音频解包，`src/lol_audio_unpack/mapping/` 负责事件映射。
- 运行时支持：`src/lol_audio_unpack/runtime/` 负责 WAD 索引、缓存与独立 WAV 转码 stage。
- 共享模型与数据层：`src/lol_audio_unpack/model/`、`src/lol_audio_unpack/manager/`。
- 界面：`src/lol_audio_unpack/gui/`，当前围绕执行中心、总览与设置页展开。

## 打包与验证

- [音频 ID 与内容实测](../research/historical-wem.md)：历史换号证据与当前内容共享方式
- [界面任务与导出规则](gui-tasks-and-exports.md)：选择确认、任务快照、分类回退与共享边界
- [本地数据源验证合同](prepared-source-contract.md)：输入预检、精确资源绑定与旧配置迁移
- [文档网站维护](doc-site.md)：在 `docs/` 独立运行 VitePress，复用仓库 Markdown
- [控制台本地打包与验收](cli-packaging.md)
- [基准测试与性能参考](../api/benchmarking_and_performance.md)
- [界面共享实体数据刷新](../gui/shared_entity_data_refresh.md)

正式可执行文件还需人工检查启动、路径、真实操作和使用体验；构建成功不能代替这些检查。

## 自动化使用

Agent 或脚本按用户要求选择动作：整实体音频可直接执行 `update extract wav`；需要筛选事件时，
先查询映射，再按所选文件独立转码。沿用默认处理范围和输出结构，额外筛选、重命名或整理须有用户要求。
完成后报告结果位置和未完成项。命令见 [控制台使用说明](../cli-package.md)。
