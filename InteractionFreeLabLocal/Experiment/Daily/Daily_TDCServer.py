# numpy==1.24.0
# pytimetag
# numba

import os
import numpy as np
import numba
from pytimetag import DataBlock
import time
from datetime import datetime
from threading import Thread, Semaphore
from queue import Queue
import TimeTagger

@numba.njit(cache=True)
def generateDataBlockContent(timestampsBuffer, channelsBuffer):
    sizes = np.zeros(16, dtype='int')
    for section in range(len(channelsBuffer)):
        channels = channelsBuffer[section]
        for i in range(len(channels)):
            sizes[channels[i]] += 1
    contents = [np.zeros(size, dtype='<i8') for size in sizes]
    ps = np.zeros(16, dtype='int')
    for section in range(len(timestampsBuffer)):
        timestamps = timestampsBuffer[section]
        channels = channelsBuffer[section]
        for i in range(len(timestamps)):
            ch = channels[i]
            contents[ch][ps[ch]] = timestamps[i]
            ps[ch] += 1
    return contents


def dataSreamGenerator(config):
    class Data:
        def __init__(self, data):
            self.timestamps = (data / 16).astype('<i8')
            self.channels = data % 16 + 1

        def getChannels(self):
            return self.channels

        def getTimestamps(self):
            return self.timestamps

        def size(self):
            return len(self.timestamps)

    class Generator:
        def __init__(self):
            self.beginTime = 0
            self.__buffer = np.zeros(0, dtype='<i8')
            self.__bufferPosition = 0

        def __gen(self):
            db = DataBlock.generate({'CreationTime': time.time(), 'DataTimeBegin': self.beginTime,
                                     'DataTimeEnd': self.beginTime + 1000000000000}, config)
            self.beginTime += 1000000000000
            self.__buffer = np.hstack(
                [self.__buffer[self.__bufferPosition:]] + [db.content[i] * 16 + i for i in range(len(db.content)) if
                                                           db.content[i].shape[0] > 0])
            self.__buffer = np.sort(self.__buffer)
            self.__bufferPosition = 0

        def isRunning(self):
            return True

        def getData(self, count=1000000):
            t1 = time.time()
            if self.__buffer.shape[0] - self.__bufferPosition < count:
                self.__gen()
            r = self.__buffer[self.__bufferPosition: self.__bufferPosition + count]
            self.__bufferPosition += count
            data = Data(r)
            t2 = time.time()
            return data

    return Generator()


class TimeTagDataStreamConbiner:
    def __init__(self, splitBy, timeRange=None, queueSize=15):
        self.splitBy = splitBy
        self.splitDataRange = timeRange
        self.splitDataTime = None
        self.timestampsBuffer = None
        self.channelsBuffer = None
        self.dataBlockQueue = Queue()
        self.currentSectionStart = None
        self.queueSize = queueSize

    def __searchForSplit(self, timestamps, channels):
        if self.splitBy is None:
            if self.splitDataTime is None:
                self.splitDataTime = timestamps[0]
            p = np.searchsorted(timestamps, self.splitDataTime)
            if p < len(timestamps):
                self.splitDataTime += self.splitDataRange
                return p
        else:
            p = np.where(channels == self.splitBy)[0]
            if len(p) > 0:
                if self.splitDataTime == None:
                    self.splitDataTime = [timestamps[p[0]]]
                else:
                    self.splitDataTime = [self.splitDataTime[-1], timestamps[p[0]]]
                return p[0]
        return None

    def deal(self, timestamps, channels):
        newDB = False
        splitPoint = self.__searchForSplit(timestamps, channels)
        if splitPoint is None:
            if self.timestampsBuffer is not None:
                self.timestampsBuffer.append(timestamps)
                self.channelsBuffer.append(channels)
        else:
            if self.timestampsBuffer is None:
                self.timestampsBuffer = []
                self.channelsBuffer = []
            else:
                ts = numba.typed.List(self.timestampsBuffer + [timestamps[:splitPoint]])
                cs = numba.typed.List(self.channelsBuffer + [channels[:splitPoint]])
                t2 = time.time()
                if self.splitBy is None:
                    dataTimeBegin = self.splitDataTime - self.splitDataRange * 2
                    dataTimeEnd = self.splitDataTime - self.splitDataRange
                else:
                    dataTimeBegin = self.splitDataTime[0]
                    dataTimeEnd = self.splitDataTime[1]
                self.dataBlockQueue.put(
                    DataBlock.create(generateDataBlockContent(ts, cs), self.currentSectionStart, int(dataTimeBegin),
                                     int(dataTimeEnd)))
                newDB = True
                if self.dataBlockQueue.qsize() > self.queueSize:
                    self.dataBlockQueue.get()

                self.timestampsBuffer = [timestamps[splitPoint:]]
                self.channelsBuffer = [channels[splitPoint:]]
            self.currentSectionStart = time.time()
            return newDB


