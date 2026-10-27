import time
from interactionfreepy import IFWorker, IFException
import msgpack
import sys
import numpy as np
import numba
from pytimetag import DataBlock
from threading import Thread, Lock
import math
from queue import Queue
from datetime import datetime

def benchMarker():
  conbinerByChannel = TimeTagDataStreamConbiner(splitBy=1, queueSize=15)
  stream = dataSreamGenerator({
      0: ['Period', 25000], 1: ['Period', 1],
      2: ['Pulse', 100000000, 1000000, 1000], 3: ['Pulse', 100000000, 1000000, 1000],
      4: ['Pulse', 100000000, 1000000, 1000], 5: ['Pulse', 100000000, 1000000, 1000]})
  datas = [stream.getData() for i in range(5000)]

  for data in datas[:2000]:
    channels = data.getChannels()
    timestamps = data.getTimestamps()
    newDB = conbinerByChannel.deal(timestamps, channels)

  t1 = time.time()
  for data in datas[2000:]:
    channels = data.getChannels()
    timestamps = data.getTimestamps()
    newDB = conbinerByChannel.deal(timestamps, channels)
    if newDB:
      print(newDB)
  t2 = time.time()
  print(t2 - t1)

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
      db = DataBlock.generate({'CreationTime': time.time(), 'DataTimeBegin': self.beginTime, 'DataTimeEnd': self.beginTime + 1000000000000}, config)
      self.beginTime += 1000000000000
      self.__buffer = np.hstack([self.__buffer[self.__bufferPosition:]] + [db.content[i] * 16 + i for i in range(len(db.content)) if db.content[i].shape[0] > 0])
      self.__buffer = np.sort(self.__buffer)
      self.__bufferPosition = 0

    def isRunning(self):
      return True

    def getData(self, count=100000):
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
    self._durationLock = Lock()
    self._pendingRange = None
    self._sectionBegin = None

  def __searchForSplit(self, timestamps, channels):
    p = np.where(channels == self.splitBy)[0]
    if len(p) > 0:
      if self.splitDataTime is None:
        self.splitDataTime = [timestamps[p[0]]]
      else:
        self.splitDataTime = [self.splitDataTime[-1], timestamps[p[0]]]
      return p[0]
    return None

  def deal(self, timestamps, channels):
    if self.splitBy is None:
      return self._dealTimeRanged(timestamps, channels)
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
        dataTimeBegin = self.splitDataTime[0]
        dataTimeEnd = self.splitDataTime[1]
        self.dataBlockQueue.put(DataBlock.create(generateDataBlockContent(ts, cs), self.currentSectionStart, int(dataTimeBegin), int(dataTimeEnd)))
        newDB = True
        if self.dataBlockQueue.qsize() > self.queueSize:
          self.dataBlockQueue.get()

        self.timestampsBuffer = [timestamps[splitPoint:]]
        self.channelsBuffer = [channels[splitPoint:]]
      self.currentSectionStart = time.time()
      return newDB

  def setBlockDuration(self, seconds):
    if self.splitBy is not None:
      raise RuntimeError('Runtime duration applies only to time-based blocks')
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
      raise ValueError('Block duration must be a number in seconds')
    if not math.isfinite(seconds) or not 0.001 <= seconds <= 1.0:
      raise ValueError('Realtime block duration must be between 0.001 and 1.0 seconds')
    duration = int(round(seconds * 1e12))
    with self._durationLock:
      if self._sectionBegin is None:
        self.splitDataRange = duration
      else:
        # Last request wins; requesting the active duration cancels an update.
        self._pendingRange = None if duration == self.splitDataRange else duration
      return self._status()

  def _status(self):
    return {'ActiveSeconds': self.splitDataRange / 1e12,
            'PendingSeconds': None if self._pendingRange is None else self._pendingRange / 1e12}

  def getBlockStatus(self):
    if self.splitBy is not None:
      raise RuntimeError('Runtime duration applies only to time-based blocks')
    with self._durationLock:
      return self._status()

  def _dealTimeRanged(self, timestamps, channels):
    if len(timestamps) == 0:
      return False
    with self._durationLock:
      if self._sectionBegin is None:
        self._sectionBegin = int(timestamps[0])
        self.splitDataTime = self._sectionBegin + self.splitDataRange
        self.timestampsBuffer, self.channelsBuffer = [], []
        self.currentSectionStart = time.time()
    position = 0
    emitted = False
    # An input batch can cross several windows, especially after shortening.
    while self.splitDataTime <= timestamps[-1]:
      end = self.splitDataTime
      splitPoint = int(np.searchsorted(timestamps, end, side='left'))
      ts = numba.typed.List(self.timestampsBuffer + [timestamps[position:splitPoint]])
      cs = numba.typed.List(self.channelsBuffer + [channels[position:splitPoint]])
      block = DataBlock.create(generateDataBlockContent(ts, cs), self.currentSectionStart,
                               self._sectionBegin, end)
      self.dataBlockQueue.put(block)
      if self.dataBlockQueue.qsize() > self.queueSize:
        self.dataBlockQueue.get()
      emitted = True
      self.timestampsBuffer, self.channelsBuffer = [], []
      position = splitPoint
      with self._durationLock:
        self._sectionBegin = end
        if self._pendingRange is not None:
          self.splitDataRange = self._pendingRange
          self._pendingRange = None
        self.splitDataTime = end + self.splitDataRange
      self.currentSectionStart = time.time()
    self.timestampsBuffer.append(timestamps[position:])
    self.channelsBuffer.append(channels[position:])
    return emitted

