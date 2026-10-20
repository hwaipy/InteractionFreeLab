from datetime import datetime
import sys
from Instrument.tdc.SwabianTimeTag.SwabianTimeTag import SwabianTimeTag
from Instrument.tdc.TDCServer import TDCServer
import numpy as np
import pytimetag
from interactionfreepy import IFWorker, IFLoop
import msgpack
import numba
from pytimetag import DataBlock
from Instrument.tdc.SwabianTimeTag.SwabianTimeTag import generateDataBlockContent
import time
from rich.progress import Progress
from rich.live import Live
from rich.table import Table
import os

class ReadTimeTDC:
  def __init__(self):
    self.dataBuffer = []
    self.analysers = {}

  def offer(self, data):
    self.dataBuffer.append(data)
    if len(self.dataBuffer) > 10 * 1800:
      self.dataBuffer.pop(0)

  def getRecent(self, count, reversed=False):
    result = [d for d in self.dataBuffer]
    result = result if (len(result) <= count) else result[-count:]
    if (reversed):
      result.reverse()
    return result

  def getRanged(self, begin, end, reversed=False):
    begin = datetime.fromisoformat(begin).timestamp()
    end = datetime.fromisoformat(end).timestamp()
    result = [d for d in self.dataBuffer if d['FetchTime'] >= begin and d['FetchTime'] <= end]
    if (reversed):
      result.reverse()
    return result

  # def getRecentDipCenter(self, count, target, reversed=True):
  #   data = self.getRecent(count, reversed)

  #   def estimateCenter(target):
  #     dataAs = np.array([d[f'TFQKDSync{target}'][f'Histogram[Sync {target}]'] for d in data])
  #     dataA = np.sum(dataAs, axis=0)
  #     if target == 'Alice':
  #       dataA = np.hstack((dataA[-int(len(dataA) / 4):], dataA[:int(len(dataA) / 4)]))
  #     else:
  #       dataA = dataA[int(len(dataA) / 4):int(len(dataA) / 4 * 3)]

  #     b, a = signal.butter(8, 5 / len(dataA), 'highpass')
  #     filteredDataA = signal.filtfilt(b, a, dataA)

  #     peakValue = min(filteredDataA)
  #     center = np.where(filteredDataA == peakValue)[0][0]
  #     for right in range(center, len(filteredDataA)):
  #       if filteredDataA[right] > peakValue / 2:
  #         break
  #     for left in range(center, 0, -1):
  #       if filteredDataA[left] > peakValue / 2:
  #         break
  #     weight = 0
  #     count = 0
  #     for i in range(left, right + 1):
  #       weight += i * filteredDataA[i]
  #       count += filteredDataA[i]
  #     valid = min(filteredDataA[:left]) > peakValue * 0.7 and max(filteredDataA[right:]) > peakValue * 0.7
  #     center = weight / count / len(dataA) * 10
  #     return center if valid else np.nan
  #   return np.average([d['FetchTime'] / 1000.0 for d in data]), estimateCenter(target)


class LongRandomNumberEncodingAnalyser(pytimetag.EncodingAnalyser):
  def __init__(self, ifworker, channelCount, randomNumberLimit):
    super().__init__(channelCount, randomNumberLimit)
    self.worker = ifworker
    self.longRandomNumberID = None
    self.longRandomNumber = None
    self.longRandomNumberToBeUpdate = False

  def configure(self, paras):
    if (paras.__contains__('RandomNumbers')):
      rns = paras['RandomNumbers']
      if isinstance(rns, str):
        self.longRandomNumberID = rns
        self.longRandomNumberToBeUpdate = True
        paras.pop('RandomNumbers')
      else:
        self.longRandomNumberID = None
        self.longRandomNumber = None
    super().configure(paras)

  def dataIncome(self, dataBlock):
    if self.longRandomNumberToBeUpdate:
      self.longRandomNumberToBeUpdate = False
      bytes = self.worker.TF_FileStorage.readMassive(self.longRandomNumberID)
      self.longRandomNumber = np.array(msgpack.unpackb(bytes))
      paras = {'RandomNumbers': self.longRandomNumber}
      super().configure(paras)
    result = super().dataIncome(dataBlock)
    if result and self.longRandomNumberID:
      result['Configuration']['RandomNumbers'] = self.longRandomNumberID
    return result