class SwabianTimeTag:
    def __init__(self, sn, splitBy, splitIn=100000000000):
        self.sn = sn
        self.splitBy = splitBy
        self.isSim = sn == 'SIM'
        self.bufferSize = int(10e6)
        self.stream = None
        self.dealTime = 0
        self.dealTimes = [0] * 4
        self.conbinerByTime = TimeTagDataStreamConbiner(splitBy=None, timeRange=splitIn, queueSize=150)
        self.conbinerByChannel = None if self.splitBy is None else TimeTagDataStreamConbiner(splitBy=splitBy,
                                                                                             queueSize=15)

        if not self.isSim:
            print(TimeTagger.scanTimeTagger())
            self.tagger = TimeTagger.createTimeTagger(sn)

    def start(self, config={}):
        if self.isSim:
            self.stream = dataSreamGenerator(config)
        else:
            import TimeTagger
            self.stream = TimeTagger.TimeTagStream(tagger=self.tagger, n_max_events=self.bufferSize,
                                                   channels=[i for i in range(1, 9, 1)])
            self.stream.start()
        Thread(target=self.__loop).start()

    def getNextDataBlock(self, timeRanged=False):
        if timeRanged:
            return self.conbinerByTime.dataBlockQueue.get()
        else:
            if self.conbinerByChannel:
                return self.conbinerByChannel.dataBlockQueue.get()
            else:
                raise AttributeError('Channel Splitted DataBlock is not configured.')

    def __loop(self):
        try:
            while self.stream.isRunning():
                data = self.stream.getData()
                if data.size:
                    t1 = time.time()
                    channels = data.getChannels() - 1
                    timestamps = data.getTimestamps()
                    self.conbinerByTime.deal(timestamps, channels)
                    newDB = False
                    if self.conbinerByChannel:
                        newDB = self.conbinerByChannel.deal(timestamps, channels)

                    t4 = time.time()
                    self.dealTime += t4 - t1
                    if newDB:
                        self.dealTime = 0
                time.sleep(0.01)
        except BaseException as e:
            import traceback
            traceback.format_exc(e)

    def setTriggerLevel(self, channel, triggerLevel):
        self.tagger.setTriggerLevel(channel, triggerLevel)

    def setDeadtime(self, channel, deadtime):
        self.tagger.setDeadtime(channel, deadtime)


