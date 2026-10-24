from datetime import datetime
import sys
from Instrument.tdc.SwabianTimeTag.SwabianTimeTag import SwabianTimeTag
from Instrument.tdc.TDCServer import TDCServer
import numpy as np
from tdc.TFQKDQBERAnalyser import TFQKDQBERAnalyser, DataBlockParseResult
import pytimetag
from interactionfreepy import IFWorker
import msgpack
import numba
from pytimetag import DataBlock
from Instrument.tdc.SwabianTimeTag.SwabianTimeTag import generateDataBlockContent
import time
from rich.live import Live
from rich.table import Table
import os
import pickle
from datetime import datetime
import math
from collections import OrderedDict
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import urllib
from rich.console import Group
from rich.text import Text
from tdc.SyncAnalyser import SyncAnalyser

class RealTimeTDC:
  def __init__(self):
    self.dataBuffer = []
    self.analysers = {}
    self.receivedTimes = []
    self.receivedTimeAve = np.nan
    self.receivedTimeStd = np.nan

  def offer(self, data):
    # print(f'one new rt datablock at {datetime.now()}')
    self.receivedTimes.append(time.time())
    self.dataBuffer.append(data)
    if len(self.receivedTimes) > 10 * 1800:
      self.receivedTimes.pop(0)
    if len(self.dataBuffer) > 10 * 1800:
      self.dataBuffer.pop(0)

    if len(self.receivedTimes) >= 50:
      values = np.asarray(self.receivedTimes[-50:], dtype=float)
      diffs = np.diff(values)  # 49 个相邻差值：后一个减前一个
      self.receivedTimeAve = np.average(diffs)
      self.receivedTimeStd = np.std(diffs)

  def getRecent(self, count, reversed=False, delayOnly=False):
    result = [d for d in self.dataBuffer]
    result = result if (len(result) <= count) else result[-count:]
    if (reversed):
      result.reverse()
    if delayOnly:
      result = [{
        'FetchTime': r['FetchTime'],
        'Delays': [r["TFQKDSyncAlice"]["Delay"], r["TFQKDSyncBob"]["Delay"]]
        } for r in result]
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

# class QKDQBERAnalyser(pytimetag.Analyser):
#   def __init__(self, ifworker, channelCount, randomNumberLimit):
#     super().__init__()
#     self.worker = ifworker
#     self.channelCount = channelCount
#     self.randomNumberLimit = randomNumberLimit
#     self.aliceLongRandomNumberID = None
#     self.aliceLongRandomNumber = None
#     self.bobLongRandomNumberID = None
#     self.bobLongRandomNumber = None
#     self.aliceLongRandomNumberToBeUpdate = False
#     self.bobLongRandomNumberToBeUpdate = False
#     self.setConfiguration('AliceRandomNumbers', np.ones(1, dtype='int'), lambda x: True)
#     self.setConfiguration('BobRandomNumbers', np.ones(1, dtype='int'), lambda x: True)
#     self.setConfiguration('Period', 10000, pytimetag.Validator.float(0))
#     self.setConfiguration('PulsePosition', 5000, pytimetag.Validator.float(0))
#     self.setConfiguration('Gate', 1000, pytimetag.Validator.float(0))
#     self.setConfiguration('TriggerChannel', 0, pytimetag.Validator.int(0, channelCount - 1))
#     self.setConfiguration('Channel 1', 2, pytimetag.Validator.int(0, channelCount - 1))
#     self.setConfiguration('Channel 2', 3, pytimetag.Validator.int(0, channelCount - 1))

