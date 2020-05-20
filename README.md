# lol_extract_voice

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)

提取英雄联盟中游戏内音频文件

1. 先将WAD文件解包
2. 区分出音频文件(bkn, wpk), 进行解包转码

## 内容列表

- [安装](#安装)
- [使用说明](#使用说明)
- [相关仓库](#相关仓库)
- [维护者](#维护者)
- [使用许可](#使用许可)

## 安装

这个项目使用 [Python](https://www.python.org)。请确保你本地已经安装了。

```shell script
python -m pip install -r requirements.txt
```

## 使用说明

首先按实际情况修改**Config.py**中, **GAME_PATH**和**OUT_PATH**

然后执行脚本
```shell script
python Start.py
```

代码中增加了大量的注释, 帮助修改
## 相关仓库

- [CTDB](https://github.com/CommunityDragon/CDTB) — 💌 A toolbox to work with League of Legends game files and export files for CDragon. It can be used as a library or a command-line tool.
- [RavioliGameTools](http://www.scampers.org/steve/sms/other.htm#ravioli_download) — 💌 The Ravioli Game Tools are a set of programs to explore, analyze and extract files from various game resource files. 

## 维护者

[@Virace](https://github.com/Virace) 


## 使用许可

[MIT](LICENSE) © Apache License



