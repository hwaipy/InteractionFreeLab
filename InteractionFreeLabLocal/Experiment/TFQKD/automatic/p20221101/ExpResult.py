import TDCDataParser
from interactionfreepy import IFWorker
import time
from urllib.request import urlopen
from pytimetag import DataBlock
import numpy as np
import pandas as pd
import datetime
import multiprocessing
from worker_config import worker, ip
import matplotlib.pyplot as plt
from PIL import Image
import msgpack
from collections import abc


def mapping2str_v1(mapping: abc.Mapping, prefix: str = "    ", lvl: int = 0) -> str:
    # prefix = "    "  为基础缩进符号
    # lvl = 0  为整数，表示缩进的层级，以最外层花括号的缩进作为0级，之后逐层增1，则各层的缩进符号可以写为 prefix * lvl
    sub_lvl = lvl + 1
    cur_prefix = prefix * lvl
    sub_prefix = prefix * sub_lvl

    sub_items = ["{"]  # 这一部分的缩进由上一层的sub_item的起始字符`sub_prefix + key + ": `确定
    for key, value in mapping.items():
        sub_item = sub_prefix + key + ": "
        # 仅在value为字典时才会递归调用
        if isinstance(value, abc.Mapping):  # 可以看做是在模拟d0中的b1
            # 进入下一字典层级中
            sub_item += mapping2str_v1(value, prefix, sub_lvl)  # 递归调用的部分实际上可以看做是在模拟b1中的a2
        else:
            # 对于非字典项，直接转化为字符串
            sub_item += str(value)  # 模拟d0中的a1
        sub_items.append(sub_item)
    sub_items.append(cur_prefix + "}")
    # 使用'\n'连接a1、b1、c1
    sub_items = "\n".join(sub_items)
    return sub_items


def getDataBlock(fetchTime):
    while len(fetchTime) == 25: fetchTime = time.strftime('%Y-%m-%dT%H:%M:%S.000000+08:00', time.strptime(fetchTime, '%Y-%m-%dT%H:%M:%S+08:00'))

    res = urlopen(f'http://{ip}:1001/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock')
    data = res.read()
    res.close()
    dataBlock = DataBlock.deserialize(data)
    dataBlock = {
        'CreationTime': dataBlock.creationTime,
        'DataTimeBegin': dataBlock.dataTimeBegin,
        'DataTimeEnd': dataBlock.dataTimeEnd,
        'Sizes': dataBlock.sizes,
        'Resolution': dataBlock.resolution,
        'Content': dataBlock.content,
    }
    return dataBlock


def IDtoRNS(id: str):
    return msgpack.unpackb(worker.TF_FileStorage.readMassive(id=id))

def TotalData(resultlist):
    print('*' * 20, '总数据', '*' * 20)
    df_count = pd.DataFrame.from_dict([r['Count'] for r in resultlist]).sum(axis=0)
    print(df_count)

    print('探测器计数：', df_count['All data1List'], df_count['All data2List'])
    print(f"基矢匹配的事件：reference {df_count['All References']}, signal {df_count['All Signals']}")
    print(f"筛选码事件  00: {df_count['Sifted Key OO']}  XX: {df_count['Sifted Key XX']}  YY: {df_count['Sifted Key YY']}  ZZ: {df_count['Sifted Key ZZ']}")

    df_sifted = pd.DataFrame.from_dict([r['Sifted Key'] for r in resultlist])
    siftedZZ = list(np.array(list(df_sifted['ZZ'])).sum(axis=0))
    siftedYY = list(np.array(list(df_sifted['YY'])).sum(axis=0))
    siftedXX = list(np.array(list(df_sifted['XX'])).sum(axis=0))
    errorXX = list(np.array(list(df_sifted['phase sifted XX'])).sum(axis=0))
    errorYY = list(np.array(list(df_sifted['phase sifted YY'])).sum(axis=0))

    df_RNCount = pd.DataFrame.from_dict([r['RNCount'] for r in resultlist])
    RNCount_ZZ = list(np.array(list(df_RNCount['ZZ'])).sum(axis=0))
    SiftedKeyperRN_ZZ = [siftedZZ[i] / RNCount_ZZ[i] for i in range(4)]

    print(f"Sifted Key ZZ中[00, 01, 10, 11]的数量：{siftedZZ}, bit error={TDCDataParser.DataBlockParser.errorRateZZ(TDCDataParser.DataBlockParser.lastObject, siftedZZ)}")
    print(f"Sifted Key per RN for ZZ [00, 01, 10, 11] = {SiftedKeyperRN_ZZ} expected error Rate = {TDCDataParser.DataBlockParser.expectedZZerror(TDCDataParser.DataBlockParser.lastObject, 0.03, SiftedKeyperRN_ZZ)}")
    print(f"相位筛选后的Sifted Key XX事件数量：{np.sum(siftedXX)}, phase error={(errorXX[1] + errorXX[2]) / np.sum(errorXX)}")
    print(f"相位筛选后的Sifted Key YY事件数量：{np.sum(siftedYY)}, phase error={(errorYY[1] + errorYY[2]) / np.sum(errorYY)}")
    print('*' * 20, 'END', '*' * 20)


