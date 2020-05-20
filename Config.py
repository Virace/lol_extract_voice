import os
import sys
import json


base = os.path.dirname(__file__)

# 将目录中CDTB加入环境变量, 试得代码中可以直接导入包
# 但是Start.py中需要将引入Config放入前面
sys.path.append(os.path.join(base, "tools", "CDTB"))

# 游戏目录
GAME_PATH = r'D:\Games\Ol\Tencent\League of Legends'

# 输出目录
OUT_PATH = r'E:\Caches\Office\Temp'

# RExtractorConsole CLI
REC_CLI = os.path.join(base, 'tools', 'RavioliGameTools', 'RExtractorConsole.exe')

# 解包哪个国家, 需要什么填写什么.
# 如果留空则选取所有WAD文件, 小写
REGION = 'zh_cn'

# 最终文件夹是否用中文英雄名保存
CHINESE = True

# 读取英雄中文信息, 涉及到中文内容文件. 注意编码
CHAMPION_INFO = json.load(open(os.path.join(base, 'data', 'champion-summary.json'), encoding='utf-8'))
