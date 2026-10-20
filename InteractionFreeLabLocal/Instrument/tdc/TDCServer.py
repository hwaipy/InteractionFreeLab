from datetime import datetime
import time
import sys
from Instrument.tdc.SwabianTimeTag.SwabianTimeTag import SwabianTimeTag
from threading import Thread, Semaphore
import traceback
from queue import Queue

class TDCServer:
  def __init__(self, tdc, channelCount, funcStorePostProcessData=None, funcStoreRaw=None, funcFastProcess=None, funcStoreAdaptedRaw=None):
    self.tdc = tdc
    self.funcStoreRaw = funcStoreRaw
    self.funcStoreAdaptedRaw = funcStoreAdaptedRaw
    self.funcStorePostProcessData = funcStorePostProcessData
    self.funcFastProcess = funcFastProcess
    self.channelCount = channelCount
    self.delays = [0] * self.channelCount
    self.analysers = {}
    self.analysersFastMode = {}
    self.adaptors = []
    self.adaptors_fast = []
    self.postProcessOn = False
    self.rawDataStoreOn = False
    self.__rawDataStoreQueue = Queue()
    self.__adaptedRawDataStoreQueue = Queue()
    self.runtimeMetaMonitor = None
    self.__flagRawDataStore = 0
    self.__flagAdaptedRawDataStore = 0
    self.__flagRealTimeDeal = 0
    self.__flagPostProcess = 0

  def start(self):
    Thread(target=self.__loopRawDataStore).start()
    Thread(target=self.__loopAdaptedRawDataStore).start()
    Thread(target=self.__loopRealTimeDeal).start()
    Thread(target=self.__loopPostProcess).start()

  def __loopRealTimeDeal(self):
    while True:
      try:
        self.__flagRealTimeDeal += 1
        db = self.tdc.getNextDataBlock(timeRanged=True)
        if self.funcFastProcess:
          overallBeginTime = time.time()
          executionTimes = {}
          result = {}
          dataBlock = db.synced(self.delays)
          executionTimes['Fetch Delay'] = overallBeginTime - dataBlock.creationTime
          executionTimes['Unpack Time'] = time.time() - overallBeginTime

          for adaptor in self.adaptors_fast:
            dataBlock = adaptor(dataBlock)

          for analyserName in self.analysersFastMode:
            analyser = self.analysersFastMode[analyserName]
            beginTime = time.time()
            result[analyserName] = analyser.dataIncome(dataBlock)
            endTime = time.time()
            executionTimes[analyserName] = endTime - beginTime
          executionTimes['Overall'] = time.time() - overallBeginTime
          result['ExecutionTimes'] = executionTimes
          # print(executionTimes)
          result['Configurations'] = {'Delays': self.delays}
          result['FetchTime'] = db.creationTime
          self.funcFastProcess(result)
      except BaseException as e:
        print(e)

  def __loopPostProcess(self):
    while True:
      self.__flagPostProcess += 1
      try:
        dataBlock = self.tdc.getNextDataBlock(timeRanged=False)
        if self.postProcessOn:
          self.__performPostProcess(dataBlock)
      except BaseException as e:
        print(e)

  def __loopRawDataStore(self):
    while True:
      self.__flagRawDataStore += 1
      try:
        tobeStored = self.__rawDataStoreQueue.get()
        self.funcStoreRaw(tobeStored[0])
        # tobeStored[2]['EndTime'] = time.time()
        # tobeStored[1].release()
      except BaseException as e:
        print(e)
      finally:
        tobeStored[2]['EndTime'] = time.time()
        tobeStored[1].release()

  def __loopAdaptedRawDataStore(self):
    while True:
      self.__flagAdaptedRawDataStore += 1
      try:
        tobeStored = self.__adaptedRawDataStoreQueue.get()
        self.funcStoreAdaptedRaw(tobeStored[0])
        # tobeStored[2]['EndTime'] = time.time()
        # tobeStored[1].release()
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
      self.__rawDataStoreQueue.put([dataBlock.synced([0] * len(self.delays)), rawDataStoreSemaphore, rawDataStoreResult])

    executionTimes['Fetch Delay'] = overallBeginTime - dataBlock.creationTime
    executionTimes['Unpack Time'] = time.time() - overallBeginTime

    beginTime = time.time()
    for adaptor in self.adaptors:
      dataBlock = adaptor(dataBlock)
    endTime = time.time()
    executionTimes['Adapting'] = endTime - beginTime

    if self.rawDataStoreOn and self.funcStoreAdaptedRaw:
      adaptedRawDataStoreSemaphore = Semaphore(0)
      self.__adaptedRawDataStoreQueue.put([dataBlock, adaptedRawDataStoreSemaphore, adaptedRawDataStoreResult])

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

