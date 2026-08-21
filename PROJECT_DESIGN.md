# Lol Audio Unpack 项目设计

## 顶层职责

- `src/lol_audio_unpack/`：可安装应用包。
- `tests/`：默认离线行为与集成测试；`tests/system/` 存放显式真实链路。
- `scripts/`：benchmark、图标、构建和维护入口。
- `config/`：可复制的配置样例。
- `docs/`：用户与 API 文档。
- `.github/`：tag 触发的 Windows GUI 构建与 release 流程。

## 入口与组合

`unpack`、`mapping` 与 `python -m lol_audio_unpack` 最终进入 `cli/`。CLI 负责解析动作、
校验互斥配置模式、构造 `AppContext` 与 `OperationOptions`，再把 update、extract、wav、
mapping 交给 `LolAudioUnpackApp`。

GUI 只负责收集用户输入、展示状态和启动任务。可复用规则不得反向依赖控件；日志层、任务层和
UI 层通过异步边界交接，UI 吞吐不能阻塞解包或 mapping。

CLI、Python API、remote orchestration 与 GUI 共用 `ResultStatus`、`EntityResult`、`StageResult`
和 `RunResult`。日志只负责诊断，不能替代 typed result 成为成功、失败或退出码的事实来源。

## 核心模块边界

- `app/context.py` 把设置解析为不可混淆的 `AppConfig`、`AppPaths` 与 `AppContext`。
- `app/facade.py` 编排 DataUpdater、BinUpdater、DataReader、解包、转码和 mapping。
- `manager/data_updater.py` 从 LCU 资源建立版本化 `data.*`。
- `manager/bin_updater.py` 组织英雄与地图处理器，生成 banks/events；local update 同时生成 v2 resource bindings。
- `manager/resource_pack_discovery.py` 只扫描用户显式选定的 FINAL WAD，有界解析历史 `BANK_UNITS` 并生成独立 resource-pack artifact。
- `manager/data_reader.py` 读取版本化结构化数据；`LolAudioUnpackApp` 在自身 `AppContext` 生命周期内懒加载并复用 reader，update/discovery 写入边界后整体失效。直接构造的 reader 实例彼此独立；精确 binding 消费可显式要求 v2。
- `model/binding.py` 固定 declared BIN、bank reference、物理 WAD 与完整度诊断合同。
- `runtime/wad_index.py` 对 FINAL root/current-language WAD 建立进程内 TOC cache，并按目标 hash 解析容器。
- `unpack/` 读取实体资源引用，从 WAD/BNK/WPK 落盘原始 WEM 与报告。
- `mapping/` 读取 events 与音频容器，使用 NativeHIRC 或显式 wwiser 建立 hash 映射。
- `runtime/remote/` 准备最小远端运行树，并按工作项清理可回收资源。
- `runtime/wav/` 把独立 WAV stage 适配到 `pyvgmstream`，旧协调器仅保留显式兼容入口。

## 本地数据流

```text
CLI / GUI
  -> create_app_context
  -> DataUpdater: manifest/<version>/data.*
  -> BinUpdater: banks/** (local resource schema v2) + events/**
  -> optional selected-WAD discovery: banks/events/resource_packs/**
  -> DataReader
  -> unpack: audios/** + reports/**
  -> wav: wavs/** + reports/**
  -> mapping: hashes/**
```

地图处理先使用 ID `0` 建立 Common 数据，再对目标地图去重。英雄与地图的完整二进制正确性由
真实系统链路验证，不通过大量伪造上游对象重复证明。

本地 resource binding 只持久化游戏根相对 WAD identity。resolver 先查询 root WAD TOC，
按分类语义查询当前语言 WAD，并只在 hash 歧义时解压候选 payload。旧 `skins` / `banks`
投影由同一组成功 bindings 派生，供尚未切换到逐 binding 消费的链路兼容使用。

```text
logical entity (champion / map / resource_pack)
  -> declared BIN path
  -> BinBinding (WAD identity + entry hash)
  -> BANK_UNITS logical path
  -> BankBinding (WAD identity + entry hash + root/localized role)
  -> BNK/WPK payload
  -> original WEM ID + exact relative output path
```

local v2 的 unpack 与 mapping 只消费成功 binding，不再从 alias、category 或文件名猜测物理
WAD。完整度可为 `complete` / `partial` / `failed`；未解析项进入 artifact 与报告诊断，
不会被静默改写为其他资源。resource pack 沿用该链路，但 stable string key、artifact 与
audios/hashes/reports 均隔离在 `resource_packs` 分组；默认 update 不扫描它们。

## GUI 数据与预览