@numba.njit(cache=True)
def find_first(arr, target):
    for i in range(arr.size):
        if arr[i] == target:
            return i
    return -1

class SwabianTimeTag:
  def __init__(self, sn, splitBy, splitIn=100000000000):
    self.sn = sn
    self.splitBy = splitBy
    self.isSim = sn == 'SIM'
    self.bufferSize = int(10e6)
    self.stream = None
    # self.dealTime = 0
    # self.dealTimes = [0] * 4
    self.conbinerByTime = TimeTagDataStreamConbiner(splitBy=None, timeRange=splitIn, queueSize=150)
    self.conbinerByChannel = None if self.splitBy is None else TimeTagDataStreamConbiner(splitBy=splitBy, queueSize=15)

    if not self.isSim:
      import TimeTagger
      print(TimeTagger.scanTimeTagger())
      self.tagger = TimeTagger.createTimeTagger(sn)

  def start(self, config={}):
    if self.isSim:
      self.stream = dataSreamGenerator(config)
    else:
      import TimeTagger
      self.stream = TimeTagger.TimeTagStream(tagger=self.tagger, n_max_events=self.bufferSize, channels=[i for i in range(1, 9, 1)])
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
          channels = data.getChannels() - 1
          timestamps = data.getTimestamps()
          idx = find_first(channels, 1)
          if idx >= 0:
            has1pps = True
            dt = datetime.now()
            # print(f'A 1pps signal received at {dt}')

          self.conbinerByTime.deal(timestamps, channels)
          newDB = False
          if self.conbinerByChannel:
            newDB = self.conbinerByChannel.deal(timestamps, channels)

          # t4 = time.time()
          # self.dealTime += t4 - t1
          # if newDB:
          #   self.dealTime = 0
        time.sleep(0.001)
    except BaseException as e:
      import traceback
      traceback.format_exc(e)

  def setTriggerLevel(self, channel, triggerLevel):
    print('set trigger level', channel, triggerLevel)
    self.tagger.setTriggerLevel(channel, triggerLevel)

  def setDeadtime(self, channel, deadtime):
    self.tagger.setDeadtime(channel, deadtime)


if __name__ == '__main__':
  benchMarker()
  sys.exit()

  isSim = True

  hasEnoughParameters = len(sys.argv) >= 6
  ifserver = sys.argv[1] if hasEnoughParameters else 'tcp://10.1.3.1:1061'
  sn = sys.argv[2] if hasEnoughParameters else '1947000s70'
  triggerLevelsStr = sys.argv[3] if hasEnoughParameters else '0.5,0.5,0.07,0.08,0.08,0.07,0.5,0.5'
  deadtime = int(sys.argv[4]) if hasEnoughParameters else 60000
  server = sys.argv[5] if hasEnoughParameters else 'TF_SwabianTDCAdapter'

  st = SwabianTimeTag('SIM' if isSim else sn, 1)
  triggerLevels = [float(s) for s in triggerLevelsStr.split(',')]
  forever = True

  if not isSim:
    for i in range(len(triggerLevels)):
      st.setTriggerLevel(i, triggerLevels[i])
      st.setDeadtime(i, deadtime)

  st.start({
        0: ['Period', 25000], 1: ['Period', 1], 
        2: ['Pulse', 100000000, 1000000, 1000], 3: ['Pulse', 100000000, 1000000, 1000], 
        4: ['Pulse', 100000000, 1000000, 1000], 5: ['Pulse', 100000000, 1000000, 1000]})