from interactionfreepy import IFWorker
from functional import seq
import numpy as np
from datetime import datetime, timedelta
import time
from threading import Thread
import pytz
from queue import Queue
import msgpack
import os
import io


class Reviewer:
    def __init__(self, worker, collectionTDC, collectionMonitor, collectionResult, startTime, stopTime=None):
        self.worker = worker
        self.collectionTDC = collectionTDC
        self.collectionMonitor = collectionMonitor
        self.collectionResult = collectionResult
        self.startTime = startTime
        self.stopTime = stopTime

    def review(self):
        qberSections = seq(self.worker.Storage.range(self.collectionTDC, self.startTime, self.stopTime, by='FetchTime', filter={'FetchTime': 1, 'Data.MDIQKDQBER.ChannelMonitorSync': 1})).map(lambda m: QBERSection(m))
        qbersList = QBERs.create(qberSections)
        channelSections = seq(self.worker.Storage.range(self.collectionMonitor, self.startTime, self.stopTime, by='FetchTime', filter={'Data.Triggers': 1, 'Data.TimeFirstSample': 1, 'Data.TimeLastSample': 1})).map(lambda m: ChannelSection(m))
        channelsList = Channels.create(channelSections)

        dataPairs = qbersList.map(lambda qber: [qber, channelsList.filter(lambda channel: np.abs(qber.systemTime - channel.channelMonitorSyncs[0]) < 3)]).filter(lambda z: z[1].size() > 0).map(lambda z: [z[0], z[1][0]]).list()
        for dataPair in dataPairs:
            dpp = DataPairParser(dataPair[0], dataPair[1],
                                 lambda id, filter: self.worker.Storage.get(self.collectionTDC, id, '_id', filter),
                                 lambda id, filter: self.worker.Storage.get(self.collectionMonitor, id, '_id', filter),
                                 lambda result, fetchTime: self.worker.Storage.append(self.collectionResult, result, fetchTime),
                                 [[0, -0.4, 4.5], [-1, -0.4, 4.5]])
            dpp.parse()
            dpp.release()

    def deleteExists(self):
        data = self.worker.Storage.range(self.collectionResult, self.startTime, self.stopTime, by='FetchTime', filter={'FetchTime': 1})
        for d in data:
            id = d['_id']
            self.worker.Storage.delete(self.collectionResult, id, '_id')


