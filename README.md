# lol_extract_voice
![](https://img.shields.io/badge/python-%3E%3D3.8-blue)

批量提取联盟中音频文件


- [介绍](#介绍)
- [安装](#安装)
- [使用](#使用)
- [问题](#问题)
- [维护者](#维护者)
- [感谢](#感谢)
- [许可证](#许可证)


### 介绍
提取联盟中音频文件, 并且生成事件ID与音频ID对应哈希表. 详见[lol-audio-events-hashtable](https://github.com/Virace/lol-audio-events-hashtable)

v2版本相对于之前的版本有比较大的更新:
  - 支持输出事件, 意思就是现在你可以知道那个语音是在什么情况下触发得了
  - 多进程提取, 提取速度从原来的15-20分钟到现在的5-6分钟. (测试环境i7-8750H, 默认配置满载提取) 这还是增加了上面功能后的事件. (实测在3950X下只需要2分钟, 未满载)

### 安装
```shell
git clone --recurse-submodules -b v2 https://github.com/Virace/lol_extract_voice
```
注意子模块CDTB的哈希表更新, 
```shell
git submodule update --remote
```

如果你clone的时候没有添加 **--recurse-submodules** 参数, 也可以在之后执行
```shell
git submodule init
```

因为部分代码使用了新版本特性, 比如: 海象表达式等. 所以Python版本最低为3.8

```shell
pip install -r requirements.txt
```

环境中有一个包是从GitHub安装的, 详情见: [py-bnk-extract](https://github.com/Virace/py-bnk-extract)

### 使用
使用前查看[index.py](index.py), main函数文档. 

直接进入目录新建test.py, (名字无要求)
```python
from index import main
main(r'C:\League of Legends',
     r"C:\Out",
     r'C:\vgmstream-win\test.exe',
     'zh_cn',
     'wav',
     5)
```
第三个参数为vgmstream工具, 可以在这里下载[https://vgmstream.org/downloads](https://vgmstream.org/downloads), 用于转码.
最后一个参数为多进程数量, 如果需要满载就不填写就行. 总线程超过32的CPU请手动填写实际数量.

### 问题
- 多余代码未整理
- 注释过少
- 除zh_cn外区域未测试

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
