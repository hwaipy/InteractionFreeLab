# import matplotlib.pyplot as plt
# from interactionfreepy import IFWorker
# import time
# import numpy as np
# from worker_config import worker, ip
# from collections import abc
# from RandomNumberMatcher import RandomNumbersMatcher
# import msgpack

# def mapping2str_v1(mapping: abc.Mapping, prefix: str = "    ", lvl: int = 0) -> str:
#     # prefix = "    "  为基础缩进符号
#     # lvl = 0  为整数，表示缩进的层级，以最外层花括号的缩进作为0级，之后逐层增1，则各层的缩进符号可以写为 prefix * lvl
#     sub_lvl = lvl + 1
#     cur_prefix = prefix * lvl
#     sub_prefix = prefix * sub_lvl

#     sub_items = ["{"]  # 这一部分的缩进由上一层的sub_item的起始字符`sub_prefix + key + ": `确定
#     for key, value in mapping.items():
#         sub_item = sub_prefix + key + ": "
#         # 仅在value为字典时才会递归调用
#         if isinstance(value, abc.Mapping):  # 可以看做是在模拟d0中的b1
#             # 进入下一字典层级中
#             sub_item += mapping2str_v1(value, prefix, sub_lvl)  # 递归调用的部分实际上可以看做是在模拟b1中的a2
#         else:
#             # 对于非字典项，直接转化为字符串
#             sub_item += str(value)  # 模拟d0中的a1
#         sub_items.append(sub_item)
#     sub_items.append(cur_prefix + "}")
#     # 使用'\n'连接a1、b1、c1
#     sub_items = "\n".join(sub_items)
#     return sub_items

# # TF数据总计


# # TF数据结果统计
# def TFexpResult(beginTime, endTime):
#     storage = worker.Storage

#     # 获取所有在范围内的数据的采集时间
#     # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
#     ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=10000)
#     print(f'{len(ranges)} seconds of data fetched...')

#     refStats_N = []
#     resultlist = []
#     for dataMeta in ranges[:]:
#         fetchTime = dataMeta['FetchTime']
#         dataBlock = getDataBlock(fetchTime)
#         meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
#         configs = meta['Data']['QKDQBER']['Configuration']
#         parser = TDCDataParser.DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])

#         result = parser.parse()
#         print('\n当前时间：', datetime.datetime.now())
#         print('该秒数据时间：', fetchTime)
#         print('探测器计数：', result['Count']['All data1List'], result['Count']['All data2List'])
#         print(f"基矢匹配的事件：reference {result['Count']['All References']}, signal {result['Count']['All Signals']}")
#         print(f"筛选码事件  00: {result['Count']['Sifted Key OO']}  XX: {result['Count']['Sifted Key XX']}  YY: {result['Count']['Sifted Key YY']}  ZZ: {result['Count']['Sifted Key ZZ']}")
#         print(f"Sifted Key ZZ中[00, 01, 10, 11]的数量：{result['Sifted Key']['ZZ']}, bit error={result['errorRate']['ZZ']}")
#         print(f"Sifted Key per RN for ZZ [00, 01, 10, 11] = {result['Sifted Key per RN']['ZZ']} expected error Rate = {result['errorRate']['ZZ expected']}")
#         print(f"相位筛选后的Sifted Key XX事件数量：{np.sum(result['Sifted Key']['XX'])}, phase error={result['errorRate']['XX']}")
#         print(f"相位筛选后的Sifted Key YY事件数量：{np.sum(result['Sifted Key']['YY'])}, phase error={result['errorRate']['YY']}")
#         # refStats = parser.ref_rns_matched(refDeltaMetas=result['reference']['ref'], matchedRandomNumbers=result['RNS']['matchedRandomNumbers'], selected=True)
#         # refStats_N.extend(refStats)
#         resultlist.append(result)
#     # TDCDataParser.DataBlockParser.ref_plot(refStats=refStats_N)
#     TotalData(resultlist)
#     return


# # 光子数随时间的变化统计
# def count_plot(beginTime, endTime):
#     storage = worker.Storage

#     # 获取所有在范围内的数据的采集时间
#     # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
#     ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=100000)
#     print(f'{len(ranges)} seconds of data fetched.')

#     count_total = {'intervene0': [], 'intervene1': [], 'AliceSync': [], 'BobSync': []}
#     for dataMeta in ranges[:]:
#         fetchTime = dataMeta['FetchTime']
#         print(fetchTime)
#         dataBlock = getDataBlock(fetchTime)
#         meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
#         configs = meta['Data']['QKDQBER']['Configuration']
#         parser = TDCDataParser.DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])
#         count = parser.dataCount()
#         for key in count.keys():
#             count_total[key].append(count[key])

