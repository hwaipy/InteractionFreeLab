from interactionfreepy import IFWorker
from datetime import datetime, timedelta
import time
import msgpack
import numpy as np
import matplotlib.pyplot as plt
import base64
from io import BytesIO


class TDCandADCSyncer:
    def __init__(self, endpoint, collectionTDC, collectionADC, collectionPair):
        self.worker = IFWorker(endpoint)
        self.collectionTDC = collectionTDC
        self.collectionADC = collectionADC
        self.collectionPair = collectionPair

    def shot(self):
        lastPair = self.worker.Storage.latest(self.collectionPair, by='FetchTime', filter={'Data': 1}, length=1)
        after = None if lastPair == None else self.__aLittleBitPrevious(lastPair['Data']['TDCEntryMetas'][-1]['FetchTime'])
        while True:
            success, TDCEntries = self.findNextTDCSyncPair(after=after)
            if success:
                TDCEntryMetas = [{'FetchTime': entry['FetchTime'], 'DataBlockBegin': entry['Data']['ChannelMonitor']['DataBlockBegin'], 'DataBlockEnd': entry['Data']['ChannelMonitor']['DataBlockEnd'], 'Sync': entry['Data']['ChannelMonitor']['Sync']} for entry in TDCEntries]
                if self.__isNeighborSyncs(TDCEntryMetas[0]['FetchTime'], TDCEntryMetas[-1]['FetchTime']):
                    print('Find one: {} -> {}'.format(TDCEntryMetas[0]['FetchTime'], TDCEntryMetas[-1]['FetchTime']))
                    success, ADCEntries = self.findADCSyncPair(TDCEntryMetas[0]['FetchTime'], TDCEntryMetas[-1]['FetchTime'])
                    result = {'TDCEntryMetas': TDCEntryMetas}
                    if success:
                        detailedTDCData = self.fetchDetailedTDCData(entry['_id'] for entry in TDCEntries)  # ['DataBegin', 'DataEnd', 'SyncBegin', 'SyncEnd', 'ChannelMonitor1', 'ChannelMonitor2']
                        detailedADCData = self.fetchDetailedADCData([entry['_id'] for entry in ADCEntries])  # ['SyncBegin', 'SyncEnd', 'ChannelMonitor1', 'ChannelMonitor2']
                        syncedTDCandADC = self.syncTDCandADC(detailedTDCData, detailedADCData)
                        result['SyncedTDCandADC'] = {
                            'SyncedChannelMonitor1': msgpack.packb(syncedTDCandADC['ADCChannelMonitor1']),
                            'SyncedChannelMonitor2': msgpack.packb(syncedTDCandADC['ADCChannelMonitor2']),
                            'RelationshipFigure': syncedTDCandADC['RelationshipFigure']
                        }
                    # else:
                    #     print('NO corresponding ADC entry')
                    #     raise RuntimeError('afawe')
                    self.worker.Storage.append(self.collectionPair, result, fetchTime=TDCEntries[0]['FetchTime'])
                    return
                else:
                    after = self.__aLittleBitPrevious(TDCEntryMetas[-1]['FetchTime'])
                    continue
            else:
                if TDCEntries == None:
                    time.sleep(2)
                    print('.')
                else:
                    after = self.__aLittleBitPrevious(TDCEntries['FetchTime'])
                continue

    def findNextTDCSyncPair(self, after=None, number=20):
        matchedTDCEntries = self.worker.Storage.first(self.collectionTDC, by='FetchTime', after=after, filter={'_id': 1, 'FetchTime': 1, 'Data.ChannelMonitor.DataBlockBegin': 1, 'Data.ChannelMonitor.DataBlockEnd': 1, 'Data.ChannelMonitor.Sync': 1}, length=20)
        if not isinstance(matchedTDCEntries, list): matchedTDCEntries = [matchedTDCEntries]
        syncTDCEntries = [entry for entry in matchedTDCEntries if len(entry['Data']['ChannelMonitor']['Sync']) > 0]
        if len(syncTDCEntries) >= 2:
            return True, matchedTDCEntries[matchedTDCEntries.index(syncTDCEntries[0]):matchedTDCEntries.index(syncTDCEntries[1]) + 1]
        elif len(matchedTDCEntries) < number:
            return False, None
        elif len(syncTDCEntries) == 0:
            return False, matchedTDCEntries[-1]
        else:
            return False, matchedTDCEntries[-1] if matchedTDCEntries.index(syncTDCEntries[0]) == 0 else syncTDCEntries[0]

    def findADCSyncPair(self, begin, end):
        begin = str(datetime.fromisoformat(begin) - timedelta(seconds=3))
        end = str(datetime.fromisoformat(end) + timedelta(seconds=3))
        matchedADCEntries = self.worker.Storage.range(self.collectionADC, begin, end, by='FetchTime', filter={'_id': 1, 'FetchTime': 1, 'Data.Triggers': 1})
        syncADCEntries = [entry for entry in matchedADCEntries if len(entry['Data']['Triggers']) > 0]
        if len(syncADCEntries) == 2:
            return True, matchedADCEntries[matchedADCEntries.index(syncADCEntries[0]):matchedADCEntries.index(syncADCEntries[1]) + 1]
        else:
            return False, None

    def syncTDCandADC(self, detailedTDCData, detailedADCData):
        adcMonitor1 = [[] for i in range(len(detailedTDCData['ChannelMonitor1']))]
        adcMonitor2 = [[] for i in range(len(detailedTDCData['ChannelMonitor2']))]
        syncADCBegin = detailedADCData['SyncBegin']
        syncADCEnd = detailedADCData['SyncEnd']
        syncTDCBegin = detailedTDCData['SyncBegin']
        syncTDCEnd = detailedTDCData['SyncEnd']
        dataTDCBegin = detailedTDCData['DataBegin']
        dataTDCEnd = detailedTDCData['DataEnd']
        timeUnitTDC = (dataTDCEnd - dataTDCBegin) / len(detailedTDCData['ChannelMonitor1'])
        eta = (syncTDCEnd - syncTDCBegin) / (syncADCEnd - syncADCBegin)

        def fillADCMonitor(cmkey, adcMonitor):
            for iADC in range(len(detailedADCData[cmkey])):
                tTDC = (iADC - syncADCBegin) * eta + syncTDCBegin
                iTDC = (tTDC - dataTDCBegin) / timeUnitTDC
                iTDC = -1 if iTDC < 0 else int(iTDC)
                if (iTDC >= 0 and iTDC < len(detailedTDCData[cmkey])):
                    adcMonitor[iTDC].append(detailedADCData[cmkey][iADC])
            for iMonitor in range(len(adcMonitor)):
                mList = adcMonitor[iMonitor]
                adcMonitor[iMonitor] = sum(mList) / len(mList) if len(mList) > 0 else -10000

        fillADCMonitor('ChannelMonitor1', adcMonitor1)
        fillADCMonitor('ChannelMonitor2', adcMonitor2)

        iSyncTDC = [int((syncTDCBegin - dataTDCBegin) / timeUnitTDC) + 1, int((syncTDCEnd - dataTDCBegin) / timeUnitTDC) - 1]
        fig = plt.figure(figsize=(3.2, 2.5))
        ax = fig.add_subplot(1, 1, 1)
        ax.scatter(detailedTDCData['ChannelMonitor1'][iSyncTDC[0]:iSyncTDC[1]], adcMonitor1[iSyncTDC[0]:iSyncTDC[1]], s=1)
        ax.scatter(detailedTDCData['ChannelMonitor2'][iSyncTDC[0]:iSyncTDC[1]], adcMonitor2[iSyncTDC[0]:iSyncTDC[1]], s=1)
        figfile = BytesIO()
        plt.savefig(figfile, format='png')
        plt.close(fig)
        binaries = figfile.getvalue()
        encodedFig = base64.b64encode(binaries).decode('utf-8')

        return {
            'TDCChannelMonitor1': detailedTDCData['ChannelMonitor1'],
            'TDCChannelMonitor2': detailedTDCData['ChannelMonitor2'],
            'ADCChannelMonitor1': adcMonitor1,
            'ADCChannelMonitor2': adcMonitor2,
            'RelationshipFigure': encodedFig,
        }

    def fetchDetailedADCData(self, ids):
        entries = [self.worker.Storage.get(self.collectionADC, id, filter={'_id': 1, 'Data': 1, 'FetchTime': 1}) for id in ids]
        data = [[], []]
        for entry in entries:
            for channelNum in [1, 2]:
                entry['Data']['Channel{}'.format(channelNum)] = msgpack.unpackb(entry['Data']['Channel{}'.format(channelNum)])
                data[channelNum - 1] += entry['Data']['Channel{}'.format(channelNum)]
        return {
            'SyncBegin': entries[0]['Data']['Triggers'][0],
            'SyncEnd': sum([len(entry['Data']['Channel1']) for entry in entries[:-1]]) + entries[-1]['Data']['Triggers'][0],
            'ChannelMonitor1': data[0],
            'ChannelMonitor2': data[1],
        }

    def fetchDetailedTDCData(self, ids):
        entries = [self.worker.Storage.get(self.collectionTDC, id, filter={'_id': 1, 'Data.ChannelMonitor': 1, 'FetchTime': 1}) for id in ids]
        channels = entries[0]['Data']['ChannelMonitor']['Configuration']['Channels']
        channelMonitors = []
        for channel in channels:
            channelMonitorRaw = [entry['Data']['ChannelMonitor']['CountSections'][str(channel)] for entry in entries]
            channelMonitor = []
            for raw in channelMonitorRaw:
                channelMonitor += raw
            channelMonitors.append(channelMonitor)
        return {
            'DataBegin': entries[0]['Data']['ChannelMonitor']['DataBlockBegin'],
            'DataEnd': entries[-1]['Data']['ChannelMonitor']['DataBlockEnd'],
            'SyncBegin': entries[0]['Data']['ChannelMonitor']['Sync'][0],
            'SyncEnd': entries[-1]['Data']['ChannelMonitor']['Sync'][0],
            'ChannelMonitor1': channelMonitors[0],
            'ChannelMonitor2': channelMonitors[1],
        }

    def syncADCChannel(self, binNum, data, syncStart, syncStop):
        samples = []
        for d in data:
            samples += d
        splitPoints = np.linspace(syncStart, syncStop, binNum + 1)
        splitPoints = np.vstack((splitPoints[:-1], splitPoints[1:])).astype(int).transpose()
        averages = [np.average(samples[splitPoint[0]:splitPoint[1]]) for splitPoint in splitPoints]
        return averages

    def __aLittleBitPrevious(self, time):
        time = datetime.fromisoformat(time)
        time = time - timedelta(milliseconds=1)
        return str(time)

    def __isNeighborSyncs(self, time1, time2):
        time1 = datetime.fromisoformat(time1)
        time2 = datetime.fromisoformat(time2)
        deltaTime = time2 - time1
        deltaSeconds = deltaTime.total_seconds()
        return deltaSeconds < 12 and deltaSeconds > 8


if __name__ == '__main__':
    print('Start SyncTDCandADC')
    syncer = TDCandADCSyncer('tcp://172.16.60.200:224', 'TFQKD_TDC', 'TFQKD_ChannelMonitor', 'TFQKD_TDCandADCSync')
    while True:
        syncer.shot()
        # break
