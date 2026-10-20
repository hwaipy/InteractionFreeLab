from interactionfreepy import IFWorker
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import scipy.optimize as optimize
from numpy import *
import math
from urllib.request import urlopen
from pytimetag import DataBlock
import time
from worker_config import worker, ip
import msgpack
pi = np.pi
# Q1：ZZ的双探测器响应事件如何处理？
# Q2：decoy state的计算应该用哪些数据计算？


class DataBlockParser:
    lastObject = None
    # phase_invariant_time = 10 * 10 ** 9

    def __init__(self, dataBlock, randomNumbersMatcher, triggerChannel=0, data1Channel=2, data2Channel=3, pulsePeriod=10000, center=5000, gateSignal=1000, gateRef=5000, phaseThreshold=pi/8/2, phase_invariant_time=0.5 * 10 ** 9, ref_colleted=False, rnStat=None):
        self.dataBlock = dataBlock
        self.randomNumbersMatcher = randomNumbersMatcher
        self.rnsAlice = randomNumbersMatcher.rnsAlice
        self.rnsBob = randomNumbersMatcher.rnsBob
        self.rnslength = len(self.rnsAlice)
        self.pulsePeriod = pulsePeriod
        self.numPulse = int(1E12/self.pulsePeriod)
        self.center = center
        self.gateSignal = gateSignal
        self.gateRef = gateRef
        self.triggerChannel = triggerChannel
        self.data1Channel = data1Channel
        self.data2Channel = data2Channel
        self.phaseThreshold = phaseThreshold  # [phi-phaseThreshold, phi+phaseThreshold]
        self.phase_invariant_time = phase_invariant_time
        self.group = round(10 ** 12 / self.phase_invariant_time)
        self.expectedZ1 = 0.03
        self.results = {'RNS':{}, 'Count': {}, 'RNCount': {}, 'Sifted Key': {}, 'Sifted Key per RN': {}, 'errorRate': {}, 'codeRate': np.nan, 'reference': {}}
        self.ref_colleted = ref_colleted
        self.matchedRandomNumbers = self.randomNumbersMatcher.matchedRandomNumbers
        self.rnStat = rnStat
        DataBlockParser.lastObject = self

    @classmethod
    def IDtoRNS(cls, id: str):
        return msgpack.unpackb(worker.TF_FileStorage.readMassive(id=id))

    def dataCount(self):
        data = self.dataBlock['Content']
        # print('===================================')
        # print(len(triggerList))
        count = dict()
        count['intervene0'] = len(data[2])
        count['intervene1'] = len(data[3])
        count['AliceSync'] = len(data[4])
        count['BobSync'] = len(data[5])
        return count

    def parse(self):
        data = self.dataBlock['Content']
        triggerList = data[0]  # 25000
        # print('===================================')
        # print(len(triggerList))
        data1List = data[2]
        data2List = data[3]

        # Alice、Bob匹配的随机数matchedRandomNumbers。定义为：
        # 基矢不匹配、Gap，均为-1
        # 对于OO态：为0
        # 对于XX或YY态：为0bPPPPDD，其中PPPP为(alice相位-bob相位)%16，DD为01(XX)或10(YY)
        # 对于ZZ态：为0bAB11，其中A为alice编码，B为Bob编码，0代表不发，1代表发
        # 对于Ref；为0b1PPPP00，其中PPPP为(alice相位-bob相位)%16
        if self.matchedRandomNumbers is None:
            matchedRandomNumbers, rnStat = self.matchedRandomNumbers_fitting(self.rnsAlice, self.rnsBob)
            # rnStat记录了随机数不匹配的、匹配的（XYZ态）脉冲对数分别是多少
            self.results['RNCount'] = rnStat
            self.results['RNS']['matchedRandomNumbers'] = matchedRandomNumbers
            # self.results['RNS']['Alice'] = self.rnsAlice
            # self.results['RNS']['Bob'] = self.rnsBob
            # print(np.sum(rnStat['XX'])+np.sum(rnStat['YY'])+np.sum(rnStat['ZZ'])+np.sum(rnStat['OO']))
        else:
            matchedRandomNumbers = self.matchedRandomNumbers
            self.results['RNCount'] = self.rnStat
        # print('matchedRandomNumbers=', matchedRandomNumbers)
        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        deltaMetas = self.__deltaMeta(triggerList, data1List, data2List)
        # 将所有deltaMeta拆分为signal序列和ref序列，且只保留0、X、Y、Z态匹配的数据
        signalDeltaMetas, refDeltaMetas = self.split(deltaMetas, matchedRandomNumbers)
        # print(len(signalDeltaMetas), len(refDeltaMetas))
        self.results['Count']['All data1List'] = len(data1List)
        self.results['Count']['All data2List'] = len(data2List)
        self.results['Count']['All References'] = len(refDeltaMetas)
        self.results['Count']['All Signals'] = len(signalDeltaMetas)

        # 对于signalDeltaMatas，需要去掉trigger序号和相对trigger的脉冲序号相等的事例（即一个脉冲周期内两个探测器响应）-----------也许被删去的每对光子需要增加0.5个错误计数
        signalDeltaMetas = self.__purgeSamePulseEvents(signalDeltaMetas)
        # print(len(signalDeltaMetas))
        self.results['Count']['Single Dectected Signals'] = len(signalDeltaMetas)

        # 只保留门宽内的数据
        signalDeltaMetas = self.__gated(signalDeltaMetas, self.center, self.gateSignal)
        refDeltaMetas = self.__gated(refDeltaMetas, self.center, self.gateRef)
        # print(len(signalDeltaMetas), len(refDeltaMetas))
        if self.ref_colleted: self.results['reference']['ref'] = refDeltaMetas
        self.results['Count']['Valid Signals'] = len(signalDeltaMetas)
        self.results['Count']['Valid References'] = len(refDeltaMetas)

        # 按照两边的随机数，选出基矢匹配的事件，即sifted key
        OODeltaMetas, XXDeltaMetas, YYDeltaMetas, ZZDeltaMetas = self.__sifted(signalDeltaMetas, matchedRandomNumbers)
        self.results['Count']['Sifted Key OO'] = len(OODeltaMetas)
        self.results['Count']['Sifted Key XX'] = len(XXDeltaMetas)
        self.results['Count']['Sifted Key YY'] = len(YYDeltaMetas)
        self.results['Count']['Sifted Key ZZ'] = len(ZZDeltaMetas)
        # print(len(OODeltaMetas), len(XXDeltaMetas), len(YYDeltaMetas), len(ZZDeltaMetas))

        self.results['Sifted Key']['OO'] = [len(OODeltaMetas)]
        # results['Sifted Key']['ZZ']中:[00的数量, 01的数量, 10的数量, 11的数量]， 计算bit error
        self.results['Sifted Key']['ZZ'] = self.__siftedKeyParseZZ(ZZDeltaMetas, matchedRandomNumbers)
        # print(self.results['Sifted Key']['ZZ'])

        # phaseDeltas:把一秒切分为len(phaseDeltas) = group份,记录每份的相位
        phaseDeltas = self.__fitPhaseDelta(refDeltaMetas, matchedRandomNumbers)
        # siftedKeyXX， siftedKeyYY为[[pi/2相位差探测器0计数, pi/2相位差探测器1计数, 3pi/2相位差探测器0计数, 3pi/2相位差探测器1计数] for 16个相位编码]
        siftedKeyXX = self.__siftedKeyParseXY(XXDeltaMetas, matchedRandomNumbers, phaseDeltas)
        siftedKeyYY = self.__siftedKeyParseXY(YYDeltaMetas, matchedRandomNumbers, phaseDeltas)
        # self.check_siftedKeyParseXY(XXDeltaMetas, matchedRandomNumbers, phaseDeltas)
        # self.check_siftedKeyParseXY(YYDeltaMetas, matchedRandomNumbers, phaseDeltas)
        # print(siftedKeyXX, siftedKeyYY)

        self.results['Sifted Key']['XX'] = [np.sum(siftedKeyXX[i]) for i in range(16)]
        self.results['Sifted Key']['YY'] = [np.sum(siftedKeyYY[i]) for i in range(16)]

        # Sifted Key 的概率
        for basis in ['OO', 'XX', 'YY', 'ZZ']:
            sk = self.results['Sifted Key'][basis]
            rn = self.results['RNCount'][basis]
            self.results['Sifted Key per RN'][basis] = [sk[i] / rn[i] for i in range(len(sk))]

        # print(self.results)
        # XY误码率
        self.results['errorRate']['XX'], self.results['Sifted Key']['phase sifted XX'] = self.errorRateXY(siftedKeyXX)
        self.results['errorRate']['YY'], self.results['Sifted Key']['phase sifted YY'] = self.errorRateXY(siftedKeyYY)
        # Z误码率
        self.results['errorRate']['ZZ'] = self.errorRateZZ(siftedKey=self.results['Sifted Key']['ZZ'])
        self.results['errorRate']['ZZ expected'] = self.expectedZZerror(P_expectedZ1=self.expectedZ1, keyperRN=self.results['Sifted Key per RN']['ZZ'])
        # 成码率
        self.results['codeRate'] = self.codeRate(phaseError=np.average([self.results['errorRate']['XX'], self.results['errorRate']['YY']]), bitError=self.results['errorRate']['ZZ'])

        return self.results

    def statistics(self, printYN=False):
        data = self.dataBlock['Content']
        triggerList = data[0]  # 25000
        # print('===================================')
        # print(len(triggerList))
        data1List = data[2]
        data2List = data[3]

        print('photon counts:', len(data1List), len(data2List))

        # 随机数统计
        # statistics_all, key_list = self.statistics_rns(self.rnsAlice, self.rnsBob, printYN=printYN)
        statistics_all = self.randomNumbersMatcher.statistics_all
        key_list = self.randomNumbersMatcher.key_list

        # 统计探测事件
        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        deltaMetas = self.__deltaMeta(triggerList, data1List, data2List)
        # 将所有deltaMeta提取出signal事件
        all_signalDeltaMetas, all_refDeltaMetas = self.split(deltaMetas, self.rnsAlice)
        # 对于signalDeltaMatas，需要去掉trigger序号和相对trigger的脉冲序号相等的事例（即一个脉冲周期内两个探测器响应）-----------也许被删去的每对光子需要增加0.5个错误计数
        all_signalDeltaMetas = self.__purgeSamePulseEvents(all_signalDeltaMetas)
        # 只保留门宽内的数据
        all_signalDeltaMetas = self.__gated(all_signalDeltaMetas, self.center, self.gateSignal)

        def rns2key(rns):
            keys_list = []
            if rns < 0 or rns >=64: raise ValueError('not signal')
            if rns % 4 == 0: keys_list.append('signal0')
            if rns % 4 == 1: keys_list.append('signalX')
            if rns % 4 == 2: keys_list.append('signalY')
            if rns % 4 == 3: keys_list.append('signalZ')
            if rns == 3: keys_list.append('signalZ0')
            if rns == 7: keys_list.append('signalZ1')
            return keys_list

        statistics_all['all']['signal']['detector_count'] = len(all_signalDeltaMetas)
        statistics_all['all']['ref']['detector_count'] = len(all_refDeltaMetas)
        for deltaMeta in all_signalDeltaMetas:
            index = deltaMeta[5]
            Arns = self.rnsAlice[index]
            Brns = self.rnsBob[index]
            Akeys = rns2key(Arns)
            Bkeys = rns2key(Brns)
            for Akey in Akeys:
                for Bkey in Bkeys:
                    statistics_all[Akey][Bkey]['detector_count'] += 1

        return statistics_all, key_list

    @classmethod
    # def statistics_rns(cls, Alice_rns, Bob_rns, printYN=True):
    #     # 随机数统计
    #     from LongRandomWaveform import LongWaveformGenerator
    #     # 统计前预处理
    #     LongWaveformGenerator.selectSame(Alice_rns, Bob_rns)
    #     result = dict()
    #     result['Alice'] = LongWaveformGenerator.analyzeRNS(Alice_rns)
    #     if printYN:print(result['Alice']['count'])
    #     result['Bob'] = LongWaveformGenerator.analyzeRNS(Bob_rns)
    #     if printYN:print(result['Bob']['count'])
    #     length_rns = len(Alice_rns)
    #     length_rns_signal = len(result["Alice"]["signal"])

    #     key_list = result['Alice'].keys()
    #     key_list = [i for i in key_list if 'signal' in i and i != 'signal']
    #     statistics_all = dict()

    #     # 随机数统计
    #     allref = LongWaveformGenerator.selectSame(result['Alice']['ref'], result['Bob']['ref'])
    #     allsig = LongWaveformGenerator.selectSame(result['Alice']['signal'], result['Bob']['signal'])
    #     statistics_all['all'] = {'ref': {'count': len(allref), 'ratio': len(allref) / length_rns, 'detector_count': 0}, 'signal': {'count': len(allsig), 'ratio': len(allsig) / length_rns, 'detector_count': 0}}
    #     if printYN:print(f'reference对数：{len(allref)}, 占比：{len(allref) / length_rns}')
    #     if printYN:print(f'signal对数：{len(allsig)}, 占比：{len(allsig) / length_rns}')
    #     # signal统计
    #     for key0 in key_list:
    #         statistics_all[key0] = dict()
    #         for key1 in key_list:
    #             statistics_all[key0][key1] = dict()
    #             # statistics_all[key0][key1]['index'] = LongWaveformGenerator.selectSame(result['Alice'][key0], result['Bob'][key1])
    #             statistics_all[key0][key1]['count'] = len(LongWaveformGenerator.selectSame(result['Alice'][key0], result['Bob'][key1]))
    #             statistics_all[key0][key1]['ratio'] = statistics_all[key0][key1]['count'] / length_rns_signal
    #             statistics_all[key0][key1]['detector_count'] = 0
    #             if printYN:print(f'Alice={key0}, Bob={key1}, 个数={statistics_all[key0][key1]["count"]}, 占signal比：{statistics_all[key0][key1]["ratio"]}')

    #     lZZ = [statistics_all['signalZ0']['signalZ0']['count'], statistics_all['signalZ0']['signalZ1']['count'], statistics_all['signalZ1']['signalZ0']['count'], statistics_all['signalZ1']['signalZ1']['count']]
    #     if printYN:print(f'ZZ态(AB)[00, 01, 10, 11] 个数{lZZ}, 占比：{[i / length_rns for i in lZZ]}, 占signal比：{[i / length_rns_signal for i in lZZ]}, 占ZZ比：{[i / statistics_all["signalZ"]["signalZ"]["count"] for i in lZZ]}')
    #     return statistics_all, key_list

    def freq_diff(self):
        data = self.dataBlock['Content']
        triggerList = data[0]  # 25000
        # print(len(triggerList))
        data1List = data[2]
        data2List = data[3]

        matchedRandomNumbers, rnStat = self.matchedRandomNumbers_fitting(self.rnsAlice, self.rnsBob)
        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        deltaMetas = self.__deltaMeta(triggerList, data1List, data2List)
        # 将所有deltaMeta拆分为signal序列和ref序列，且只保留0、X、Y、Z态匹配的数据
        signalDeltaMetas, refDeltaMetas = self.split(deltaMetas, matchedRandomNumbers)

        # 只保留门宽内的数据
        refDeltaMetas = self.__gated(refDeltaMetas, self.center, self.gateRef)

        refStats = self.ref_rns_matched(refDeltaMetas, matchedRandomNumbers)
        # 计算0相位差的ref脉冲对随机数的计数
        bincount = [r[0][0] for r in refStats]
        return bincount

    def expectedZZerror(self, P_expectedZ1, keyperRN):
        a = (1 - P_expectedZ1) ** 2 * keyperRN[0]
        b = (1 - P_expectedZ1) * P_expectedZ1 * keyperRN[1]
        c = (1 - P_expectedZ1) * P_expectedZ1 * keyperRN[2]
        d = P_expectedZ1 ** 2 * keyperRN[3]
        return (a + d) / (a + b + c + d)

    def codeRate(self, phaseError, bitError):
        def H2(error):
            return -error * np.log2(error) - (1 - error) * np.log2(1 - error)
        f = 1.1
        return 1-H2(phaseError) * f - H2(bitError)

    def errorRateZZ(self, siftedKey):
        return (siftedKey[0] + siftedKey[3]) / np.sum(siftedKey)

    def errorRateXY(self, siftedKey:list):
        error = list(np.array(siftedKey).sum(axis=0))
        # for i in range(len(siftedKey)):
        #     error = [(error[j]+siftedKey[i][j]) for j in range(len(error))]
        return (error[1]+error[2])/np.sum(error), error

    def ref_rns_matched(self, refDeltaMetas, matchedRandomNumbers, selected=False):
        # 处理数据
        # signalDeltaMetas, refDeltaMetas 每个元素包含5项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        refStats = np.zeros((self.group, 16, 2))  # [[[0, 0] for j in range(16)] for i in range(groupCount)]
        for deltaMeta in refDeltaMetas:
            mrn = matchedRandomNumbers[deltaMeta[5]]
            if mrn & 0b1000000 == 0b1000000:
                encode = ((mrn >> 2) & 0b1111)
                if selected:
                    if (self.rnsAlice[deltaMeta[5]] >> 2) & 0b1111 == encode: refStats[deltaMeta[4], encode, deltaMeta[3]] += 1
                else:
                    refStats[deltaMeta[4], encode, deltaMeta[3]] += 1
        # refStats = [[[0探测器计数, 1探测器计数] for j in range(16个相位编码随机数)] for i in range(groupCount)]
        return refStats

    def __fitPhaseDelta(self, refDeltaMetas, matchedRandomNumbers):
        # 处理数据
        # signalDeltaMetas, refDeltaMetas 每个元素包含5项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        refStats = np.zeros((self.group, 16, 2))  # [[[0, 0] for j in range(16)] for i in range(groupCount)]
        for deltaMeta in refDeltaMetas:
            mrn = matchedRandomNumbers[deltaMeta[5]]
            if mrn & 0b1000000 == 0b1000000:
                encode = ((mrn >> 2) & 0b1111)
                refStats[deltaMeta[4], encode, deltaMeta[3]] += 1
        # refStats = [[[0探测器计数, 1探测器计数] for j in range(16个相位编码随机数)] for i in range(groupCount)]

        # 随时间画出两探测器分光比（到探测器0的比例）
        phaseDeltas = []
        yss = []
        for refStat in refStats:
            # ys = 去探测器0的比例
            ys = [refStat[i][0] / np.sum(refStat[i]) if np.sum(refStat[i]) > 0 else np.nan for i in range(len(refStat))]
            yss.append(ys)
            xs = [i / 16 * 2 * np.pi for i in range(16) if not np.isnan(ys[i])]
            ys = [y for y in ys if not np.isnan(y)]
            phi = np.nan if len(ys) == 0 else optimize.curve_fit(self.func, xs, ys, p0=0, maxfev=500000)[0][0]
            phaseDeltas.append(phi)
            # print(phi, ys)

        # phaseDeltas:把一秒切分为len(phaseDeltas)=group份,记录每份的相位
        # print(phaseDeltas)
        return phaseDeltas

    @staticmethod
    def ref_plot(refStats, plot2show=False):
        # 随时间画出两探测器分光比（到探测器0的比例）
        phaseDeltas = []
        yss = []
        for refStat in refStats:
            # ys = 去探测器0的比例
            ys = [refStat[i][0] / np.sum(refStat[i]) if np.sum(refStat[i]) > 0 else np.nan for i in range(len(refStat))]
            yss.append(ys)
            xs = [i / 16 * 2 * np.pi for i in range(16) if not np.isnan(ys[i])]
            ys = [y for y in ys if not np.isnan(y)]
            phi = np.nan if len(ys) == 0 else optimize.curve_fit(DataBlockParser.func, xs, ys, p0=0, maxfev=500000)[0][0]
            phaseDeltas.append(phi)
            # print(phi, ys)

        max, min = [], []
        for i in range(4):
            l = [ys[i * 4] for ys in yss]
            # plt.plot(range(len(yss)), l)
            max.append(np.max(l))
            min.append(np.min(l))
        # plt.grid()
        # plt.title(f'phase of Reference = 0, $\pi$/, $\pi$, 3$\pi$/2\nextinction ratio = {np.max([np.max(max) / (1-np.max(max)), (1-np.min(min))/np.min(min)])}')
        # plt.show()

        # 画出每个时间片段的拟合相位
        # plt.plot([i for i in range(len(phaseDeltas))], phaseDeltas)
        # plt.title('phaseDeltas')
        # plt.show()

        # 探测器0计数
        max, min = [], []
        for i in range(4):
            l = [rs[i*4][0] for rs in refStats]
            plt.plot(range(len(l)), l, label=f'{i/2}$\pi$')
            max.append(np.max(l))
            min.append(np.min(l))
        plt.title(f"Detector0\nphase of Reference = 0, $\pi$/, $\pi$, 3$\pi$/2\nextinction ratio = {np.max(max) / np.min(min)}")
        plt.legend()
        plt.show()

        # 探测器1计数
        if plot2show:
            max, min = [], []
            for i in range(4):
                l = [rs[i * 4][1] for rs in refStats]
                plt.plot(range(len(l)), l, label=f'{i/2}$\pi$')
                max.append(np.max(l))
                min.append(np.min(l))
            plt.title(f"Detector1\nphase of Reference = 0, $\pi$/, $\pi$, 3$\pi$/2\nextinction ratio = {np.max(max) / np.min(min)}")
            plt.legend()
            plt.show()
        return

    def channel_extinction_ratio(self):
        data = self.dataBlock['Content']
        triggerList = data[0]  # 25000
        # print('===================================')
        # print(len(triggerList))
        data1List = data[2]
        data2List = data[3]

        # Alice、Bob匹配的随机数matchedRandomNumbers。定义为：
        # 基矢不匹配、Gap，均为-1
        # 对于OO态：为0
        # 对于XX或YY态：为0bPPPPDD，其中PPPP为(alice相位-bob相位)%16，DD为01(XX)或10(YY)
        # 对于ZZ态：为0bAB11，其中A为alice编码，B为Bob编码，0代表不发，1代表发
        # 对于Ref；为0b1PPPP00，其中PPPP为(alice相位-bob相位)%16
        matchedRandomNumbers, rnStat = self.matchedRandomNumbers_fitting(self.rnsAlice, self.rnsBob)

        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        deltaMetas = self.__deltaMeta(triggerList, data1List, data2List)
        # 将所有deltaMeta拆分为signal序列和ref序列，且只保留0、X、Y、Z态匹配的数据
        signalDeltaMetas, refDeltaMetas = self.split(deltaMetas, matchedRandomNumbers)
        self.results['Count']['All data1List'] = len(data1List)
        self.results['Count']['All data2List'] = len(data2List)
        self.results['Count']['All References'] = len(refDeltaMetas)
        self.results['Count']['All Signals'] = len(signalDeltaMetas)

        # 对于signalDeltaMatas，需要去掉trigger序号和相对trigger的脉冲序号相等的事例（即一个脉冲周期内两个探测器响应）-----------也许被删去的每对光子需要增加0.5个错误计数
        signalDeltaMetas = self.__purgeSamePulseEvents(signalDeltaMetas)
        self.results['Count']['Single Dectected Signals'] = len(signalDeltaMetas)

        # 只保留门宽内的数据
        signalDeltaMetas = self.__gated(signalDeltaMetas, self.center, self.gateSignal)
        refDeltaMetas = self.__gated(refDeltaMetas, self.center, self.gateRef)
        # print(len(signalDeltaMetas), len(refDeltaMetas))
        self.results['reference']['ref'] = refDeltaMetas
        self.results['Count']['Valid Signals'] = len(signalDeltaMetas)
        self.results['Count']['Valid References'] = len(refDeltaMetas)

        refStats = self.countChannel(signalDeltaMetas)
        return refStats

    def countChannel(self, DeltaMetas):
        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        # 处理数据
        # signalDeltaMetas, refDeltaMetas 每个元素包含5项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        refStats = np.zeros((self.group, 2))  # [[[0, 0] for j in range(16)] for i in range(groupCount)]
        for deltaMeta in DeltaMetas:
            refStats[deltaMeta[4], deltaMeta[3]] += 1
        # refStats = [[[0探测器计数, 1探测器计数] for j in range(16个相位编码随机数)] for i in range(groupCount)]
        return refStats

    @classmethod
    def channelCountPlot(self, refStats):
        # 探测器0计数
        l0 = [rs[0] for rs in refStats]
        plt.plot(range(len(l0)), l0, label=f"Detector0\next_ratio = {np.max(l0) / np.min(l0)}")

        # 探测器1计数
        l1 = [rs[1] for rs in refStats]
        plt.plot(range(len(l1)), l1, label=f"Detector1\next_ratio = {np.max(l1) / np.min(l1)}")
        plt.legend()
        plt.show()
        return

    @staticmethod
    def func(x, phi0):
        return (np.sin(x + phi0) + 1) / 2

    def __deltaMeta(self, triggerList, data1List, data2List, invariant_time=None):
        if not invariant_time: invariant_time = self.phase_invariant_time
        numPulse_eachTrigger = int(self.numPulse/len(triggerList))
        def deltaMeta(triggerList, dataList, detectornum, rnslength):
            currentTriggerIndex = 0
            deltaMetas = []

            for time in dataList:
                for i in range(currentTriggerIndex, len(triggerList)):
                    if triggerList[i] < time:
                        currentTriggerIndex = i
                    else:
                        break
                delta = time - triggerList[currentTriggerIndex]
                pulseIndex = delta // self.pulsePeriod
                invariantTimeIndex = int((time - triggerList[0]) // invariant_time)
                if 0 <= pulseIndex < len(self.rnsAlice): deltaMetas.append([currentTriggerIndex, pulseIndex, delta % self.pulsePeriod, detectornum, invariantTimeIndex, (numPulse_eachTrigger*currentTriggerIndex+pulseIndex) % rnslength])
            return deltaMetas

        # 对齐Trigger
        # 计算每个周期内光子的到达时间 单位ps
        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        deltaMetas1 = deltaMeta(triggerList, data1List, detectornum=0, rnslength=self.rnslength)
        deltaMetas2 = deltaMeta(triggerList, data2List, detectornum=1, rnslength=self.rnslength)
        deltaMetas = deltaMetas1 + deltaMetas2
        deltaMetas.sort()

        return deltaMetas

    @classmethod
    def split(cls, deltaMetas, rns):
        # 将所有deltaMeta拆分为signal序列和ref序列
        signalDeltaMetas = []
        refDeltaMetas = []
        for deltaMeta in deltaMetas:
            rn = rns[deltaMeta[5]]
            if 0 <= rn < 64:
                signalDeltaMetas.append(deltaMeta)
            elif 0 <= rn < 128:
                refDeltaMetas.append(deltaMeta)
        return signalDeltaMetas, refDeltaMetas

    def __purgeSamePulseEvents(self, deltaMetas):
        newDeltaMetas = []
        i = 0
        while i < len(deltaMetas) - 1:
            if deltaMetas[i][:2] == deltaMetas[i + 1][:2]:
                i += 1
            else:
                newDeltaMetas.append(deltaMetas[i])
            i += 1
        if i == len(deltaMetas) - 1: newDeltaMetas.append(deltaMetas[i])
        return newDeltaMetas

    @classmethod
    def matchedRandomNumbers_fitting(cls, rnsAlice, rnsBob):
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
        rnStat = dict()
        rnStat['Invalid'] = [len([r for r in matchedRandomNumbers if r == -1])]  # 不匹配的数量
        rnStat['OO'] = [len([r for r in matchedRandomNumbers if r == 0])]  # 真空态数量
        rnStat['XX'] = stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b01 and r >= 0], 16)  # [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
        rnStat['YY'] = stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b10 and r >= 0], 16)  # [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
        rnStat['ZZ'] = stat([(r >> 2) for r in matchedRandomNumbers if (r & 0b1000011) == 0b11 and r >= 0], 4)  # [4个元素，表示Alice、Bob的Z态为发1或不发0]
        rnStat['Ref'] = stat([((r & 0b111111) >> 2) for r in matchedRandomNumbers if (r & 0b1000000) == 0b1000000 and r >= 0], 16)  # [16个元素，每个元素表示 每个相位编码的随机数 有多少个]
        # print(rnStat)
        return matchedRandomNumbers, rnStat

    def __gated(self, deltaMetas, center, gate):
        lowerBound = center - gate / 2
        upperBound = center + gate / 2
        return [dm for dm in deltaMetas if lowerBound <= dm[2] <= upperBound]

    def __sifted(self, deltaMetas, matchedRandomNumbers):
        siftedDeltaMetas = [[] for i in range(4)]
        for deltaMeta in deltaMetas:
            mrn = matchedRandomNumbers[deltaMeta[5]]
            if mrn >= 0:
                siftedDeltaMetas[(mrn & 0b11)].append(deltaMeta)
        return siftedDeltaMetas

    def __siftedKeyParseZZ(self, deltaMetas, matchedRandomNumbers):
        stat = [0] * 4
        for dm in deltaMetas:
            # signalDeltaMetas, refDeltaMetas 每个元素包含5项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
            mrn = matchedRandomNumbers[dm[5]]
            stat[(mrn >> 2)] += 1
        return stat

    def __siftedKeyParseXY(self, deltaMetas, matchedRandomNumbers, phaseDeltas):

        def cal_phi(actualPhase, phi, phaseThreshold):
            actualPhase = actualPhase % (2 * pi)
            if not 0 <= phi < 2 * pi: raise ValueError('phi is not in range [0, 2pi)')
            if phaseThreshold <= phi < (2*pi-phaseThreshold):
                if abs(actualPhase-phi) <= phaseThreshold: return True
            else:
                if phaseThreshold > phi:
                    if abs(actualPhase - phi) <= phaseThreshold or (2 * pi - actualPhase) <= (phaseThreshold - phi): return True
                else:
                    if abs(actualPhase - phi) <= phaseThreshold or actualPhase <= (phi + phaseThreshold - 2 * pi): return True
            return False

        # 确保相位容忍的设置满足要求
        if (2 * self.phaseThreshold) > (2 * pi / 16): raise ValueError('phaseThreshold > 2pi/16')
        # stat = [[pi/2相位差探测器0计数, pi/2相位差探测器1计数, 3pi/2相位差探测器0计数, 3pi/2相位差探测器1计数] for 16个相位编码]
        stat = [[0] * 4 for i in range(16)]
        # deltaMeta 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        for dm in deltaMetas:
            mrn = matchedRandomNumbers[dm[5]]
            encode = ((mrn & 0b111100) >> 2)
            phaseDelta = phaseDeltas[dm[4]]
            actualPhaseDelta = (encode / 16 * 2 * pi + phaseDelta) % (2 * pi)
            for j in [0, 2]:
                phi = j * pi/2 + pi / 2
                if cal_phi(actualPhase=actualPhaseDelta, phi=phi, phaseThreshold=self.phaseThreshold): stat[encode][j+dm[3]] += 1
        return stat

    def check_siftedKeyParseXY(self, deltaMetas, matchedRandomNumbers, phaseDeltas):
        def cal_phi(actualPhase, phi, phaseThreshold):
            actualPhase = actualPhase % (2 * pi)
            if not 0 <= phi < 2 * pi: raise ValueError('phi is not in range [0, 2pi)')
            if phaseThreshold <= phi < (2*pi-phaseThreshold):
                if abs(actualPhase-phi) <= phaseThreshold: return True
            else:
                if phaseThreshold > phi:
                    if abs(actualPhase - phi) <= phaseThreshold or (2 * pi - actualPhase) <= (phaseThreshold - phi): return True
                else:
                    if abs(actualPhase - phi) <= phaseThreshold or actualPhase <= (phi + phaseThreshold - 2 * pi): return True
            return False

        # 确保相位容忍的设置满足要求
        if (2 * self.phaseThreshold) >= (2 * pi / 16): raise ValueError('phaseThreshold > 2pi/16')
        # deltaMeta 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号

        phaseDeltas = [i % (2*pi) for i in phaseDeltas]
        # print('phaseDeltas=', phaseDeltas)
        # 筛选出有效时间片段
        collet_data = dict()
        for i in range(len(phaseDeltas)):
            for j in range(16):
                phi = j / 16 * 2 * pi
                if cal_phi(actualPhase=phaseDeltas[i], phi=phi, phaseThreshold=self.phaseThreshold):
                    collet_data.setdefault(f'{i}', [[0, 0] for k in range(16)])

        # 将有效时间片段的数据统计整理
        for dm in deltaMetas:
            mrn = matchedRandomNumbers[dm[5]]
            encode = ((mrn & 0b111100) >> 2)
            invariant_time_num = dm[4]
            phaseDelta = phaseDeltas[invariant_time_num]
            actualPhaseDelta = (encode / 16 * 2 * pi + phaseDelta) % (2 * pi)

            # 判断是否属于有效时间片段, 若属于, 则加入统计
            if f'{dm[4]}' in collet_data.keys():
                collet_data[f'{dm[4]}'][encode][dm[3]] += 1

        # print('collet_data=', collet_data)

        max, min = 0, 0
        for key in collet_data.keys():
            # print((4-round(phaseDeltas[int(key)]/pi*8)) % 16, (12-round(phaseDeltas[int(key)]/pi*8)) % 16, collet_data[key])
            max += collet_data[key][(4-round(phaseDeltas[int(key)]/pi*8)) % 16][0] + collet_data[key][(12-round(phaseDeltas[int(key)]/pi*8)) % 16][1]
            min += collet_data[key][(4-round(phaseDeltas[int(key)]/pi*8)) % 16][1] + collet_data[key][(12-round(phaseDeltas[int(key)]/pi*8)) % 16][0]
        print(max, min)

        return

    @classmethod
    def formatResults(clz, results):
        totalTime = len(results)
        basis = ['OO', 'XX', 'YY', 'ZZ']

        print(f'Reference Count: {np.average([r["Count"]["References"] for r in results]):,.0f}/s')

        allSignalCount = np.average([r["Count"]["All Signals"] for r in results])
        singleDetectedSignalCount = np.average([r["Count"]["Single Dectected Signals"] for r in results])
        validSignalCount = np.average([r["Count"]["Valid Signals"] for r in results])
        print(
            f'Signal Count: {validSignalCount:,.0f}/s (from {allSignalCount:,.0f}/s in total, {(1 - singleDetectedSignalCount / allSignalCount) * 100:.3f}% double click, {((singleDetectedSignalCount - validSignalCount) / allSignalCount) * 100:.2f}% gated.)')

        siftedKeyCounts = [sum([r["Count"]["Sifted Key " + base] for r in results]) for base in basis]
        siftedKeyCountsStrings = [f'{basis[i]} = {siftedKeyCounts[i]:,.0f} ({siftedKeyCounts[i] / totalTime:,.0f}/s)' for i in range(len(basis))]
        print(f'Sifted Key Count: ' + ', '.join(siftedKeyCountsStrings))

        siftedKeys = {}
        RNCounts = {}
        siftedKeysPerRN = {}
        for base in basis:
            siftedKey = np.sum(np.array([r['Sifted Key'][base] for r in results]), axis=0)
            RNCount = np.sum(np.array([r['RNCount'][base] for r in results]), axis=0)
            siftedKeys[base] = list(siftedKey)
            RNCounts[base] = list(RNCount)
            siftedKeysPerRN[base] = list(siftedKey / RNCount)

        print(f'Vacuum / Z11 = {(siftedKeysPerRN["OO"][0] / siftedKeysPerRN["ZZ"][3]):,.6f}')
        print(f'Normalized Z: ' + ', '.join([f'{c / siftedKeysPerRN["ZZ"][3]:,.6f}' for c in siftedKeysPerRN['ZZ']]))

    def searchPMperiod(self):
        data = self.dataBlock['Content']
        triggerList = data[0]  # 25000
        # print('===================================')
        # print(len(triggerList))
        data1List = data[2]
        data2List = data[3]

        # Alice、Bob匹配的随机数。定义为：
        # 基矢不匹配、Gap，均为-1
        # 对于OO态：为0
        # 对于XX或YY态：为0bPPPPDD，其中PPPP为(alice相位-bob相位)%16，DD为01(XX)或10(YY)
        # 对于ZZ态：为0bAB11，其中A为alice编码，B为Bob编码，0代表不发，1代表发
        # 对于Ref；为0b1PPPP00，其中PPPP为(alice相位-bob相位)%16
        matchedRandomNumbers, rnStat = self.matchedRandomNumbers_fitting(self.rnsAlice, self.rnsBob)
        self.results['RNCount'] = rnStat

        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        deltaMetas = self.__deltaMeta(triggerList, data1List, data2List)
        # 将所有deltaMeta拆分为signal序列和ref序列
        signalDeltaMetas, refDeltaMetas = self.split(deltaMetas, matchedRandomNumbers)

        # 只保留门宽内的数据
        signalDeltaMetas = self.__gated(signalDeltaMetas, self.center, self.gateSignal)
        refDeltaMetas = self.__gated(refDeltaMetas, self.center, self.gateRef)

        # 将数据按每段phase_invariant_time分为group段，每段视作全局相位近似不变
        signalClassify = self.__classify(signalDeltaMetas, matchedRandomNumbers)
        # signalClassify = [[[0探测器计数, 1探测器计数] for j in range(16个相位编码随机数)] for i in range(invariantTimeIndex)]

        # 相位筛选获得error_rate
        selected_signalgroup = self.select_phase(signalClassify)

        # 计算数据周期
        # freq = self.curve_freq(signalClassify)
        # print('freq = ', freq)

        return selected_signalgroup

    def __classify(self, DeltaMetas, matchedRandomNumbers):

        # signalDeltaMetas, refDeltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        classify = np.zeros((self.group, 16, 2))  # [[[0, 0] for j in range(16)] for i in range(groupCount)]
        for deltaMeta in DeltaMetas:
            # Alice、Bob匹配的随机数matchedRandomNumbers。定义为：
            # 基矢不匹配、Gap，均为-1
            # 对于OO态：为0
            # 对于XX或YY态：为0bPPPPDD，其中PPPP为(alice相位-bob相位)%16，DD为01(XX)或10(YY)
            # 对于ZZ态：为0bAB11，其中A为alice编码，B为Bob编码，0代表不发，1代表发
            # 对于Ref；为0b1PPPP00，其中PPPP为(alice相位-bob相位)%16
            mrn = matchedRandomNumbers[deltaMeta[5]]
            encode = ((mrn >> 2) & 0b1111)
            if mrn > 0 : classify[deltaMeta[4], encode, deltaMeta[3]] += 1
            # classify = [[[0探测器计数, 1探测器计数] for j in range(16个相位编码随机数)] for i in range(invariantTimeIndex)]
        return classify

    def curve_freq(self, classify):
        freqs = []
        for list in classify:
            ys = list[:, 0] / (np.sum(list, axis=1))
            xs = [i / 16 * 2 * np.pi for i in range(16) if not np.isnan(ys[i])]
            ys = [y for y in ys if not np.isnan(y)]
            freq = np.nan if len(ys) == 0 else optimize.curve_fit(self.freqfunc, xs, ys, p0=[1, 0], maxfev=50000)[0][0]
            #  , bounds=([0.5, -2*np.pi], [2, 2*np.pi])
            freqs.append(freq)
            # print(freq)
        aver_freq = average(freqs)

        # plt.plot([i for i in range(len(classify[0]))], classify[0][:, 0] / (np.sum(classify[0], axis=1)))
        # plt.grid()
        # plt.show()
        return aver_freq

    def freqfunc(self, x, freq, phi0):
        return (1 - np.cos(2 * np.pi * freq * x + phi0)) / 2

    @classmethod
    def plot(self, data=None, Divide=250, from_time=0, to_time=40000, binNum=1000):
        if not data: data = DataBlockParser.lastObject.dataBlock['Content']

        to_time = to_time * 1E3
        period = 40000 * 1E3
        divideTime = round((to_time - from_time) / Divide)
        binTime = round(divideTime / binNum)

        # 对齐Trigger,保留从from_time到to_time时间到达的光子事件
        def deltaMeta(triggerList, dataList):
            currentTriggerIndex = 0
            deltaMetas = []
            for time in dataList:
                for i in range(currentTriggerIndex, len(triggerList)):
                    if triggerList[i] < time:
                        currentTriggerIndex = i
                    else:
                        break
                delta = time - triggerList[currentTriggerIndex]
                deltaMetas.append([currentTriggerIndex, delta, delta // divideTime, delta % divideTime // binTime])
            return deltaMetas

        def counter(triggerList, dataList):
            # 对齐Trigger,deltaMetas每个元素为[0]对应的trigger序号，[1]相对trigger的到达时间，[2]事件在trigger内的divide序号，[3]光子在此divide片段的bin序号]
            deltaMetas = deltaMeta(triggerList, dataList)
            # 计算每个bin内的光子数
            binCount = [0 for i in range(binNum)]
            for each in deltaMetas:
                binCount[each[3]] += 1
            return binCount

        triggerList = data[0]  # 25000
        data1List = data[2]
        data2List = data[3]

        binCount1 = counter(triggerList, data1List)
        binCount2 = counter(triggerList, data2List)

        Time = [i * binTime for i in range(binNum)]
        plt.plot(Time, binCount1)
        plt.plot(Time, binCount2)
        plt.grid()
        plt.show()
        return binCount1, binCount2

    def plotSignalPulse(self, binNum=100, DivideTime=10 * 10 ** 9, plotYN=True):
        def cal_histograms(signalDeltaMetas):
            histograms = [[0 for i in range(binNum)] for j in range(DivideNum)]
            # 计算每个bin内的光子数
            for each in signalDeltaMetas:
                binnum = each[2] // binTime
                histograms[each[4]][binnum] += 1
            return histograms

        # 参数
        pulsePeriod = self.pulsePeriod
        binTime = round(pulsePeriod / binNum)
        data = self.dataBlock['Content']
        triggerList = data[0]  # 25000
        data1List = data[2]
        data2List = data[3]
        DivideNum = round(1E12 / DivideTime)

        # 数据处理
        matchedRandomNumbers, rnStat = self.matchedRandomNumbers_fitting(self.rnsAlice, self.rnsBob)
        # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号, [5]对应的matchedRandomNumbers序列的随机数序号
        deltaMetas = self.__deltaMeta(triggerList, data1List, data2List, invariant_time=DivideTime)
        # 将所有deltaMeta拆分为signal序列和ref序列，且只保留0、X、Y、Z态匹配的数据
        signalDeltaMetas, refDeltaMetas = self.split(deltaMetas, matchedRandomNumbers)
        self.results['Count']['All data1List'] = len(data1List)
        self.results['Count']['All data2List'] = len(data2List)
        self.results['Count']['All Signals'] = len(signalDeltaMetas)

        # 获得脉冲直方图
        histograms = cal_histograms(signalDeltaMetas)
        histograms_array = np.array(histograms)
        histogram_total = list(np.sum(histograms_array, axis=0))

        Time = [i * binTime for i in range(binNum)]

        if plotYN:
            plt.plot(Time, histogram_total)
            plt.title('1 second signal pulse')
            plt.grid()
            plt.show()

        return histograms

    def select_phase(self, Classify):
        def phaseCurve(list):
            xs = [i/16*2*np.pi for i in range(len(list))]
            phi = np.nan if len(list) == 0 else optimize.curve_fit(func, xs, list, p0=0, maxfev=500000)[0][0]
            phi = phi % (2*np.pi)
            maxphase = (np.pi - phi) % (2*np.pi)
            minphase = (0 - phi) % (2 * np.pi)
            maxIndex = round(maxphase/(2*np.pi)*16) % 16
            minIndex = round(minphase/(2*np.pi)*16) % 16
            return phi, maxIndex, minIndex

        def func(x, phi0):
            return (1 - np.cos(x + phi0)) / 2

        # 两线以和的归一化方式化为一线
        Classify_p = [list[:, 0]/(np.sum(list, axis=1)[:]) for list in Classify]
        # classify = [[[0探测器计数, 1探测器计数] for j in range(16个相位编码随机数)] for i in range(invariantTimeIndex)]
        selected_group = []
        for i in range(len(Classify_p)):
            phi, maxIndex, minIndex = phaseCurve(Classify_p[i])
            if phi % (2*np.pi/16) <= (self.phaseThreshold/2) or phi % (2*np.pi/16) >= ((2*np.pi/16)-(self.phaseThreshold/2)):
                selected_group0 = [i, phi, Classify_p[i][maxIndex], Classify_p[i][minIndex]]
                selected_group.append(selected_group0)
        # selected_group筛选出了符合相位要求的脉冲组，每个元素记录了这些脉冲组的信息[group的序号, 拟合相位, pi相位对应的计数率（归一化）, 0或2pi相位对应的计数率（归一化）]
        return selected_group

    @classmethod
    def e_center(self, histogram, pulsePeriod=10000, binCount=100):
        # 找脉冲中心
        xs = np.linspace(0, pulsePeriod, binCount + 1)[:-1]
        xs += (xs[1] - xs[0]) / 2

        maxValue = np.max(histogram)
        maxIndex = np.where(histogram == maxValue)[0][0]
        inPulseIndices = np.where(histogram > maxValue * 0.2)[0]
        maxIndexInPulse = np.where(inPulseIndices == maxIndex)[0][0]
        inPulseIndices = inPulseIndices[np.where(inPulseIndices == [i + maxIndex - maxIndexInPulse for i in range(len(inPulseIndices))])]
        est_center = sum([xs[i] * histogram[i] for i in inPulseIndices]) / sum([histogram[i] for i in inPulseIndices])
        return est_center/1000


# 扫半波电压用
def TDCRawDataParser_16phase(beginTime, endTime):
    ###################
    # # 随机数定义
    # # AWG对随机数的定义是： （从右到左）前2位指代decoy state，3-6位指代phase encoding，7位指代ref/signal
    # # TDC数据处理中对随机数的定义稍有不同： （从右到左）前2位指代decoy state。7-8位指代ref (01)/signal (00)/gap (10）。如果是X或Y态或ref，3-6位指代phase encoding；如果是O态，3-6位反正也无意义；如果是Z态，3-6位指代Z0 (0000)或Z1 (0001)
    #########  ########## ##########

    # 定义概览数据的存储地点
    storage = worker.Storage

    # 定义被处理数据的起止时间
    # beginTime = '2021-12-17 21:55:00'
    # endTime = '2021-12-17 21:56:00'

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1})
    print(f'{len(ranges)} seconds of data fetched.')

    max = []
    min = []
    for dataMeta in ranges[:]:
        beginTime = time.time()
        fetchTime = dataMeta['FetchTime']
        dataBlock = getDataBlock(fetchTime)
        # dataBlock = worker.TDCRawDataServer.fetchRawDataBlock('http://192.168.25.5:1001', fetchTime.replace('T', ' ').replace(':', '-')[:-9])
        # print('dataBlock')
        # print(dataBlock)
        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'], gateRef=1500)

        selected_group = parser.searchPMperiod()
        # print('selected_group', selected_group)
        for group in selected_group:
            max.append(group[2])
            min.append(group[3])
        # parser.parse()
        # results.append(parser.results)
        endTime = time.time()
        print(f'parsed in {endTime - beginTime} s.')
    max_aver = average(max)
    min_aver = average(min)
    # print(f'********* All Parse Finished **********')
    # DataBlockParser.formatResults(results)
    return max_aver, min_aver


