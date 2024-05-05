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
2. 进入目录 `pip install -r requirements.txt` 或者  `pip install -r requirements.lock`
3. 编写配置文件, 详见[配置文件](#配置文件)
4. 运行 python main.py

#### 配置文件

项目目录下.lol.env文件或是环境变量`LOL_ENV_PATH`提供的文件路径, https://saurabh-kumar.com/python-dotenv/#file-format

```
# 游戏目录
LOL_GAME_PATH=''

# 区域代码
LOL_GAME_REGION=zh_CN

# 输出目录
LOL_OUTPUT_PATH=''

# 排除类型 VO、SFX、MUSIC， 语音、特效、背景音乐。使用英文逗号分割('VO,SFX,MUSIC')
LOL_EXCLUDE_TYPE='SFX,MUSIC'

# vgmstream可执行文件路径(vgmstream-cli.exe)，为空则不会转码
LOL_VGMSTREAM_PATH=''
```
**GAME_PATH**选择游戏根目录, 例如: `D:\Games\League of Legends`，这个文件夹打开里面会有`Game`文件夹。

**GAME_REGION**就是各种区域代码, 例如: `zh_CN`，`en_US`，`ko_KR`，`ja_JP`，`es_ES`，`fr_FR`，`de_DE`，`it_IT`，`pl_PL`，`pt_BR`，`ro_RO`，`ru_RU`，`tr_TR`等等。

---
以下是第三方程序或者CI/CD使用的优化

`LOL_ENV_PATH`环境变量, 用于指定配置文件路径, 例如: `/root/.lol.env`。默认为项目执行目录。

`LOL_ENV_ONLY`环境变量, 用于指定是否只使用环境变量, 例如: `True`。默认为`False`, 如果设置为`True`, 则不会读取配置文件。

所有配置文件中提到的项目均可设置环境变量传入，方便CI/CD使用。


### 开发进度
- [x] 功能实现
- [x] 降低代码复杂度
- [x] 增加对图片资源提取
- [x] 版本区分
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