class QKDQBERAnalyser(pytimetag.Analyser):
  def __init__(self, ifworker, channelCount, randomNumberLimit):
    super().__init__()
    self.worker = ifworker
    self.channelCount = channelCount
    self.randomNumberLimit = randomNumberLimit
    self.aliceLongRandomNumberID = None
    self.aliceLongRandomNumber = None
    self.bobLongRandomNumberID = None
    self.bobLongRandomNumber = None
    self.aliceLongRandomNumberToBeUpdate = False
    self.bobLongRandomNumberToBeUpdate = False
    self.setConfiguration('AliceRandomNumbers', np.ones(1, dtype='int'), lambda x: True)
    self.setConfiguration('BobRandomNumbers', np.ones(1, dtype='int'), lambda x: True)
    self.setConfiguration('Period', 10000, pytimetag.Validator.float(0))
    self.setConfiguration('PulsePosition', 5000, pytimetag.Validator.float(0))
    self.setConfiguration('Gate', 1000, pytimetag.Validator.float(0))
    self.setConfiguration('TriggerChannel', 0, pytimetag.Validator.int(0, channelCount - 1))
    self.setConfiguration('Channel 1', 2, pytimetag.Validator.int(0, channelCount - 1))
    self.setConfiguration('Channel 2', 3, pytimetag.Validator.int(0, channelCount - 1))

  def configure(self, paras):
    if (paras.__contains__('AliceRandomNumbers')):
      aliceRNS = paras['AliceRandomNumbers']
      if isinstance(aliceRNS, str):
        self.aliceLongRandomNumberID = aliceRNS
        self.aliceLongRandomNumberToBeUpdate = True
        # bytes = self.worker.TF_FileStorage.readMassive(self.aliceLongRandomNumberID)
        # self.aliceLongRandomNumber = np.array(msgpack.unpackb(bytes))
        # paras['AliceRandomNumbers'] = self.aliceLongRandomNumber
        paras.pop('AliceRandomNumbers')
      else:
        self.aliceLongRandomNumberID = None
        self.aliceLongRandomNumber = None
    if (paras.__contains__('BobRandomNumbers')):
      bobRNS = paras['BobRandomNumbers']
      if isinstance(bobRNS, str):
        self.bobLongRandomNumberID = bobRNS
        self.bobLongRandomNumberToBeUpdate = True
        # bytes = self.worker.TF_FileStorage.readMassive(self.bobLongRandomNumberID)
        # self.bobLongRandomNumber = np.array(msgpack.unpackb(bytes))
        # paras['BobRandomNumbers'] = self.bobLongRandomNumber
        paras.pop('BobRandomNumbers')
      else:
        self.bobLongRandomNumberID = None
        self.bobLongRandomNumber = None
    super().configure(paras)

  def dataIncome(self, dataBlock):
    if self.aliceLongRandomNumberToBeUpdate:
      self.aliceLongRandomNumberToBeUpdate = False
      bytes = self.worker.TF_FileStorage.readMassive(self.aliceLongRandomNumberID)
      self.aliceLongRandomNumber = np.array(msgpack.unpackb(bytes))
      paras = {'AliceRandomNumbers': self.aliceLongRandomNumber}
      super().configure(paras)
    if self.bobLongRandomNumberToBeUpdate:
      self.bobLongRandomNumberToBeUpdate = False
      bytes = self.worker.TF_FileStorage.readMassive(self.bobLongRandomNumberID)
      self.bobLongRandomNumber = np.array(msgpack.unpackb(bytes))
      paras = {'BobRandomNumbers': self.bobLongRandomNumber}
      super().configure(paras)
    result = super().dataIncome(dataBlock)
    if result:
      if self.aliceLongRandomNumberID:
        result['Configuration']['AliceRandomNumbers'] = self.aliceLongRandomNumberID
      if self.bobLongRandomNumberID:
        result['Configuration']['BobRandomNumbers'] = self.bobLongRandomNumberID
    return result

