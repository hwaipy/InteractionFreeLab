import os
import msgpack
import numpy as np
import io
import matplotlib.pyplot as plt
from functional import seq
import time


class PowerMonitoredDataBlock:
    def __init__(self, entries):
        self.entries = entries

    @classmethod
    def load(cls, path):
        file = open(path, 'rb')
        bytes = file.read(os.path.getsize(path))
        file.close()
        unpacker = msgpack.Unpacker(raw=False)
        unpacker.feed(bytes)
        unpacked = unpacker.unpack()

        summaries = unpacked['Summaries']
        entries = [PowerMonitoredDataBlockEntry(summary) for summary in summaries]
        memfile = io.BytesIO(unpacked['Contents'])
        contents = np.load(memfile, allow_pickle=True)
        for i in range(len(entries)):
            entries[i].content = contents[i]
        pmdb = PowerMonitoredDataBlock(entries)
        return pmdb

    def showCountPowerRelationship(self):
        count1 = np.array([len(e.content[4]) for e in self.entries])
        count2 = np.array([len(e.content[5]) for e in self.entries])
        power1 = np.array([e.relatedPower1 for e in self.entries])
        power2 = np.array([e.relatedPower2 for e in self.entries])
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(1, 1, 1)
        ax.scatter(power1, count2, s=1)
        ax.scatter(power2, count1, s=1)
        plt.show()

    def calculateChannelDelays(self):
        self.makePulseHistogram(seq(self.entries).map(lambda e: e.content[0]).flatten().to_list(), seq(self.entries).map(lambda e: e.content[4]).flatten().to_list())
        self.makePulseHistogram(seq(self.entries).map(lambda e: e.content[0]).flatten().to_list(), seq(self.entries).map(lambda e: e.content[5]).flatten().to_list())

    def makePulseHistogram(self, triggerList, signalList):
        tList = np.array(triggerList)
        sList = np.array(signalList)
        maxValue = 16000

        idx = np.searchsorted(tList, sList)
        deltas = (sList - tList[idx - 1])
        deltas = deltas % maxValue
        hist = np.histogram(deltas, bins=200, range=(0, maxValue))

        plt.plot(hist[1][:-1], hist[0])
        plt.show()
        return hist[1][:-1], hist[0]

    def makeFullHistogram(self, triggerList, signalList, showRange=(-200000, 200000), binCount=1000, raw=False, show=True):
        tList = np.array(triggerList)
        sList = np.array(signalList)

        idxStart = np.searchsorted(tList, sList + showRange[0])
        idxStop = np.searchsorted(tList, sList + showRange[1])
        outbounding = np.where(idxStop >= tList.shape[0] - 1)[0]
        if len(outbounding) > 0:
            idxStart = idxStart[:-len(outbounding)]
            idxStop = idxStop[:-len(outbounding)]

        deltas = np.array([])
        for i in range(0, np.max(idxStop - idxStart) + 2):
            whereOfSignal = np.where((idxStop - idxStart) >= i)
            whereOfTrigger = idxStart[np.where((idxStop - idxStart) >= i)]
            delta1 = sList[whereOfSignal] - tList[whereOfTrigger + 1]
            delta2 = sList[whereOfSignal] - tList[whereOfTrigger]
            delta = np.hstack((delta1, delta2))
            deltas = np.hstack((deltas, delta))

        hist = np.histogram(deltas, bins=binCount, range=showRange)

        if show:
            plt.plot(hist[1][:-1], hist[0])
            plt.show()
        if raw: return deltas
        return hist[1][:-1], hist[0]

    def calculateFilteredVisibility(self, entries, period=8000, gate=3000, sidePulses=[-100, -90, -80, 80, 90, 100], raw=False):
        if len(entries) == 0: return 0, 0 if raw else 0
        showRange = ((min(sidePulses) - 1) * period, (max(sidePulses) + 1) * period)
        deltas = self.makeFullHistogram(seq(entries).map(lambda e: e.content[8]).flatten().to_list(), seq(self.entries).map(lambda e: e.content[9]).flatten().to_list(), showRange, raw=True, show=False)
        cDip = deltas[np.where((deltas > -gate / 2) & (deltas < gate / 2))].shape[0]
        cSide = [deltas[np.where((deltas > period * sidePulse - gate / 2) & (deltas < period * sidePulse + gate / 2))].shape[0] for sidePulse in sidePulses]
        if raw: return cDip, (sum(cSide) / len(cSide))
        return cDip / (sum(cSide) / len(cSide))

    def HOMScan(self):
        powerRatios = np.array(seq(self.entries).map(lambda e: e.powerRatio).to_list())
        threshold = 0.8
        entries = np.array(self.entries)
        for expectedRatio in np.logspace(-1.5, 1, 30):
            lowerBound = expectedRatio * threshold
            upperBound = expectedRatio / threshold
            relatedEntries = entries[np.where((powerRatios > lowerBound) & (powerRatios < upperBound))]
            hom = self.calculateFilteredVisibility(relatedEntries, raw=True)
            print('{}\t{}\t{}'.format(expectedRatio, hom[0], hom[1]))


class PowerMonitoredDataBlockEntry:
    channelMonitorConfig = [[-1, -0.4, 4.5], [0, -0.4, 4.5]]

    def __init__(self, unpacked):
        self.tdcStart = unpacked['TDCStart']
        self.tdcStop = unpacked['TDCStop']
        self.relatedPowerCount = unpacked['RelatedPowerCount']
        self.relatedPower1 = unpacked['Power1']
        self.relatedPower2 = unpacked['Power2']
        self.powerRatio = self.__getPowerRatio()

    def __getPowerRatio(self):
        p1 = self.relatedPower1 - PowerMonitoredDataBlockEntry.channelMonitorConfig[0][1] if PowerMonitoredDataBlockEntry.channelMonitorConfig[0][0] == 0 else self.relatedPower1 - PowerMonitoredDataBlockEntry.channelMonitorConfig[1][1]
        p2 = self.relatedPower2 - PowerMonitoredDataBlockEntry.channelMonitorConfig[1][1] if PowerMonitoredDataBlockEntry.channelMonitorConfig[1][0] == 1 else self.relatedPower2 - PowerMonitoredDataBlockEntry.channelMonitorConfig[0][1]
        if PowerMonitoredDataBlockEntry.channelMonitorConfig[0][0] < 0: p1 = 1
        if PowerMonitoredDataBlockEntry.channelMonitorConfig[1][0] < 0: p2 = 1
        if p2 <= 0: return 1e200
        if p1 <= 0: return 1e-200
        return p1 / p2


if __name__ == '__main__':
    print('starting')
    pmdb = PowerMonitoredDataBlock.load('E:/MDIQKD_Parse/DataBlock/PowerMonitoredDataBlocks/2020-07-27T22-52-36.095.pmdatablocks') #
    pmdb.showCountPowerRelationship()
    # pmdb.calculateChannelDelays()
    pmdb.HOMScan()
    # deltas = pmdb.makeFullHistogram(seq(pmdb.entries).map(lambda e: e.content[8]).flatten().to_list(), seq(pmdb.entries).map(lambda e: e.content[9]).flatten().to_list(), (-20000, 20000), show=True)