#     for key in count_total.keys():
#         if key != 'BobSync': plt.plot(count_total[key], label=key)
#     plt.title(f'Count 1s per point\n{beginTime} to {endTime}')
#     plt.xlabel('time(s)')
#     plt.ylabel('count')
#     plt.legend()
#     plt.show()
#     return


# # 消光比统计（ref）
# def get_channel_extinction_ratio(beginTime, endTime):
#     storage = worker.Storage

#     # 获取所有在范围内的数据的采集时间
#     # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
#     ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=10000)
#     print(f'{len(ranges)} seconds of data fetched.')

#     refStats_N = []
#     for dataMeta in ranges[:]:
#         fetchTime = dataMeta['FetchTime']
#         dataBlock = getDataBlock(fetchTime)
#         meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
#         configs = meta['Data']['QKDQBER']['Configuration']
#         parser = TDCDataParser.DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])

#         refStats = parser.channel_extinction_ratio()
#         refStats_N.extend(refStats)
#     TDCDataParser.DataBlockParser.channelCountPlot(refStats=refStats_N)
#     return


# def statistic(beginTime, endTime):
#     storage = worker.Storage

#     # 获取所有在范围内的数据的采集时间
#     ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=1000000)
#     print(f'{len(ranges)} seconds of data fetched...')

#     randomNumbersMatcher = None

#     resultlist = None
#     for dataMeta in ranges[:]:
#         fetchTime = dataMeta['FetchTime']
#         dataBlock = getDataBlock(fetchTime)
#         meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
#         configs = meta['Data']['QKDQBER']['Configuration']
#         if not randomNumbersMatcher: randomNumbersMatcher = RandomNumbersMatcher(configs['AliceRandomNumbers'], configs['BobRandomNumbers'])
#         parser = TDCDataParser.DataBlockParser(dataBlock, randomNumbersMatcher, triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])
#         statistics_all, key_list = parser.statistics()
#         print('stat')
#         if resultlist is None:
#             resultlist = statistics_all
#         #     resultlist = msgpack.unpackb(msgpack.packb(statistics_all.copy()))
#         #     print(resultlist['signalZ']['signalZ']['detector_count'])
#         # else:
#         #     resultlist['all']['ref']['detector_count'] += statistics_all['all']['ref']['detector_count']
#         #     resultlist['all']['signal']['detector_count'] += statistics_all['all']['signal']['detector_count']
#         #     print(statistics_all['signalZ']['signalZ']['detector_count'])
#         #     for Akey in key_list:
#         #         for Bkey in key_list:
#         #             resultlist[Akey][Bkey]['detector_count'] += statistics_all[Akey][Bkey]['detector_count']

#     print('*' * 100)
#     print(mapping2str_v1(resultlist))
#     # print(resultlist)
#     print('*' * 100)


from interactionfreepy import IFWorker
import logging
from rich.progress import track, Progress
import msgpack
from numba import jit
import numpy as np
from urllib.request import urlopen
from pytimetag import DataBlock
from TDCDataParser import DataBlockParser
from datetime import datetime
import pandas as pd