def TFexpResult(beginTime, endTime):
    storage = worker.Storage

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=1000000)
    print(f'{len(ranges)} seconds of data fetched...')
    metas = []
    for dataMeta in ranges:
        metas.append(worker.Storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1}))

    resultlist = []
    config = worker.Storage.get('TFQKD_TDC', ranges[0]['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1})['Data']['QKDQBER']['Configuration']
    rnsAlice = IDtoRNS(config['AliceRandomNumbers'])
    rnsBob = IDtoRNS(config['BobRandomNumbers'])
    print('Loading RNS Done.')
    matchedRandomNumbers, rnStat = TDCDataParser.DataBlockParser.matchedRandomNumbers_fitting(rnsAlice, rnsBob)
    print('Process RNS Done.')

    for meta in metas:
        fetchTime = meta['FetchTime']
        while len(fetchTime) == 25: fetchTime = time.strftime('%Y-%m-%dT%H:%M:%S.000000+08:00', time.strptime(fetchTime, '%Y-%m-%dT%H:%M:%S+08:00'))
        dataBlock = getDataBlock(fetchTime)
        configs = meta['Data']['QKDQBER']['Configuration']
        resultlist.append(parseDataBlock(dataBlock, configs, fetchTime, None, None, matchedRandomNumbers, rnStat))

    TotalData(resultlist)


def count_plot(beginTime, endTime):
    def count(dataMeta):
        fetchTime = dataMeta['FetchTime']
        dataBlock = getDataBlock(fetchTime)
        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = TDCDataParser.DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'],
                                               data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])
        count = parser.dataCount()
        return count

    storage = worker.Storage

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=1000000)
    print(f'{len(ranges)} seconds of data fetched.')

    count_total = {'intervene0': [], 'intervene1': [], 'AliceSync': [], 'BobSync': []}

    resultlist = []
    with multiprocessing.Pool(processes=40) as pool:
        for dataMeta in ranges:
            resultlist.append(pool.apply_async(count, (dataMeta,)))
        pool.close()
        pool.join()

        # 取结果
        for result in resultlist:
            count = result.get()
            for key in count_total.keys():
                count_total[key].append(count[key])

    for key in count_total.keys():
        if key != 'BobSync': plt.plot(count_total[key], label=key)
    plt.title(f'Count 1s per point\n{beginTime} to {endTime}')
    plt.xlabel('time(s)')
    plt.ylabel('count')
    plt.legend()
    plt.savefig('count_plot.png')
    plt.close()
    im = Image.open('count_plot.png')
    im.show()
    return


