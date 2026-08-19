# Lol Audio Unpack 项目开发规范

## 1. 适用范围与权威来源

本规范适用于仓库根目录以及 `src/`、`tests/`、`scripts/`、`docs/`。
规则优先级为：当前用户要求、根 `AGENTS.md`、局部 `AGENTS.project.md`、本文件、
`PRODUCT.md`、`PROJECT_CONSTRAINTS.md`、`PROJECT_DESIGN.md`、当前仓库与命令输出。

每轮代码工作至少读取根 `AGENTS.md`、本文件以及与目标文件直接相关的文档。
产品目标、硬约束和架构事实分别以另外三个项目文件为准；发现文档与源码不一致时，
先以可执行源码和真实命令确认现状，再同步权威文档。

## 2. 技术栈与真实命令

- Python：`>=3.10`，包采用 `src/` 布局。
- 包管理与运行：uv，锁文件为 `uv.lock`。
- CLI：标准库 `argparse` 解析动作式命令；公开入口为 `unpack`、`mapping`。
- GUI：PySide6 与 PySide6-Fluent-Widgets，作为可选依赖组 `gui`。
- 核心外部边界：`league-tools`、`riotmanifest`、`pyvgmstream`、本地文件系统与子进程。

```powershell
# 安装核心与开发依赖
uv sync

# 安装 GUI 运行依赖
uv sync --extra gui

# 在 GUI 运行依赖上额外安装 pytest-qt
uv sync --extra gui --group gui-test

# 运行入口
uv run unpack --help
uv run python -m lol_audio_unpack --help

# 对本轮改动的 Python 路径执行格式与静态检查
uv run ruff format --check <changed-python-paths...>
uv run ruff check <changed-python-paths...>

# 默认离线门禁；tests/system 不会被默认发现
uv run pytest

# 定向层级
uv run pytest -m unit
uv run pytest -m integration

# 稳定 GUI 逻辑与状态切换；默认门禁不收集 tests/gui
uv run pytest tests/gui -q

# 真实本地客户端系统链路
uv run pytest tests/system/test_local_game.py -q -s

# 最新远端快照 smoke
uv run pytest tests/system/test_remote_snapshot.py -q -s

# 旧 WAV 协调器的显式多进程兼容门禁
uv run pytest tests/system/test_wav_coordinator.py -q

# 构建 Python 包
uv build
```

`<changed-python-paths...>` 必须替换为本轮实际新增或修改的 Python 路径。当前存量文件尚未建立
整仓 Ruff format 基线，不得为了通过格式门禁顺带改写无关文件。

当前没有声明类型检查器，因此不存在可声称通过的 typecheck 命令。GUI 可执行文件由
`scripts/pyinstaller/build_gui.py` 和 tag release workflow 构建；稳定逻辑由显式 pytest-qt
门禁验证，正式可执行文件和视觉质量仍属于发布与人工验收门禁。

## 3. 代码组织

- `src/lol_audio_unpack/app/`：运行上下文、目标解析、产物定位和应用编排门面。
- `src/lol_audio_unpack/config/`：INI schema、读取与写回。
- `src/lol_audio_unpack/cli/`：动作式参数解析、校验、调度与 CLI 文案。
- `src/lol_audio_unpack/manager/`：结构化数据更新、BIN 处理与读取。
- `src/lol_audio_unpack/unpack/`：WAD/BNK/WPK 音频解包。
- `src/lol_audio_unpack/mapping/`：事件到音频的 NativeHIRC 或 wwiser 映射。
- `src/lol_audio_unpack/runtime/`：远端快照、WAD 缓存和 WAV 转码等运行期适配。
- `src/lol_audio_unpack/model/`：跨层共享的音频实体模型。
- `src/lol_audio_unpack/gui/`：展示与人工交互层，不承载可复用核心规则。
- `tests/system/`：显式执行的真实系统链路；默认 pytest 不递归进入。
- `scripts/`：基准、构建与维护工具，不作为正确性测试的替代品。

依赖方向以 `cli/gui -> app -> manager/unpack/mapping/runtime -> model/utils` 为主。
可脱离 UI 判断的业务规则应下沉到核心层。只有形成稳定能力边界、需要公开面或已有多文件
协作时才新增子包，不为单个小文件形式化分层。

## 4. 命名与文档

- Python 使用 `snake_case`，类使用 `PascalCase`；稳定领域词保留 `WAD`、`BIN`、`LCU`、
  `VO`、`SFX`、`WEM`、`WAV`。
- 标识符只表达当前作用域无法提供的信息。局部变量优先 1 至 3 个核心词，移除模块、类型或
  上下文已经说明的重复前缀；同一组概念统一使用同一词根。
- 函数名以动词开头；测试数据工厂使用 `make_*`，解析使用 `resolve_*`，执行场景使用
  `run_*`。测试函数名可比生产标识符更长，以便失败报告表达行为。
- 新 Python 文件必须有中文模块 docstring；新增或修改的公开函数、类、方法使用中文
  Google 风格 docstring。复杂内部逻辑说明原因、边界和不变量，不逐行复述实现。
- 不删除仍然有效的解释性注释。搬移或重命名逻辑时同步迁移注释，失效注释必须改写。
- 公开入口或用户命令变化时，同步更新 `README.md`、`docs/api/` 与本规范中的直接引用。

## 5. 错误与日志

- CLI 参数错误、路径缺失和稳定业务校验通过明确异常与退出状态反馈；用户消息说明可执行的
  修复方向，不直接暴露内部堆栈或原始第三方异常。
- 内部日志使用 Loguru。`INFO/SUCCESS` 表达阶段与结果，`DEBUG/TRACE` 表达决策细节，
  `WARNING` 表达可恢复降级，`ERROR/CRITICAL` 表达当前单元或流程失败。
