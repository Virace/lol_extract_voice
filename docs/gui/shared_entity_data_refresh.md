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

指 GUI 与后端共用的“英雄 / 地图实体索引信息”。

当前它主要服务于：

- 实体总览左侧列表
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
  位置：[setting_page.py](/H:/Programming/Python/lol_audio_unpack/src/lol_audio_unpack/gui/view/setting_page.py#L733)

### 2.2 `ExecutionPage`

职责：

- 维护任务队列
- 创建任务快照
- 区分“当前任务运行中”与“队列仍有未完成任务”

关键实现：

- `ExecutionPage.has_incomplete_tasks()`  
  位置：[execution_page.py](/H:/Programming/Python/lol_audio_unpack/src/lol_audio_unpack/gui/view/execution_page.py#L505)

当前约束：

- 共享数据刷新不再只看 `running`
- 而是看 `waiting + running` 的整体队列状态

### 2.3 `MainWindow`

职责：

- 串联设置页、执行中心、实体总览
- 调度共享实体数据刷新
- 处理缺数据时的后台自动准备

关键实现：

- `_on_task_queue_busy_changed()`  
  位置：[window.py](/H:/Programming/Python/lol_audio_unpack/src/lol_audio_unpack/gui/window.py#L483)
- `_schedule_runtime_entity_refresh()`  
  位置：[window.py](/H:/Programming/Python/lol_audio_unpack/src/lol_audio_unpack/gui/window.py#L570)
- `_start_shared_data_prepare()`  
  位置：[window.py](/H:/Programming/Python/lol_audio_unpack/src/lol_audio_unpack/gui/window.py#L609)

## 3. 当前主链

### 3.1 运行时配置变更

当运行时配置变化时：

1. `SettingPage` 保存配置
2. 发出 `entity_data_config_changed`
3. `MainWindow` 不立即重载
4. 而是标记一次待处理刷新，并启动短暂延迟
5. 如果队列仍有未完成任务，则继续延后
6. 等待队列清空后，再真正发起共享实体数据刷新

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
6. 读取成功后构建英雄 / 地图实体列表并更新 UI

这里的关键点是：

- `DataReader` 负责判断“当前输出目录里是否已经有可读共享数据”
- GUI 不会在每次刷新时都先跑一遍更新

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

- 队列未清空时锁定运行时配置
- 个性化配置保持可编辑
- `vgmstream-cli` 这类不参与共享实体数据链的工具路径继续可编辑
- 队列清空后再处理待刷新的共享实体数据

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

- 执行中心里勾选“强制更新数据”
- 由任务本身的快照决定

所以当前系统里其实有两层 `update`：

1. 给共享实体数据服务的后台准备
2. 给具体任务流程服务的任务步骤

它们不应该被混成一个按钮语义。

## 9. 现阶段的推荐维护原则

后续如果继续调整 GUI 刷新逻辑，建议保持以下原则不变：

1. 先区分“任务快照”“运行时配置”“共享实体数据”
2. 共享实体数据优先走 `DataReader`
3. 只在可自动修复的错误上补 `DataUpdater`
4. 锁运行时配置，不锁个性化配置
5. 队列未清空时不落地新的共享实体数据刷新

只要这 5 条不被打破，后续无论是继续细化自动准备策略，还是扩展远程模式，都不容易把 GUI 语义弄乱。
