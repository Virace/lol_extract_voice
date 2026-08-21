# 共享实体数据刷新逻辑

本文档面向开发者，说明当前 GUI 中“共享实体数据”的状态边界、刷新触发条件，以及 `DataReader` / `DataUpdater` 在 GUI 主链中的职责划分。

## 1. 术语

### 1.1 任务快照

指执行中心在创建任务时冻结下来的运行参数集合。

特点：

- 已入队任务只使用自己的快照
- 后续修改全局设置不会回写旧任务
- 作用域是“任务执行”

### 1.2 运行时配置

指会进入 `GuiConfig.to_app_context_overrides()` 的配置项，也就是 GUI 用来构造后端 `AppContext` 的参数。

当前包含：

- `SOURCE_MODE`
- `GAME_PATH`
- `OUTPUT_PATH`
- `GAME_REGION`
- `GROUP_BY_TYPE`
- `REMOTE_LIVE_REGION`
- `CLEANUP_REMOTE`
- `REMOTE_VERSION`
- `REMOTE_LCU_MANIFEST_URL`
- `REMOTE_GAME_MANIFEST_URL`
- `WWISER_PATH`

当前不包含：

- `VGMSTREAM_PATH`

作用域：

- 决定后续新任务的默认上下文
- 决定共享实体数据刷新应使用哪套后端上下文

### 1.3 共享实体数据

指 GUI 与后端共用的“英雄 / 地图 / 特殊内容实体索引信息”。

当前它主要服务于：

- 实体总览左侧目录（英雄、地图、特殊内容）
- 执行中心目标摘要
- 选择同步后的任务输入基线

注意：

- 这里说的共享数据，不是整份 GUI 配置
- 也不是任务队列本身的状态

## 2. 当前组件分工

### 2.1 `SettingPage`

职责：

- 管理 GUI 配置输入
- 将运行时配置与个性化配置分层
- 在运行时配置变化时发出 `entity_data_config_changed`
- 在队列忙碌时只锁后端相关分组

关键实现：

- `SettingPage.set_runtime_config_locked()`  
  位置：[`setting_page.py`](../../src/lol_audio_unpack/gui/view/setting_page.py)

### 2.2 `ExecutionPage`

职责：

- 维护任务队列
- 创建任务快照
- 区分“当前任务运行中”与“队列仍有等待或运行任务”

关键实现：

- `ExecutionPage.has_incomplete_tasks()`  
  位置：[`execution_page.py`](../../src/lol_audio_unpack/gui/view/execution_page.py)

当前约束：

- 共享数据刷新不再只看 `running`
- 而是看 `waiting + running` 的整体队列状态
- `partial`、`failed`、`cancelled` 都是终态，不会继续锁定运行时配置或阻断已确认产物的刷新

### 2.3 `MainWindow`

职责：

- 串联设置页、执行中心、实体总览
- 调度共享实体数据刷新
- 处理缺数据时的后台自动准备

关键实现：

- `_on_task_queue_busy_changed()`  
  位置：[`window.py`](../../src/lol_audio_unpack/gui/window.py)
- `_schedule_runtime_entity_refresh()`  
  位置：[`window.py`](../../src/lol_audio_unpack/gui/window.py)
- `_start_shared_data_prepare()`  
  位置：[`window.py`](../../src/lol_audio_unpack/gui/window.py)

## 3. 当前主链

### 3.1 运行时配置变更

当运行时配置变化时：

1. `SettingPage` 保存配置
2. 发出 `entity_data_config_changed`
3. `MainWindow` 不立即重载
4. 而是标记一次待处理刷新，并启动短暂延迟
5. 如果队列仍有等待或运行任务，则继续延后
6. 等待队列不再执行后，再真正发起共享实体数据刷新

这样可以避免用户先改游戏目录、又马上改输出目录时触发多次重复刷新。

### 3.2 手动刷新

左侧“刷新数据”的语义是：

`确保共享实体数据可用`

