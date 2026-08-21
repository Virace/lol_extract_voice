# GUI 共享实体数据就绪与自动准备

本文面向维护者，说明 GUI 如何判断英雄/地图目录是否可信、何时自动准备结构化数据，以及页面、
任务门禁和进度如何保持一致。

## 1. 三类不同状态

共享目录流程必须与另外两类状态分开：

- **任务快照**：执行中心创建任务时冻结的参数。后续修改设置不会改写已入队任务。
- **运行时配置**：用于构造后续 `AppContext` 的游戏目录、输出目录、来源模式、区域和 remote
  快照设置。
- **共享实体数据**：英雄、地图与可选特殊内容的结构化目录，供主页、执行中心和实体总览共同
  使用。

个性化设置（主题、平滑滚动、日志抽屉等）不属于共享目录上下文，不触发目录重建。

## 2. 单一事实来源

`SharedDataController` 持有当前 `SharedDataState`，页面不得再根据中文消息、日志内容或 worker
是否正常结束推断就绪状态。

一次完整扫描由 `SharedDataScanWorker` 在后台运行，内部调用
`EntityDataLoader.scan_catalog()`，返回一个 `SharedDataScanResult`。该结果同时包含：

- 当前 `generation`、effective source mode 和版本；
- 英雄、地图、特殊内容三个 section；
- 每个 section 的权威 expected IDs、成功 rows、失败项与未准备项；
- 按稳定问题码聚合的 `problems`；
- 由必需目录事实派生的 complete、partial 或 failed readiness。

逐实体异常可以被扫描器收集后继续扫描，但不能只写日志并丢弃。英雄或地图 expected 集合为空、
Map 0 缺失、任一必需 ID 未形成有效行，都不能进入 `ready`。

结构化特殊内容和显式 resource pack 是可选、local-only 目录。它们未准备不会降低普通英雄/地图的
readiness；默认共享扫描也不会遍历全部历史 FINAL WAD。

## 3. 状态机

| Phase | 含义 | 阻止新任务 |
| --- | --- | --- |
| `blocked` | 必要配置缺失或无效 | 是 |
| `checking` | 正在建立上下文或完整扫描 | 是 |
| `waiting` | 配置已变更，等待现有任务队列结束 | 是 |
| `preparing` | 正在执行自动或手动共享 update | 是 |
| `verifying` | update 完成，正在重建 reader 并完整复检 | 是 |
| `ready` | 全部必需英雄与地图通过当前 generation 复检 | 否 |
| `partial` | 有可信 rows，但必需目录不完整 | 是 |
| `failed` | 无法形成可信必需目录或准备失败 | 是 |
| `cancelled` | 准备被权威结果标记为取消 | 是 |

`active`、`blocks_new_tasks` 和语义角色都由 phase 派生。只有 `ready` 可以创建新任务或把总览选择
发送到执行中心；partial 可以浏览已经验证成功的 rows，但页面持续显示目录不完整状态。

每次 reader 相关配置变化都会增加 `generation`。旧 worker 的 scan、prepare、failure 和 progress
回调在应用前检查 generation，不允许覆盖新上下文。

## 4. 检查、准备与复检

首次启动、手动刷新、配置变化和显式重试共用同一条主链：

1. 校验必要配置并异步建立 `AppContext`。
2. 完整扫描当前目录。
3. complete 时原子发布三类 rows，再发布 `ready`。
4. 若全部阻断问题都可自动修复，按失败证据生成 repair scope。
5. 每个 generation 最多自动执行一次普通 update，默认 `force_update=False`。
6. 消费 update 返回的真实 `StageResult`。
7. success 或 partial 时重建读取上下文并完整复检；failed/cancelled 直接进入对应终态。
8. 复检 complete 且准备结果不是 partial 时才能进入 `ready`。

自动可修复问题包括数据缺失/过期/为空、banks 缺失、local resource schema 不兼容、binding 不完整、
Map 0 缺失和可分类的 artifact 损坏。配置、权限或来源不可用不会触发自动循环。

共享 readiness 的扫描只读取基础 `data` 与 banks，不读取 events，也不把最终 mapping 产物作为目录
就绪条件。自动准备仍沿用普通 update，以便在 events 本身缺失或过期时保留后续事件映射能力；若
events 已经新鲜，即使 banks 因 schema 迁移需要重建，也不会重复解析或写入英雄/地图事件数据。

普通更新后同类可修复问题仍存在时，主页提供“重新生成实体数据”。这是用户显式选择的二级恢复，
才会使用 `force_update=True`；初次自动迁移不会删除旧文件或默认 force。结构化 artifact 仍通过
同目录临时文件和原子替换发布，失败时保留原文件。

## 5. `StageResult` 与扫描各自证明什么