class RealtimeReviewer:
    def __init__(self, worker, collectionTDC, collectionMonitor, collectionResult, startTime, channelMonitorConfig):
        self.worker = worker
        self.collectionTDC = collectionTDC
        self.collectionMonitor = collectionMonitor
        self.collectionResult = collectionResult
        self.startTime = datetime.fromisoformat(startTime)
        self.tz = pytz.timezone('Asia/Shanghai')
        self.tdcSummeryQueue = Queue()
        self.channelMonitorConfig = channelMonitorConfig

    def start(self):
        Thread(target=self.__startUpdateSummaryLoop).start()
        Thread(target=self.__startCalculateLoop).start()

    def __startUpdateSummaryLoop(self):
        latestResult = self.worker.Storage.latest(self.collectionResult, by='FetchTime', filter={'FetchTime': 1})
        if latestResult == None:
            rangeStart = self.startTime
        else:
            latestFetchTime = datetime.fromisoformat(latestResult['FetchTime']) + timedelta(milliseconds=1)
            rangeStart = max(self.startTime, latestFetchTime)
        rangeStop = rangeStart + timedelta(minutes=10)
        while True:
            try:
                data = self.worker.Storage.range(self.collectionTDC, rangeStart.isoformat(), rangeStop.isoformat(), by='FetchTime', filter={'FetchTime': 1, 'Data.MDIQKDQBER.ChannelMonitorSync': 1})
                debug_info(1, 'fetched {}'.format(len(data)))
                seq(data).map(lambda d: self.tdcSummeryQueue.put(d)).to_list()
                if len(data) == 0:
                    rangeStop = rangeStop + timedelta(minutes=10)
                else:
                    rangeStart = datetime.fromisoformat(data[-1]['FetchTime']) + timedelta(milliseconds=1)
                    rangeStop = rangeStart + timedelta(minutes=10)
                if rangeStop > datetime.now().astimezone(self.tz):
                    time.sleep(3)
                debug_info(1, 'Loop done. {} ~ {}'.format(rangeStart, rangeStop))
            except BaseException as e:
                print(e)
                time.sleep(3)

    def __startCalculateLoop(self):
        qberSections = []
        while True:
            try:
                # 1. take all items from self.tdcSummeryQueue to qberSections
                while self.tdcSummeryQueue.qsize() > 0:
                    try:
                        qberSections.append(QBERSection(self.tdcSummeryQueue.get()))
                    except BaseException as e:
                        print(e)
                        pass

                # 2. find the first two sections that has slowSync
                syncedEntryIndices = seq(qberSections).zip_with_index().filter(lambda z: z[0].slowSync).map(lambda z: z[1])
                debug_info(2, 'SumQueue orgnized. {}'.format(syncedEntryIndices.size()))
                if syncedEntryIndices.size() >= 2:
                    # 3. take data between two slowSyncs, remove them from qberSections
                    qbers = QBERs(qberSections[syncedEntryIndices[0]:syncedEntryIndices[1] + 1])
                    qberSections = qberSections[syncedEntryIndices[1]:]
                    debug_info(2, 'before DCC')
                    self.__dealCalculate(qbers)
                    debug_info(2, 'don e DCC')
                else:
                    time.sleep(1)
            except BaseException as e:
                print(e)
                time.sleep(3)

    def __dealCalculate(self, qbers):
        print('deal QBERs with FetchTime of {}'.format(datetime.fromtimestamp(qbers.sections[0].pcTime)))
        rangeStart = datetime.fromtimestamp(qbers.sections[0].pcTime).astimezone(self.tz) - timedelta(seconds=3)
        rangeStop = datetime.fromtimestamp(qbers.sections[-1].pcTime).astimezone(self.tz) + timedelta(seconds=3)
        while True:
            latest = self.worker.Storage.latest(self.collectionMonitor, by='FetchTime', after=rangeStop.isoformat(), filter={'Data.Triggers': 1})
            if latest:
                break
        channelSections = seq(self.worker.Storage.range(self.collectionMonitor, rangeStart.isoformat(), rangeStop.isoformat(), by='FetchTime', filter={'Data.Triggers': 1, 'Data.TimeFirstSample': 1, 'Data.TimeLastSample': 1})).map(lambda m: ChannelSection(m))
        channelsList = Channels.create(channelSections)
        if channelsList.size() > 0:
            channels = channelsList[0]
            matched = np.abs(qbers.systemTime - channels.channelMonitorSyncs[0]) < 3
            if matched:
                t1 = time.time()
                dpp = DataPairParser(qbers, channels,
                                     lambda id, filter: self.worker.Storage.get(self.collectionTDC, id, '_id', filter),
                                     lambda id, filter: self.worker.Storage.get(self.collectionMonitor, id, '_id', filter),
                                     lambda result, fetchTime: self.worker.Storage.append(self.collectionResult, result, fetchTime),
                                     self.channelMonitorConfig)
                t2 = time.time()
                print("$"*20,t2-t1)
                dpp.parse()
            else:
                print('Not Matched')
            print('Data parsed: {}'.format(datetime.fromtimestamp(qbers.systemTime)))
        else:
            print('channelsList has no content. channelSections has {} items.'.format(channelSections.len()))


class HOMandQBEREntry:
    def __init__(self, ratioLow, ratioHigh):
        self.ratioLow = ratioLow
        self.ratioHigh = ratioHigh
        self.homCounts = np.zeros((6))
        self.qberCounts = np.zeros((32))
        self.validSectionCount = 0

    def append(self, qberEntry):
        self.homCounts += qberEntry.HOMs
        self.qberCounts += qberEntry.QBERs
        self.validSectionCount += 1

    def toData(self):
        return [self.ratioLow, self.ratioHigh, self.validSectionCount] + [i for i in self.homCounts] + [i for i in self.qberCounts]