它不会无条件跑 `DataUpdater`，而是：

1. 先尝试直接重载共享数据
2. 只有在可自动修复的错误上才补一次后台数据准备
3. 准备完成后重新刷新实体数据

### 3.3 共享数据重载

当前共享数据重载的第一步是“读”而不是“更”。

读取链：

1. 基于当前运行时配置构造 `AppContext`
2. 为 `OverviewPage` 设置新的上下文
3. `DataLoadWorker` 中创建 `EntityDataLoader`
4. `EntityDataLoader` 内部创建 `DataReader`
5. `DataReader` 读取 `manifest/<version>/data.*`
6. 读取成功后以一次完整英雄扫描分出普通英雄与结构化特殊内容，并构建英雄 / 地图 / 特殊内容目录更新 UI
7. 只枚举已持久化的 resource-pack artifact 补充“历史资源包”分组；不在共享刷新中扫描 FINAL WAD

这里的关键点是：

- `DataReader` 负责判断“当前输出目录里是否已经有可读共享数据”
- 每次构造 `DataReader` 都绑定当前 `AppContext` 且实例彼此独立；运行时配置变化会重建上下文与
  loader，无需删除进程级单例。执行任务内的地图预检则复用该任务 `LolAudioUnpackApp` 的 reader
- GUI 不会在每次刷新时都先跑一遍更新
- 特殊内容对应的银行或映射未准备好时仍保留目录项，并如实显示“未准备”；不能因为产物缺失而静默丢行
- `remote_snapshot` 只允许浏览特殊内容目录，不能选择、同步或进入任务执行链
- 任务完成后的增量刷新会一次读取冠军元数据，但只重建本次请求的普通英雄和特殊内容行，不会为少量 special key 重新扫描全部普通英雄状态
- resource-pack 增量刷新仅读取请求 key 的 banks/events/audio/hash artifact；selected-WAD TOC/BIN 发现必须由显式后台扫描任务触发

右侧预览与共享目录分开管理：事件视图消费 mapping，“全部音频”枚举当前实体的
WEM 路径。当 mapping 缺失而 WEM 存在时，GUI 默认进入“全部音频”；当映射中有
`audioPaths` 时，试听、导出和定位只使用该事件的精确路径，不回退到全局 WEM ID 猜测。
事件预览不会为此提前递归枚举实体的全部 WEM；首次打开“全部音频”才启动后台加载，
摘要区显示加载状态，完成后把路径级引用一次交给分批布局模型。同一实体内往返切换
以及离开总览页后返回时，复用已经加载的事件树、全部音频模型与路径缓存，不重复读取
预览、重置模型或扫描输出目录。索引过程在独立的单线程低优先级
线程池执行，摘要区显示已处理数、总数和百分比；离开总览页后 worker 可继续完成缓存，
但不会更新隐藏页或构建大列表，返回后才应用结果。

### 3.4 任务终态与产物刷新

执行子进程返回的 `ExecutionTaskResult` 必须携带权威 `RunResult`。GUI 不从 signal 名称、完成日志
或最后一条进度消息猜测结果，而是按 `RunResult.status` 映射四种终态：

- `success` → `已完成`，允许终态进度到 100%
- `partial` → `部分完成`，使用 warning 通知且不显示满格成功
- `failed` → `失败`，使用 error 通知且不显示满格成功
- `cancelled` → `已取消`，不显示满格成功

`completed_steps` 只记录 success/partial 且本轮确有产物的阶段；GUI 的强制 update 成功是唯一无需
逐实体 artifact 的阶段例外。extract、mapping 和 WAV 的产物证据来自 `EntityResult.artifacts`，
不是原始目标列表、旧输出目录、日志或进度文本。

任务结束后只刷新 artifacts 对应的英雄、地图、特殊内容或 resource-pack key。failed 实体若在失败前
已确认落盘，仍可触发这类有界刷新；没有 artifact 的 failed 不刷新。强制终止子进程无法取得可靠的
最终产物快照，因此取消操作不会猜测性刷新，也不会把进度强制改为 100%。

