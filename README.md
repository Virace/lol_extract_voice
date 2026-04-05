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

---

- [介绍](#介绍)
- [当前代码结构](#当前代码结构)
- [使用方法](#使用方法)
- [后续处理](#后续处理)
- [维护者](#维护者)
- [感谢](#感谢)
- [许可证](#许可证)

## 介绍

- 支持提取英雄与地图的 `VO`、`SFX`、`MUSIC` 音频。
- 默认输出原始 `.wem` 文件，文件名保留游戏数据中的原始 ID。
- 数据更新阶段会携带事件信息，可进一步用于映射生成。
- GUI 当前已完成：执行解包、生成映射、查看映射。

文档导航、GUI 当前状态、Remote 模式、基准测试与设计说明见：

- [docs/README.md](./docs/README.md)
- [docs/API.md](./docs/API.md)

## 当前代码结构

- 根包 `lol_audio_unpack`：保留 `setup_app` 与 `__version__` 两个顶层入口。
- 应用编排层：`src/lol_audio_unpack/app/`，负责 `AppContext`、`OperationOptions`、`LolAudioUnpackApp` 与 remote 工作流。
- 配置层：`src/lol_audio_unpack/config/`，集中维护共享设置 schema 与标准 INI 读写。
- CLI 入口：`src/lol_audio_unpack/cli/`，`unpack` / `mapping` console script 共用同一套动作式解析与调度实现。
- 核心流水线：`src/lol_audio_unpack/unpack/` 负责音频解包，`src/lol_audio_unpack/mapping/` 负责事件映射。
- 运行时支持：`src/lol_audio_unpack/runtime/remote/` 负责 remote 准备，`src/lol_audio_unpack/runtime/wav/` 负责独立 WAV 转码 stage。
- 共享模型与数据层：`src/lol_audio_unpack/model/`、`src/lol_audio_unpack/manager/`。
- GUI：`src/lol_audio_unpack/gui/`，当前围绕执行中心、总览与设置页展开。

## 使用方法

### GUI

方式一：直接使用 release 包。

- 从 GitHub Releases 下载对应平台的发布包。
- 解压后直接运行其中的 GUI 可执行文件。

方式二：从源码启动 GUI。

```bash
git clone https://github.com/Virace/lol_audio_unpack.git
cd lol_audio_unpack
uv sync --extra gui
uv run unpack-gui
```

GUI 会始终围绕默认配置文件工作：

- 源码运行：当前工作目录下的 `lol-audio-unpack.ini`
- 打包运行：可执行文件同目录下的 `lol-audio-unpack.ini`
- GUI 只消费 `[app]` 分组；动作分组仅供 CLI 的 profile 模式使用

可直接参考仓库内示例文件：

- [config/lol-audio-unpack.example.ini](./config/lol-audio-unpack.example.ini)

### CLI

安装：

```bash
git clone https://github.com/Virace/lol_audio_unpack.git
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
  - `--source-mode {local_path,remote_snapshot}`
  - `--exclude-type TYPES`
  - `--wwiser-path PATH`
  - `--group-by-type` / `--no-group-by-type`
  - `--remote-live-region REGION`
  - `--cleanup-remote` / `--no-cleanup-remote`
  - `--remote-version VERSION`
  - `--remote-lcu-manifest-url URL`
  - `--remote-game-manifest-url URL`
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
- 旧 `.lol.env` / `LOL_*` 方式已经不再是当前主线用法。

更详细的 CLI / 配置 / Remote 使用说明见：

- [docs/README.md](./docs/README.md)
- [docs/api/cli_api.md](./docs/api/cli_api.md)
- [docs/api/config_api.md](./docs/api/config_api.md)
- [docs/api/remote_mode.md](./docs/api/remote_mode.md)

## 后续处理

当前工具专注于更新、解包与映射生成；后处理仍建议独立完成。

- 本工具输出原始 `.wem` 文件。
- 音频试听、转码等能力当前未在 GUI 内完成。
- 若需要转码，可使用配套的 [vgmstream-cli-build](https://github.com/Virace/vgmstream-cli-build/releases)。

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
