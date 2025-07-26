# lol_audio_unpack (v3-lite)
![](https://img.shields.io/badge/python-%3E%3D3.10-blue)

一个极简、高效的英雄联盟音频提取工具。

---

### **关于 v3-lite 分支**
`v3-lite` 是一个追求**速度**和**纯粹性**的轻量级分支。它的核心目标是以最快的方式解包英雄相关的音频文件，不进行任何多余的分析和处理。

-   **专注核心功能**: 仅包含英雄音频解包。
-   **原始数据**: 输出的音频文件名将保留其在游戏数据中的原始ID (`.wem`格式)，不会进行重命名或分类。
-   **不包含**:
    -   地图、UI等非英雄音频的解包。
    -   音频事件分析（如技能触发、台词分类等）。
    -   内置的音频转码功能。

对于需要完整事件分析和自动分类的用户，请关注主分支的开发。

---

- [介绍](#介绍)
- [使用方法](#使用方法)
- [设计哲学](#设计哲学)
- [性能参考](#性能参考)
- [后续处理：音频转码](#后续处理音频转码)
- [维护者](#维护者)
- [感谢](#感谢)
- [许可证](#许可证)


### 介绍
提取联盟客户端中的英雄音频文件，专注于提供原始、未处理的音频数据。

### 使用方法
1.  **克隆仓库**:
    ```bash
    git clone https://github.com/Virace/lol_audio_unpack.git -b v3-lite
    cd lol_audio_unpack
    ```

2.  **安装依赖**:
    *   **方式一: 使用 `uv` (推荐)**
        ```bash
        # 安装uv (如果尚未安装)
        pip install uv
        # 使用uv安装依赖和项目
        uv pip install .
        ```
    *   **方式二: 使用 `pip`**
        ```bash
        pip install .
        ```

3.  **编写配置文件**:
    在项目根目录创建 `.lol.env` 或 `.lol.env.dev` 文件。详见[配置文件](#配置文件)。

4.  **运行脚本**:
    所有命令都需要在项目根目录执行。

    ```bash
    # 1. 更新数据 (首次运行或游戏更新后执行一次即可)
    python -m lol_audio_unpack --update-data

    # 2. 解包音频
    # 解包所有英雄 (使用默认4线程)
    python -m lol_audio_unpack --all

    # 或，解包所有英雄 (使用8个线程)
    python -m lol_audio_unpack --all --max-workers 8

    # 或，解包指定ID的英雄 (例如，解包英雄ID为555的派克)
    python -m lol_audio_unpack --hero-id 555
    ```

#### 配置文件
项目将从根目录下的 `.lol.env` 文件加载配置。如果存在 `.lol.env.dev` 文件，则会优先加载后者（开发模式）。

所有配置项也可以通过环境变量提供（例如 `export LOL_GAME_PATH=/path/to/game`），这在CI/CD环境中非常有用。

```dotenv
# 游戏客户端根目录 (例如: D:\Games\League of Legends)
LOL_GAME_PATH=''

# 游戏语言区域 (例如: zh_CN, en_US, ko_KR)
LOL_GAME_REGION='zh_CN'

# 数据输出目录
LOL_OUTPUT_PATH=''

# 包含的音频类型 (VO: 语音, SFX: 特效, MUSIC: 音乐), 使用英文逗号分割
# 注意：当前解包逻辑主要针对 VO 类型，其他类型可能无法正确解包
LOL_INCLUDE_TYPE='VO'
```

### 设计哲学
-   **速度优先**: 通过简化的处理流程和优化的文件I/O，最大化解包效率。
-   **数据纯粹**: 不对文件进行任何形式的重命名或分类。文件名即ID，保留了数据的原始性，方便后续工具进行二次处理。
-   **责任分离**: 核心解包功能与音频转码等后处理步骤完全解耦。本工具只做一件事：快速解包。

### 性能参考
在典型的开发环境 (SSD, 多核CPU)下，测试数据如下：
- **解包**: 使用4线程解包全部英雄语音，耗时约 **15 秒**。
- **转码**: 将所有解包后的 `.wem` 文件转码为 `.wav`，耗时约 **15 分钟**。

### 后续处理：音频转码
本工具输出的音频文件为 `.wem` 格式。为了方便播放和使用，你可能需要将它们转换为 `.mp3` 或 `.wav` 等常见格式。

我们现在提供了一个**魔改版的 [vgmstream-cli](https://github.com/Virace/vgmstream-cli-build)** 工具，它支持以下增强功能：

1. **目录递归处理**：可以直接指定包含 `.wem` 文件的目录，工具会自动递归扫描并处理所有文件。
2. **增强的输出路径通配符**：
   * `?p`: 代表源文件的完整路径（包含最后的路径分隔符）。
   * `?b`: 代表源文件的基础名称（不含扩展名）。
3. **源文件删除选项**：通过 `-Y` 参数可以在转换成功后删除源文件。**⚠️ 注意：这是一个危险操作，请谨慎使用！**

#### 使用方法
- **命令行直接调用**:
  假设你的音频文件位于 `D:/audios` 目录下：
  ```bash
  # 将所有 .wem 文件转换为 .wav 格式，并保持原始目录结构
  .\vgmstream-cli.exe -o "?p?b.wav" "D:/audios"

  # 转换并删除原始的 .wem 文件（谨慎使用！）
  .\vgmstream-cli.exe -o "?p?b.wav" "D:/audios" -Y
  ```
- **使用测试脚本进行批量转码**:
  项目提供了一个测试脚本，可以方便地进行批量转码并验证结果。
  ```bash
  python tests/test_transcode.py
  ```
  > **注意**: 脚本中的 `vgmstream-cli.exe` 路径是硬编码的。如果你的路径不同，请直接修改 `tests/test_transcode.py` 文件中的路径。

你可以从 [Virace/vgmstream-cli-build](https://github.com/Virace/vgmstream-cli-build/releases) 下载最新版本的魔改工具。

**注意**: 如果你准备将所有提取的英雄语音转码为WAV格式，请确保有足够的硬盘空间。15.14版本所有VO相关WEM音频总共大小接近3G，转码后文件大小接近**40G**。

这种方式将转码与核心逻辑分离，让你可以自由选择是否需要以及如何进行格式转换。

### 维护者
**Virace**
- blog: [孤独的未知数](https://x-item.com)

### 感谢
- [@Morilli](https://github.com/Morilli/bnk-extract), **bnk-extract**
- [@Pupix](https://github.com/Pupix/lol-file-parser), **lol-file-parser**
- [@CommunityDragon](https://github.com/CommunityDragon/CDTB), **CDTB**
- [@vgmstream](https://github.com/vgmstream/vgmstream), **vgmstream**
- 以及**JetBrains**提供开发环境支持
  <a href="https://www.jetbrains.com/?from=kratos-pe" target="_blank"><img src="https://cdn.jsdelivr.net/gh/virace/kratos-pe@main/jetbrains.svg"></a>

### 许可证
[GPLv3](LICENSE)