class DailyTDCServer:
    def __init__(self, tdc, channelCount, funcStorePostProcessData=None, funcStoreRaw=None):
        self.tdc = tdc
        self.funcStoreRaw = funcStoreRaw
        self.funcStorePostProcessData = funcStorePostProcessData
        self.channelCount = channelCount
        self.delays = [0] * self.channelCount
        self.analysers = {}
        self.analysersFastMode = {}
        self.adaptors = []
        self.postProcessOn = False
        self.rawDataStoreOn = False
        self.__rawDataStoreQueue = Queue()
        self.runtimeMetaMonitor = None

    def start(self):
        Thread(target=self.__loopRawDataStore).start()
        Thread(target=self.__loopPostProcess).start()

    def __loopPostProcess(self):
        while True:
            try:
                dataBlock = self.tdc.getNextDataBlock(timeRanged=True)
                if self.postProcessOn:
                    self.__performPostProcess(dataBlock)
            except BaseException as e:
                print(e)

    def __loopRawDataStore(self):
        while True:
            try:
                tobeStored = self.__rawDataStoreQueue.get()
                self.funcStoreRaw(tobeStored[0])
            except BaseException as e:
                print(e)
            finally:
                tobeStored[2]['EndTime'] = time.time()
                tobeStored[1].release()

    def __performPostProcess(self, dataBlock):
        overallBeginTime = time.time()
        executionTimes = {}
        result = {}
        dataBlock = dataBlock.synced(self.delays)
        rawDataStoreSemaphore = None
        rawDataStoreResult = {}
        adaptedRawDataStoreResult = {}

        if self.rawDataStoreOn and self.funcStoreRaw:
            rawDataStoreSemaphore = Semaphore(0)
            self.__rawDataStoreQueue.put(
                [dataBlock.synced([0] * len(self.delays)), rawDataStoreSemaphore, rawDataStoreResult])

        executionTimes['Fetch Delay'] = overallBeginTime - dataBlock.creationTime
        executionTimes['Unpack Time'] = time.time() - overallBeginTime

        beginTime = time.time()
        for adaptor in self.adaptors:
            dataBlock = adaptor(dataBlock)
        endTime = time.time()
        executionTimes['Adapting'] = endTime - beginTime

        for analyserName in self.analysers:
            try:
                analyser = self.analysers[analyserName]
                # print(f'Analyser {analyserName}     isOn={analyser.on}')
                beginTime = time.time()
                result[analyserName] = analyser.dataIncome(dataBlock)
                # print(f'result updated with {result[analyserName].keys()}')
                endTime = time.time()
                executionTimes[analyserName] = endTime - beginTime
            except BaseException as e:
                print(f'Exception raised during Analyser[{analyserName}]: {str(e)}')
        if rawDataStoreSemaphore:
            rawDataStoreSemaphore.acquire()
            executionTimes['Massive Store Time'] = rawDataStoreResult['EndTime'] - overallBeginTime

        executionTimes['Overall'] = time.time() - overallBeginTime
        result['ExecutionTimes'] = executionTimes
        if self.runtimeMetaMonitor:
            self.runtimeMetaMonitor(dataBlock.sizes, executionTimes)
        else:
            print(dataBlock.sizes)
            print(executionTimes)

        result['Configurations'] = {'Delays': self.delays}
        if self.funcStorePostProcessData:
            self.funcStorePostProcessData(dataBlock, result)

    def installAnalyser(self, name, analyser, fastMode=False):
        self.analysers[name] = analyser
        if fastMode:
            self.analysersFastMode[name] = analyser

    def turnOnAnalyser(self, name, paras={}):
        self.analysers[name].turnOn(paras)

    def configureAnalyser(self, name, paras={}):
        self.analysers[name].configure(paras)

    def getAnalyserConfiguration(self, name):
        return self.analysers[name].getConfigurations()

    def turnOffAnalyser(self, name):
        self.analysers[name].turnOff()

    def isAnalyserOn(self, name):
        return self.analysers[name].isTurnedOn()

    def turnOffAllAnalysers(self):
        for analyser in self.analysers: analyser.turnOff()

    def setDelays(self, delays):
        if (len(delays) != len(self.delays)): raise AttributeError(f'Delays should has length of {len(self.delays)}.')
        for i in range(len(delays)): self.setDelay(i, delays[i])

    def setDelay(self, channel, delay):
        self.delays[channel] = int(delay)

    def getDelays(self):
        return [d for d in self.delays]

    def getChannelCount(self):
        return self.channelCount

    def setRawDataStore(self, p):
        self.rawDataStoreOn = p

    def isRawDataStore(self):
        return self.rawDataStoreOn

    def setPostProcessStatus(self, p):
        self.postProcessOn = p

    def getPostProcessStatus(self):
        return self.postProcessOn

    def setTriggerLevel(self, channel, triggerLevel):
        self.tdc.setTriggerLevel(channel + 1, triggerLevel)

    def setDeadtime(self, channel, deadtime):
        self.tdc.setDeadtime(channel + 1, deadtime)


if __name__ == '__main__':
    sn = '1947000s70'
    triggerLevels = [0.5, 0.5, 0.07, 0.08, 0.08, 0.07, 0.5, 0.5]
    deadtime = 60000
    defaultDelays = [0, 0, 5000, 5000, 5000, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    rawStoreLocalPath = './store_test'

    st = SwabianTimeTag(sn, splitBy=None, splitIn=1000000000000)

    forever = True

    for i in range(len(triggerLevels)):
        st.setTriggerLevel(i + 1, triggerLevels[i])
        st.setDeadtime(i + 1, deadtime)

    st.start({
        0: ['Period', 25000], 1: ['Period', 1],
        2: ['Pulse', 100000000, 1000000, 1000], 3: ['Pulse', 100000000, 1000000, 1000],
        4: ['Pulse', 100000000, 1000000, 1000], 5: ['Pulse', 100000000, 1000000, 1000]})


    def storeRawData(dataBlock):
        datetimeStr = str(datetime.fromtimestamp(dataBlock.creationTime))
        date = datetimeStr[:10]
        hour = datetimeStr[11:13]
        dateTime = datetimeStr.replace(':', '-')[:23]
        dir = '/'.join([rawStoreLocalPath, date, hour])
        os.makedirs(dir, exist_ok=True)
        path = '/'.join([dir, dateTime + '.datablock'])
        file = open(path, 'wb')
        file.write(dataBlock.serialize())
        file.close()
        print(f'Stored Raw Locally: {path}')


    server = DailyTDCServer(tdc=st, channelCount=16, funcStoreRaw=storeRawData)
    server.setDelays(defaultDelays)
    server.setPostProcessStatus(True)
    server.setRawDataStore(True)

    def monitor(counts, exeTimes):
        print(counts)

    server.runtimeMetaMonitor = monitor

    server.start()
    print('server started')