class TFResultConfig:
  def __init__(self, worker):
    self.worker = worker
    self.configs = {}
    self.__logging = logging.getLogger('TFResultConfig')

  def getRandomNumberConfig(self, config):
    rnsAliceID = config['AliceRandomNumbers']
    rnsBobID = config['BobRandomNumbers']
    assert isinstance(rnsAliceID, str)
    assert isinstance(rnsBobID, str)
    key = rnsAliceID + ' + ' + rnsBobID
    if not self.configs.__contains__(key):
      self.__logging.info('RandomNumber config not exist, creating...')
      rnsAlice = msgpack.unpackb(self.worker.TF_FileStorage.readMassive(id=rnsAliceID))
      rnsBob = msgpack.unpackb(self.worker.TF_FileStorage.readMassive(id=rnsBobID))
      self.__logging.info(f'RandomNumber downloaded. length_A = {len(rnsAlice)}, length_B = {len(rnsBob)}.')
      matchedRandomNumbers, rnStat = self.__matchedRandomNumbers(rnsAlice, rnsBob)
      self.__logging.info(f'Matched RandomNumbers created.')
      keyPairs, stat, matched = self.statisticsRNS(rnsAlice, rnsBob)
      self.__logging.info(f'RandomNumber Config creation complete.')
      self.configs[key] = {
          'rnsAlice': rnsAlice,
          'rnsBob': rnsBob,
          'matchedRandomNumbers': matchedRandomNumbers,
          'rnStat': rnStat,
          'statKeyPairs': keyPairs,
          'randomNumberStatistics': stat,
          'fullMatchedRandomNumbers': matched
      }
    return self.configs[key]

  def __matchedRandomNumbers(self, rnsAlice, rnsBob):
    @njit(cache=True)
    def jit_matchedRandomNumbers(rnsAlice, rnsBob):
      matchedRandomNumbers = [-1] * len(rnsAlice)
      for i in range(len(rnsAlice)):
        rnA = rnsAlice[i]
        rnB = rnsBob[i]
        # rnA和rnB 同为XX、YY或ZZ的signal
        if rnA < 64 and rnB < 64 and (rnA & 0b11) == (rnB & 0b11):
          basis = rnA & 0b11  # 记录X、Y、Z态
          encodeA = ((rnA & 0b111100) >> 2)  # 只留下相位编码
          encodeB = ((rnB & 0b111100) >> 2)
          if basis == 0:  # 真空态
            matchedRandomNumbers[i] = 0
          elif basis == 3:  # Z态
            matchedRandomNumbers[i] = (encodeA << 3) + (encodeB << 2) + 0b11
          else:  # X、Y态
            encode = (encodeA - encodeB) % 16  # 编码相位差
            matchedRandomNumbers[i] = (encode << 2) + basis
        # rnA rnB 同为reference光 或gap
        elif 64 <= rnA < 128 and 64 <= rnB < 128:
          encodeA = ((rnA & 0b111100) >> 2)
          encodeB = ((rnB & 0b111100) >> 2)
          encode = (encodeA - encodeB) % 16
          matchedRandomNumbers[i] = (encode << 2) + 0b1000000

      # Alice、Bob匹配的随机数。定义为：
      # 对于Ref、基矢不匹配、Gap，均为-1
      # 对于OO态：为0
      # 对于XX或YY态：为0bPPPPDD，其中PPPP为(alice相位-bob相位)%16，DD为01(XX)或10(YY)
      # 对于ZZ态：为0bAB11，其中A为alice编码，B为Bob编码，0代表不发，1代表发
      def stat(rnList, n):
        st = [0] * n
        for r in rnList:
          st[r] += 1
        return st
      rnStat = [
          [len([r for r in matchedRandomNumbers if r == -1])],  # Invalid: 不匹配的数量
          [len([r for r in matchedRandomNumbers if r == 0])],  # OO: 真空态数量
          stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b01 and r >= 0], 16),  # XX: [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
          stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b10 and r >= 0], 16),  # YY: [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
          stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b11 and r >= 0], 4),  # ZZ: [4个元素，表示Alice、Bob的Z态为发1或不发0]
          stat([((r & 0b111111) >> 2) for r in matchedRandomNumbers if (r & 0b1000000) == 0b1000000 and r >= 0], 16),  # Ref: [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
      ]
      return matchedRandomNumbers, rnStat
    matchedRandomNumber, rnStat = jit_matchedRandomNumbers(np.array(rnsAlice), np.array(rnsBob))
    return matchedRandomNumber, {'Invalid': rnStat[0], 'OO': rnStat[1], 'XX': rnStat[2], 'YY': rnStat[3], 'ZZ': rnStat[4], 'Ref': rnStat[5]}

  def statisticsRNS(self, rnsAlice, rnsBob):
    keys = ['ref', 'gap', 'signal0', 'signalX', 'signalY', 'signalZ0', 'signalZ1']
    keyMappingList = [0] * 256
    for i in range(256):
      if i >= 128:
        key = 'gap'
      elif i >= 64:
        key = 'ref'
      elif i % 4 == 0:
        key = 'signal0'
      elif i % 4 == 1:
        key = 'signalX'
      elif i % 4 == 2:
        key = 'signalY'
      elif i % 4 == 3:
        if i % 8 == 3:
          key = 'signalZ0'
        if i % 8 == 7:
          key = 'signalZ1'
      keyMappingList[i] = keys.index(key)

    @njit(cache=True)
    def jit_statistics(rnsAlice, rnsBob, keySize, keyMappingList):
      stat = [0] * (keySize * keySize)
      matched = [0] * len(rnsAlice)
      for i in range(len(rnsAlice)):
        rnA = rnsAlice[i]
        rnB = rnsBob[i]
        kA = keyMappingList[rnA]
        kB = keyMappingList[rnB]
        k = kA * keySize + kB
        stat[k] += 1
        matched[i] = k
      return stat, matched

    stat, matched = jit_statistics(np.array(rnsAlice), np.array(rnsBob), len(keys), np.array(keyMappingList))
    keyPairs = []
    for kA in keys:
      for kB in keys:
        keyPairs.append(f'{kA}-{kB}')
    return keyPairs, stat, matched

  def statistics_rns(self, Alice_rns, Bob_rns, printYN=True):
      # 随机数统计
    from LongRandomWaveform import LongWaveformGenerator
    # 统计前预处理
    LongWaveformGenerator.selectSame(Alice_rns, Bob_rns)
    result = dict()
    result['Alice'] = LongWaveformGenerator.analyzeRNS(Alice_rns)
    if printYN:
      print(result['Alice']['count'])
    result['Bob'] = LongWaveformGenerator.analyzeRNS(Bob_rns)
    if printYN:
      print(result['Bob']['count'])
    length_rns = len(Alice_rns)
    length_rns_signal = len(result["Alice"]["signal"])

    key_list = result['Alice'].keys()
    key_list = [i for i in key_list if 'signal' in i and i != 'signal']
    statistics_all = dict()

    # 随机数统计
    allref = LongWaveformGenerator.selectSame(result['Alice']['ref'], result['Bob']['ref'])
    allsig = LongWaveformGenerator.selectSame(result['Alice']['signal'], result['Bob']['signal'])
    statistics_all['all'] = {'ref': {'count': len(allref), 'ratio': len(allref) / length_rns, 'detector_count': 0}, 'signal': {'count': len(allsig), 'ratio': len(allsig) / length_rns, 'detector_count': 0}}
    if printYN:
      print(f'reference对数：{len(allref)}, 占比：{len(allref) / length_rns}')
    if printYN:
      print(f'signal对数：{len(allsig)}, 占比：{len(allsig) / length_rns}')
    # signal统计
    for key0 in key_list:
      statistics_all[key0] = dict()
      for key1 in key_list:
        statistics_all[key0][key1] = dict()
        # statistics_all[key0][key1]['index'] = LongWaveformGenerator.selectSame(result['Alice'][key0], result['Bob'][key1])
        statistics_all[key0][key1]['count'] = len(LongWaveformGenerator.selectSame(result['Alice'][key0], result['Bob'][key1]))
        statistics_all[key0][key1]['ratio'] = statistics_all[key0][key1]['count'] / length_rns_signal
        statistics_all[key0][key1]['detector_count'] = 0
        if printYN:
          print(f'Alice={key0}, Bob={key1}, 个数={statistics_all[key0][key1]["count"]}, 占signal比：{statistics_all[key0][key1]["ratio"]}')

    lZZ = [statistics_all['signalZ0']['signalZ0']['count'], statistics_all['signalZ0']['signalZ1']['count'], statistics_all['signalZ1']['signalZ0']['count'], statistics_all['signalZ1']['signalZ1']['count']]
    if printYN:
      print(f'ZZ态(AB)[00, 01, 10, 11] 个数{lZZ}, 占比：{[i / length_rns for i in lZZ]}, 占signal比：{[i / length_rns_signal for i in lZZ]}, 占ZZ比：{[i / statistics_all["signalZ"]["signalZ"]["count"] for i in lZZ]}')
    print(statistics_all)
    return statistics_all, key_list


