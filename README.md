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

### CLI

安装：

```bash
git clone https://github.com/Virace/lol_audio_unpack.git
cd lol_audio_unpack
uv sync
```

全部解包示例：

```bash
uv run unpack --update --extract --skip-events
```

CLI 参数总表：

- 数据更新组
  - `--update`
  - `--update-champions [IDs|ALIASES]`
  - `--update-maps [IDs]`
  - `-f, --force`
  - `--skip-events`
- 音频解包组
  - `--extract`
  - `--extract-champions [IDs|ALIASES]`
  - `--extract-maps [IDs]`
- 映射组
  - `--mapping`
  - `--mapping-champions [IDs|ALIASES]`
  - `--mapping-maps [IDs]`
  - `--integrate-data`
- 通用参数
  - `--max-workers N`
  - `-l, --log-level`
  - `--dev`
  - `--with-bp-vo` / `--no-with-bp-vo`
  - `--enable-league-tools-log`
  - `--cleanup-remote` / `--no-cleanup-remote`
- 配置覆盖参数
  - `-g, --game-path PATH`
  - `-o, --output-path PATH`
  - `-r, --game-region REGION`
  - `-t, --exclude-type TYPES`
  - `-w, --wwiser-path PATH`
  - `-b, --group-by-type` / `--no-group-by-type`

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