def prepareAnalysers(workerRN, channelCount):
  analysers = {}
  analysers['Counter'] = pytimetag.CounterAnalyser()
  analysers['Counter'].turnOn()
  analysers['MultiHistogram'] = pytimetag.HistogramAnalyser(channelCount)
  analysers['MultiHistogram'].turnOn({'Sync': 0, 'Signals': [2, 3], 'ViewStart': 0, 'ViewStop': 40000000, 'BinCount': 1000, 'Divide': 1})
  analysers['TFQKDEncoding'] = LongRandomNumberEncodingAnalyser(workerRN, channelCount, 256)
  analysers['TFQKDEncoding'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 2, 'RandomNumbers': '2023-06-03 23-29-07.013601 R513371', 'Histograms': {
      'All Pulses': [i for i in range(128)],
      'All Signals': [i for i in range(64)],
      'All Ref': [64, 128],
      'Vacuum': [i for i in range(64) if i % 4 == 0],
      'X': [i for i in range(64) if i % 4 == 1],
      'Y': [i for i in range(64) if i % 4 == 2],
      'Z': [i for i in range(64) if i % 4 == 3],
  }})
  analysers['TFQKDSyncAlice'] = LongRandomNumberEncodingAnalyser(workerRN, channelCount, 256)
  analysers['TFQKDSyncBob'] = LongRandomNumberEncodingAnalyser(workerRN, channelCount, 256)
  analysers['TFQKDSyncAliceMonitor'] = LongRandomNumberEncodingAnalyser(workerRN, channelCount, 256)
  analysers['TFQKDSyncBobMonitor'] = LongRandomNumberEncodingAnalyser(workerRN, channelCount, 256)
  analysers['TFQKDSyncAlice'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': '2023-06-03 23-29-07.013601 R513371', 'Histograms': {'Sync Alice': [i for i in range(64)]}})
  analysers['TFQKDSyncBob'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': '2023-06-03 23-30-47.632215 R298145', 'Histograms': {'Sync Bob': [i for i in range(64)]}})
  analysers['TFQKDSyncAliceMonitor'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': '2023-06-03 23-29-07.013601 R513371', 'Histograms': {'Sync Alice Monitor': [i for i in range(64)]}})
  analysers['TFQKDSyncBobMonitor'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': '2023-06-03 23-30-47.632215 R298145', 'Histograms': {'Sync Bob Monitor': [i for i in range(64)]}})
  analysers['ChannelMonitor'] = pytimetag.FastCounterAnalyser()
  analysers['ChannelMonitor'].turnOn({'Channels': [4, 5], 'Frequency': 1000})
  analysers['QKDQBER'] = QKDQBERAnalyser(workerRN, channelCount, 256)
  analysers['QKDQBER'].turnOn({'AliceRandomNumbers': '2023-06-03 23-29-07.013601 R513371', 'BobRandomNumbers': '2023-06-03 23-30-47.632215 R298145', 'Period': 10000, 'PulsePosition': 5000, 'Gate': 1000, 'TriggerChannel': 0, 'Channel 1': 2, 'Channel 2': 3})
  return analysers

def JITasAIT(analysers):
  progress = Progress()
  task = progress.add_task("Preparing JIT method in TDCServer...", total=len(analysers) + 1)
  progress.start()

  ts = numba.typed.List([np.random.randint(0, 1000000000000, 1000, dtype='i8')])
  cs = numba.typed.List([np.random.randint(0, 16, 1000, dtype='i8')])
  db = DataBlock.create(generateDataBlockContent(ts, cs), time.time(), 0, 1000000000000)
  progress.update(task, advance=1)

  for analyserName in analysers:
    analyser = analysers[analyserName]
    analyser.dataIncome(db)
    progress.update(task, advance=1)
  progress.stop()
  
    
if __name__ == '__main__':
  worker = None

  hasEnoughParameters = len(sys.argv) >= 10
  ifserver = sys.argv[1] if hasEnoughParameters else 'tcp://10.1.1.1:1061'
  sn = sys.argv[2] if hasEnoughParameters else '1947000s70'
  triggerLevelsStr = sys.argv[3] if hasEnoughParameters else '0.5,0.5,0.07,0.08,0.08,0.07,0.5,0.5'
  deadtime = int(sys.argv[4]) if hasEnoughParameters else 60000
  defaultDelaysStr = sys.argv[5] if hasEnoughParameters else "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0"
  serviceName = sys.argv[6] if hasEnoughParameters else 'TF_TDCServer_Test'
  storeCollection = sys.argv[7] if hasEnoughParameters else 'TDCServerTestCollection'
  serviceNameRTT = sys.argv[8] if hasEnoughParameters else 'RealTimeTDC'
  isSim = sys.argv[9].lower() == 'true' if hasEnoughParameters else True
  rawStore = sys.argv[10].lower() == 'true' if len(sys.argv) >= 11 else False
  rawStoreLocalPath = sys.argv[11] if len(sys.argv) >= 12 else None

  channelCount = 16
  workerRN = IFWorker(ifserver)
  analysers = prepareAnalysers(workerRN, channelCount)
  JITasAIT(analysers)

  st = SwabianTimeTag('SIM' if isSim else sn, 1)
  triggerLevels = [float(s) for s in triggerLevelsStr.split(',')]
  defaultDelays = [float(s) for s in defaultDelaysStr.split(',')]
  forever = True

  rt = ReadTimeTDC()

  if not isSim:
    for i in range(len(triggerLevels)):
      st.setTriggerLevel(i + 1, triggerLevels[i])
      st.setDeadtime(i + 1, deadtime)

  st.start({
      0: ['Period', 25000], 1: ['Period', 1],
      2: ['Pulse', 100000000, 1000000, 1000], 3: ['Pulse', 100000000, 1000000, 1000],
      4: ['Pulse', 100000000, 1000000, 1000], 5: ['Pulse', 100000000, 1000000, 1000]})

  def storePostProcessData(dataBlock, result):
    worker.blockingInvoker('Storage', timeout=2).append(storeCollection, result, fetchTime=dataBlock.creationTime)
    # worker.Storage.append(storeCollection, result, fetchTime=dataBlock.creationTime)

  def storeRawData(dataBlock):
    datetimeStr = str(datetime.fromtimestamp(dataBlock.creationTime))
    date = datetimeStr[:10]
    hour = datetimeStr[11:13]
    dateTime = datetimeStr.replace(':', '-')[:23]
    if rawStoreLocalPath:
      dir = '/'.join([rawStoreLocalPath, date, hour])
      os.makedirs(dir, exist_ok=True)
      path = '/'.join([dir, dateTime + '.datablock'])
      print(f'Store Raw Locally: {path}')
      file = open(path, 'wb')
      file.write(dataBlock.serialize())
      file.close()
    else:
      path = '/'.join([date, hour, dateTime + '.datablock'])
      print(f'Store Raw: {path}')
      worker.blockingInvoker('TF_FileStorage', timeout=2).writeFile("TFQKD_RAW", path, dataBlock.serialize())

  server = TDCServer(st, channelCount, storePostProcessData, storeRawData, rt.offer)
  server.setDelays(defaultDelays)
  server.setPostProcessStatus(True)
  server.setRawDataStore((not isSim) and (rawStore))
  print(f'is store: {(not isSim) and (rawStore)}')

  worker = IFWorker(ifserver, serviceName, server, force=True)
  workerRTT = IFWorker(ifserver, serviceNameRTT, rt, force=True)

  for name in ['Counter', 'MultiHistogram', 'TFQKDEncoding', 'ChannelMonitor', 'QKDQBER', 'TFQKDSyncAliceMonitor', 'TFQKDSyncBobMonitor']:
    server.installAnalyser(name, analysers[name])
  for name in ['TFQKDSyncAlice', 'TFQKDSyncBob']:
    server.installAnalyser(name, analysers[name], fastMode=True)

  rt.analysers = {
    'TFQKDSyncAlice': server.analysers['TFQKDSyncAlice'],
    'TFQKDSyncBob': server.analysers['TFQKDSyncBob']
  }

#     analysers("ExceptionMonitor") = new ExceptionMonitorAnalyser(channelCount)
#     analysers("DeltaMetaAnalyser") = new DeltaMetaAnalyser(channelCount)
#     process.turnOnAnalyser("ExceptionMonitor", Map("SyncChannels" -> List(0)))
#     process.turnOnAnalyser("DeltaMetaAnalyser", Map("SyncChannel" -> 0, "Channel1" -> 2, "Channel2" -> 3, "GateWidth" -> 1200, "GroupBy" -> 250, "Period" -> 10000, "Center" -> 5000))

  table = Table()
  live = Live(table, refresh_per_second=4)
  # import threading
  # def t():
  #   while True:
  #     time.sleep(1)
  #     table.add_row('a', 'b', 'c')
  #     print('hahaha')
  # threading.Thread(target=t, daemon=True).start()
  def monitor(counts, exeTimes):
    table = Table()
    table.add_column("Channel")
    table.add_column("Counts")
    table.add_column("    ")
    table.add_column("Analyser")
    table.add_column("Exe Time")
    exeNames = list(exeTimes.keys())
    exeNames.sort()
    rowCount = max(8, len(exeNames))
    for nr in range(rowCount):
      row = []
      if nr < 8:
        row += [f'{nr}', f'{counts[nr]}']
      else:
        row += ['', '']
      row += ['    ']
      if nr < len(exeNames):
        row += [f'{exeNames[nr]}', f'{int(exeTimes[exeNames[nr]] * 1000)} ms']
      else:
        row += ['', '']
      table.add_row(*row)
    live.update(table)

  server.runtimeMetaMonitor = monitor
  live.start()

  

  server.start()