# 数据画图用
def interaction_plot(beginTime, endTime):
    """
    随机数定义
    AWG对随机数的定义是： （从右到左）前2位指代decoy state，3-6位指代phase encoding，7位指代ref/signal
    TDC数据处理中对随机数的定义稍有不同： （从右到左）前2位指代decoy state。7-8位指代ref (01)/signal (00)/gap (10）。如果是X或Y态或ref，3-6位指代phase encoding；如果是O态，3-6位反正也无意义；如果是Z态，3-6位指代Z0 (0000)或Z1 (0001)
    """

    # 定义概览数据的存储地点
    storage = worker.Storage

    # 定义被处理数据的起止时间
    # beginTime = '2021-12-17 21:55:00'
    # endTime = '2021-12-17 21:56:00'

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1})
    print(f'{len(ranges)} seconds of data fetched.')

    for dataMeta in ranges[:1]:
        beginTime = time.time()
        fetchTime = dataMeta['FetchTime']
        dataBlock = getDataBlock(fetchTime)
        # dataBlock = worker.TDCRawDataServer.fetchRawDataBlock('http://192.168.25.5:1001', fetchTime.replace('T', ' ').replace(':', '-')[:-9])

        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'], gateRef=1500)
        parser.plot()


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


def TF(beginTime, endTime):
    """
    随机数定义
    AWG对随机数的定义是： （从右到左）前2位指代decoy state，3-6位指代phase encoding，7位指代ref/signal
    TDC数据处理中对随机数的定义稍有不同： （从右到左）前2位指代decoy state。7-8位指代ref (01)/signal (00)/gap (10）。如果是X或Y态或ref，3-6位指代phase encoding；如果是O态，3-6位反正也无意义；如果是Z态，3-6位指代Z0 (0000)或Z1 (0001)
    """

    # 定义概览数据的存储地点
    storage = worker.Storage

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1})
    print(f'{len(ranges)} seconds of data fetched.')

    for dataMeta in ranges[:]:
        beginTime = time.time()
        fetchTime = dataMeta['FetchTime']
        dataBlock = getDataBlock(fetchTime)
        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'])

        result = parser.parse()
        print(result['errorRate'], result['codeRate'])
    return