class DataPairParser:
    def __init__(self, qbers, channels, getterTDC, getterMonitor, resultUploader, channelMonitorConfig):
        self.qbers = qbers
        self.channels = channels
        self.resultUploader = resultUploader
        self.channelMonitorConfig = channelMonitorConfig
        self.qbers.load(getterTDC)
        self.channels.load(getterMonitor)
        self.__performTimeMatch()
        self.__performEntryMatch()
        self.timeMatchedQBEREntries = self.qbers.entries.filter(lambda e: e.relatedPowerCount > 0)

    def parse(self):
        result = {}
        result['CountChannelRelations'] = self.__countChannelRelations()
        result['HOMandQBERs'] = self.HOMandQBERs(1.02, 200)
        self.resultUploader(result, self.qbers.sections[0].meta['FetchTime'])

    def __performTimeMatch(self):
        qberSyncPair = self.qbers.channelMonitorSyncs
        timeUnit = (qberSyncPair[1] - qberSyncPair[0]) / (self.channels.riseIndices[1] - self.channels.riseIndices[0])
        firstRiseIndex = self.channels.riseIndices[0]
        seq(range(self.channels.riseIndices[0], self.channels.riseIndices[1])).for_each(lambda i: self.channels.entries[i].setTDCTime((i - firstRiseIndex) * timeUnit + qberSyncPair[0]))

    def __performEntryMatch(self):
        channelSearchIndexStart = 0
        channelEntrySize = self.channels.entries.size()
        for entry in self.qbers.entries.list():
            channelSearchIndex = channelSearchIndexStart
            while channelSearchIndex < channelEntrySize:
                channelEntry = self.channels.entries[channelSearchIndex]
                if channelEntry.tdcTime < entry.tdcStart:
                    channelSearchIndex += 1
                    channelSearchIndexStart += 1
                elif channelEntry.tdcTime < entry.tdcStop:
                    entry.appendRelatedChannelEntry(channelEntry)
                    channelSearchIndex += 1
                else:
                    break

    def __countChannelRelations(self):
        data = self.timeMatchedQBEREntries.map(lambda e: e.counts + e.relatedPowers()).list()
        m = {'Heads': ['Count 1', 'Count 2', 'Power 1', 'Power 2'], 'Data': data}
        return m

    def HOMandQBERs(self, ratioBase, ratioMaxIndex):
        ratios = list(np.logspace(-ratioMaxIndex, ratioMaxIndex, 2 * ratioMaxIndex + 1, base=ratioBase))
        ratioPairs = seq([0] + ratios).zip(ratios + [1e100])
        homAndQberEntries = ratioPairs.map(lambda ratioPair: HOMandQBEREntry(ratioPair[0], ratioPair[1]))

        def getRatioPairIndex(powers):
            p1 = 1 if self.channelMonitorConfig[0][0] < 0 else powers[self.channelMonitorConfig[0][0]] - self.channelMonitorConfig[0][1]
            p2 = 1 if self.channelMonitorConfig[1][0] < 0 else powers[self.channelMonitorConfig[1][0]] - self.channelMonitorConfig[1][1]
            if p1 == 0 or p2 > self.channelMonitorConfig[1][2]:
                index = 0
            elif p2 == 0 or p1 > self.channelMonitorConfig[0][2]:
                index = 2 * ratioMaxIndex + 1
            else:
                index = np.max([np.min([ratioMaxIndex + int(np.floor(np.log10(p1 / p2) / np.log10(1.02))) + 1, 2 * ratioMaxIndex + 1]), 0])
            return index

        self.timeMatchedQBEREntries.for_each(lambda entry: homAndQberEntries[getRatioPairIndex(entry.relatedPowers())].append(entry))
        totalEntryCount = self.timeMatchedQBEREntries.size()
        r = homAndQberEntries.map(lambda e: e.toData()).list()
        return {'TotalEntryCount': totalEntryCount, 'SortedEntries': r}

    def release(self):
        self.qbers.release()
        self.channels.release()