update 的 `StageResult` 证明准备过程的执行事实，完整扫描证明 GUI 目录的可读事实，两者缺一不可：

- success：进入 verifying，不直接显示成功；
- partial：仍进行复检以发布实际 rows，但最终至少为 partial；
- failed：直接 failed，不调用成功重载路径；
- cancelled：直接 cancelled，不显示 100% 或成功通知。

worker `finished` 只表示后台函数返回。进度达到 total 只表示当前阶段已处理完，都不能替代上述 typed
结果。

## 6. 进度与全局所有权

核心 update 通过可选 `OperationProgress` 回调发布 `data`、`champion_banks` 和 `map_banks` 阶段；
完整扫描通过 `SharedDataProgress` 发布 champions、special 和 maps 阶段。

- total 未知的上下文建立或短阶段使用不确定动画，不显示虚构百分比或 ETA。
- total 已知时，主页与全局宿主消费同一份归一化 current/total 快照；填充宽度直接跟随真实比值。
- 普通进度在控制器边界以 50 ms 窗口保留最新值，阶段 started/finished 和终态立即发布。
- 进度回调不等待 UI 绘制，实体总览也不会因每个计数更新而重建目录模型。

全局进度条同时服务用户任务与共享准备。若短暂重叠，正在执行的用户任务优先；共享状态继续保存，
任务结束后只恢复仍属最新 generation 的共享进度。共享准备不进入用户任务队列，也不显示用户任务的
取消按钮。主页已经显示共享准备的页内状态与进度条，因此在主页隐藏同源全局条；切换到其他页面时
立即恢复。用户任务的全局进度不受主页抑制规则影响。

## 7. 页面与恢复动作

- **主页**：显示 phase、动态英雄/地图摘要、单一确定或不确定进度条，以及稳定恢复按钮；计数只在
  实体状态卡中出现一次。
- **执行中心**：只有 ready 启用创建任务；活跃阶段显示“准备数据中”，waiting 显示“等待当前任务
  结束”，其余终态保留原因 Tooltip。
- **实体总览**：活跃阶段显示加载占位；partial 保留 verified rows，但禁用“发送到执行中心”。
- **全局进度**：除主页外，用户切换标签页后继续展示共享准备状态。

恢复动作使用稳定 action key，由窗口层绑定真实行为：

- 配置缺失/无效、输出不可写：打开全局设置；
- 可修复问题：重试更新；普通迁移后仍失败时可重新生成；
- 来源不可用或未分类错误：先提供重试，日志只作为补充诊断。

通知只提示有意义的状态转折。普通启动直接 ready 不弹成功通知；自动准备开始、准备并复检成功、
initial partial/failed 各按 generation 去重。持久页面状态始终是主要反馈。

## 8. 队列与刷新边界

运行时配置在队列仍有等待或运行任务时进入 `waiting`。已有任务继续使用创建时的上下文快照，设置页
锁定后端相关分组；队列清空后，控制器自动继续新 generation 的 checking。

任务完成后的产物增量刷新与共享 readiness 分离：它只按 `EntityResult.artifacts` 更新已有目录行，
不会把 partial/failed 变成 ready，也不会触发共享自动准备。强制终止拿不到可靠产物快照时不做猜测性
刷新。

## 9. 验证边界

自动化测试覆盖 phase 映射、完整/部分/失败扫描、Map 0、可选 special、一次自动准备、StageResult
四态、generation 拒旧、队列 waiting、进度模式/节流、恢复动作、ready-only 门禁，以及旧 schema 经
普通 update adapter 后复检为 ready。

布局、颜色、缩放、键盘可达性和主观流畅度不使用像素或源码字面量测试。它们保留在原生 Windows
GUI manual Review，通过标准入口 `uv run unpack-gui` 验收。

### 共享进度 mock

需要反复检查首页页内进度与其他页面底部全局进度时，先正常启动 GUI，打开全局日志抽屉后按住
`Ctrl` 点击日志标题，进入开发控制台。输入下列命令即可启动只作用于展示层的循环 mock：

```text
shared progress
```

默认每 50 ms 前进一步，依次模拟 checking、英雄更新、地图更新、英雄复检、地图复检和 ready；
一轮结束后自动重新开始。需要放慢观察时可指定 10–2000 ms 的步进间隔：

```text
shared progress 80
```

再次执行 `shared progress <interval_ms>` 会按新速度重新开始；`shared inspect` 查看运行状态，
`shared stop` 停止并恢复最新真实状态。

mock 不会读取、扫描、更新或写入真实实体数据。它只覆盖首页共享状态和底部全局进度条，不改变执行
中心的真实数据与任务门禁；真实共享状态再次发布时，mock 会自动停止，避免遮蔽后台事实。