#   class TDCServerProcessor(threadCount: Int = 1) {
#     private val postProcessManagerExecutionContext = ExecutionContext.fromExecutorService(Executors.newSingleThreadExecutor())
#     private val postProcessExecutionContext = ExecutionContext.fromExecutorService(Executors.newFixedThreadPool(threadCount))
#     private val remoteStorageExecutionContext = ExecutionContext.fromExecutorService(Executors.newSingleThreadExecutor())
#     private val remoteMassiveStorageExecutionContext = ExecutionContext.fromExecutorService(Executors.newSingleThreadExecutor())
#     private val postProcessDataBuffer = new LinkedBlockingQueue[DataBlock]()
#     private val postProcessDataBufferMaxSize = 50e6
#     private val previousStoreFuture = new AtomicReference[Future[Any]](null)

  def installAnalyser(self, name, analyser, fastMode=False): 
    self.analysers[name] = analyser
    if fastMode:
      self.analysersFastMode[name] = analyser

  def turnOnAnalyser(self, name, paras={}): self.analysers[name].turnOn(paras)

  def configureAnalyser(self, name, paras={}): self.analysers[name].configure(paras)

  def getAnalyserConfiguration(self, name): return self.analysers[name].getConfigurations()

  def turnOffAnalyser(self, name): self.analysers[name].turnOff()

  def isAnalyserOn(self, name): return self.analysers[name].isTurnedOn()

  def turnOffAllAnalysers(self): 
    for analyser in self.analysers: analyser.turnOff()

  def setDelays(self, delays):
    if (len(delays) != len(self.delays)): raise AttributeError(f'Delays should has length of {len(self.delays)}.')
    for i in range(len(delays)): self.setDelay(i, delays[i])
  
  def setDelay(self, channel, delay): self.delays[channel] = int(delay)

  def getDelays(self): return [d for d in self.delays]

  def getChannelCount(self): return self.channelCount

  def setRawDataStore(self, p): self.rawDataStoreOn = p

  def isRawDataStore(self): return self.rawDataStoreOn

  def setPostProcessStatus(self, p): self.postProcessOn = p

  def getPostProcessStatus(self): return self.postProcessOn

  def setTriggerLevel(self, channel, triggerLevel):
    self.tdc.setTriggerLevel(channel + 1, triggerLevel)

  def setDeadtime(self, channel, deadtime):
    self.tdc.setDeadtime(channel + 1, deadtime)


if __name__ == '__main__':
  import pytimetag
  from interactionfreepy import IFWorker, IFLoop

#   worker = None

#   hasEnoughParameters = len(sys.argv) >= 9
#   ifserver = sys.argv[1] if hasEnoughParameters else 'tcp://10.1.1.1:1061'
#   sn = sys.argv[2] if hasEnoughParameters else '1947000s70'
#   triggerLevelsStr = sys.argv[3] if hasEnoughParameters else '0.5,0.5,0.07,0.08,0.08,0.07,0.5,0.5'
#   deadtime = int(sys.argv[4]) if hasEnoughParameters else 60000
#   defaultDelaysStr = sys.argv[3] if hasEnoughParameters else "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0"
#   serviceName = sys.argv[6] if hasEnoughParameters else 'TF_TDCServer_Test'
#   storeCollection = sys.argv[7] if hasEnoughParameters else 'TDCServerTestCollection'
#   isSim = bool(sys.argv[8]) if hasEnoughParameters else True

#   st = SwabianTimeTag('SIM' if isSim else sn, 1)
#   triggerLevels = [float(s) for s in triggerLevelsStr.split(',')]
#   defaultDelays = [float(s) for s in defaultDelaysStr.split(',')]
#   forever = True