def calcPulseCenter(beginTime, endTime, DivideTime=10 * 10 ** 9):
    """
    随机数定义
    AWG对随机数的定义是： （从右到左）前2位指代decoy state，3-6位指代phase encoding，7位指代ref/signal
    TDC数据处理中对随机数的定义稍有不同： （从右到左）前2位指代decoy state。7-8位指代ref (01)/signal (00)/gap (10）。如果是X或Y态或ref，3-6位指代phase encoding；如果是O态，3-6位反正也无意义；如果是Z态，3-6位指代Z0 (0000)或Z1 (0001)
    """

    # 定义概览数据的存储地点
    storage = worker.Storage

    # 定义被处理数据的起止时间
    # beginTime = '2021-12-17 21:55:00'
    # endTime = '2021-12-17 21:56:00'

    # 获取所有在范围内的数据的采集时间
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1})
    print(f'{len(ranges)} seconds of data fetched.')
    centers = []
    n = 0
    for dataMeta in ranges[:]:
        fetchTime = dataMeta['FetchTime']
        print(n)
        n += 1
        dataBlock = getDataBlock(fetchTime)
        # dataBlock = worker.TDCRawDataServer.fetchRawDataBlock('http://192.168.25.5:1001', fetchTime.replace('T', ' ').replace(':', '-')[:-9])

        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'], gateRef=1500)

        histograms = parser.plotSignalPulse(binNum=100, DivideTime=DivideTime, plotYN=False)
        centerlist = [DataBlockParser.e_center(h) for h in histograms]
        centers.extend(centerlist)

    return centers, np.std(centers)


