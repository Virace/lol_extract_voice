#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2020/11/29 2:59
# @Author  : Virace and yanmeng2
# @Email   : Virace@aliyun.com
# @Site    : https://x-item.com
# @File    : asr.py
# @Update  : 2020/11/29 2:59
# @Software: PyCharm
# @Detail  : 讯飞 非实时转写调用demo

import base64
import hashlib
import hmac
import json
import os
import time

import requests
from concurrent.futures import ThreadPoolExecutor

lfasr_host = 'http://raasr.xfyun.cn/api'

# 请求的接口名
api_prepare = '/prepare'
api_upload = '/upload'
api_merge = '/merge'
api_get_progress = '/getProgress'
api_get_result = '/getResult'
# 文件分片大小10M
file_piece_sice = 10485760

# ——————————————————转写可配置参数————————————————
# 参数可在官网界面（https://doc.xfyun.cn/rest_api/%E8%AF%AD%E9%9F%B3%E8%BD%AC%E5%86%99.html）查看，根据需求可自行在gene_params方法里添加修改
# 转写类型
lfasr_type = 0
# 是否开启分词
has_participle = 'false'
has_seperate = 'true'
# 多候选词个数
max_alternatives = 0
# 子用户标识
suid = ''


class SliceIdGenerator:
    """slice id生成器"""

    def __init__(self):
        self.__ch = 'aaaaaaaaa`'

    def getNextSliceId(self):
        ch = self.__ch
        j = len(ch) - 1
        while j >= 0:
            cj = ch[j]
            if cj != 'z':
                ch = ch[:j] + chr(ord(cj) + 1) + ch[j + 1:]
                break
            else:
                ch = ch[:j] + 'a' + ch[j + 1:]
                j = j - 1
        self.__ch = ch
        return self.__ch


appid = "*****"
secret_key = "****"


# 根据不同的apiname生成不同的参数,本示例中未使用全部参数您可在官网(https://doc.xfyun.cn/rest_api/%E8%AF%AD%E9%9F%B3%E8%BD%AC%E5%86%99.html)查看后选择适合业务场景的进行更换
def gene_params(apiname, upload_file_path=None, taskid=None, slice_id=None):
    ts = str(int(time.time()))
    m2 = hashlib.md5()
    m2.update((appid + ts).encode('utf-8'))
    md5 = m2.hexdigest()
    md5 = bytes(md5, encoding='utf-8')
    # 以secret_key为key, 上面的md5为msg， 使用hashlib.sha1加密结果为signa
    signa = hmac.new(secret_key.encode('utf-8'), md5, hashlib.sha1).digest()
    signa = base64.b64encode(signa)
    signa = str(signa, 'utf-8')
    param_dict = {}

    if apiname == api_prepare:
        file_len = os.path.getsize(upload_file_path)
        file_name = os.path.basename(upload_file_path)
        # slice_num是指分片数量，如果您使用的音频都是较短音频也可以不分片，直接将slice_num指定为1即可
        # slice_num = int(file_len / file_piece_sice) + (0 if (file_len % file_piece_sice == 0) else 1)
        param_dict['app_id'] = appid
        param_dict['signa'] = signa
        param_dict['ts'] = ts
        param_dict['file_len'] = str(file_len)
        param_dict['file_name'] = file_name
        param_dict['slice_num'] = '1'
    elif apiname == api_upload:
        param_dict['app_id'] = appid
        param_dict['signa'] = signa
        param_dict['ts'] = ts
        param_dict['task_id'] = taskid
        param_dict['slice_id'] = slice_id
    elif apiname == api_merge:
        file_name = os.path.basename(upload_file_path)
        param_dict['app_id'] = appid
        param_dict['signa'] = signa
        param_dict['ts'] = ts
        param_dict['task_id'] = taskid
        param_dict['file_name'] = file_name
    elif apiname == api_get_progress or apiname == api_get_result:
        param_dict['app_id'] = appid
        param_dict['signa'] = signa
        param_dict['ts'] = ts
        param_dict['task_id'] = taskid
    return param_dict


