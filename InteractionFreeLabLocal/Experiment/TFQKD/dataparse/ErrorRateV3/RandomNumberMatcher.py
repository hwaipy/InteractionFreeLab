# from worker_config import worker, ip
# import msgpack

# class RandomNumbersMatcher:
#     def __init__(self, rnsAlice, rnsBob):
#         self.rnsAlice = rnsAlice if not isinstance(rnsAlice, str) else msgpack.unpackb(worker.TF_FileStorage.readMassive(id=rnsAlice))
#         self.rnsBob = rnsBob if not isinstance(rnsBob, str) else msgpack.unpackb(worker.TF_FileStorage.readMassive(id=rnsBob))

#         self.statistics_all, self.key_list = self.statistics_rns(self.rnsAlice, self.rnsBob)
#         self.matchedRandomNumbers, self.rnstat = self.__match()
#         # import time
#         # t1 = time.time()
#         # self.__match()
#         # t2 = time.time()
#         # print(t2 - t1)

#     def __match(self):
#         matchedRandomNumbers = [-1] * len(self.rnsAlice)
#         for i in range(len(self.rnsAlice)):
#             rnA = self.rnsAlice[i]
#             rnB = self.rnsBob[i]
#             # rnA和rnB 同为XX、YY或ZZ的signal
#             if rnA < 64 and rnB < 64 and (rnA & 0b11) == (rnB & 0b11):
#                 basis = rnA & 0b11  # 记录X、Y、Z态
#                 encodeA = ((rnA & 0b111100) >> 2)  # 只留下相位编码
#                 encodeB = ((rnB & 0b111100) >> 2)
#                 if basis == 0:  # 真空态
#                     matchedRandomNumbers[i] = 0
#                 elif basis == 3:  # Z态
#                     matchedRandomNumbers[i] = (encodeA << 3) + (encodeB << 2) + 0b11
#                 else:  # X、Y态
#                     encode = (encodeA - encodeB) % 16  # 编码相位差
#                     matchedRandomNumbers[i] = (encode << 2) + basis
#             # rnA rnB 同为reference光 或gap
#             elif 64 <= rnA < 128 and 64 <= rnB < 128:
#                 encodeA = ((rnA & 0b111100) >> 2)
#                 encodeB = ((rnB & 0b111100) >> 2)
#                 encode = (encodeA - encodeB) % 16
#                 matchedRandomNumbers[i] = (encode << 2) + 0b1000000

#         # Alice、Bob匹配的随机数。定义为：
#         # 对于Ref、基矢不匹配、Gap，均为-1
#         # 对于OO态：为0
#         # 对于XX或YY态：为0bPPPPDD，其中PPPP为(alice相位-bob相位)%16，DD为01(XX)或10(YY)
#         # 对于ZZ态：为0bAB11，其中A为alice编码，B为Bob编码，0代表不发，1代表发
#         def stat(rnList, n):
#             st = [0] * n
#             for r in rnList:
#                 st[r] += 1
#             return st
#         rnStat = dict()
#         rnStat['Invalid'] = [len([r for r in matchedRandomNumbers if r == -1])]  # 不匹配的数量
#         rnStat['OO'] = [len([r for r in matchedRandomNumbers if r == 0])]  # 真空态数量
#         rnStat['XX'] = stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b01 and r >= 0], 16)  # [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
#         rnStat['YY'] = stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b10 and r >= 0], 16)  # [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
#         rnStat['ZZ'] = stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b11 and r >= 0], 4)  # [4个元素，表示Alice、Bob的Z态为发1或不发0]
#         rnStat['Ref'] = stat([((r & 0b111111) >> 2) for r in matchedRandomNumbers if (r & 0b1000000) == 0b1000000 and r >= 0], 16)  # [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
#         # print(rnStat)
#         return matchedRandomNumbers, rnStat

#     def statistics_rns(self, Alice_rns, Bob_rns, printYN=False):

#         import time
#         t1 = time.time()

#         # 随机数统计
#         from LongRandomWaveform import LongWaveformGenerator
#         # 统计前预处理
#         LongWaveformGenerator.selectSame(Alice_rns, Bob_rns)
#         result = dict()
#         result['Alice'] = LongWaveformGenerator.analyzeRNS(Alice_rns)
#         if printYN:print(result['Alice']['count'])
#         result['Bob'] = LongWaveformGenerator.analyzeRNS(Bob_rns)
#         if printYN:print(result['Bob']['count'])
#         length_rns = len(Alice_rns)
#         length_rns_signal = len(result["Alice"]["signal"])

#         key_list = result['Alice'].keys()
#         key_list = [i for i in key_list if 'signal' in i and i != 'signal']
#         statistics_all = dict()

#         # 随机数统计
#         allref = LongWaveformGenerator.selectSame(result['Alice']['ref'], result['Bob']['ref'])
#         allsig = LongWaveformGenerator.selectSame(result['Alice']['signal'], result['Bob']['signal'])
#         statistics_all['all'] = {'ref': {'count': len(allref), 'ratio': len(allref) / length_rns, 'detector_count': 0}, 'signal': {'count': len(allsig), 'ratio': len(allsig) / length_rns, 'detector_count': 0}}
#         if printYN:print(f'reference对数：{len(allref)}, 占比：{len(allref) / length_rns}')
#         if printYN:print(f'signal对数：{len(allsig)}, 占比：{len(allsig) / length_rns}')
#         # signal统计
#         for key0 in key_list:
#             statistics_all[key0] = dict()
#             for key1 in key_list:
#                 statistics_all[key0][key1] = dict()
#                 # statistics_all[key0][key1]['index'] = LongWaveformGenerator.selectSame(result['Alice'][key0], result['Bob'][key1])
#                 statistics_all[key0][key1]['count'] = len(LongWaveformGenerator.selectSame(result['Alice'][key0], result['Bob'][key1]))
#                 statistics_all[key0][key1]['ratio'] = statistics_all[key0][key1]['count'] / length_rns_signal
#                 statistics_all[key0][key1]['detector_count'] = 0
#                 if printYN:print(f'Alice={key0}, Bob={key1}, 个数={statistics_all[key0][key1]["count"]}, 占signal比：{statistics_all[key0][key1]["ratio"]}')

#         lZZ = [statistics_all['signalZ0']['signalZ0']['count'], statistics_all['signalZ0']['signalZ1']['count'], statistics_all['signalZ1']['signalZ0']['count'], statistics_all['signalZ1']['signalZ1']['count']]
#         if printYN:print(f'ZZ态(AB)[00, 01, 10, 11] 个数{lZZ}, 占比：{[i / length_rns for i in lZZ]}, 占signal比：{[i / length_rns_signal for i in lZZ]}, 占ZZ比：{[i / statistics_all["signalZ"]["signalZ"]["count"] for i in lZZ]}')

#         # t2 = time.time()

#         # print()
#         # print()
#         # print(statistics_all)
#         # print()
#         # print()
#         # print()
#         # print()
#         # print(key_list)
#         # print()
#         # print()
#         # print(t2 - t1)
#         # import sys
#         # sys.exit(0)


#         return statistics_all, key_list