#   def configure(self, paras):
#     if (paras.__contains__('AliceRandomNumbers')):
#       aliceRNS = paras['AliceRandomNumbers']
#       if isinstance(aliceRNS, str):
#         self.aliceLongRandomNumberID = aliceRNS
#         self.aliceLongRandomNumberToBeUpdate = True
#         # bytes = self.worker.TF_FileStorage.readMassive(self.aliceLongRandomNumberID)
#         # self.aliceLongRandomNumber = np.array(msgpack.unpackb(bytes))
#         # paras['AliceRandomNumbers'] = self.aliceLongRandomNumber
#         paras.pop('AliceRandomNumbers')
#       else:
#         self.aliceLongRandomNumberID = None
#         self.aliceLongRandomNumber = None
#     if (paras.__contains__('BobRandomNumbers')):
#       bobRNS = paras['BobRandomNumbers']
#       if isinstance(bobRNS, str):
#         self.bobLongRandomNumberID = bobRNS
#         self.bobLongRandomNumberToBeUpdate = True
#         # bytes = self.worker.TF_FileStorage.readMassive(self.bobLongRandomNumberID)
#         # self.bobLongRandomNumber = np.array(msgpack.unpackb(bytes))
#         # paras['BobRandomNumbers'] = self.bobLongRandomNumber
#         paras.pop('BobRandomNumbers')
#       else:
#         self.bobLongRandomNumberID = None
#         self.bobLongRandomNumber = None
#     super().configure(paras)

#   def dataIncome(self, dataBlock):
#     if self.aliceLongRandomNumberToBeUpdate:
#       self.aliceLongRandomNumberToBeUpdate = False
#       bytes = self.worker.TF_FileStorage.readMassive(self.aliceLongRandomNumberID)
#       self.aliceLongRandomNumber = np.array(msgpack.unpackb(bytes))
#       paras = {'AliceRandomNumbers': self.aliceLongRandomNumber}
#       super().configure(paras)
#     if self.bobLongRandomNumberToBeUpdate:
#       self.bobLongRandomNumberToBeUpdate = False
#       bytes = self.worker.TF_FileStorage.readMassive(self.bobLongRandomNumberID)
#       self.bobLongRandomNumber = np.array(msgpack.unpackb(bytes))
#       paras = {'BobRandomNumbers': self.bobLongRandomNumber}
#       super().configure(paras)
#     result = super().dataIncome(dataBlock)
#     if result:
#       if self.aliceLongRandomNumberID:
#         result['Configuration']['AliceRandomNumbers'] = self.aliceLongRandomNumberID
#       if self.bobLongRandomNumberID:
#         result['Configuration']['BobRandomNumbers'] = self.bobLongRandomNumberID
#     return result

class TempStoreAnalyser(pytimetag.Analyser):
  def __init__(self):
    super().__init__()
    self.setConfiguration('MaxSize', 60, pytimetag.Validator.int(0, 1000))
    self.map = OrderedDict()
    dataMap = self.map

    class MyHandler(BaseHTTPRequestHandler):
      def do_GET(self):
        if self.path.endswith('.datablock'):
          dataname = self.path[1:]
          dataname = urllib.parse.unquote(dataname)
          data = dataMap[dataname]

          self.send_response(200)
          self.send_header('Content-type', 'application/octet-stream')
          self.end_headers()
          self.wfile.write(data)

      def log_message(self, format, *args):
        pass
        # print(f"{self.address_string()} - {format%args}")

    self.server = HTTPServer(('0.0.0.0', 1000), MyHandler)
    MyHandler.dataMap = self.map
    self.httpThread = Thread(target=self.server.serve_forever, daemon=True)
    self.httpThread.start()

  def analysis(self, dataBlock):
    maxSize = self.getConfiguration('MaxSize')
    datetimeStr = str(datetime.fromtimestamp(dataBlock.creationTime))
    date = datetimeStr[:10]
    hour = datetimeStr[11:13]
    dateTime = datetimeStr.replace(':', '-')[:23]
    path = '/'.join([date, hour, dateTime + '.datablock'])
    self.map[path] = dataBlock.serialize()
    while len(self.map) > maxSize:
      self.map.popitem(last=False)
    return {}

  def getTempStoredDataBlock(self, path):
    data = analysers['TempStore'].map[path]
    return data


