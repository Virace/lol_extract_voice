# 文档导航

本文档集合只描述当前分支的最新结构、入口和运行语义。

## 1. 快速入口

- [根目录 README（快速上手、GUI/CLI、配置文件示例）](../README.md)
- [示例配置文件](../config/lol-audio-unpack.example.ini)
- [API 总览](./API.md)
- [Python API（分域包与公开入口）](./api/python_api.md)
- [CLI 参数与执行语义](./api/cli_api.md)
- [配置与上下文 API](./api/config_api.md)
- [解包与映射 API](./api/pipeline_api.md)
- [Remote 模式（运行与接入）](./api/remote_mode.md)
- [基准测试与性能参考](./api/benchmarking_and_performance.md)
- [GUI 共享实体数据刷新说明](./gui/shared_entity_data_refresh.md)

## 2. 当前代码结构

- 根包：`src/lol_audio_unpack/__init__.py`、`src/lol_audio_unpack/__main__.py`
- 应用编排：`src/lol_audio_unpack/app/`
- 配置与 INI：`src/lol_audio_unpack/config/`
- CLI：`src/lol_audio_unpack/cli/`
- 解包：`src/lol_audio_unpack/unpack/`
- 映射：`src/lol_audio_unpack/mapping/`
- 运行时支持：`src/lol_audio_unpack/runtime/remote/`、`src/lol_audio_unpack/runtime/wav/`
- 数据准备与读取：`src/lol_audio_unpack/manager/`
- 共享实体模型：`src/lol_audio_unpack/model/`
- GUI：`src/lol_audio_unpack/gui/`
- 通用工具：`src/lol_audio_unpack/utils/`

## 3. GUI 当前状态

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 执行解包 | 已完成 | 当前 GUI 可创建并执行音频解包任务。 |
| WAV 转码 | 已完成 | 当前 GUI 可在任务中启用独立 WAV 转码 stage。 |
| 生成映射 | 已完成 | 当前 GUI 可创建并执行映射任务。 |
| 查看映射 | 已完成 | 当前 GUI 已具备映射结果查看链路。 |
| 音频试听 | 已完成 | 实体总览提供“事件 / 全部音频 / 原始数据”三种预览；缺少事件映射时仍可按 WEM 相对路径试听、导出 WAV 和打开位置。 |
| 新手引导 | 已完成 | 首次启动会引导用户完成设置、执行中心与总览页基础认知。 |
| 环境状态 | 已完成 | 首页用图标与语义色区分准备中、已就绪、待配置和失败状态。 |

GUI 保留四个独立标签页的职责。执行中心仍在同一页面完成批量任务配置：英雄和地图 ID 都留空时
处理全部英雄与地图；任意一项填写后，只处理已输入的 ID。实体总览继续使用左侧实体列表和右侧
具体信息，并用 `A` / `M` 分别表示音频产物和事件映射产物。事件映射存在时默认显示事件树；尚未生成映射时会默认显示全部已解包音频，同一 WEM ID 的不同路径会作为独立条目保留。

## 4. Remote 模式

Remote 模式适合：

- 没有本地完整游戏客户端
- 运行环境磁盘受限（CI、容器、临时服务器）
- 只想处理少量英雄 / 地图

Remote 模式的当前主线：

- 使用上游 `RiotManifest` 提供的一对已对齐 LCU / GAME manifest
- `update` 先全局执行一次
- `extract / mapping` 通过 `LolAudioUnpackApp.run_workflow(...)` 按实体顺序执行
- 单实体完成后会清理当前远端 WAD
- remote 模式主要优化磁盘峰值，不优化总耗时

详细说明见：

- [Remote 模式（运行与接入）](./api/remote_mode.md)

## 5. 基准测试与性能参考

项目内置基准脚本：`scripts/benchmark_cli.py`。

核心口径：

- `--mode single_vo` 测量单英雄 VO 更新与解包
- `--mode full_extract` 测量全量更新与解包
- `--runner cli|api|both` 用于比较两种项目入口
- benchmark 只记录性能，不替代正确性或系统测试

详细参数、示例命令、输出结构与历史性能参考见：

- [基准测试与性能参考](./api/benchmarking_and_performance.md)

## 6. 设计哲学

- **速度优先**：通过简化流程和优化 I/O，尽量提升解包效率。
- **数据纯粹**：不对输出文件做重命名或分类，文件名即游戏数据中的原始 ID。
- **责任分离**：核心能力专注于更新、解包、WAV 转码与映射；更复杂的后处理继续保持解耦。
