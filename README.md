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
4. 编写配置文件, 详见[配置文件](config.py)
5. 运行 python main.py

### 开发进度
- [x] 功能实现
- [x] 降低代码复杂度
- [ ] 版本区分
- [ ] 降低后续文件更新难度
- [ ] 文件打包
- [ ] GUI



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