def parseDataBlock(dataBlock, configs, fetchTime, AliceRandomNumbers=None, BobRandomNumbers=None, matchedRandomNumbers=None, rnStat=None):

    if AliceRandomNumbers is None: AliceRandomNumbers = configs['AliceRandomNumbers']
    if BobRandomNumbers is None: BobRandomNumbers = configs['BobRandomNumbers']
    parser = TDCDataParser.DataBlockParser(dataBlock, AliceRandomNumbers, BobRandomNumbers, triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'], matchedRandomNumbers=matchedRandomNumbers, rnStat=rnStat)
    result = parser.parse()
    print('\n当前时间：', datetime.datetime.now())
    print('该秒数据时间：', fetchTime)
    print('探测器计数：', result['Count']['All data1List'], result['Count']['All data2List'])
    print(f"基矢匹配的事件：reference {result['Count']['All References']}, signal {result['Count']['All Signals']}")
    print(f"筛选码事件  00: {result['Count']['Sifted Key OO']}  XX: {result['Count']['Sifted Key XX']}  YY: {result['Count']['Sifted Key YY']}  ZZ: {result['Count']['Sifted Key ZZ']}")
    print(f"Sifted Key ZZ中[00, 01, 10, 11]的数量：{result['Sifted Key']['ZZ']}, bit error={result['errorRate']['ZZ']}")
    print(f"Sifted Key per RN for ZZ [00, 01, 10, 11] = {result['Sifted Key per RN']['ZZ']} \nexpected error Rate = {result['errorRate']['ZZ expected']}")
    print(f"相位筛选后的Sifted Key XX事件数量：{np.sum(result['Sifted Key']['XX'])}, phase error={result['errorRate']['XX']}")
    print(f"相位筛选后的Sifted Key YY事件数量：{np.sum(result['Sifted Key']['YY'])}, phase error={result['errorRate']['YY']}")
    return result


# 消光比统计
def get_channel_extinction_ratio(beginTime, endTime):
    storage = worker.Storage

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=1000000)
    print(f'{len(ranges)} seconds of data fetched.')

    refStats_N = []
    for dataMeta in ranges[:]:
        fetchTime = dataMeta['FetchTime']
        dataBlock = getDataBlock(fetchTime)
        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = TDCDataParser.DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'],
                                               data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])

        refStats = parser.channel_extinction_ratio()
        refStats_N.extend(refStats)
    TDCDataParser.DataBlockParser.channelCountPlot(refStats=refStats_N)
    return


def statistic(beginTime, endTime):
    storage = worker.Storage

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=1000000)
    print(f'{len(ranges)} seconds of data fetched...')

    resultlist = None
    for dataMeta in ranges[:]:
        fetchTime = dataMeta['FetchTime']
        dataBlock = getDataBlock(fetchTime)
        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = TDCDataParser.DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])

        statistics_all, key_list = parser.statistics()
        if resultlist is None: resultlist = statistics_all.copy()
        else:
            resultlist['all']['ref']['detector_count'] += statistics_all['all']['ref']['detector_count']
            resultlist['all']['signal']['detector_count'] += statistics_all['all']['signal']['detector_count']
            for Akey in key_list:
                for Bkey in key_list:
                    resultlist[Akey][Bkey]['detector_count'] += statistics_all[Akey][Bkey]['detector_count']

    print('*' * 30)
    print(mapping2str_v1(resultlist))
    print('*' * 30)


if __name__ == '__main__':
    # TFexpResult(beginTime='2022-08-16T23:54:50+08:00', endTime='2022-08-16T23:54:52+08:00')
    # TFexpResult(beginTime='2022-08-24T16:32:00+08:00', endTime='2022-08-24T16:32:10+08:00')
    # TFexpResult(beginTime='2022-08-24T16:41:00+08:00', endTime='2022-08-24T16:41:50+08:00')  # 发射概率<0.05
    # 正常采数 0824 16：32：00-16：42：00
    # 8.29 16:00-22:00 半波电压正确
    # 9.1  10:34-11:10 单脉冲无相位调制
    # get_channel_extinction_ratio(beginTime='2022-09-01T11:00:00+08:00', endTime='2022-09-01T11:00:10+08:00')  # 发射概率<0.05
    # 9.6 21:32 - 9.7 1:09ref更新方案后采数
    # TFexpResult(beginTime='2022-09-06T21:32:00+08:00', endTime='2022-09-06T23:32:00+08:00')  # 发射概率<0.05

    # count_plot(beginTime='2022-10-02T03:00:00+08:00', endTime='2022-10-02T06:00:00+08:00')

    # 长随机数同源光验证 20221011 04:40-10:30
    # TFexpResult(beginTime='2022-10-11T04:40:00+08:00', endTime='2022-10-11T04:40:10+08:00')

    statistic(beginTime='2022-10-12T07:40:00+08:00', endTime='2022-10-12T07:45:00+08:00')