class QBERs:
    def __init__(self, sections):
        self.sections = seq(sections)
        self.systemTime = sections[0].pcTime
        self.TDCTimeOfSectionStart = sections[0].tdcStart
        self.channelMonitorSyncs = seq([self.sections[0], self.sections[-1]]).map(lambda s: (s.slowSync - self.TDCTimeOfSectionStart) / 1e12)
        #     val valid = math.abs(channelMonitorSyncs(1) - channelMonitorSyncs(0) - 10) < 0.001

    def load(self, getter):
        self.sections.for_each(lambda z: z.load(getter))

        def createQBEREntryList(section):
            entryCount = len(section.contentCountEntries)

            def createQBEREntry(i):
                entryTDCStartStop = seq([i, i + 1]).map(lambda j: ((section.tdcStop - section.tdcStart) / entryCount * j + section.tdcStart - self.TDCTimeOfSectionStart) / 1e12)
                entryHOMs = section.contentHOMEntries[i]
                entryQBERs = section.contentQBEREntries[i]
                entryCounts = section.contentCountEntries[i]
                return QBEREntry(entryTDCStartStop[0], entryTDCStartStop[1], entryHOMs, entryCounts, entryQBERs)

            return seq(range(entryCount)).map(lambda i: createQBEREntry(i))

        self.entries = self.sections.map(lambda section: createQBEREntryList(section)).flatten()

    def release(self):
        self.sections.for_each(lambda z: z.release())

    @classmethod
    def create(cls, entries):
        syncedEntryIndices = seq(entries).zip_with_index().filter(lambda z: z[0].slowSync).map(lambda z: z[1])
        return syncedEntryIndices[:-1].zip(syncedEntryIndices[1:]).map(lambda z: QBERs(entries[z[0]:z[1] + 1]))


class QBERSection:
    def __init__(self, meta):
        self.meta = meta
        self.dbID = meta['_id']
        self.data = meta["Data"]
        self.mdiqkdQberMeta = self.data['MDIQKDQBER']
        syncs = self.mdiqkdQberMeta['ChannelMonitorSync']
        self.tdcStart = syncs[0]
        self.tdcStop = syncs[1]
        self.slowSync = None if len(syncs) <= 2 else syncs[2]
        self.pcTime = datetime.fromisoformat(self.meta['FetchTime']).timestamp()

    def load(self, getter):
        self.content = getter(self.dbID, {'Data.DataBlockCreationTime': 1, 'Data.MDIQKDQBER': 1})
        self.contentData = self.content['Data']
        self.contentQBER = self.contentData['MDIQKDQBER']
        self.contentQBEREntries = self.contentQBER['QBER Sections']
        self.contentHOMEntries = self.contentQBER['HOM Sections']
        self.contentCountEntries = self.contentQBER['Count Sections']

    def release(self):
        self.content = None
        self.contentData = None
        self.contentQBER = None
        self.contentQBEREntries = None
        self.contentHOMEntries = None
        self.contentCountEntries = None


class QBEREntry:
    def __init__(self, tdcStart, tdcStop, HOMs, counts, QBERs):
        self.tdcStart = tdcStart
        self.tdcStop = tdcStop
        self.HOMs = HOMs
        self.counts = counts
        self.QBERs = QBERs
        self.relatedPowerCount = 0
        self.power1Sum = 0
        self.power2Sum = 0

    def appendRelatedChannelEntry(self, entry):
        self.power1Sum += entry.power1
        self.power2Sum += entry.power2
        self.relatedPowerCount += 1

    def relatedPowers(self):
        if self.relatedPowerCount == 0: return [0.0, 0.0]
        return [self.power1Sum / self.relatedPowerCount, self.power2Sum / self.relatedPowerCount]