`SharedDataController` 是 GUI 共享目录的单一状态 owner。它为每次上下文建立递增
`generation`，通过 `SharedDataScanWorker` 和 `EntityDataLoader.scan_catalog()` 原子扫描英雄、
地图与可选特殊内容，并发布 `SharedDataState`。只有当前 generation 的必需普通英雄和地图在
完整复检后均可读，状态才是 `ready`；`partial`、`failed`、`cancelled`、配置阻断以及所有活跃
阶段都阻止创建新任务。日志、worker 的 `finished` 信号和进度到达 total 都不能替代扫描结果或
`StageResult`。

扫描发现缺失、过期、旧 schema、Map 0 缺失或可修复损坏时，每个 generation 最多自动执行一次
普通 update，默认不 force、不删除旧 artifact。update 的 `StageResult` 为 success/partial 时进入
完整复检，failed/cancelled 直接进入对应终态；普通更新后仍存在同类可修复问题时，用户可以显式
选择“重新生成实体数据”。主页、执行中心、实体总览和主窗口全局进度条都从同一
`SharedDataState` 派生文案、计数、动作与门禁。已知总量显示真实 current/total，未知总量才使用
不确定动画；普通进度在 GUI 边界节流，阶段边界与终态立即发布。全局进度短暂重叠时，用户创建的
执行任务优先，共享准备状态保留并在任务结束后按有效 generation 恢复。

实体总览左侧是英雄、地图、特殊内容三个目录；特殊内容使用一层 group 树，
同时容纳结构化的 `champion:<id>` 与显式发现的 `resource_pack:...` key。列表和
预览只读共享 artifact；selected-WAD 发现在后台任务中运行，不阻塞 UI 线程。

右侧预览分为“事件 / 全部音频 / 原始数据”。事件视图使用 mapping 中的精确
`audioPaths`；全部音频直接枚举当前实体的 WEM 路径。因此“没有 mapping”不等于
“没有音频”，同 ID 但不同路径的 WEM 也不会被全局字典合并。事件视图只解析
mapping 实际引用的路径；全量 WEM 枚举在首次进入“全部音频”时交给后台 worker，
固定行高列表使用分批布局并在当前上下文缓存结果。隐藏 tab 不提前递归扫描或重置
数万行模型；同一实体离开总览页再返回时直接复用当前事件树与全部音频模型，不重新
读取预览或装填记录。完成首次加载后往返切换也不会重新枚举。后台索引使用独立、单线程、
低优先级线程池，并按整数百分比向摘要卡发送计数进度；离开总览页后继续填充缓存，
但不在隐藏页面创建列表模型，返回页面时再应用结果。

## 远端数据流

远端模式先解析对齐的 LCU/GAME manifest pair，下载目标实体所需的最小 LCU、BIN 与 WAD
资源，装配 `_prepared_game/` 兼容运行树，再复用本地 manager、unpack 与 mapping。
工作项结束后按配置清理准备产物；持久结果继续写入版本化 manifest、audios、hashes 和 reports。
`.use_local_bin` 与 `remote_snapshot` 来源在 local resolver 之前短路，remote 暂不要求 v2 bindings。
结构化特殊内容与 resource-pack selected-WAD 发现都是 local-only；GUI 在选择层禁用，
应用门面与后台 task boundary 会再次拒绝，不会改变普通英雄/地图的 remote v1 范围。

## 输出与公共契约

- `manifest/<version>/data.*`：聚合实体和版本元数据。
- `manifest/<version>/banks/**`：音频容器路径；local 顶层含 `resourceSchemaVersion: 2` 与逐条 bindings。
- `manifest/<version>/events/**`：事件数据。
- `manifest/<version>/{banks,events}/resource_packs/**`：显式发现的历史资源包 artifact。
- `audios/<version>/**`：原始 WEM。
- `wavs/<version>/**`：可选 WAV。
- `hashes/<version>/**`：mapping。
- `reports/<version>/**`：解包与转码报告。

关键 Python 导入面由各包 `__init__.py` 声明，并由 `tests/test_public_api.py` 做最小 import smoke。
文件格式、CLI 和配置的详细契约分别以 `docs/api/python_api.md`、`docs/api/cli_api.md`、
`docs/api/config_api.md` 为准。

`EntityResult.artifacts` 只记录本轮确认落盘的路径，是 GUI 增量刷新和 remote 完成回调的唯一
产物证据；旧目录、日志文本、进度消息和原始目标选择均不能替代它。GUI 终态直接映射
`RunResult.status`：success、partial、failed、cancelled 分别显示完成、部分完成、失败和已取消；
只有 success 可以收口为 100%，强制取消因拿不到可靠产物快照而不触发输出刷新。

## 错误与恢复模型

参数与稳定前置条件失败应尽早抛出明确异常。批量实体允许单项失败后继续，但必须记录单项影响、
累计趋势和最终摘要。远端下载、fallback、重试、清理、WAV 熔断以及本地 BIN 回退均需要可观察
日志。用户可恢复错误提供操作方向；完整异常上下文只进入内部日志。结构化 artifact 通过
`write_data(...)` 使用同目录临时文件和原子替换；该保证不泛化到 WEM、报告或远端 payload。