- fallback、重试、跳过、自动回退、吞掉异常继续以及 worker 启动/完成/失败必须可观察。
  批处理在结束时给出成功、部分失败或全部失败摘要。
- Qt 与 `pyvgmstream` 日志只做最小桥接；业务影响由核心任务层另行记录。生产日志不得输出
  密钥、完整凭证或不必要的用户本地信息。

## 6. 变更门禁

修改时实时纠正本轮新增或直接涉及的命名、导入边界、文档和临时路径。不得为顺手整理扩大到
无关的全仓重构。`pyproject.toml`、依赖、公开 API、输出格式、配置 schema 或远端契约变化
需要相称的兼容分析与验证。

最低门禁：

1. 对改动文件运行 Ruff 格式与静态检查。
2. 运行能证明目标行为的最小 pytest 集合。
3. 影响核心共享逻辑时运行默认离线门禁。
4. 影响 WAD/BIN、目标选择、解包、mapping 或远端准备时，运行对应显式系统门禁。
5. 同步更新直接相关的命令与 API 文档。
6. 最终报告已运行证据、未运行边界、人工验收项和推迟风险。

### 测试策略

测试目标是防止项目自有编排、配置、产物布局与边界适配回归；测试数量和覆盖率不是交付指标。

| 风险或稳定契约 | 可观察行为 | 最低有效证据 | 环境或依赖 | 位置与时机 |
| --- | --- | --- | --- | --- |
| CLI 与配置模式漂移 | 子进程可启动；动作、显式参数和完整 INI 模式得到正确结果 | 解析行为测试 + 两条 CLI 子进程 smoke | 核心开发依赖 | `tests/cli/`；相关修改与默认门禁 |
| 项目自有纯逻辑回归 | 路径、目标、版本、序列化、统计和状态转换输出稳定 | 单元或轻量集成测试 | 临时文件；仅隔离外部边界 | 对应模块测试；相关修改时 |
| 公共 Python 入口漂移 | 文档推荐的关键符号可从声明模块导入 | 一组参数化 import smoke | 核心开发依赖 | `tests/test_public_api.py`；公开面修改时 |
| GUI 稳定逻辑回归 | 配置持久化、任务状态、异步信号、错误恢复和试听生命周期稳定 | 精选 pytest-qt 行为测试 | `uv sync --extra gui --group gui-test`；原生 Windows 优先 | `tests/gui/`；GUI 逻辑修改时显式运行 |
| 本地真实音频链路失效 | `update -> bindings/events -> extract -> NativeHIRC mapping` 生成 WEM、报告与 hash | 单条共享准备系统测试；英雄 1、Jade 60009、地图 0/11/22；普通英雄、Jade 与地图 11 保留 mapping，Map 22 验证 binding 与 WEM | 当前版本含 Jade 的真实本地客户端、临时磁盘 | `tests/system/test_local_game.py`；核心 WAD/BIN 链路或交付前显式运行 |
| 远端快照编排失效 | CLI 从 live manifest 下载代表英雄 VO 并生成 data、WEM 与报告 | 单条远端 CLI smoke | Riot 网络，最长 900 秒 | `tests/system/test_remote_snapshot.py`；远端改动或发布前 |
| 旧 WAV 协调器多进程兼容回归 | 超时重试、熔断、报告和进度生命周期一致 | 显式系统兼容测试 | Windows 多进程 | `tests/system/test_wav_coordinator.py`；该兼容面修改时 |

明确边界：

- 不单独复测 `league-tools`、`riotmanifest`、`pyvgmstream` 等上游包内部算法；只验证本项目的
  调用契约与真实集成结果。
- WAD/BNK/WPK 解包不建立庞大 mock 单测矩阵；真实正确性由一条本地系统链路证明，项目自有
  的目标选择、错误处理和产物组织保留低层测试。
- 同一状态矩阵只保留一个主要测试层。能参数化合并时不重复启动完整 CLI、下载或解包流程。
- 不用源码字符串、私有名称、文件摆放、旧符号不存在或框架默认行为充当业务回归测试。
- 私有 rename、注释、文案、格式和 benchmark 报告排版不新增自动化测试；使用 Ruff、目标
  diff 与真实命令验证。

GUI 自动化只保留不依赖视觉判定的稳定行为：配置读写、任务状态切换、异步 worker/信号、
错误恢复、筛选和试听生命周期。截图、颜色、像素、边距、尺寸、控件类型、源码字面量以及
框架默认行为不作为回归测试。首次启动整体流程、视觉层级、主题缩放、高日志量主观流畅度、
重启和正式打包可执行文件由人工验收。

远端地图专用准备与 wwiser fallback 当前不在默认或单条远端 smoke 中；只有相关边界变化或
发布需要时，使用显式预置资源做专项验收，不在测试内自动下载 wwiser。

## 7. 项目例外

- GUI 视觉与布局只做人工验收；稳定状态、异步边界和错误恢复保留精选 pytest-qt 测试。
  能下沉到核心层的业务规则优先下沉，但不以此为由删除仍需 Qt 事件循环证明的真实交互状态。
- 真实系统测试默认不被 pytest 发现，必须显式指定 `tests/system/` 文件；这样避免日常命令
  意外访问本地客户端或网络。
- 地图数据更新必须包含 ID `0`（Common）后再处理目标地图；任何系统测试和实际工作流都不得
  用仅传目标地图的假绿结果替代该约束。
- 临时缓存、测试产物和 benchmark 默认写入 `.temp/`；长期可审查的基准结论需要用户明确
  决定是否另行归档。