def std_AutosyncRoundTime():
    f = open('./时钟同步_数据整理/每秒500光子同步延长同步周期/AutosyncPeriodTest.txt', 'r')
    flines = f.readlines()
    flines = [eval(flines[i]) for i in range(len(flines))]
    print(flines, type(flines))
    timelist = []
    stdlist = []
    DivideTime = 100 * 10 ** 9
    for k in flines:
        time = k[0]
        print('roundTime=', time)
        beginTime = k[1]
        endTime = k[2]
        centers, std = calcPulseCenter(beginTime=beginTime, endTime=endTime, DivideTime=DivideTime)
        print(centers)
        timelist.append(time)
        stdlist.append(std)

        plt.plot([i * (DivideTime / 1E12) for i in range(len(centers))], centers)
        plt.title(f'roundTime={time / 10}s std={np.std(centers)}\nDivideTime={DivideTime / 1E12}s calPulse=28k/s')
        plt.xlabel('Time(s)')
        plt.ylabel('PulseCenter(ns)')
        plt.savefig(f'./时钟同步_数据整理/每秒500光子同步延长同步周期/Picture/{round(time / 10)}s perRound.png', dpi=1000)
        plt.close()

        file = open('./时钟同步_数据整理/每秒500光子同步延长同步周期/AutosyncPeriodTestResult.txt', 'a')
        file.write(str(time) + '\n')
        file.write(str([i * (DivideTime / 1E12) for i in range(len(centers))]) + '\n')
        file.write(str(centers) + '\n')
        file.close()

    plt.plot(timelist, stdlist)
    plt.savefig(f'./时钟同步_数据整理/每秒500光子同步延长同步周期/Picture/std-roundTime.png', dpi=1000)
    plt.close()


if __name__ == '__main__':
    # TF(beginTime='2022-08-16T23:54:50+08:00', endTime='2022-08-16T23:54:52+08:00')
    # Time = ['2022-02-21T02:54:19+08:00', '2022-02-21T02:54:39+08:00']
    # interaction_plot(Time[0], Time[1])
    # max_aver, min_aver = TDCRawDataParser_16phase(Time[0], Time[1])
    # print(max_aver, min_aver)
    std_AutosyncRoundTime()