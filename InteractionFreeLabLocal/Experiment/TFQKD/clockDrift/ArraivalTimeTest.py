import time
from pytimetag import DataBlock
import numpy as np
from SyncAnalyser import SyncAnalyser
import tick
from DopplerUtil import DopplerUtil
import os
from interactionfreepy import IFWorker
import msgpack
from scipy.optimize import curve_fit

def generateRandomNumbers(refCount, gapCount, signalCount, repeat, px, py, pz, seed=None):
    import random
    assert px + py + pz < 1
    rand = random.Random(seed)
    rns = []
    for i in range(repeat):
        cnt = 0
        for iRef in range(refCount):
            # rns.append(0b01000000)
            rns.append(0b01000000 + (rand.randint(0, 15) << 2))
        for iGap in range(gapCount):
            # rns.append(0b10000000)
            rns.append(0b10000000 + (rand.randint(0, 15) << 2))
        for iSignal in range(signalCount):
            # r = 0b00000000
            r = 0b00000000 + (rand.randint(0, 15) << 2)
            decoy = rand.random()
            if decoy < pz: r += 0b11
            elif decoy < pz + py: r += 0b10
            elif decoy < pz + py + px: r += 0b01
            else: 
                cnt += 1
                r += 0b00
            rns.append(r)
    return rns

class TFQKDDataParser:
    def __init__(self, storage, dataBlockFetcher):
        self.storage = storage
        self.dataBlockFetcher = dataBlockFetcher
        self.analyser = SyncAnalyser(16, 256)
        self.analyser.turnOn()
        self.dopplerUtil = DopplerUtil()

    def parse(self, beginTime, endTime):
        metas = self.__fetchMetas(beginTime, endTime)
        tick.turnOff()

        for meta in metas:
            tick.tick('begin a DataBlock')
            fetchTime = meta['FetchTime']
            configs = meta['Data']['TFQKDSyncAlice']['Configuration']
            self.__fixConfig(configs, meta['Data'])
            dataBlock = self.dataBlockFetcher(fetchTime)
            dataBlock = self.dopplerUtil.rescale(dataBlock)
            tick.tick('DataBlock fetched')
            result = self.__parse(dataBlock, configs)
            tick.tick('end a DataBlock')
            # print(result)
            delay = calcDelay(result)
            with open('output.csv', 'w+') as f:
                f.write(f'{fetchTime}\t{delay}\n')
            print(f'DONE: {fetchTime}')

        if False:
            print('Benchmarking individual DataBlock parsing...')
            meta = metas[-1]
            tick.turnOn()
            tick.tick('begin a DataBlock')
            fetchTime = meta['FetchTime']
            configs = meta['Data']['TFQKDSyncAlice']['Configuration']
            self.__fixConfig(configs, meta['Data'])
            dataBlock = self.dataBlockFetcher(fetchTime)
            dataBlock = self.dopplerUtil.rescale(dataBlock)
            tick.tick('DataBlock fetched')
            t1 = time.time()
            result = self.__parse(dataBlock, configs)
            t2 = time.time()
            tick.tick('end a DataBlock')
            print(f'Elapsed time for single DataBlock parsing: {t2 - t1:.3} seconds')

    def __fetchMetas(self, beginTime, endTime):
        if not isinstance(beginTime, list): beginTime = [beginTime]
        if not isinstance(endTime, list): endTime = [endTime]
        assert len(beginTime) == len(endTime)
        metas = []
        for i in range(len(beginTime)):
            ranges = self.storage.range('TFQKD_TDC', beginTime[i], endTime[i], filter={'_id': 1}, limit=1000000)
            for dataMeta in ranges:
                metas.append(self.storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1}))
        return metas
    
    def __fixConfig(self, configs, data):
        ############## ⬇️ DEBUG For LCL ONLY  ##############
        configs.clear()
        configs['RandomNumbers'] = generateRandomNumbers(refCount=140, gapCount=5, signalCount=255, repeat=10, px=0.063, py=0.209, pz=0.053, seed=24)
        configs['Period'] = 10000
        configs['PulsePosition'] = 5000
        configs['TriggerChannel'] = 0
        configs['SignalChannel'] = 4
        configs['BinCount'] = 625
        configs['Histograms'] = {'Sync Alice': [i for i in range(128)]}
        ############## ⬆️ DEBUG For LCL ONLY  ##############

    def __parse(self, dataBlock, configs):
        self.analyser.configure(configs)
        return self.analyser.dataIncome(dataBlock)

def calcDelay(result):
    def func(x, A, x0, sigma, C):
      return A * np.exp(-((x - x0) ** 2) / (2 * sigma ** 2)) + C

    period = result['Configuration']['Period']
    pulsePosition = result['Configuration']['PulsePosition']
    histogramInPulse = np.array(result['Histogram[Sync Alice]'])
    times = np.linspace(0, period, histogramInPulse.shape[0], endpoint=False)
    maxI = np.argmax(histogramInPulse)
    validPulseIndices = np.where(histogramInPulse >= histogramInPulse[maxI] * 0.3)[0]
    times = times[validPulseIndices]
    histogramInPulse = histogramInPulse[validPulseIndices]

    p0 = [np.max(histogramInPulse), times[np.argmax(histogramInPulse)], (times[-1] - times[0]) * 0.2, 0]
    # popt, _ = curve_fit(func, times, histogramInPulse, p0=p0)

    print(result['Delay'])

    # import matplotlib.pyplot as plt
    # plt.scatter(times, histogramInPulse)
    # plt.plot(times, func(times, *p0), color='red')
    # # plt.plot(times, func(times, *popt), color='green')
    # plt.savefig('histogram_in_pulse.png', dpi=300)
    # plt.close()

    # delay = popt[1] - pulsePosition + result['PulseDelta'] * period
    # print(delay)
    return result['Delay']

if __name__ == '__main__':
    # 到达时间评估
    begintime = ['2025-11-08T22:37:00+08:00']
    endtime = ['2025-11-08T23:37:00+08:00']

    worker = IFWorker('tcp://172.20.9.23:51061')
    def fetchDataBlock(fetchTime):
        print('fetching DataBlock', fetchTime)
        tick.tick('fetching DataBlock')
        date = fetchTime[:10]
        hour = fetchTime[11:13]
        dateTime = fetchTime.replace(':', '-').replace('T', ' ')[:23]
        path = '/'.join([date, hour, dateTime + '.datablock'])
        data = worker.TF_FileStorage.readFile("TFQKD_RAW", path)
        tick.tick(f'readed from server. {len(data)} bytes')
        dataBlock = DataBlock.deserialize(data)
        tick.tick('deserialized')
        return dataBlock
    parser = TFQKDDataParser(storage=worker.Storage, dataBlockFetcher=fetchDataBlock)
    parser.parse(begintime[0], endtime[0])

