from interactionfreepy import IFWorker, IFLoop
from datetime import datetime, timedelta, timezone
import numpy as np
from tornado.ioloop import IOLoop
from threading import Thread 
import time
import pytz

class PID:
    def __init__(self, P=2.0, I=0.0, D=1.0, Derivator=0, Integrator=0, Integrator_max=500, Integrator_min=-500):
        self.Kp = P
        self.Ki = I
        self.Kd = D
        self.Derivator = Derivator
        self.Integrator = Integrator
        self.Integrator_max = Integrator_max
        self.Integrator_min = Integrator_min
        self.set_point = 0.0
        self.error = 0.0

    def update(self, current_value):
        self.error = self.set_point - current_value

        self.P_value = self.Kp * self.error
        self.D_value = self.Kd * (self.error - self.Derivator)
        self.Derivator = self.error

        self.Integrator = self.Integrator + self.error

        if self.Integrator > self.Integrator_max:
            self.Integrator = self.Integrator_max
        elif self.Integrator < self.Integrator_min:
            self.Integrator = self.Integrator_min

        self.I_value = self.Integrator * self.Ki

        PID = self.P_value + self.I_value + self.D_value

        return PID

    def setPoint(self, set_point):
        self.set_point = set_point
        self.Integrator = 0
        self.Derivator = 0


def estimateCenterTime(dataSet, key):
    if len(dataSet) == 0: return np.nan
    config = dataSet[0]['Configuration'] 
    period = config['Period']
    binCount = config['BinCount']
    xs = np.linspace(0, period, binCount + 1)[:-1] 
    xs += (xs[1] - xs[0]) / 2

    histograms = np.array([d['Histogram[{}]'.format(key)] for d in dataSet])
    histogram = np.sum(histograms, axis=0)

    if np.max(histogram) / np.min(histogram) < 10 or (np.sum(histogram) / len(dataSet)) < 500:
        return np.nan

    return fitCenterTime(xs, histogram)

def fitCenterTime(xs, ys):
    maxValue = np.max(ys)
    maxIndex = np.where(ys == maxValue)[0][0]
    inPulseIndices = np.where(ys > maxValue * 0.2)[0]

    maxIndexInPulse = np.where(inPulseIndices == maxIndex)[0][0]

    inPulseIndices = inPulseIndices[np.where(inPulseIndices == [i + maxIndex - maxIndexInPulse for i in range(len(inPulseIndices))])]
    return sum([xs[i] * ys[i] for i in inPulseIndices]) / sum(ys[inPulseIndices])



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
    print('start')
    worker = IFWorker('192.168.25.5:224')
    
    def fetchLatest(limit):
        collection = 'TFQKD_TDC'
        data = worker.Storage.latest(collection, by='FetchTime', after=(datetime.now(tz=pytz.timezone('Asia/Shanghai')) - timedelta(seconds=limit)).isoformat(), filter={'_id': 1}, length=limit + 5)
        return [worker.Storage.get(collection, d['_id'], key='_id', filter={'Data.TFQKDSyncAlice': 1, 'Data.TFQKDSyncBob': 1}) for d in data]

    # worker.TF_AtomicClock_Alice.setMO(3030)

    pid = PID(P=0.01, I=0e-12, D=0.04)
    pid.setPoint(5e-9)

    mo = int(worker.TF_AtomicClock_Alice.getMO())

    while True:
    #     data = fetchLatest(7)
    #     dT = estimateCenterTime([d['Data']['TFQKDSyncAlice'] for d in data], 'Sync Alice') / 1e12
    #     # dF = 0

        t1 = time.time()
        data = worker.TFTDCAdapter.getRecent(20)
        results = [SyncData(r) for r in data]
        t2 = time.time()
        # print(f'获取到最近的 {len(results)} 条数据，耗时 {(t2 - t1) * 1000:.1f} ms。最近一条数据是 {(t2 - results[-1].fetchTime) * 1000:.1f} ms 前采集到的')

        # 示例：计算 Alice 最近 0.3 s 的时间差
        dT = SyncData.estimateCenterTime(results[-3:], 'Alice') / 1e12
        dF = pid.update(dT)
        dMO = dF / 4e-12
        
        mo -= dMO
        worker.TF_AtomicClock_Alice.setMO(int(mo + 0.5))

        print(dT, dMO, mo)

        time.sleep(10)