#   if not isSim:
#     for i in range(len(triggerLevels)):
#       st.setTriggerLevel(i, triggerLevels[i])
#       st.setDeadtime(i, deadtime)

#   st.start({
#         0: ['Period', 25000], 1: ['Period', 1], 
#         2: ['Pulse', 100000000, 1000000, 1000], 3: ['Pulse', 100000000, 1000000, 1000],
#         4: ['Pulse', 100000000, 1000000, 1000], 5: ['Pulse', 100000000, 1000000, 1000]})

#   def storePostProcessData(dataBlock, result):
#     worker.Storage.append(storeCollection, result, fetchTime = dataBlock.creationTime)

#   def storeRawData(dataBlock):
#     datetimeStr = str(datetime.fromtimestamp(dataBlock.creationTime))
#     date = datetimeStr[:10]
#     hour = datetimeStr[11:13]
#     dateTime = datetimeStr.replace(':', '-')[:23]
#     path = '/'.join([date, hour, dateTime + '.datablock'])
#     print(f'Store Raw: {path}')
#     worker.TF_FileStorage.writeFile("TFQKD_RAW_Test", path, dataBlock.serialize())

#   server = TDCServer(st, storePostProcessData, storeRawData)
#   server.setDelays(defaultDelays)
#   server.setPostProcessStatus(True)
#   server.setRawDataStore(True)

#   worker = IFWorker(ifserver, serviceName, server, force=True)

#   server.installAnalyser('Counter', pytimetag.CounterAnalyser())
#   server.turnOnAnalyser('Counter')
#   server.installAnalyser('MultiHistogram', pytimetag.HistogramAnalyser(channelCount))
#   server.turnOnAnalyser('MultiHistogram', {'Sync': 0, 'Signals': [2, 3], 'ViewStart': 0, 'ViewStop': 40000000, 'BinCount': 1000, 'Divide': 1})
#   server.installAnalyser('TFQKDEncoding', LongRandomNumberEncodingAnalyser(worker, channelCount, 256))
#   server.turnOnAnalyser('TFQKDEncoding', {'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 2, 'RandomNumbers': '2022-11-04 00-58-30.211386 R307427', 'Histograms': {
#       'All Pulses': np.array([i for i in range(128)], dtype='<i4'),
#       'All Signals': np.array([i for i in range(64)], dtype='<i4'),
#       'All Ref': np.array([64, 128], dtype='<i4'),
#       'Vacuum': np.array([i for i in range(64) if i % 4 == 0], dtype='<i4'),
#       'X': np.array([i for i in range(64) if i % 4 == 1], dtype='<i4'),
#       'Y': np.array([i for i in range(64) if i % 4 == 2], dtype='<i4'),
#       'Z': np.array([i for i in range(64) if i % 4 == 3], dtype='<i4'),
#   }})
#   server.installAnalyser('TFQKDSyncAlice', LongRandomNumberEncodingAnalyser(worker, channelCount, 256))
#   server.installAnalyser('TFQKDSyncBob', LongRandomNumberEncodingAnalyser(worker, channelCount, 256))
#   server.turnOnAnalyser('TFQKDSyncAlice', {'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': '2022-11-04 00-58-30.211386 R307427', 'Histograms': {'Sync Alice': np.array([i for i in range(64)], dtype='<i4')}})
#   server.turnOnAnalyser('TFQKDSyncBob', {'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': '2022-11-04 00-58-31.589489 R881166', 'Histograms': {'Sync Bob': np.array([i for i in range(64)], dtype='<i4')}})
#   server.installAnalyser('ChannelMonitor', pytimetag.FastCounterAnalyser())
#   server.turnOnAnalyser('ChannelMonitor', {'Channels': [4, 5], 'Frequency': 1000})
#   server.installAnalyser('QKDQBER', QKDQBERAnalyser(worker, channelCount, 256))
#   server.turnOnAnalyser('QKDQBER', {'AliceRandomNumbers': '2022-11-04 00-58-30.211386 R307427', 'BobRandomNumbers': '2022-11-04 00-58-31.589489 R881166', 'Period': 10000, 'PulsePosition': 5000, 'Gate': 1000, 'TriggerChannel': 0, 'Channel 1': 2, 'Channel 2': 3})

# #     process.setPostProcessStatus(true)
# #     // process.setRawDataStore(true)
#   server.start()