class Channels:
    def __init__(self, sections):
        self.sections = seq(sections)
        self.channelMonitorSyncs = seq([sections[0], sections[-1]]).map(lambda s: s.trigger / 1000)
        self.valid = np.abs(self.channelMonitorSyncs[1] - self.channelMonitorSyncs[0] - 10) < 0.1

    def load(self, getter):
        self.sections.for_each(lambda z: z.load(getter))

        def createChannelEntryList(section):
            channel1 = section.contentChannel1
            channel2 = section.contentChannel2
            pcTimeUnit = (section.timeLastSample - section.timeFirstSample) / (len(channel1) - 1)
            return seq(range(0, len(channel1))).map(lambda i: ChannelEntry(channel1[i], channel2[i], section.timeFirstSample + i * pcTimeUnit))

        self.entries = self.sections.map(lambda section: createChannelEntryList(section)).flatten().cache()
        self.riseIndices = [self.sections.first().riseIndex(), self.sections.last().riseIndex() + self.sections.init().map(lambda s: len(s.contentChannel1)).sum()]

    def release(self):
        seq(self.sections).for_each(lambda z: z.release())

    @classmethod
    def create(cls, entries):
        # print('creating')
        # print(entries.size())
        # for entry in entries:
        #     print(entry.trigger)
        syncedEntryIndices = seq(entries).zip_with_index().filter(lambda z: z[0].trigger).map(lambda z: z[1])
        # print(syncedEntryIndices)
        return syncedEntryIndices[:-1].zip(syncedEntryIndices[1:]).map(lambda z: Channels(entries[z[0]:z[1] + 1]))


class ChannelSection:
    def __init__(self, meta):
        self.meta = meta
        self.data = meta['Data']
        self.dbID = meta['_id']
        triggers = self.data['Triggers']
        self.trigger = None if len(triggers) == 0 else triggers[0]
        timeFirstSample_ms = self.data['TimeFirstSample']
        timeLastSample_ms = self.data['TimeLastSample']
        self.timeFirstSample = timeFirstSample_ms / 1e3
        self.timeLastSample = timeLastSample_ms / 1e3

    def load(self, getter):
        self.content = getter(self.dbID, {'Data.Channel1': 1, 'Data.Channel2': 1})
        self.contentData = self.content['Data']
        self.contentChannel1 = self.contentData['Channel1']
        self.contentChannel2 = self.contentData['Channel2']

    def release(self):
        self.content = None
        self.contentData = None
        self.contentChannel1 = None
        self.contentChannel2 = None

    def riseIndex(self):
        pcTimeUnit = (self.timeLastSample - self.timeFirstSample) / (len(self.contentChannel1) - 1)
        riseIndex = int(np.ceil((self.trigger / 1e3 - self.timeFirstSample) / pcTimeUnit))
        return riseIndex


class ChannelEntry:
    def __init__(self, power1, power2, pcTime):
        self.power1 = power1
        self.power2 = power2
        self.pcTime = pcTime
        self.tdcTime = -1

    def setTDCTime(self, tdcTime):
        self.tdcTime = tdcTime