class TFResult:
  __logging = logging.getLogger('TFResult')

  def __init__(self, beginTime, endTime, serverIP):
    self.beginTime = beginTime
    self.endTime = endTime
    self.serverIP = serverIP
    self.worker = IFWorker(endpoint=f'tcp://{self.serverIP}:224')
    self.simpleMeta = self.worker.Storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=10000)
    TFResult.__logging.info(f'{len(self.simpleMeta)} seconds of data fetched.')
    self.metas = None
    self.config = TFResultConfig(self.worker)

  def loadMeta(self):
    if self.metas:
      TFResult.__logging.warning('Meta has already been loaded.')
    else:
      TFResult.__logging.info('Start loading meta...')
      metas = []
      for step in track(range(len(self.simpleMeta)), description='Fetching full DataMetas...'):
        metas.append(self.worker.Storage.get('TFQKD_TDC', self.simpleMeta[step]['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1}))  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
      self.metas = metas
      TFResult.__logging.info(f'All {len(self.metas)} meta info loaded.')

  def parse(self):
    randomNumberConfig = self.config.getRandomNumberConfig(self.metas[0]['Data']['QKDQBER']['Configuration'])

    resultlist = []
    for dataMeta in self.metas:
      dataBlock = self.getDataBlock(dataMeta['FetchTime'])
      parser = DataBlockParser(dataBlock, randomNumberConfig, dataConfig=dataMeta['Data']['QKDQBER']['Configuration'])
      result = parser.parse()
      print('\n当前时间：', datetime.now())
      print('该秒数据时间：', dataMeta['FetchTime'])
      print('探测器计数：', result['Count']['All data1List'], result['Count']['All data2List'])
      print(f"基矢匹配的事件：reference {result['Count']['All References']}, signal {result['Count']['All Signals']}")
      print(f"筛选码事件  00: {result['Count']['Sifted Key OO']}  XX: {result['Count']['Sifted Key XX']}  YY: {result['Count']['Sifted Key YY']}  ZZ: {result['Count']['Sifted Key ZZ']}")
      print(f"Sifted Key ZZ中[00, 01, 10, 11]的数量：{result['Sifted Key']['ZZ']}, bit error={result['errorRate']['ZZ']}")
      print(f"Sifted Key per RN for ZZ [00, 01, 10, 11] = {result['Sifted Key per RN']['ZZ']} expected error Rate = {result['errorRate']['ZZ expected']}")
      print(f"相位筛选后的Sifted Key XX事件数量：{np.sum(result['Sifted Key']['XX'])}, phase error={result['errorRate']['XX']}")
      print(f"相位筛选后的Sifted Key YY事件数量：{np.sum(result['Sifted Key']['YY'])}, phase error={result['errorRate']['YY']}")
      resultlist.append(result)
    
    self.totalData(resultlist)

  def getDataBlock(self, fetchTime):
    while len(fetchTime) == 25:
      fetchTime = time.strftime('%Y-%m-%dT%H:%M:%S.000000+08:00', time.strptime(fetchTime, '%Y-%m-%dT%H:%M:%S+08:00'))
    res = urlopen(f'http://{self.serverIP}:1001/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock')
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

  def totalData(self, resultlist):
    print('*'*20, '总数据', '*'*20)
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
    SiftedKeyperRN_ZZ = [siftedZZ[i]/RNCount_ZZ[i] for i in range(4)]

    print(f"Sifted Key ZZ中[00, 01, 10, 11]的数量：{siftedZZ}")
    print(f"Sifted Key per RN for ZZ [00, 01, 10, 11] = {SiftedKeyperRN_ZZ}")
    print(f"相位筛选后的Sifted Key XX事件数量：{np.sum(siftedXX)}, phase error={(errorXX[1]+errorXX[2])/np.sum(errorXX)}")
    print(f"相位筛选后的Sifted Key YY事件数量：{np.sum(siftedYY)}, phase error={(errorYY[1]+errorYY[2])/np.sum(errorYY)}")

    print('Count for all basis:')
    df_countByBasis = pd.DataFrame.from_dict([r['CountStatByBasis'] for r in resultlist]).sum(axis=0)
    print(df_countByBasis)

    # KeyRate:
    randomNumberConfig = self.config.getRandomNumberConfig(self.metas[0]['Data']['QKDQBER']['Configuration'])
    statKeyPairs = randomNumberConfig['statKeyPairs']
    randomNumberStatistics = [i for i in randomNumberConfig['randomNumberStatistics']]
    randomNumberStatistics[0] = 0
    randomNumberStatistics[8] = 0
    randomNumberStatistics = [i / sum(randomNumberStatistics) for i in randomNumberStatistics]
    rnStatMap = {}
    for i in range(len(statKeyPairs)):
      rnStatMap[statKeyPairs[i]] = {'ratio': float(randomNumberStatistics[i]), 'detector_count': int(df_countByBasis[statKeyPairs[i]])}

    # print(rnStatMap)
    kr = self.worker.TF_KeyRate.calculate(
      rnStatMap, 
      pulseNumber=1e8 / 40 * 25 * len(self.metas), 
      intensities=[
        0.1055,  # X基弱源强度
        0.2630,  # X基强光强度
        0.5000,  # Z基相关态光源强度
      ],
      errorX=[]
    )
    print(errorXX)
    # (errorXX[1]+errorXX[2])/np.sum(errorXX)
    print(f'KeyRate = {kr}')

    print('*' * 20, 'END', '*' * 20)


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  # result = TFResult(beginTime='2022-10-12T06:40:00+08:00', endTime='2022-10-12T07:10:00+08:00', serverIP='10.1.1.1')
  result = TFResult(beginTime='2022-10-12T06:40:00+08:00', endTime='2022-10-12T06:40:10+08:00', serverIP='10.1.1.1')
  result.loadMeta()
  result.parse()