# 请求和结果解析，结果中各个字段的含义可参考：https://doc.xfyun.cn/rest_api/%E8%AF%AD%E9%9F%B3%E8%BD%AC%E5%86%99.html
def gene_request(apiname, data, files=None, headers=None):
    response = requests.post(lfasr_host + apiname, data=data, files=files, headers=headers)
    result = json.loads(response.text)
    if result["ok"] == 0:
        # print("{} success:".format(apiname) + str(result))
        return result
    else:
        # print("{} error:".format(apiname) + str(result))
        exit(0)
        return result


# 上传
def upload_request(taskid, upload_file_path):
    file_object = open(upload_file_path, 'rb')
    try:
        index = 1
        sig = SliceIdGenerator()
        while True:
            content = file_object.read(file_piece_sice)
            if not content or len(content) == 0:
                break
            files = {
                "filename": gene_params(api_upload).get("slice_id"),
                "content": content
            }
            response = gene_request(api_upload,
                                    data=gene_params(api_upload, taskid=taskid,
                                                     slice_id=sig.getNextSliceId()),
                                    files=files)
            if response.get('ok') != 0:
                # 上传分片失败
                print('upload slice fail, response: ' + str(response))
                return False
            # print('upload slice ' + str(index) + ' success')
            index += 1
    finally:
        'file index:' + str(file_object.tell())
        file_object.close()
    return True


# 合并
def merge_request(taskid, upload_file_path):
    return gene_request(api_merge, data=gene_params(api_merge, upload_file_path, taskid=taskid))


# 获取进度
def get_progress_request(taskid):
    return gene_request(api_get_progress, data=gene_params(api_get_progress, taskid=taskid))


# 获取结果
def get_result_request(taskid):
    return gene_request(api_get_result, data=gene_params(api_get_result, taskid=taskid))


def all_api_request(upload_file_path):
    # 1. 预处理
    pre_result = gene_request(apiname=api_prepare, data=gene_params(api_prepare, upload_file_path))
    taskid = pre_result["data"]
    # 2 . 分片上传
    upload_request(taskid=taskid, upload_file_path=upload_file_path)
    # 3 . 文件合并
    merge_request(taskid=taskid, upload_file_path=upload_file_path)
    # 4 . 获取任务进度
    while True:
        # 每隔20秒获取一次任务进度
        progress = get_progress_request(taskid)
        progress_dic = progress
        if progress_dic['err_no'] != 0 and progress_dic['err_no'] != 26605:
            # print('task error: ' + progress_dic['failed'])
            return
        else:
            data = progress_dic['data']
            task_status = json.loads(data)
            if task_status['status'] == 9:
                # print('task ' + taskid + ' finished')
                break
            # print('The task ' + taskid + ' is in processing, task status: ' + str(data))

        # 每次获取进度间隔20S
        time.sleep(5)
    # 5 . 获取结果
    return get_result_request(taskid=taskid)


def data_format(file_dir, _id):
    data = all_api_request(os.path.join(file_dir, _id+'.wav'))

    if data['err_no'] != 0:
        return
    if data['data']:
        skin = os.path.basename(file_dir).split('·')[0]
        champion = os.path.basename(os.path.dirname(file_dir)).split('·')[0]
        data = json.loads(data['data'])
        res = ''.join([_item['onebest'] for _item in data]).replace('，', ', ').replace('。', '.')
        o = os.path.join(r'D:\lol\Temp', f'{champion}·{skin}·{_id}·{res}')
        open(o, 'w+').close()


# 注意：如果出现requests模块报错："NoneType" object has no attribute 'read', 请尝试将requests模块更新到2.20.0或以上版本(本demo测试版本为2.20.0)
# 输入讯飞开放平台的appid，secret_key和待转写的文件路径
if __name__ == '__main__':
    print(data_format(r"D:\lol\Res\Aatrox·暗裔剑魔·亚托克斯\Skin02·霸天剑魔 亚托克斯", '946616539'))