class DataBlock:
    def __init__(self, fetchTime, dataTimeBegin, dataTimeEnd, content, sectionCount):
        self.fetchTime = fetchTime
        self.dataTimeBegin = dataTimeBegin
        self.dataTimeEnd = dataTimeEnd
        self.content = content
        self.sectionCount = sectionCount
        self.sectionUnit = 1e12 / sectionCount
        self.__divide()

    @classmethod
    def load(cls, path):
        file = open(path, 'rb')
        data = file.read(os.path.getsize(path))
        file.close()
        unpacker = msgpack.Unpacker(raw=False)
        unpacker.feed(data)
        entries = []
        for packed in unpacker:
            entries.append(packed)
        if len(entries) != 1:
            raise RuntimeError('There is {} entries in DataBlock file {}, which is not valid.'.format(len(packed), path))
        entry = entries[0]
        dataBlock = DataBlock(datetime.fromtimestamp(entry['CreationTime'] / 1000.0).astimezone(pytz.timezone('Asia/Shanghai')), entry['DataTimeBegin'], entry['DataTimeEnd'], entry['Content'], 1000)
        return dataBlock

    def __divide(self):
        def __divideAChannel(data):
            data = np.array(data)
            asi = ((data - self.dataTimeBegin) / self.sectionUnit).astype(int)
            divided = [data[asi == i] for i in range(0, self.sectionCount)]
            return divided

        dividedContent = [__divideAChannel(self.content[i]) for i in range(0, len(self.content))]
        self.dataBlockEntries = seq(range(0, self.sectionCount)).map(lambda i: DataBlockEntry(self.dataTimeBegin + self.sectionUnit * i, self.dataTimeBegin + self.sectionUnit * (i + 1), seq(range(0, len(self.content))).map(lambda c: dividedContent[c][i]).to_list())).to_list()


class DataBlockEntry:
    def __init__(self, tdcStart, tdcStop, content):
        self.tdcStart = tdcStart
        self.tdcStop = tdcStop
        self.content = content
        self.relatedPowerCount = 0
        self.power1Sum = 0
        self.power2Sum = 0

    def appendRelatedChannelEntry(self, entry):
        self.power1Sum += entry.power1
        self.power2Sum += entry.power2
        self.relatedPowerCount += 1

    # def relatedPowers(self):
    #     if self.relatedPowerCount == 0: return [0.0, 0.0]
    #     return [self.power1Sum / self.relatedPowerCount, self.power2Sum / self.relatedPowerCount]

    def serialize(self):
        content = {
            'TDCStart': self.tdcStart,
            'TDCStop': self.tdcStop,
            # 'Content': memfile.getvalue(),
            'RelatedPowerCount': self.relatedPowerCount,
            'Power1': self.power1Sum / self.relatedPowerCount,
            'Power2': self.power2Sum / self.relatedPowerCount,
        }
        return msgpack.packb(content)


