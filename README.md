# lol_extract_voice
![](https://img.shields.io/badge/python-%3E%3D3.8-blue)

批量提取联盟中音频文件


- [介绍](#介绍)
- [安装](#安装)
- [使用](#使用)
- [维护者](#维护者)
- [感谢](#感谢)
- [许可证](#许可证)


### 介绍
提取联盟中音频文件, 并且生成事件ID与音频ID对应哈希表. 详见[lol-audio-events-hashtable](https://github.com/Virace/lol-audio-events-hashtable)



### 安装

因为部分代码使用了新版本特性, 比如: 海象表达式等. 所以Python版本最低为3.8

`pip install -r requirements.txt`

环境中有一个包是从GitHub安装的, 详情见: [py-bnk-extract](https://github.com/Virace/py-bnk-extract)

### 使用
使用前查看[index.py](index.py), main函数文档. 

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