def prepareAnalysers(workerRN, channelCount):
  analysers = {}
  analysers['Counter'] = pytimetag.CounterAnalyser()
  analysers['Counter'].turnOn()
  analysers['MultiHistogram'] = pytimetag.HistogramAnalyser(channelCount)
  analysers['MultiHistogram'].turnOn({'Sync': 0, 'Signals': [2, 3], 'ViewStart': 0, 'ViewStop': 40000000, 'BinCount': 1000, 'Divide': 1})
  analysers['TFQKDEncoding'] = LongRandomNumberEncodingAnalyser(workerRN, channelCount, 256)
  analysers['TFQKDEncoding'].turnOn({'Period': 5000, 'TriggerChannel': 1, 'SignalChannel': 4, 'RandomNumbers': [0], 'PulsePerTrigger': 100000000,
  'Histograms': {
      'All Pulses': [i for i in range(128)],
      'All Signals': [i for i in range(64)],
      'All Ref': [64, 128],
      'Vacuum': [i for i in range(64) if i % 4 == 0],
      'X': [i for i in range(64) if i % 4 == 1],
      'Y': [i for i in range(64) if i % 4 == 2],
      'Z': [i for i in range(64) if i % 4 == 3],
  }})
  analysers['TFQKDEncoding2'] = LongRandomNumberEncodingAnalyser(workerRN, channelCount, 256)
  analysers['TFQKDEncoding2'].turnOn({'Period': 5000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': [0], 'PulsePerTrigger': 100000000,
  'Histograms': {
      'All Pulses': [i for i in range(128)],
      'All Signals': [i for i in range(64)],
      'All Ref': [64, 128],
      'Vacuum': [i for i in range(64) if i % 4 == 0],
      'X': [i for i in range(64) if i % 4 == 1],
      'Y': [i for i in range(64) if i % 4 == 2],
      'Z': [i for i in range(64) if i % 4 == 3],
  }})
  analysers['TFQKDSyncAlice'] = SyncAnalyser(channelCount, 256)
  analysers['TFQKDSyncBob'] = SyncAnalyser(channelCount, 256)
  analysers['TFQKDSyncAlice'].turnOn({'Period': 5000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': [0], 'PulsePosition': 2500, 'Histograms': {'Sync Alice': [i for i in range(128)]}})
  analysers['TFQKDSyncBob'].turnOn({'Period': 5000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': [0], 'PulsePosition': 2500, 'Histograms': {'Sync Bob': [i for i in range(128)]}})
  analysers['TFQKDSyncAliceMonitor'] = SyncAnalyser(channelCount, 256)
  analysers['TFQKDSyncBobMonitor'] = SyncAnalyser(channelCount, 256)
  analysers['TFQKDSyncAliceMonitor'].turnOn({'Period': 5000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': [0], 'PulsePosition': 2500, 'Histograms': {'Sync Alice Monitor': [i for i in range(64)]}})
  analysers['TFQKDSyncBobMonitor'].turnOn({'Period': 5000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': [0], 'PulsePosition': 2500, 'Histograms': {'Sync Bob Monitor': [i for i in range(64)]}})
  analysers['ChannelMonitor'] = pytimetag.FastCounterAnalyser()
  analysers['ChannelMonitor'].turnOn({'Channels': [4, 5], 'Frequency': 1000})
  # analysers['QKDQBER'] = QKDQBERAnalyser(workerRN, channelCount, 256)
  # analysers['QKDQBER'].turnOn({'AliceRandomNumbers': '2023-06-03 23-29-07.013601 R513371', 'BobRandomNumbers': '2023-06-03 23-30-47.632215 R298145', 'Period': 10000, 'PulsePosition': 5000, 'Gate': 1000, 'TriggerChannel': 0, 'Channel 1': 2, 'Channel 2': 3})
  # analysers['QKDQBER'].turnOn({'AliceRandomNumbers': [0], 'BobRandomNumbers': [0], 'Period': 10000, 'PulsePosition': 5000, 'Gate': 1000, 'TriggerChannel': 0, 'Channel 1': 2, 'Channel 2': 3})
  analysers['QKDQBER'] = TFQKDQBERAnalyser(channelCount)
  analysers['QKDQBER'].configure({
    'AliceRandomNumbers': [(i) % 128 for i in range(128)], 'BobRandomNumbers': [(i) % 128 for i in range(128)], 
    'TimeEachBlock': int(1e12), 'FrequencyFrame': int(1e11), 'PhaseFrame': int(2e8), 'IntensityFrame': int(1e9),
    'Period': 5000, 'TriggerPeriod': 80000000, 'PulsePosition': 2500, 'Gate': 1000, 'GateRef': 1000, 
    'TriggerChannel': 0, 'Channel 1': 2, 'Channel 2': 3, 'SyncChannelAlice': 4, 'SyncChannelBob': 5})
  
  analysers['TempStore'] = TempStoreAnalyser()
  analysers['TempStore'].turnOn()
  return analysers

def JITasAIT(analysers):
  # progress = Progress()
  # task = progress.add_task("Preparing JIT method in TDCServer...", total=len(analysers) + 1)
  # progress.start()

  ts = numba.typed.List([np.random.randint(0, 1000000000000, 1000, dtype='i8')])
  cs = numba.typed.List([np.random.randint(0, 16, 1000, dtype='i8')])
  db = DataBlock.create(generateDataBlockContent(ts, cs), time.time(), 0, 1000000000000)
  # progress.update(task, advance=1)

  for analyserName in analysers:
    analyser = analysers[analyserName]
    analyser.dataIncome(db)
    # progress.update(task, advance=1)
  # progress.stop()

class DopplerUtil:
  def __init__(self, tagout=False) -> None:
    self.latestOnePPSOriginalTime = None
    self.onePPSCount = 0
    self.startDopplerShiftAtPS = None
    self.startDopplerShiftAt = None
    self.dopplerShiftTimeStep = 0.01
    self.tagout = tagout
    self.timingMap = []
    
  def prepare(self, beginTimeStamp, curveFile):
    self.startDopplerShiftAt = beginTimeStamp
    self.startDopplerShiftAtPS = None
    with open(curveFile, 'rb') as file:
      self.dopplerTimings = pickle.load(file)
      # self.dopplerTimings = msgpack.unpackb(file.read())
      self.dopplerShiftFs = self.dopplerTimings['f']
      print(f'Doppler Timing loaded: {curveFile}')
      timingMap = [] # 左边多普勒前，右边多普勒后
      expectedWavenumbers = [0]
      for f in self.dopplerShiftFs:
        expectedWavenumbers.append(expectedWavenumbers[-1] + f * self.dopplerShiftTimeStep)
      expectedWavenumbers = np.array(expectedWavenumbers)
      for i in range(len(expectedWavenumbers) - 1):
        pulseIndex = math.ceil(expectedWavenumbers[i])
        expTiming = pulseIndex * 100000
        actTiming = int((i * 0.01 + (pulseIndex - expectedWavenumbers[i]) / self.dopplerShiftFs[i]) * 1e12)
        timingMap.append([expTiming, actTiming])
      self.timingMap = np.array(timingMap)
    self.latestOnePPSOriginalTime = None

  def rescale(self, datablock):
    if self.latestOnePPSOriginalTime is None and datablock.sizes[1] == 0:
      return DataBlock.create([[] for i in range(len(datablock.sizes))], datablock.creationTime, -2, -1, datablock.resolution)
    if datablock.sizes[1] > 0:
      self.latestOnePPSOriginalTime = datablock.content[1][0]
      self.onePPSCount += 1

    datablock = self.frequencyRescaleAdaptor(datablock)
    datablock = self.dopplerReshapingAdaptor(datablock)
    return datablock

  def frequencyRescaleAdaptor(self, dataBlock):
    if dataBlock.sizes[0] < 2: return dataBlock
    content = dataBlock.content
    latestOnePPSScaledTime = (self.onePPSCount - 1) * 1000000000000
    freqScale = 1 / ((content[0][-1] - content[0][0]) / (content[0].size - 1) * 25000 / 1e12)
    offset = latestOnePPSScaledTime - self.latestOnePPSOriginalTime * freqScale
    newContents = []
    for ch in content:
      newCH = rescaleChannel(ch, freqScale, offset, copy=False)
      newContents.append(newCH)

    newDataBlock = DataBlock.create(newContents, dataBlock.creationTime, dataBlock.dataTimeBegin * freqScale + offset, dataBlock.dataTimeEnd * freqScale + offset, dataBlock.resolution)
    return newDataBlock

  def dopplerReshapingAdaptor(self, dataBlock):
    if self.startDopplerShiftAt == None: return dataBlock
    if self.startDopplerShiftAtPS is None:
      if dataBlock.sizes[1] == 0: return dataBlock
      else:
        if int(dataBlock.creationTime + 0.5) == self.startDopplerShiftAt:
          if self.tagout: print('Doppler Shift Begins!')
          self.startDopplerShiftAtPS = dataBlock.content[1][0]
        else: return dataBlock
    dopplerShiftDuration = self.dopplerShiftTimeStep * (len(self.dopplerShiftFs) - 1)
    if self.tagout: print(f'Performing Doppler Shift @ second {int(dataBlock.creationTime + 0.5) - self.startDopplerShiftAt}.')
    content = dataBlock.content
    newContents = []
    newContents.append(content[0].copy())
    newContents.append(content[1].copy())
    for i in range(2, len(content)):
      newContent = mapTiming_rev_array(content[i], self.timingMap, self.startDopplerShiftAtPS, copy=False)
      newContents.append(newContent)
    
    dopplerShiftEnd = self.startDopplerShiftAt + dopplerShiftDuration
    if dataBlock.sizes[1] > 0 and int(dataBlock.creationTime + 0.5) >= dopplerShiftEnd and self.startDopplerShiftAtPS is not None:
      if self.tagout: print('Doppler Shift Ends!')
      self.startDopplerShiftAtPS = None
            
    newDataBlock = DataBlock.create(newContents, dataBlock.creationTime, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, dataBlock.resolution)
    return newDataBlock

@numba.njit(cache=True)
def rescaleChannel(ch, freqScale, offset, copy=False):
  newCH = ch if not copy else np.zeros(shape=ch.shape, dtype=ch.dtype)
  for i in range(len(ch)):
    newCH[i] = ch[i] * freqScale + offset
  return ch

@numba.njit(cache=True)
def mapTiming_rev_array(tRights, timingMap, offset, copy=False):
  tLefts = tRights if not copy else np.zeros(shape=tRights.shape, dtype=tRights.dtype)
  m_p = 0
  for iRight in range(len(tRights)):
    tRight = tRights[iRight] - offset
    if m_p < len(timingMap) - 1 and timingMap[m_p][1] > tRight: continue
    while m_p < len(timingMap) - 1 and timingMap[m_p + 1][1] <= tRight: m_p += 1
    if m_p >= len(timingMap) - 1: break
    tLeft1, tRight1 = timingMap[m_p]
    tLeft2, tRight2 = timingMap[m_p + 1]
    tLeft = (tRight - tRight1) / (tRight2 - tRight1) * (tLeft2 - tLeft1) + tLeft1
    tLefts[iRight] = tLeft + offset
  return tLefts

if __name__ == '__main__':
  worker = None

  hasEnoughParameters = len(sys.argv) >= 11
  ifserver = sys.argv[1] if hasEnoughParameters else 'tcp://10.1.1.1:224'
  sn = sys.argv[2] if hasEnoughParameters else '1947000s70'
  triggerLevelsStr = sys.argv[3] if hasEnoughParameters else '0.5,0.5,0.07,0.08,0.08,0.07,0.5,0.5'
  deadtime = int(sys.argv[4]) if hasEnoughParameters else 60000
  defaultDelaysStr = sys.argv[5] if hasEnoughParameters else "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0"
  serviceName = sys.argv[6] if hasEnoughParameters else 'TF_TDCServer_Test'
  storeCollection = sys.argv[7] if hasEnoughParameters else 'TDCServerTestCollection'
  serviceNameRTT = sys.argv[8] if hasEnoughParameters else 'RealTimeTDC'
  relatedAtomicServiceName = sys.argv[9] if hasEnoughParameters else 'NoAtomic'
  isSim = sys.argv[10].lower() == 'true' if hasEnoughParameters else True
  rawStore = sys.argv[11].lower() == 'true' if len(sys.argv) >= 12 else False
  rawStoreLocalPath = sys.argv[12] if len(sys.argv) >= 13 else None
  adaptedRawStoreLocalPath = sys.argv[13] if len(sys.argv) >= 14 else None

  channelCount = 16
  workerRN = IFWorker(ifserver)
  analysers = prepareAnalysers(workerRN, channelCount)

  st = SwabianTimeTag('SIM' if isSim else sn, 1)
  triggerLevels = [float(s) for s in triggerLevelsStr.split(',')]
  defaultDelays = [float(s) for s in defaultDelaysStr.split(',')]
  forever = True

  rt = RealTimeTDC()

  if not isSim:
    for i in range(len(triggerLevels)):
      st.setTriggerLevel(i + 1, triggerLevels[i])
      st.setDeadtime(i + 1, deadtime)

  st.start({
      0: ['Period', 250000], 1: ['Period', 1],
      2: ['Pulse', 100000000, 1000000, 1000], 3: ['Pulse', 100000000, 1000000, 1000],
      4: ['Pulse', 100000000, 1000000, 1000], 5: ['Pulse', 100000000, 1000000, 1000]})

  # syncDelays = [np.nan, np.nan]
  # qberStatus = {'text': None}

  def storePostProcessData(dataBlock, result):
    # delays = [result["TFQKDSyncAlice"]["Delay"], result["TFQKDSyncBob"]["Delay"]]
    # syncDelays[:] = delays
    worker.blockingInvoker('Storage', timeout=2).append(storeCollection, result, fetchTime=dataBlock.creationTime)
        # worker.Storage.append(storeCollection, result, fetchTime=dataBlock.creationTime)
    # if 'QKDQBER' in result.keys() and result['QKDQBER'] is not None and (len(result['QKDQBER'].keys()) > 1):
    #   qberStatus['text'] = DataBlockParseResult.toString(result['QKDQBER'])
    # else:
    #   qberStatus['text'] = None

  def storeRawData(dataBlock):
    datetimeStr = str(datetime.fromtimestamp(dataBlock.creationTime))
    date = datetimeStr[:10]
    hour = datetimeStr[11:13]
    dateTime = datetimeStr.replace(':', '-')[:23]
    if rawStoreLocalPath:
      if rawStoreLocalPath == 'None': pass
      else:
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

  def storeAdaptedRawData(dataBlock):
    pass

  def tuneCH0(delta):
    print(f'tuning CH0 with delay {delta} ps.')
    # deltalist = [40000000 - delta, delta]
    # deltalist_abs = [abs(t) for t in deltalist]
    # min_value = min(deltalist_abs)
    # min_index = deltalist_abs.index(min_value)
    # # delta = deltalist[min_index]
    # worker.TF_AtomicClock_Calvin.delay1PPS(1E9-delta)
    
    delta /= 1000   # to ns
    move = (int(1000000000 - delta if delta < 20000 else 40000 - delta) + 100) % 1000000000
    print('1pps need to move', move, ', that is ', move / 1e3, 'µs')
    if move > 0: worker.blockingInvoker(relatedAtomicServiceName).delay1PPS(move)

  class TF_TDCServer(TDCServer):
    def __init__(self, tdc, channelCount, funcStorePostProcessData, funcStoreRaw=None, funcFastProcess=None, funcStoreAdaptedRaw=None, funcTuneCH0=None):
      super().__init__(tdc, channelCount, funcStorePostProcessData, funcStoreRaw, funcFastProcess, funcStoreAdaptedRaw)
      self.dataBlockNumber = 0
      self.dopplerUtil = DopplerUtil(tagout=True)
      self.dopplerUtil_fast = DopplerUtil()

      self.ch0Offset = 0
      self.ch0Tuned = False
      self.ch0DeltaValues = []
      self.latestCH1ForFast = None
      self.funcTuneCH0 = funcTuneCH0
  
      def ch1OffsetAdaptor(dataBlock):
        if dataBlock.sizes[1] == 0: return dataBlock
        current1PPSTime = dataBlock.content[1][0]
        next25kTime = dataBlock.content[0][dataBlock.content[0] >= current1PPSTime]
        if len(next25kTime) == 0: return dataBlock
        # print('---   ', next25kTime[0] - current1PPSTime)
        dataBlock.content[1][0] += next25kTime[0] - current1PPSTime
        self.ch0Offset = int(next25kTime[0] - current1PPSTime)
        if not self.ch0Tuned and self.funcTuneCH0:
          # self.funcTuneCH0(self.ch0Offset)
          self.ch0Tuned = True
        return dataBlock

      self.adaptors = [self.dopplerUtil.rescale, ch1OffsetAdaptor]
      self.adaptors_fast = [self.dopplerUtil_fast.rescale, ch1OffsetAdaptor]

    def startDopplerShift(self, timestamp):
      if not isinstance(timestamp, int): raise ValueError('Doppler Shift should begin at Integer Second.')
      # self.dopplerUtil.prepare(timestamp, 'Doppler_Timing.msgpack')
      # self.dopplerUtil_fast.prepare(timestamp, 'Doppler_Timing.msgpack')
      self.dopplerUtil.prepare(timestamp, 'Doppler_Timing.pkl')
      self.dopplerUtil_fast.prepare(timestamp, 'Doppler_Timing.pkl')
      print(f'Doppler shift will be started at {datetime.fromtimestamp(self.dopplerUtil.startDopplerShiftAt)}')
    
    def getCH0Offset(self):
      return self.ch0Offset

    def getDopplerShiftTimeRange(self):
      begin = 0 if self.dopplerUtil.startDopplerShiftAt is None else self.dopplerUtil.startDopplerShiftAt
      return [begin, begin + len(self.dopplerUtil.timingMap) * 0.01]

    def getEncodingDelays():
      pass

  server = TF_TDCServer(st, channelCount, storePostProcessData, storeRawData, rt.offer, storeAdaptedRawData, tuneCH0)
  server.setDelays(defaultDelays)
  server.setPostProcessStatus(True)
  server.setRawDataStore((not isSim) and (rawStore))
  print(f'is store: {(not isSim) and (rawStore)}')
  # if isSim: server.startDopplerShift(int(datetime.now().timestamp()) + 20)

  JITasAIT(analysers)
  print('done JITasAIT')

  worker = IFWorker(ifserver, serviceName, server, force=True)
  workerRTT = IFWorker(ifserver, serviceNameRTT, rt, force=True)
  print('worker started')

  for name in ['Counter', 'MultiHistogram', 'TFQKDEncoding', 'TFQKDEncoding2', 'ChannelMonitor', 'QKDQBER', 'TFQKDSyncAliceMonitor', 'TFQKDSyncBobMonitor', 'TempStore']:
    server.installAnalyser(name, analysers[name])
  for name in ['TFQKDSyncAlice', 'TFQKDSyncBob']:
    server.installAnalyser(name, analysers[name], fastMode=True)

  rt.analysers = {
    'TFQKDSyncAlice': server.analysers['TFQKDSyncAlice'],
    'TFQKDSyncBob': server.analysers['TFQKDSyncBob']
  }
  print('analysers installed')

  table = Table()
  live = Live(table, refresh_per_second=4)
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

    message = Text(
      f"最近 5 s RealTimeTDC 获取时间差 {rt.receivedTimeAve * 1000:.1f} ± {rt.receivedTimeStd * 1000:.1f} ms"
    )

    # delays = syncDelays[:]
    # delayMessage = Text(
    #   f'Delays: Alice {(np.nan if delays[0] is None else delays[0] / 1000):9.2f} ns   '
    #   f'Bob {(np.nan if delays[1] is None else delays[1] / 1000):9.2f} ns'
    # )
    # display = [table, delayMessage, message]
    display = [table, message]
    # if server.isAnalyserOn('QKDQBER'):
    #   display.append(Text(qberStatus['text'] or 'QBER: waiting for results...'))
    # else:
    #   qberStatus['text'] = None
    live.update(Group(*display))

  server.runtimeMetaMonitor = monitor
  live.start()

  server.start()
  print('server started')
