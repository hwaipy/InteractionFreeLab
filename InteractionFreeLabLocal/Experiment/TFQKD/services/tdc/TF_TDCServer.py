import sys
from Instrument.tdc.SwabianTimeTag.SwabianTimeTag import SwabianTimeTag, generateDataBlockContent
from Instrument.tdc.TDCServer import TDCServer
import numpy as np
import pytimetag
from interactionfreepy import IFWorker, IFLoop
import msgpack
import numba
from pytimetag import DataBlock, EncodingAnalyser
import time
from rich.progress import Progress
from rich.live import Live
from rich.table import Table
import os
import pickle
from datetime import datetime, timedelta
import math
from TFQKDQBERAnalyser import TFQKDQBERAnalyser, DataBlockParseResult
from SyncAnalyser import SyncAnalyser

def prepareAnalysers(workerRN, channelCount):
  analysers = {}
  analysers['Counter'] = pytimetag.CounterAnalyser()
  analysers['Counter'].turnOn()
  analysers['MultiHistogram'] = pytimetag.HistogramAnalyser(channelCount)
  analysers['MultiHistogram'].turnOn({'Sync': 0, 'Signals': [2, 3], 'ViewStart': 0, 'ViewStop': 40000000, 'BinCount': 1000, 'Divide': 1})
  analysers['TFQKDEncoding'] = EncodingAnalyser(channelCount, 256)
  analysers['TFQKDEncoding'].turnOn({'Period': 10000, 'TriggerChannel': 1, 'SignalChannel': 4, 
  'RandomNumbers': [0], 'PulsePerTrigger': 100000000,
  'Histograms': {
      'All Pulses': [i for i in range(128)],
      'All Signals': [i for i in range(64)],
      'All Ref': [64, 128],
      'Vacuum': [i for i in range(64) if i % 4 == 0],
      'X': [i for i in range(64) if i % 4 == 1],
      'Y': [i for i in range(64) if i % 4 == 2],
      'Z': [i for i in range(64) if i % 4 == 3],
  }})
  analysers['TFQKDEncoding2'] = EncodingAnalyser(channelCount, 256)
  analysers['TFQKDEncoding2'].turnOn({'Period': 10000, 'TriggerChannel': 1, 'SignalChannel': 5, 
  'RandomNumbers': [0], 'PulsePerTrigger': 100000000,
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
  analysers['TFQKDSyncAlice'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': [0], 'PulsePosition': 5000, 'Histograms': {'Sync Alice': [i for i in range(128)]}})
  analysers['TFQKDSyncBob'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': [0], 'PulsePosition': 5000, 'Histograms': {'Sync Bob': [i for i in range(128)]}})
  analysers['TFQKDSyncAliceMonitor'] = SyncAnalyser(channelCount, 256)
  analysers['TFQKDSyncBobMonitor'] = SyncAnalyser(channelCount, 256)
  analysers['TFQKDSyncAliceMonitor'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': [0], 'PulsePosition': 5000, 'Histograms': {'Sync Alice Monitor': [i for i in range(64)]}})
  analysers['TFQKDSyncBobMonitor'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': [0], 'PulsePosition': 5000, 'Histograms': {'Sync Bob Monitor': [i for i in range(64)]}})
  analysers['ChannelMonitor'] = pytimetag.FastCounterAnalyser()
  analysers['ChannelMonitor'].turnOn({'Channels': [4, 5], 'Frequency': 1000})
  analysers['QKDQBER'] = TFQKDQBERAnalyser(channelCount)
  analysers['QKDQBER'].configure({
    'AliceRandomNumbers': [(i) % 128 for i in range(128)], 'BobRandomNumbers': [(i) % 128 for i in range(128)], 
    'TimeEachBlock': int(1e12), 'FrequencyFrame': int(1e11), 'PhaseFrame': int(2e8), 'IntensityFrame': int(1e9),
    'Period': 10000, 'TriggerPeriod': 40000000, 'PulsePosition': 5000, 'Gate': 1000, 'GateRef': 2000, 
    'TriggerChannel': 0, 'Channel 1': 2, 'Channel 2': 3, 'SyncChannelAlice': 4, 'SyncChannelBob': 5})
  return analysers

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
  ifserver = sys.argv[1] if hasEnoughParameters else 'tcp://172.20.8.102:1061'
  sn = sys.argv[2] if hasEnoughParameters else '1947000s70'
  triggerLevelsStr = sys.argv[3] if hasEnoughParameters else '0.5,0.5,0.07,0.08,0.08,0.07,0.5,0.5'
  deadtime = int(sys.argv[4]) if hasEnoughParameters else 60000
  defaultDelaysStr = sys.argv[5] if hasEnoughParameters else "0,0,5000,5000,5000,5000,0,0,0,0,0,0,0,0,0,0"
  serviceName = sys.argv[6] if hasEnoughParameters else 'TF_TDCServer_Test'
  storeCollection = sys.argv[7] if hasEnoughParameters else 'TDCServerTestCollection'
  relatedAtomicServiceName = sys.argv[9] if hasEnoughParameters else 'NoAtomic'
  isSim = sys.argv[10].lower() == 'true' if hasEnoughParameters else True
  rawStore = sys.argv[11].lower() == 'true' if len(sys.argv) >= 12 else False
  rawStoreLocalPath = sys.argv[12] if len(sys.argv) >= 13 else None
  adaptedRawStoreLocalPath = sys.argv[13] if len(sys.argv) >= 14 else None

  channelCount = 16
  workerRN = IFWorker(ifserver)

  st = SwabianTimeTag('SIM' if isSim else sn, 1)
  triggerLevels = [float(s) for s in triggerLevelsStr.split(',')]
  defaultDelays = [float(s) for s in defaultDelaysStr.split(',')]
  forever = True

  if not isSim:
    for i in range(len(triggerLevels)):
      st.setTriggerLevel(i + 1, triggerLevels[i])
      st.setDeadtime(i + 1, deadtime)

  st.start({
      0: ['Period', 25000], 1: ['Period', 1],
      2: ['Pulse', 100000000, 1000000, 1000], 3: ['Pulse', 100000000, 1000000, 1000],
      4: ['Pulse', 100000000, 1000000, 1000], 5: ['Pulse', 100000000, 1000000, 1000]})

  server = None

  def storePostProcessData(dataBlock, result):
    worker.blockingInvoker('Storage', timeout=2).append(storeCollection, result, fetchTime=dataBlock.creationTime)
    # worker.Storage.append(storeCollection, result, fetchTime=dataBlock.creationTime)
    delays = [result["TFQKDSyncAlice"]["Delay"], result["TFQKDSyncBob"]["Delay"]]
    print(f'Delays:     {(np.nan if delays[0] == None else delays[0]):.1f} ps   {(np.nan if delays[1] == None else delays[1]):.1f} ps')
    if 'QKDQBER' in result.keys() and (len(result['QKDQBER'].keys()) > 1):
      print(DataBlockParseResult.toString(result['QKDQBER']))

  def storeRawData(dataBlock):
    t1 = time.time()
    datetimeStr = str(datetime.fromtimestamp(dataBlock.creationTime))
    date = datetimeStr[:10]
    hour = datetimeStr[11:13]
    dateTime = datetimeStr.replace(':', '-')[:23]
    data = dataBlock.serialize()
    t2 = time.time()
    if rawStoreLocalPath:
      if rawStoreLocalPath == 'None': pass
      else:
        dir = '/'.join([rawStoreLocalPath, date, hour])
        os.makedirs(dir, exist_ok=True)
        path = '/'.join([dir, dateTime + '.datablock'])
        print(f'Store Raw Locally: {path}')
        file = open(path, 'wb')
        file.write()
        file.close()
    else:
      path = '/'.join([date, hour, dateTime + '.datablock'])
      print(f'Store Raw: {path}')
      worker.blockingInvoker('TF_FileStorage', timeout=2).writeFile("TFQKD_RAW", path, dataBlock.serialize())
    t3 = time.time()
    print(t2 - t1, t3 - t2)

  def storeAdaptedRawData(dataBlock):
    pass

  def tuneCH0(delta):
    print(f'tuning CH0 with delay {delta} ps.')
    delta /= 1000   # to ns
    move = (int(1000000000 - delta if delta < 20000 else 40000 - delta) + 100) % 1000000000
    print('1pps need to move', move, ', that is ', move / 1e3, 'µs')
    if move > 0: worker.blockingInvoker(relatedAtomicServiceName).delay1PPS(move)

  class TF_TDCServer(TDCServer):
    def __init__(self, tdc, channelCount, funcStorePostProcessData, funcStoreRaw=None, funcFastProcess=None, funcStoreAdaptedRaw=None, funcTuneCH0=None):
      super().__init__(tdc, channelCount, funcStorePostProcessData, funcStoreRaw, funcFastProcess, funcStoreAdaptedRaw)
      self.dataBlockNumber = 0
      self.dopplerUtil = DopplerUtil(tagout=True)

      self.ch0Offset = 0
      self.ch0Tuned = False
      self.ch0DeltaValues = []
      self.latestCH1ForFast = None
      self.funcTuneCH0 = funcTuneCH0
      def ch0OffsetAdaptor(dataBlock):
        ch0 = []
        if dataBlock.sizes[1] > 0 and dataBlock.dataTimeEnd - dataBlock.dataTimeBegin > 500000000000:
          ch0 = np.linspace(0, 1000000000000, 25000, endpoint=False) + dataBlock.content[1][0]
        else:
          if dataBlock.sizes[1] > 0:
            self.latestCH1ForFast = dataBlock.content[1][0]
          if self.latestCH1ForFast:
            ch0 = np.linspace(0, 1000000000000, 25000, endpoint=False) + self.latestCH1ForFast
            ch0 = ch0[(ch0 >= dataBlock.dataTimeBegin) & (ch0 < dataBlock.dataTimeEnd)]
          
        dataBlock.content[0] = ch0
        return dataBlock

      def ch1OffsetAdaptor(dataBlock):
        if dataBlock.sizes[1] == 0: return dataBlock
        current1PPSTime = dataBlock.content[1][0]
        next25kTime = dataBlock.content[0][dataBlock.content[0] >= current1PPSTime]
        if len(next25kTime) == 0: return dataBlock
        dataBlock.content[1][0] += next25kTime[0] - current1PPSTime
        self.ch0Offset = int(next25kTime[0] - current1PPSTime)
        if not self.ch0Tuned and self.funcTuneCH0:
          self.ch0Tuned = True
        return dataBlock

      self.adaptors = [self.dopplerUtil.rescale, ch1OffsetAdaptor]

    def startDopplerShift(self, timestamp):
      if not isinstance(timestamp, int): raise ValueError('Doppler Shift should begin at Integer Second.')
      self.dopplerUtil.prepare(timestamp, 'Doppler_Timing.pkl')
      print(f'Doppler shift will be started at {datetime.fromtimestamp(self.dopplerUtil.startDopplerShiftAt)}')
    
    def getCH0Offset(self):
      return self.ch0Offset

    def getDopplerShiftTimeRange(self):
      begin = 0 if self.dopplerUtil.startDopplerShiftAt is None else self.dopplerUtil.startDopplerShiftAt
      return [begin, begin + len(self.dopplerUtil.timingMap) * 0.01]

  server = TF_TDCServer(tdc=st, channelCount=channelCount, funcStorePostProcessData=storePostProcessData, funcStoreRaw=storeRawData, funcStoreAdaptedRaw=storeAdaptedRawData, funcTuneCH0=tuneCH0)
  server.setDelays(defaultDelays)
  server.setPostProcessStatus(True)
  server.setRawDataStore((not isSim) and (rawStore))
  print(f'is store: {(not isSim) and (rawStore)}')
  # if isSim: server.startDopplerShift(int(datetime.now().timestamp()) + 20)

  worker = IFWorker(ifserver, serviceName, server, force=True)
  print('worker started')

  analysers = prepareAnalysers(workerRN, channelCount)
  for name in analysers.keys():
    server.installAnalyser(name, analysers[name])

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
    live.update(table)

  server.runtimeMetaMonitor = monitor
  live.start()

  server.start()
  print('server started')
