# 文档导航

本文档集合只描述当前分支的最新结构、入口和运行语义。

## 1. 快速入口

- [根目录 README（快速上手、GUI/CLI、配置文件示例）](../README.md)
- [产品定位与优化方向](../PRODUCT.md)
- [GUI 连续性约束](../PROJECT_CONSTRAINTS.md#gui-连续性)
- [页面职责与视觉基线](../PROJECT_DESIGN.md#页面与视觉基线)
- [示例配置文件](../config/lol-audio-unpack.example.ini)
- [API 总览](./API.md)
- [Python API（分域包与公开入口）](./api/python_api.md)
- [CLI 参数与执行语义](./api/cli_api.md)
- [配置与上下文 API](./api/config_api.md)
- [解包与映射 API](./api/pipeline_api.md)
- [已准备本地数据源合同](./api/prepared_source.md)
- [基准测试与性能参考](./api/benchmarking_and_performance.md)
- [GUI 共享实体数据刷新说明](./gui/shared_entity_data_refresh.md)

## 2. 当前代码结构

- 根包：`src/lol_audio_unpack/__init__.py`、`src/lol_audio_unpack/__main__.py`
- 应用编排：`src/lol_audio_unpack/app/`
- 配置与 INI：`src/lol_audio_unpack/config/`
- CLI：`src/lol_audio_unpack/cli/`
- 解包：`src/lol_audio_unpack/unpack/`
- 映射：`src/lol_audio_unpack/mapping/`
- 运行时支持：`src/lol_audio_unpack/runtime/wad_index.py`、`src/lol_audio_unpack/runtime/wav/`
- 数据准备与读取：`src/lol_audio_unpack/manager/`
- 共享实体模型：`src/lol_audio_unpack/model/`
- GUI：`src/lol_audio_unpack/gui/`
- 通用工具：`src/lol_audio_unpack/utils/`

## 3. GUI 当前状态

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 执行解包 | 已实现 | 当前 GUI 可创建并执行音频解包任务。 |
| WAV 转码 | 已实现，有范围限制 | 英雄与地图任务可启用独立 WAV stage；本地资源包不支持该批量 stage。 |
| 生成映射 | 已实现 | 当前 GUI 可创建并执行映射任务。 |
| 查看映射 | 已实现 | 当前 GUI 已具备映射结果查看链路。 |
| 音频试听 | 已实现 | 实体总览提供“事件 / 全部音频 / 原始数据”三种预览；缺少事件映射时仍可按 WEM 相对路径试听、导出 WAV 和打开位置。 |
| 所选音频导出 | 已实现 | 当前单个实体内选择已有 WEM，支持目录全选、节点、排除项、撤销与导出核对；不跨实体累积。 |
| 任务结果与失败重试 | 已实现 | 居中常驻通知与可恢复的覆盖式详情，保留执行快照与原失败事实；按文件、容器、实体或阶段明确核对重试范围。 |
| 本地资源包 | 已实现 | 总览的“特殊内容”可显式选择并后台扫描多个本地 FINAL `.wad.client`，再将已发现资源包送入执行中心。 |
| 新手引导 | 已实现 | 首次启动会引导用户完成设置、执行中心与总览页基础认知。 |
| 环境状态 | 已实现 | 默认只准备基础目录，所选任务按需准备资源；可开启提前准备。页面共用 typed readiness，只有 ready 可创建任务。 |
| 多任务队列、暂停与续跑 | 未开放 | 执行中心当前使用单任务模式；暂停/恢复未落地，取消存在强制终止路径，不承诺可续跑。 |

上表描述代码能力，不等同于正式发布验收。GUI 启动、视觉质量、不同缩放比例和完整真实链路仍按
`PROJECT_STANDARD.md` 保留人工验收门禁。

GUI 以主页、执行中心、实体总览组织主流程，装备查询提供辅助线索，全局设置和关于保留独立职责。
当前选择导出与失败重试保持主要页面结构；语义查找、暂停和跨会话恢复仍属于候选能力，
不应按规划当成现有功能。执行中心仍在同一页面完成批量任务配置：英雄和地图 ID 都留空时
处理全部英雄与地图；任意一项填写后，只处理已输入的 ID。实体总览使用“英雄 / 地图 / 特殊内容”三类
左侧目录和右侧具体信息，并用 `A` / `M` 分别表示音频产物和事件映射产物。结构化特殊内容在统一列表行中标识“经典召唤师峡谷、
末日人机、无尽狂潮”等模式，普通英雄目录不会重复这些条目；发送到执行中心后仍按对应英雄数值 ID 执行。
特殊内容直接使用当前 `game_path` 的本地资源。事件映射存在时默认显示事件树；
尚未生成映射时会默认显示全部已解包音频，同一 WEM ID 的不同路径会作为独立条目保留。大型实体的全量 WEM
在首次进入“全部音频”时后台加载并使用分批布局；列表上方的上下文行显示计数进度，离开总览页后只继续填充缓存，不构建
隐藏列表。返回同一实体时复用已加载的事件树与全部音频模型，不再次装填数万条记录。事件预览只解析 mapping
实际引用的路径，不预先重置隐藏列表。

事件与全部音频沿用透明背景和统一首行起点，列表保留适度水平内收；左右列表在底部分隔线处裁切，
平滑滚动时允许末行部分可见，分隔线与按钮之间保持独立留白。

本地资源包不是自动全盘扫描：在搜索栏旁更多菜单中使用“扫描本地 WAD…”，只选择当前游戏
`Game/DATA/FINAL` 下需要处理的 `.wad.client`。扫描在后台执行，目录会显示每个已持久化资源包的来源、
命名空间、发现状态和 `A` / `M` 输出状态；解包产物位于 `audios/<version>/resource_packs/`，映射位于
`hashes/<version>/resource_packs/`。资源包当前不支持执行中心的整实体 WAV stage；已经解包的 WEM
可以在总览中试听和选择导出，即使映射尚未生成也可从“全部音频”进入。

## 4. 已准备本地数据源

程序只消费 `game_path` 指向的本地目录。该目录可以是已安装客户端，也可以由外部工具预先准备；
两者使用同一结构预检、update 与 resource schema v2 流程。

最小共享结构包括：

- `Game/content-metadata.json`
- `Game/DATA/FINAL`
- `LeagueClient/Plugins/rcp-be-lol-game-data/description.json`
- 当前目标实际引用的 LCU 与 GAME WAD 资源

程序不内置下载、远端清单解析或网络回退；`LeagueClient.exe` 不是必需项。外部准备工具完成目录
后，直接把该目录作为 `game_path` 使用即可。

详细说明见：

- [已准备本地数据源合同](./api/prepared_source.md)

## 5. 基准测试与性能参考

项目内置基准脚本：`scripts/benchmark_cli.py`。

核心口径：

- `--mode single_vo` 测量单英雄 VO 更新与解包
- `--mode full_extract` 测量全量更新与解包
- `--mode targeted` 使用显式英雄/地图 ID 比较相同客户与输出盘上的可重现范围
- `--runner cli|api|both` 用于比较两种项目入口
- benchmark 只记录性能，不替代正确性或系统测试

详细参数、示例命令、输出结构与历史性能参考见：

- [基准测试与性能参考](./api/benchmarking_and_performance.md)

## 6. 设计哲学

- **速度优先**：通过简化流程和优化 I/O，尽量提升解包效率。
- **数据纯粹**：不对输出文件做重命名或分类，文件名即游戏数据中的原始 ID。
- **责任分离**：核心能力专注于更新、解包、WAV 转码与映射；更复杂的后处理继续保持解耦。
