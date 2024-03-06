# lol_extract_voice
![](https://img.shields.io/badge/python-%3E%3D3.10-blue)

批量提取联盟中音频文件


- [介绍](#介绍)
- [使用方法](#使用方法)
- [开发进度](#开发进度)
- [维护者](#维护者)
- [感谢](#感谢)
- [许可证](#许可证)


### 介绍
提取联盟中音频文件, 并且生成事件ID与音频ID对应哈希表. 详见[lol-audio-events-hashtable](https://github.com/Virace/lol-audio-events-hashtable)

### 使用方法
1. git clone https://github.com/Virace/lol_extract_voice -b v3
2. 安装peotry, https://python-poetry.org/docs/master/#installation
3. 进入目录 poetry install
4. 编写配置文件, 详见[配置文件](#配置文件)
5. 运行 python main.py

#### 配置文件
```python
# 游戏目录
GAME_PATH: str = ''

# 输出目录
OUTPUT_PATH: str = ''

# 要处理的区域文件
GAME_REGION: str = 'zh_CN'

# 排除处理的类型 (VO/SFX/MUSIC) 台词音频/效果音频/背景音乐
EXCLUDE_TYPE: list = ['SFX']

# vgmstream cli程序, 用来转码, 如果不提供则默认输出为wem格式。
VGMSTREAM_PATH: str = ''
```
**GAME_PATH**选择游戏根目录, 例如: `D:\Games\League of Legends`，这个文件夹打开里面会有`Game`文件夹。

**GAME_REGION**就是各种区域代码, 例如: `zh_CN`，`en_US`，`ko_KR`，`ja_JP`，`es_ES`，`fr_FR`，`de_DE`，`it_IT`，`pl_PL`，`pt_BR`，`ro_RO`，`ru_RU`，`tr_TR`等等。

**EXCLUDE_TYPE**一般只处理语音的话, 可以排除掉SFX和MUSIC, 例如: `['SFX', 'MUSIC']`。

另外增加了对环境变量的支持，前缀为**LOL_xxx**，比如**LOL_GAME_PATH**，**LOL_OUTPUT_PATH**，**LOL_GAME_REGION**，**LOL_EXCLUDE_TYPE**，**LOL_VGMSTREAM_PATH**。

正常情况下config.py手动填写以及环境变量互补，手动填写优先级最高，如果没有填写留空则会使用环境变量。

也可将**LOL_ENV_ONLY**设置为**True**(非`0`
、`false`的字符串或留空 都可以)，则只使用环境变量。方便第三方工具调用。

### 开发进度
- [x] 功能实现
- [x] 降低代码复杂度
- [x] 增加对图片资源提取
- [ ] 版本区分
- [x] 降低后续文件更新难度
- [ ] 文件打包
- [ ] ~~GUI~~



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