人工检查四态时，可按住 `Ctrl` 点击全局日志抽屉标题打开开发控制台，再依次执行
`queue result success`、`queue result partial`、`queue result failed`、`queue result cancelled`。
这些命令只注入 typed result 与调试队列状态，不执行真实解包、映射或文件写入；`queue clear`
可清除 fixture。

## 4. 自动补 `DataUpdater` 的条件

当前只在这类错误上自动补一次后台数据准备：

- 缺核心数据文件
- 明确提示“请先运行更新程序”
- 数据版本与游戏版本严重不匹配，需要立即更新

也就是说，自动准备的前提是：

`共享实体数据当前不可用，但问题本质上可以通过补一次 update 修复`

对应思路是：

- 先读
- 读不到再补更新
- 更新后再重读

## 5. 不自动补 `DataUpdater` 的情况

下面这类错误不应被解释为“该 update 了”：

- 游戏目录错误
- 输出目录错误
- 权限不足
- 路径不可访问
- 其他明显属于配置无效的异常

原因是这些错误不能靠更新流程自愈。

如果强行自动 update，只会让错误更难理解，甚至掩盖真正的问题。

## 6. 为什么要分层锁定

这个设计是为了解决一个很具体的问题：

- 页面上的全局设置可以改变
- 但队列里已入队任务的快照不能改变

如果队列里还有等待任务，用户这时修改运行时配置，会出现：

- 设置页显示的是新路径
- 后续等待任务跑的还是旧快照
- 实体总览如果此时刷新，又可能切到新的共享数据上下文

这三件事会让界面语义变得不一致。

所以当前策略是：

- 队列仍有等待或运行任务时锁定运行时配置
- 个性化配置保持可编辑
- `vgmstream-cli` 这类不参与共享实体数据链的工具路径继续可编辑
- 队列不再等待或运行后再处理待刷新的共享实体数据

## 7. 两类刷新不要混淆

当前实现中需要始终区分下面两件事：

### 7.1 GUI 个性化配置应用

例如：

- 主题
- 主题色
- 平滑滚动
- 日志抽屉自动收起

特点：

- 只影响前端表现
- 应当立即生效
- 不应触发共享实体数据刷新

### 7.2 共享实体数据刷新

例如：

- 游戏目录变化
- 输出目录变化
- 来源模式变化
- 远程快照参数变化

特点：

- 会改变后端 `AppContext`
- 会影响 `DataReader` / `DataUpdater` 的读取与准备行为
- 必须遵守队列锁定规则

## 8. 任务执行中的 `update` 与共享数据准备不是一回事

这是另一个必须明确的边界。

### 8.1 共享数据准备

目的：

- 让实体列表可读
- 让执行中心能基于实体索引工作

触发方式：

- 运行时配置变化后的自动调度
- 手动点击“刷新数据”

### 8.2 任务执行中的 `update`

目的：

- 作为某个具体任务步骤的一部分执行

触发方式：

- 执行中心里勾选“前置强制更新”
- 由任务本身的快照决定

所以当前系统里其实有两层 `update`：

1. 给共享实体数据服务的后台准备
2. 给具体任务流程服务的任务前置补库步骤

它们不应该被混成一个按钮语义。

## 9. 现阶段的推荐维护原则

后续如果继续调整 GUI 刷新逻辑，建议保持以下原则不变：

1. 先区分“任务快照”“运行时配置”“共享实体数据”
2. 共享实体数据优先走 `DataReader`
3. 只在可自动修复的错误上补 `DataUpdater`
4. 锁运行时配置，不锁个性化配置
5. 队列仍有等待或运行任务时不落地新的共享实体数据刷新

只要这 5 条不被打破，后续无论是继续细化自动准备策略，还是扩展远程模式，都不容易把 GUI 语义弄乱。
