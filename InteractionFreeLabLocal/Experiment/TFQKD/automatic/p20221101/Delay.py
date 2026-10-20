import sys
# sys.path.append("..")
# from ExpControl import ExpControl
import ExpControl
from interactionfreepy import IFWorker
import matplotlib.pyplot as plt
import numpy as np
import datetime
import time
import threading
from PIL import Image
from urllib.request import urlopen
from pytimetag import DataBlock
import msgpack
import math
import os
import matplotlib as mpl
from worker_config import worker, ip
from AutoSyncExra_wmy import MoMethod
import LongRandomWaveform
from LongRandomWaveform import LongWaveformGenerator
mpl.rcParams['agg.path.chunksize'] = 10000


class getDelay:
    def __init__(self, AliceChannel=4, BobChannel=5, triggerChannel=0, pulsePeriod=10000, ip='interactionfree.cn', dataBlockTime=1E12, triggerlength=25000, targetPositionTime=5E3):
        """
        :param AliceChannel: Alice用于搜索首脉冲的数据通道
        :param BobChannel: Bob用于搜索首脉冲的数据通道
        :param triggerChannel: trigger对应的数据通道
        :param pulsePeriod: 脉冲周期，单位ps
        :param ip: IFworker使用的ip
        :param dataBlockTime: 每个dataBlock的时间，单位ps
        :param triggerlength: 每个dataBlock包含的trigger个数
        :param targetPositionTime: 脉冲的目标位置，单位ps
        """
        # 定义概览数据的存储地点
        self.ip = ip
        self.worker = IFWorker(f'tcp://{ip}:224')
        self.storage = self.worker.Storage
        # self.ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1})
        self.AliceChannel = AliceChannel
        self.BobChannel = BobChannel
        self.triggerChannel = triggerChannel
        self.pulsePeriod = pulsePeriod
        self.dataBlockTime = dataBlockTime
        self.triggerlength = triggerlength
        self.targetPositionTime = targetPositionTime
        self.numofPulse = round(self.dataBlockTime / self.pulsePeriod)
        print('There are', int(self.numofPulse / self.triggerlength), 'pulses in a period of trigger.')
        if not os.path.exists('./Picture'):
            os.mkdir('./Picture')

        # 获取所有在范围内的数据的采集时间
        # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})

    def refReverse(self, rns):
        phase = rns // 4
        state = (rns + 1) % 4
        rns = phase * 4 + state
        return rns

    @classmethod
    def getDataBlock(self, ip, fetchTime):
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

    # 获得通道的计数数据
    def getChanneldata(self, target='Alice', rns=([1]*1+[0]*9)*400, globalDelay=0.0, V=0, colletTime=3, setRNSonly=False):
        # 参数保护
        if target != 'Alice' and target != 'Bob': raise ValueError("target should be 'Alice' or 'Bob'")
        # 定义refrence反向
        if isinstance(rns, list): rns = [self.refReverse(rns=rns[i]) if rns[i] >= 64 and (i % 2 == 1) else rns[i] for i in range(len(rns))]
        # 定义操作
        Controlfunc = eval('LongRandomWaveform.control_' + f'{target}')

        # 控制波形生成
        Controlfunc(rnsForAWG=rns, rnsForTDC=rns, globalDelay=globalDelay, V=V)
        if setRNSonly: return
        time.sleep(5)  # 时间参数优化
        beginTime = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
        time.sleep(colletTime)
        endTime = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
        time.sleep(5)  # 时间参数优化
        ranges = self.storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1})

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
                deltaMetas.append([currentTriggerIndex,  delta])
            return deltaMetas

        deltaMetas = []
        Channel = eval('self.' + target + 'Channel')
        for dataMeta in ranges:
            fetchTime = dataMeta['FetchTime']
            dataBlock = self.getDataBlock(self.ip, fetchTime)
            triggerList = dataBlock['Content'][self.triggerChannel]
            dataList = dataBlock['Content'][Channel]
            # 对齐时钟
            # deltaMetas 每个元素包含四项，分别是[0]对应的trigger序号，[1]相对trigger的时间
            deltaMetas.extend(deltaMeta(triggerList, dataList))

        return deltaMetas

    def searchEdge(self, BinCount=[],threshold=2, nstd=2, pulserange=0.5):
        Edge1Index = np.nan
        Edge2Index = np.nan
        aver = np.mean(BinCount)
        std = np.std(BinCount)
        startIndex = 0
        maxdelta = max([abs(min(BinCount)-aver), abs(max(BinCount)-aver)])
        while abs(BinCount[startIndex] - aver) > nstd * std and abs(BinCount[startIndex] - aver) > pulserange * maxdelta:
            startIndex += 1
        while startIndex < len(BinCount) and (abs(BinCount[startIndex] - aver) <= nstd * std or abs(BinCount[startIndex] - aver) <= pulserange * maxdelta):
            startIndex += 1
        if startIndex < len(BinCount) and max(BinCount) > threshold:
            Edge1Index = startIndex
        else:
            print('aver=', aver)
            print('nstd*std=', nstd * std)
            print('startIndex=', startIndex)
            print('len(BinCount)=', len(BinCount))
            print('max(BinCount)=', max(BinCount))
            print('threshold=', threshold)
            print("There is no pulse", '!'*30)
            # raise ValueError("There is no pulse")

        round0 = 0
        while Edge1Index != np.nan and abs(BinCount[startIndex] - aver) > nstd * std and abs(BinCount[startIndex] - aver) > pulserange * maxdelta and round0 < 2:
            Edge2Index = startIndex
            startIndex += 1
            if startIndex == len(BinCount):
                startIndex = 0
                round0 += 1
        delta = [abs(data - aver) for data in BinCount]
        extremeIndex = delta.index(max(delta))
        # print('Edge1Index, Edge2Index, extremeIndex, round0=', Edge1Index, Edge2Index, extremeIndex, round0)
        if (round0 == 0 and (extremeIndex < Edge1Index or extremeIndex > Edge2Index)) or (round0 == 1 and (extremeIndex < Edge1Index and extremeIndex > Edge2Index)):

            print('round0=', round0)
            print('Edge1Index=', Edge1Index)
            print('Edge2Index', Edge2Index)
            print('extremeIndex', extremeIndex)
            # raise ValueError("There is more than one pulse")
        return Edge1Index, Edge2Index, extremeIndex, round0

    # 对1个trigger周期折叠
    def Divide(self, to_time=None, divide=400, binNum=1000, deltaMetas=[], limit=None):
        if to_time is None: to_time = round(self.dataBlockTime)
        from_time = 0
        divideTime = round((to_time - from_time) / divide)
        binTime = round(divideTime / binNum)

        for time in deltaMetas:
            time.append((time[0] * int(self.dataBlockTime/self.triggerlength) + time[1]) % divideTime // binTime)
        # 计算每个bin内的光子数
        binCount = [0 for i in range(binNum)]
        for each in deltaMetas:binCount[each[-1]] += 1
        binTimeList = [i * binTime for i in range(len(binCount))]

        if limit is not None:
            binCount = binCount[limit[0]:limit[1]]
            binTimeList = binTimeList[limit[0]:limit[1]]

        return binCount, binTime, binTimeList

    # 增加线程 绘制数据图
    def plot(self, Time, binCount, path, para, pltshow=False):
        aver = np.mean(binCount)
        std = np.std(binCount)
        plt.figure(dpi=1000)
        plt.text(x=max(Time) * 1.04,  # 文本x轴坐标
                 y=max(binCount) * 1.04,  # 文本y轴坐标
                 s=f'aver = {aver}\nstd = {std}\nEdge1Index={para[0]}\nEdge2Index={para[1]}\nextremeIndex={para[2]} of {len(binCount)}\nround0={para[3]}',  # 文本内容
                 rotation=1,  # 文字旋转
                 ha='right',  # x=2.2是文字的左端位置，可选'center', 'right', 'left'
                 va='top',  # y=8是文字的低端位置，可选'center', 'top', 'bottom', 'baseline', 'center_baseline'
                 fontdict=dict(fontsize=8, color='black',
                               family='cursive',  # 字体,可选'serif', 'sans-serif', 'cursive', 'fantasy', 'monospace'
                               weight='bold',  # 磅值，可选'light', 'normal', 'medium', 'semibold', 'bold', 'heavy', 'black'
                               )  # 字体属性设置
                 )
        plt.plot(Time, binCount)
        if pltshow:
            plt.show()
            plt.close()
        else:
            plt.savefig(path)
            plt.close()
            thread = threading.Thread(target=self.openPicture, args=(path,))
            thread.start()

    def openPicture(self, *args):
        path = args[0]
        im = Image.open(path)
        im.show()

    def Control2(self, target='Alice', keep_waveform=False):
        # 获取此时的设定波形
        if keep_waveform:rns_before = self.getRnsNow(target)
        print(f'get randomNumber of {target}')
        # 设置MO为MOsync使脉冲稳定
        mosync = MoMethod.latest_MOsync(target)
        MoMethod.setMO(mosync, target)

        divide = 5
        eachDivide = round(self.numofPulse / divide)  # 2E7
        dividepart = 400
        binNum = int(eachDivide / dividepart)  # 50000

        # step1   [64] * 400 + [0] * int(2E7 - 400)
        globalDelay1 = self.per_control(target=target, binNum=binNum, divide=divide, waveform=LongWaveformGenerator.waveformID()['Delay']['step1'], index='extremeIndex', pictureName=f'{target} step1', targetPositionTime=0, colletTime=5)

        # step2   [1] + [0] * (4000 - 1)
        globalDelay2 = self.per_control(target=target, binNum=40000, divide=int(divide * binNum / 10), waveform=LongWaveformGenerator.waveformID()['Delay']['step2'], globalDelay=globalDelay1, index='extremeIndex', pictureName=f'{target} step2', targetPositionTime=self.targetPositionTime, colletTime=5)

        globalDelay = (globalDelay1 + globalDelay2) % int(eachDivide * self.pulsePeriod / 1000)
        print('globalDelay=', globalDelay)

        # 还原之前设定的波形
        if keep_waveform:self.getChanneldata(target=target, rns=rns_before, globalDelay=globalDelay, V=0, setRNSonly=True)

        # 保存globalDelay数据
        self.worker.TF_Registry.set(f'Runtime.{target}.Time.GlobalDelay', globalDelay)

        return globalDelay

    def checkLongWaveform(self, globalDelay):
        divide = 5
        eachDivide = round(self.numofPulse / divide)  # 2E7
        dividepart = 400
        divide2 = int(eachDivide / dividepart)  # 50000

        # step1   [64] * 400 + [0] * int(2E7 - 400)
        deltaMetas = self.getChanneldata(target=target, rns=LongWaveformGenerator.waveformID()['Delay']['step1'], globalDelay=globalDelay % int(eachDivide * self.pulsePeriod / 1000), V=0, colletTime=5)
        binCount, _, binTimeList = self.Divide(divide=divide, binNum=divide2, deltaMetas=deltaMetas)  # , limit=[0, 10]
        # 保存及显示图像
        path = fr'Picture/check{target}1.png'
        self.plot(binTimeList, binCount, path, para=[np.nan, np.nan, np.nan, np.nan])

        # step2   [1] + [0] * (4000 - 1)
        deltaMetas = self.getChanneldata(target=target, rns=LongWaveformGenerator.waveformID()['Delay']['step2'], globalDelay=globalDelay % int(4000 * self.pulsePeriod / 1000), V=0, colletTime=5)
        binCount, _, binTimeList = self.Divide(divide=int(divide * divide2 / 10), binNum=40000, deltaMetas=deltaMetas)  # , limit=[0, 10]

        # 保存及显示图像
        path = fr'Picture/check{target}2.png'
        self.plot(binTimeList, binCount, path, para=[np.nan, np.nan, np.nan, np.nan])

    def per_control(self, target, binNum=None, divide=None, waveform=None, globalDelay=0.0, V=0, index='extremeIndex', pictureName=None, targetPositionTime=0.0, colletTime=3):
        """
        :param target: 'Alice' or 'Bob'
        :param globalDelay: 波形设置的全局延迟
        :param waveform: 设置的波形
        :param binNum: 直方图的bin的数量
        :param divide: 直方图的折叠次数
        :param V: 设置波形的全波电压
        :param index: 将 'extremeIndex' or 'Edge1Index' 设置为搜索脉冲的位置，单位为bin的index
        :param pictureName: 保存直方图图片的名字
        :param targetPositionTime: 搜索脉冲的目标位置，单位ps
        :return: 当前目标脉冲位置所需的globalDelay
        """
        # 缺省值填充
        if index not in ['extremeIndex', 'Edge1Index']: raise ValueError(f'"index" must be "extremeIndex" or "Edge1Index" not {index} !!')
        if binNum is None: binNum = round(self.numofPulse/divide)
        if divide is None: divide = round(self.numofPulse/binNum)
        if waveform is None:
            everybin = round(self.numofPulse/divide/binNum)
            waveform = [1] * everybin + [0] * (binNum - 1) * everybin
        # 设置波形
        deltaMetas = self.getChanneldata(target=target, rns=waveform, globalDelay=globalDelay, V=V, colletTime=colletTime)
        binCount, binTime, binTimeList = self.Divide(divide=divide, binNum=binNum, deltaMetas=deltaMetas)
        Edge1Index, Edge2Index, extremeIndex, round0 = self.searchEdge(BinCount=binCount, threshold=2, nstd=2, pulserange=0.5)
        # 保存及显示图像
        path = fr'./Picture/{pictureName}.png'
        self.plot(binTimeList, binCount, path, para=[Edge1Index, Edge2Index, extremeIndex, round0])
        positionIndex = eval(index)
        indexDelay = self.abs_difference(value=positionIndex, target_value=targetPositionTime / binTime, period=binNum)
        globalDelay = indexDelay * binTime / 1000
        print(f'globalDelay = {globalDelay} ns 误差范围约为正负{binTime/1000} ns')
        return globalDelay

    @classmethod
    def abs_difference(cls, value, target_value, period):
        value = value % period
        target_value = target_value % period
        difference = [target_value - value, target_value + period - value]
        abs_diff = [abs(i) for i in difference]
        min_index = abs_diff.index(min(abs_diff))
        min_difference = difference[min_index]
        return min_difference

    def Control(self, target='Alice', keep_waveform=False):
        # 获取此时的设定波形
        if keep_waveform: rns_before = self.getRnsNow(target)
        print(f'get randomNumber of {target}')
        # 设置MO为MOsync使脉冲稳定
        mosync = MoMethod.latest_MOsync(target)
        MoMethod.setMO(mosync, target)
        print(f'set MOsync of {target}')
        # 折叠次数
        divide = self.triggerlength
        # 波形的globalDelay
        globalDelay = 0
        # 搜索首脉冲获得Delay
        globalDelay = self.per_control(target=target, divide=divide, globalDelay=globalDelay, pictureName=target, colletTime=3)
        # 设置回之前的设定波形
        if keep_waveform: self.getChanneldata(target=target, rns=rns_before, globalDelay=globalDelay, V=0, setRNSonly=True)
        # 将globalDelay上传
        self.worker.TF_Registry.set(f'Runtime.{target}.Time.GlobalDelay', globalDelay)
        return globalDelay

    def savedata(self, target, globalDelay):
        file = open(f'globalDelay_{target}.txt', 'w')  # a为加
        file.write(str(globalDelay))
        file.close()

    def getRnsNow(self, target):
        beginTime = (datetime.datetime.now() - datetime.timedelta(seconds=4)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
        endTime = (datetime.datetime.now() - datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
        ranges = self.worker.Storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1})
        dataMeta = ranges[-1]
        meta = self.worker.Storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        rns = meta['Data']['QKDQBER']['Configuration'][f'{target}RandomNumbers']
        return rns


if __name__ == '__main__':

    Delay = getDelay(AliceChannel=4, BobChannel=5, triggerChannel=0, ip=ip)
    # target = sys.argv[1]
    target = 'Bob'
    # target = 'Alice'
    # globalDelay = Delay.Control(target=target, keep_waveform=True)
    st = time.time()
    globalDelay = Delay.Control2(target=target)
    et = time.time()
    print('用时：', et-st)

    # 检查
    # globalDelay = worker.TF_Registry.get(f'Runtime.{target}.Time.GlobalDelay')
    # print(f'globalDelay_{target}=', globalDelay)
    # Delay.checkLongWaveform(globalDelay)


