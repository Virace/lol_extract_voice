<p align="center">
  <img src="./src/lol_audio_unpack/gui/assets/app_icon.svg" alt="Lol Audio Unpack logo" width="160">
</p>

<h1 align="center">Lol Audio Unpack</h1>

<p align="center">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue" alt="Python >= 3.10">
  <a href="https://deepwiki.com/Virace/lol_extract_voice">
    <img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki">
  </a>
</p>

<p align="center">一个极简、高效的英雄联盟音频提取工具。</p>

以 GUI 为主要入口，帮助内容创作者选择对象、处理音频、查找结果并试听、导出；
CLI 和 Python API 继续提供批处理与自动化能力。

---

- [介绍](#介绍)
- [当前代码结构](#当前代码结构)
- [使用方法](#使用方法)
- [后续处理](#后续处理)
- [维护者](#维护者)
- [感谢](#感谢)
- [许可证](#许可证)

## 介绍

- 支持提取英雄、地图与显式选定本地资源包的 `VO`、`SFX`、`MUSIC` 音频。
- 默认输出原始 `.wem` 文件，文件名保留游戏数据中的原始 ID。
- 数据更新阶段会携带事件信息，可进一步用于映射生成。
- GUI 当前已实现英雄/地图/特殊内容目录、执行解包、WAV 转码、生成映射、
  事件与全部音频预览、精确路径试听/导出以及首次使用引导；正式发布仍需按
  `PROJECT_STANDARD.md` 完成启动、视觉与完整链路人工验收。

文档导航、GUI 当前状态、已准备本地目录合同、基准测试与设计说明见：

- [docs/README.md](./docs/README.md)
- [docs/API.md](./docs/API.md)
- [PROJECT_STANDARD.md](./PROJECT_STANDARD.md)（开发、命名与测试门禁）

## 当前代码结构

- 根包 `lol_audio_unpack`：保留 `setup_app` 与 `__version__` 两个顶层入口。
- 应用编排层：`src/lol_audio_unpack/app/`，负责本地源预检、`AppContext`、`OperationOptions` 与 `LolAudioUnpackApp`。
- 配置层：`src/lol_audio_unpack/config/`，集中维护共享设置 schema 与标准 INI 读写。
- CLI 入口：`src/lol_audio_unpack/cli/`，`unpack` / `mapping` console script 共用同一套动作式解析与调度实现。
- 核心流水线：`src/lol_audio_unpack/unpack/` 负责音频解包，`src/lol_audio_unpack/mapping/` 负责事件映射。
- 运行时支持：`src/lol_audio_unpack/runtime/` 负责 WAD 索引、缓存与独立 WAV 转码 stage。
- 共享模型与数据层：`src/lol_audio_unpack/model/`、`src/lol_audio_unpack/manager/`。
- GUI：`src/lol_audio_unpack/gui/`，当前围绕执行中心、总览与设置页展开。

## 使用方法

### GUI

方式一：直接使用 release 包。

- 从 [GitHub Releases Latest](https://github.com/Virace/lol_extract_voice/releases/latest) 下载对应平台的 GUI 可执行文件。
- 直接运行下载到的 `LolAudioUnpack-<version>-windows-x64.exe`。

方式二：从源码启动 GUI。

```bash
git clone https://github.com/Virace/lol_extract_voice.git lol_audio_unpack
cd lol_audio_unpack
uv sync --extra gui
uv run unpack-gui
```

GUI 会始终围绕默认配置文件工作：

- 源码运行：当前工作目录下的 `lol-audio-unpack.ini`
- 打包运行：可执行文件同目录下的 `lol-audio-unpack.ini`
- GUI 从 `[app]` 读取共享配置、从 `[gui]` 读取界面偏好，并复用 `[wav]` 的转码默认参数

首次启动或切换游戏/输出目录时，GUI 默认只准备英雄和地图基础列表，列表可读后即可选择对象。
解包或映射任务会自动按所选目标准备 BIN 资源数据；未勾选事件映射时不准备事件数据，已有版本
缓存会复用，不需要先运行 CLI。

“全局设置 → 基础设置 → 提前准备数据”默认关闭。开启后，启动或切换版本时会自动补齐普通英雄
和地图的资源、事件数据，以减少之后任务的准备时间；不会每次强制重建已有缓存。准备期间显示
真实进度，完成后复检；失败时保留原因和“重试更新”“重新生成实体数据”等恢复入口。

实体总览的“特殊内容”与英雄、地图使用相同列表。“经典召唤师峡谷”英雄来自当前客户端，
无需额外扫描。搜索栏旁更多菜单中的“扫描本地 WAD…”只扫描用户选定且位于
`Game/DATA/FINAL` 的 `.wad.client`，用于发现额外资源包；扫描后仍需创建解包任务。
已解包但尚无 mapping 的实体仍可在“全部音频”中按 WEM 精确相对路径试听。
大型地图的全部音频在首次进入该预览时后台加载；事件预览不会提前扫描数万条 WEM，
列表上方的上下文行会显示已处理数、总数和进度条。切换到其他页面不会中断操作或构建隐藏列表；
后台索引完成后保留缓存，返回同一实体时直接复用事件树与全部音频模型，标签切换不会
重新扫描或把数万条记录再次装入模型。

在当前实体内点击“选择导出”，可按目录、事件节点或单条音频选择已有 WEM，支持排除项与撤销，
确认后批量导出 WAV；选择不会跨实体累积，也不会自动解包缺失文件。任务完成后可查看结果详情，
关闭通知后仍能从执行中心的“查看本次结果”恢复，并按明确的失败范围手动重试。

皮肤和炫彩按实际资源共享关系处理：纯继承事件不重复展开，有变化的事件保留完整音频列表，
共享 WEM 只在来源皮肤下输出一份。重复选择同一文件只转码一次，已有 WAV 默认跳过；
失败转码不会留下可被下次误用的正式输出。旧的重复音频不会自动删除，重新生成映射后可在资源信息
和原始数据中查看核对结果；全部音频仍展示实际磁盘文件。

可直接参考仓库内示例文件：

- [config/lol-audio-unpack.example.ini](./config/lol-audio-unpack.example.ini)

### CLI

安装：

```bash
git clone https://github.com/Virace/lol_extract_voice.git lol_audio_unpack
cd lol_audio_unpack
uv sync
```

当前 CLI 已改为动作式命令链：

```bash
uv run unpack <ACTION...> [OPTIONS]
```

推荐两种使用方式。

方式一：纯 CLI 显式参数。

```bash
uv run unpack update extract \
  --champions Annie,Ahri \
  --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "./output"

uv run unpack update extract wav mapping \
  --champions Annie \
  --wwiser-path "./tools/wwiser.pyz" \
  --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "./output"
```

方式二：显式配置文件模式。

1. 复制示例配置文件并按需修改：

```bash
cp config/lol-audio-unpack.example.ini ./lol-audio-unpack.ini
```

示例文件里：

- 未注释的项：通常是必填或最重要的项
- 被注释的项：表示当前默认值，可按需取消注释覆盖

2. 使用 `-c` 启用配置文件模式：

```bash
uv run unpack -c
```

若要指定其他配置文件路径：

```bash
uv run unpack -c ./config/custom.ini
```

CLI 参数总表：

- 通用参数
  - `-c, --config-file [PATH]`
  - `--game-path PATH`
  - `--output-path PATH`
  - `--game-region REGION`
  - `--exclude-type TYPES`
  - `--wwiser-path PATH`
  - `--group-by-type` / `--no-group-by-type`
  - `--with-bp-vo` / `--no-with-bp-vo`
  - `--max-workers N`
  - `-l, --log-level`
  - `--dev`
  - `--enable-league-tools-log`
- `update` 子命令
  - `--champions [IDs|ALIASES]`
  - `--maps [IDs]`
  - `-f, --force`
  - `--skip-events`
- `extract` 子命令
  - `--champions [IDs|ALIASES]`
  - `--maps [IDs]`
- `wav` 子命令
  - `--wav-workers N`
  - `--wav-timeout SECONDS`
  - `--wav-retries N`
  - `--wav-format {auto,pcm16,pcm24,pcm32,float}`
- `mapping` 子命令
  - `--champions [IDs|ALIASES]`
  - `--maps [IDs]`
  - `--integrate-data`

注意：

- 不写 `-c` 时，本次命令只使用内建默认值和 CLI 显式参数。
- 写了 `-c` 后，当前命令会进入完整配置文件模式，只允许提供配置文件路径；动作与参数都从配置文件读取。
- `champions` / `maps` 需要写在 `[targets]` 中；`max_workers` 写在 `[runtime]` 中；动作启用状态分别写在 `[update]` / `[extract]` / `[wav]` / `[mapping]` 的 `enable` 中；其余动作参数写在对应 section 中。
- `game_path` 可以指向已安装客户端，也可以指向外部工具准备的等价本地目录；程序只读取本地
  文件，不会自动下载或回退到网络来源。
- 旧 `.lol.env` / `LOL_*` 方式已经不再是当前主线用法。

更详细的 CLI、配置与已准备本地目录说明见：

- [docs/README.md](./docs/README.md)
- [docs/api/cli_api.md](./docs/api/cli_api.md)
- [docs/api/config_api.md](./docs/api/config_api.md)
- [docs/api/prepared_source.md](./docs/api/prepared_source.md)

## 后续处理

当前工具专注于更新、解包、WAV 转码与映射生成；更复杂的后处理仍建议独立完成。

- 本工具默认输出原始 `.wem` 文件。
- GUI 与 CLI 已支持内置 WAV 转码；实体总览可试听、另存单文件，也可在“选择导出”模式批量导出
  当前实体的已有 WEM。支持全选、清空、撤销和仅看已选，导出前核对范围与覆盖策略。
- 任务结束后，居中通知可打开结果详情；关闭通知仍可从执行中心标题区恢复。失败重试会先展示
  实际处理范围，不把容器或阶段重跑冒充为单个音频重试。
- 若需要额外的批量后处理或特殊格式转换，可继续使用配套的 [vgmstream-cli-build](https://github.com/Virace/vgmstream-cli-build/releases)。

示例：

```bash
.\vgmstream-cli.exe -o "?p?b.wav" "D:/audios"
```

## 维护者

**Virace**

- blog: [孤独的未知数](https://x-item.com)

## 感谢

- [@Morilli](https://github.com/Morilli/bnk-extract), **bnk-extract**
- [@Pupix](https://github.com/Pupix/lol-file-parser), **lol-file-parser**
- [@CommunityDragon](https://github.com/CommunityDragon/CDTB), **CDTB**
- [@vgmstream](https://github.com/vgmstream/vgmstream), **vgmstream**
- 以及 **JetBrains** 提供开发环境支持

  <a href="https://www.jetbrains.com/?from=kratos-pe" target="_blank"><img src="https://cdn.jsdelivr.net/gh/virace/kratos-pe@main/jetbrains.svg"></a>

## 许可证

[GPLv3](LICENSE)