class DataBlockFilter:
    def __init__(self, worker, collectionTDC, collectionMonitor, pathDataBlockFiles, pathOutput, startTime, stopTime):
        self.worker = worker
        self.collectionTDC = collectionTDC
        self.collectionMonitor = collectionMonitor
        self.pathDataBlockFiles = pathDataBlockFiles
        self.pathOutput = pathOutput
        self.startTime = startTime
        self.stopTime = stopTime

    def perform(self):
        qberSections = seq(self.worker.Storage.range(self.collectionTDC, self.startTime, self.stopTime, by='FetchTime', filter={'FetchTime': 1, 'Data.MDIQKDQBER.ChannelMonitorSync': 1})).map(lambda m: QBERSection(m))
        qbersList = QBERs.create(qberSections)
        channelSections = seq(self.worker.Storage.range(self.collectionMonitor, self.startTime, self.stopTime, by='FetchTime', filter={'Data.Triggers': 1, 'Data.TimeFirstSample': 1, 'Data.TimeLastSample': 1})).map(lambda m: ChannelSection(m))
        channelsList = Channels.create(channelSections)
        dataPairs = qbersList.map(lambda qber: [qber, channelsList.filter(lambda channel: np.abs(qber.systemTime - channel.channelMonitorSyncs[0]) < 3)]).filter(lambda z: z[1].size() > 0).map(lambda z: [z[0], z[1][0]]).list()
        print("{} DataPairs found.".format(len(dataPairs)))

        for dataPair in dataPairs:
            qbers, channels = dataPair[0], dataPair[1]

            # Load DataBlock
            dataBlocks = qbers.sections.map(lambda s: DataBlock.load('{}/{}.datablock'.format(self.pathDataBlockFiles, datetime.fromtimestamp(s.pcTime).isoformat().replace(":", "-")[:-3]))).to_list()

            # Match Time
            channels.load(lambda id, filter: self.worker.Storage.get(self.collectionMonitor, id, '_id', filter))
            qberSyncPair = qbers.channelMonitorSyncs
            timeUnit = (qberSyncPair[1] - qberSyncPair[0]) / (channels.riseIndices[1] - channels.riseIndices[0])
            firstRiseIndex = channels.riseIndices[0]
            seq(range(channels.riseIndices[0], channels.riseIndices[1])).for_each(lambda i: channels.entries[i].setTDCTime((i - firstRiseIndex) * timeUnit + qberSyncPair[0]))

            # Perform Entry Match
            allChannelEntries = np.array(channels.entries.to_list())
            channelEntryTDCTimes = np.array(channels.entries.map(lambda e: e.tdcTime).to_list())
            TDCTimeOfSectionStart = dataBlocks[0].dataTimeBegin

            for dataBlock in dataBlocks:
                for entry in dataBlock.dataBlockEntries:
                    relatedChannelEntryIndeces = np.where((channelEntryTDCTimes > (entry.tdcStart - TDCTimeOfSectionStart) / 1e12) & (channelEntryTDCTimes < (entry.tdcStop - TDCTimeOfSectionStart) / 1e12))
                    relatedChannelEntries = allChannelEntries[relatedChannelEntryIndeces]
                    for channelEntry in relatedChannelEntries:
                        entry.appendRelatedChannelEntry(channelEntry)

            dbEntries = seq(dataBlocks).map(lambda db: db.dataBlockEntries).flatten().filter(lambda e: e.relatedPowerCount > 0).to_list()
            outputFileName = '{}/{}.pmdatablocks'.format(self.pathOutput, dataBlocks[0].fetchTime.isoformat().replace(" ", "T").replace(":", "-")[:-9])
            outputFile = open(outputFileName, 'wb')

            summuries = [{
                'TDCStart': e.tdcStart,
                'TDCStop': e.tdcStop,
                'RelatedPowerCount': e.relatedPowerCount,
                'Power1': e.power1Sum / e.relatedPowerCount,
                'Power2': e.power2Sum / e.relatedPowerCount,
            } for e in dbEntries]
            sContent = np.array([dbEntry.content for dbEntry in dbEntries])
            memfile = io.BytesIO()
            np.save(memfile, sContent)
            outputFile.write(msgpack.packb({
                'Summaries': summuries,
                'Contents': memfile.getvalue()
            }))
            memfile.close()
            outputFile.close()

def debug_info(level, msg):
    pass
    # print('[{}] {}'.format(level, msg))

if __name__ == '__main__':
    print(datetime.now(pytz.timezone('Asia/Shanghai')).isoformat())
    worker = IFWorker("tcp://172.16.60.199:224", 'MDIQKD_ResultFiltering', timeout=10)
    reviewer = RealtimeReviewer(worker, 'MDIQKD_GroundTDC', 'MDI_ADCMonitor', 'MDIQKD_DataReviewer', datetime.now(pytz.timezone('Asia/Shanghai')).isoformat(), [[0, -0.4, 4.5], [1, -0.4, 4.5]])    #2020.8.21
    # reviewer = RealtimeReviewer(worker, 'MDIQKD_GroundTDC', 'MDI_ADCMonitor', 'MDIQKD_DataReviewer', '2020-01-01T00:00:00+08:00', [[0, -0.4, 4.5], [1, -0.4, 4.5]])                               #2020.8.22
    reviewer.start()

    # worker = IFWorker("tcp://127.0.0.1:224")
    # reviewer = Reviewer(worker, 'MDIQKD_GroundTDC', 'MDI_ADCMonitor', 'MDIQKD_DataReviewer', '2020-08-01T01:29:30+08:00',  '2020-08-01T01:36:30+08:00')
    # reviewer.deleteExists()
    # reviewer.review()
