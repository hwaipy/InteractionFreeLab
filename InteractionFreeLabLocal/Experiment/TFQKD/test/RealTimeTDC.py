from interactionfreepy import IFWorker, IFLoop
from datetime import datetime, timedelta, timezone
import numpy as np
from tornado.ioloop import IOLoop
from threading import Thread 
import time

# 配置AWG波形的代码中，在类似于
# tdc.configureAnalyser('TFQKDSyncAlice', {'RandomNumbers': rnsAliceForAWG, 'SignalChannel': 4})
# tdc.configureAnalyser('TFQKDSyncBob', {'RandomNumbers': rnsAliceForAWG, 'SignalChannel': 4})
# 这样的地方，分别添加下面的代码：
# worker.TFTDCAdapter.configureAnalyser('TFQKDSyncAlice', {'RandomNumbers': rnsAliceForAWG, 'SignalChannel': 4})
# 或
# worker.TFTDCAdapter.configureAnalyser('TFQKDSyncAlice', {'RandomNumbers': rnsAliceForAWG, 'SignalChannel': 4})
# 这是为了让新的实时处理程序和老的TDC处理程序目前是独立运行的状态，需要分别配置随机数和通道。


class SyncData:
    def __init__(self, data):
        self.fetchTime = data['FetchTime'] / 1000.0
        self.histograms = {
            'Alice': data['TFQKDSyncAlice']['Histogram[Sync Alice]'], # 同AutoSync中的直方图数据
            'Bob': data['TFQKDSyncBob']['Histogram[Sync Bob]'] # 同AutoSync中的直方图数据
        }

    @classmethod
    def estimateCenterTime(self, dataSet, key, period=10000, binCount=100):
        if len(dataSet) == 0: return np.nan
        xs = np.linspace(0, period, binCount + 1)[:-1] 
        xs += (xs[1] - xs[0]) / 2

        histogram = np.sum(np.array([d.histograms[key] for d in dataSet]), axis=0)

        if (np.min(histogram) > 0 and np.max(histogram) / np.min(histogram) < 10) or (np.sum(histogram) / len(dataSet)) < 500:
            return np.nan

        maxValue = np.max(histogram)
        maxIndex = np.where(histogram == maxValue)[0][0]
        inPulseIndices = np.where(histogram > maxValue * 0.2)[0]

        maxIndexInPulse = np.where(inPulseIndices == maxIndex)[0][0]

        inPulseIndices = inPulseIndices[np.where(inPulseIndices == [i + maxIndex - maxIndexInPulse for i in range(len(inPulseIndices))])]
        return sum([xs[i] * histogram[i] for i in inPulseIndices]) / sum(histogram[inPulseIndices])


if __name__ == '__main__':
    worker = IFWorker('tcp://192.168.25.5:224')
    
    # 同样由于新的实时处理程序和老的TDC处理程序目前是独立运行的状态，需要把通道延时信息复制过来。
    delays = worker.TFTDCServer.getDelays()
    for i in range(len(delays)):
        worker.TFTDCAdapter.setDelay(i, delays[i])

    # 示例：获取最近10s的同步通道直方图数据。新的实时处理程序以0.1s为单位，因此需要去获取最近的100条数据
    t1 = time.time()
    data = worker.TFTDCAdapter.getRecent(100)
    results = [SyncData(r) for r in data]
    t2 = time.time()
    print(f'获取到最近的 {len(results)} 条数据，耗时 {(t2 - t1) * 1000:.1f} ms。最近一条数据是 {(t2 - results[-1].fetchTime) * 1000:.1f} ms 前采集到的')

    # 示例：计算 Alice 最近 0.3 s 的时间差
    diff = SyncData.estimateCenterTime(results[-3:], 'Alice')
    print(diff)