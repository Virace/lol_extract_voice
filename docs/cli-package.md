# 控制台使用说明

从 [GitHub Releases](https://github.com/Virace/lol_extract_voice/releases/latest) 下载 Windows x64 控制台版，在 PowerShell 中运行。
下文用 `LolAudioUnpack-CLI.exe` 简写程序名，请替换为实际文件名。

控制台独立包是源码程序的打包形式，参数与输出规则相同。从源码运行时，将 `.\LolAudioUnpack-CLI.exe`
换为 `uv run unpack`；安装方法见 [README](../README.md#从仓库运行)。
Linux、macOS 等系统使用同一源码入口，将示例中的游戏目录替换为本机路径即可。

## 动作与参数

| 动作 | 用途 | 输出目录 |
| --- | --- | --- |
| `update` | 准备英雄、地图资料 | `manifest/` |
| `extract` | 提取原始 WEM | `audios/` |
| `wav` | 将已提取音频转为 WAV | `wavs/` |
| `mapping` | 生成事件与音频的对应关系 | `hashes/` |

四个动作可组合使用。首次处理请带上 `update`，转码前需要已有解包结果。
`export-json` 和 `convert-wem` 是独立命令，不能与上述动作组合。

| 参数 | 说明 |
| --- | --- |
| `--game-path` | 本地游戏目录 |
| `--output-path` | 输出根目录，默认 `./output` |
| `--champions` | 英雄 ID 或英文别名，逗号分隔，如 `1,17` 或 `Annie,Teemo` |
| `--maps` | 地图 ID，逗号分隔；`0` 为常规公共资源 |
| `--exclude-type` | 排除 `VO`、`SFX`、`MUSIC` 中的一项或多项；默认 `SFX,MUSIC`，全部类型用 `--exclude-type=` |
| `--game-region` | 资源语言，默认 `zh_CN` |

英雄选择会包含各皮肤。相对路径以当前终端目录为起点，默认输出到 `./output`。
结果位置与文件共享规则见 [音频文件与输出目录](audio-and-output.md)。

<a id="audio-types"></a>

## 音频筛选

`--exclude-type` 用来排除类型，类型名用大写，多个值以逗号分隔。默认排除 `SFX,MUSIC`。
`VO` 是语音，`SFX` 是音效，`MUSIC` 是音乐，分组说明见 [音频类型](audio-and-output.md#audio-types)。

| 需要处理的类型 | 参数 |
| --- | --- |
| VO 语音（默认） | 不加筛选参数，或 `--exclude-type SFX,MUSIC` |
| 所有类型 | `--exclude-type=` |
| 音效和音乐 | `--exclude-type VO` |
| 语音和音效 | `--exclude-type MUSIC` |

完整参数见 [控制台参数参考](api/cli_api.md#audio-types)。

## 常用命令

### 查看帮助与版本

```powershell
.\LolAudioUnpack-CLI.exe --help
.\LolAudioUnpack-CLI.exe --version
```

### 提取英雄音频

```powershell
# 提取安妮、提莫的全部音频，直接生成 WAV
.\LolAudioUnpack-CLI.exe update extract wav --champions Annie,Teemo --exclude-type= --game-path "D:/Games/英雄联盟" --output-path .\output
```

只要语音时省略 `--exclude-type=`；排除音乐用 `--exclude-type MUSIC`，需要事件查询时再加 `mapping`。

### 提取常规公共音效

```powershell
# 解包常规公共音效并生成映射，保留 WEM，不转码
.\LolAudioUnpack-CLI.exe update extract mapping --maps 0 --exclude-type VO,MUSIC --game-path "D:/Games/英雄联盟"
```

只需要事件查询、不提取音频时，可省略 `extract`。

### 转码已有音频

```powershell
# 将已解包的英雄音频转为 WAV
.\LolAudioUnpack-CLI.exe wav --champions Annie,Teemo --game-path "D:/Games/英雄联盟"
```

<a id="config-file"></a>

### 使用配置文件

```powershell
# 从配置文件读取动作和参数
.\LolAudioUnpack-CLI.exe -c .\任务.ini
```

`-c` 与命令行动作、参数互斥；省略配置路径时读取 `config/lol-audio-unpack.ini`。
可参考 [示例配置](../config/lol-audio-unpack.example.ini)，完整约定见 [配置文件模式](api/cli_api.md#config-file)。

## 导出映射 JSON

`export-json` 按英雄或地图 ID 查找已有映射，完整导出为 JSON。查询事件对应的音频 ID 需要先执行 `mapping`。

```powershell
.\LolAudioUnpack-CLI.exe export-json --maps 0 --json-output .\common.json
```

导出英雄映射时，将 `--maps 0` 换为 `--champions 1`。每次指定一个 ID，多版本时用 `--game-version` 选择。
`--json-output` 指定 JSON 文件，省略则写入标准输出。JSON 字段与版本选择规则见
[映射导出 API](api/cli_api.md#export-json)。

## 独立 WEM 转码

`convert-wem` 接受单个文件、多个文件或文本清单，使用内置转码后端。它独立于英雄、地图和主流程配置。

**单个文件：**

```powershell
.\LolAudioUnpack-CLI.exe convert-wem --input "D:/音频/200504484.wem" --output-path .\selected-wavs
```

**多个文件：**

```powershell
.\LolAudioUnpack-CLI.exe convert-wem --input "D:/音频/a.wem" "D:/音频/b.wem" --output-path .\selected-wavs
```

**从清单批量转码：**

```powershell
.\LolAudioUnpack-CLI.exe convert-wem --input-list .\selected.txt --output-path .\selected-wavs --wav-workers 4 --wav-format pcm16
```

| 选项 | 使用方法 |
| --- | --- |
| 文本清单 | UTF-8，每行一个 WEM 路径；相对路径以清单所在目录为起点 |
| 输出目录 | 用 `--output-path` 指定，默认 `./output/wavs` |
| 已有文件 | 默认跳过，`--overwrite` 可覆盖 |
| 采样格式 | 默认 `pcm16`，其他格式见 [WAV 参数](api/cli_api.md#wav-options) |

路径布局、清单格式与其他参数见 [独立转码 API](api/cli_api.md#convert-wem)，也可运行 `convert-wem --help`。

## 输出与诊断

文件位置见 [统一输出目录](audio-and-output.md#output-folders)。Ctrl+C 可取消任务。
PowerShell 用 `$LASTEXITCODE` 查看退出码，含义见 [退出语义](api/cli_api.md#exit-status)。
转码工具异常时，可运行：

```powershell
.\LolAudioUnpack-CLI.exe --check-tools .\诊断\tools.json --check-cancel
```

其他问题见 [常见问题](faq.md)，完整参数见 [控制台参数参考](api/cli_api.md)。
