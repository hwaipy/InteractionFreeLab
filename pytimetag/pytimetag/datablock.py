__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

import math
import time
from random import Random
import msgpack
import numpy as np
from pytimetag.datablockserialJIT import serializeJIT, deserializeJIT
import numba
from multiprocessing.shared_memory import SharedMemory
from datetime import datetime

class DataBlock:
  FINENESS = 100000
  PROTOCOL_V1 = "DataBlock_V1"
  DEFAULT_PROTOCOL = PROTOCOL_V1

  @classmethod
  def create(cls, content, creationTime, dataTimeBegin, dataTimeEnd, resolution=1e-12):
    dataBlock = DataBlock(creationTime, dataTimeBegin, dataTimeEnd, [len(channel) for channel in content], resolution)
    dataBlock.content = content
    for i in range(len(dataBlock.content)):
      if isinstance(dataBlock.content[i], list):
        dataBlock.content[i] = np.array(dataBlock.content[i], dtype='<i8')
    return dataBlock

  @classmethod
  def generate(cls, generalConfig, channelConfig, seDer=False):
    creationTime = generalConfig['CreationTime'] if generalConfig.__contains__('Creationtime') else time.time() * 1000
    dataTimeBegin = generalConfig['DataTimeBegin'] if generalConfig.__contains__('DataTimeBegin') else 0
    dataTimeEnd = generalConfig['DataTimeEnd'] if generalConfig.__contains__('DataTimeEnd') else 0
    content = []
    for channel in range(16):
      channelData = []
      if channelConfig.__contains__(channel):
        config = channelConfig[channel]
        if config[0] == 'Period':
          count = config[1]
          period = (dataTimeEnd - dataTimeBegin) / count
          channelData = (np.linspace(0, count - 1, num=count) * period + dataTimeBegin).astype('<i8')
        elif config[0] == 'Random':
          channelData = np.random.randint(dataTimeBegin, dataTimeEnd, size=config[1], dtype='<i8')
          channelData.sort()
        elif config[0] == 'Pulse':
          pulseCount = config[1]
          eventCount = config[2]
          sigma = config[3]
          period = (dataTimeEnd - dataTimeBegin) / pulseCount
          pulseIndices = np.random.randint(0, pulseCount, size=eventCount)
          pulsePosition = np.random.normal(0, sigma, size=eventCount)
          channelData = (dataTimeBegin + pulseIndices * period + pulsePosition).astype('<i8')
          channelData.sort()
        else:
          raise RuntimeError('Bad mode')
      content.append(channelData)
    dataBlock = DataBlock.create(content, creationTime, dataTimeBegin, dataTimeEnd)
    if seDer:
      dataBlock = DataBlock.deserialize(dataBlock.serialize())
    return dataBlock

  @classmethod
  def deserialize(cls, data, partial=False):
    unpacker = msgpack.Unpacker(raw=False)
    unpacker.feed(data)
    recovered = unpacker.__next__()   # 50 ms
    protocol = recovered['Format']
    if protocol != cls.PROTOCOL_V1:
      raise RuntimeError("Data format not supported: {}".format(recovered("Format")))
    dataBlock = DataBlock(recovered['CreationTime'], recovered['DataTimeBegin'], recovered['DataTimeEnd'], recovered['Sizes'], recovered['Resolution'])
    dataBlock.__binaryRef = recovered['Content']
    if recovered.__contains__('ContentSerializedSizeSugggestion'):
      dataBlock.__binaryRefSizes = recovered['ContentSerializedSizeSugggestion']
    if not partial:
      dataBlock.unpack()    #     220 ms
    return dataBlock

  def __init__(self, creationTime, dataTimeBegin, dataTimeEnd, sizes, resolution=1e-12):
    self.creationTime = creationTime
    self.dataTimeBegin = dataTimeBegin
    self.dataTimeEnd = dataTimeEnd
    self.sizes = sizes
    self.resolution = resolution
    self.content = None
    self.__binaryRef = None
    self.__binaryRefSizes = None

  def release(self):
    self.content = None
    self.__binaryRef = None

  def isReleased(self):
    return self.content is None and self.__binaryRef is None

  def serialize(self, protocol=DEFAULT_PROTOCOL):
    if self.content is None:
      serializedContent = None
      sizeSuggestion = None
    else:
      serializedContent, sizeSuggestion = DataBlockSerializer.instance(protocol).serialize(self.content)
    result = {
        'Format': DataBlock.PROTOCOL_V1,
        'CreationTime': self.creationTime,
        'Resolution': self.resolution,
        'DataTimeBegin': self.dataTimeBegin,
        'DataTimeEnd': self.dataTimeEnd,
        'Sizes': self.sizes,
        'Content': serializedContent,
        'ContentSerializedSizeSugggestion': sizeSuggestion,
    }
    return msgpack.packb(result, use_bin_type=True)

  def convertResolution(self, resolution):
    ratio = self.resolution / resolution
    newDB = DataBlock(self.creationTime, int(
        self.dataTimeBegin * ratio), int(self.dataTimeEnd * ratio), self.sizes, resolution)
    if self.content is not None:
      newDB.content = []
      for ch in self.content:
        newDB.content.append((ch * ratio).astype('<i8'))
    else:
      newDB.content = None
    return newDB

  def synced(self, delays):
    sDB = DataBlock(self.creationTime, self.dataTimeBegin, self.dataTimeEnd, self.sizes, self.resolution)
    sDB.content = [self.content[i] + delays[i] for i in range(len(self.content))]
    return sDB

  def sharedMemory(self):
    sDB = DataBlockSharedMemory(self.creationTime, self.dataTimeBegin, self.dataTimeEnd, self.sizes, self.resolution)
    sDB.smContent = []
    for content in self.content:
      if len(content) == 0:
        sDB.smContent.append(None)
      else:
        sm = SharedMemory(create=True, size=content.nbytes)
        cpArray = np.ndarray(content.shape, dtype=content.dtype, buffer=sm.buf)
        cpArray[:] = content[:]
        sDB.smContent.append(sm)
    return sDB

  def unpack(self):
    if self.__binaryRef:
      # chDatas = self.__binaryRef
      # content = []
      # sizes = self.__binaryRefSizes
      # for chData in chDatas:
      #   recoveredChannel = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).deserialize(chData)
      #   content.append(recoveredChannel)
      self.content = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).deserialize(self.__binaryRef)
      self.__binaryRef = None

class DataBlockSharedMemory(DataBlock):
  def __init__(self, creationTime, dataTimeBegin, dataTimeEnd, sizes, resolution=1e-12):
    super().__init__(creationTime, dataTimeBegin, dataTimeEnd, sizes, resolution)
    self.smContent = None

  def __getattribute__(self, name):
    if name == 'content':
      contents = []
      for smContent in self.smContent:
        if smContent: contents.append(np.ndarray(int(smContent.size / 8), dtype='<i8', buffer=smContent.buf))
        else: contents.append(np.ndarray(0, dtype='<i8'))
      return contents
    return super().__getattribute__(name)

  def release(self):
    for smContent in self.smContent:
      if smContent: smContent.unlink()

class DataBlockSerializer:
  class DataBlockSerializerImp:
    def serialize(self, data, begin=None, end=None):
      raise RuntimeError('Not Implemented')

    def deserialize(self, data):
      raise RuntimeError('Not Implemented')

  class PV1DBS_JIT(DataBlockSerializerImp):
    def __init__(self):
      self.MAX_VALUE = 1e16

    def serialize(self, contents):
      serializedContentOriginal, sizeSuggestionOriginal = serializeJIT(numba.typed.List(contents), DataBlock.FINENESS)
      serializedContent = []
      sizeSuggestion = []
      for ch in serializedContentOriginal:
        if len(ch[0]) == 0: serializedContent.append([])
        else: serializedContent.append([bytes(d) for d in ch])
      for ch in sizeSuggestionOriginal: sizeSuggestion.append([] if ch == [0] else ch)
      return serializedContent, sizeSuggestion

    def deserialize(self, datas):
      reorgnizedList = []
      for data in datas:
        if len(data) == 0:
          reorgnizedList.append(numba.typed.List([np.ndarray(shape=(0,), dtype='int8', buffer=b'')]))
        else:
          reorgnizedList.append(numba.typed.List([np.ndarray(shape=(len(d),), dtype='int8', buffer=d) for d in data]))
      content = deserializeJIT(numba.typed.List(reorgnizedList))
      return content

  # class PV1DBS_Native(DataBlockSerializerImp):
  #   def __init__(self):
  #     self.MAX_VALUE = 1e16

  #   def serialize(self, data, begin=None, end=None):
  #     if len(data) == 0:
  #       return b''
  #     return serializeNative(data, 0 if begin is None else begin, len(data) if end is None else end)

  #   def deserialize(self, data):
  #     if len(data) == 0:
  #       return []
  #     return deserializeNative(data)

  DBS = {DataBlock.PROTOCOL_V1: PV1DBS_JIT()}

  @classmethod
  def instance(cls, name):
    return cls.DBS[name]

def serialize(data):
  if len(data) == 0:
    return b''
  buffer = bytearray(data[0].to_bytes(8, byteorder='big', signed=True))
  unitSize = 15
  unit = bytearray([0] * (unitSize + 1))
  hasHalfByte = False
  halfByte = 0
  i = 0
  while (i < len(data) - 1):
    delta = (data[i + 1] - data[i])
    i += 1
    value = delta
    length = 0
    keepGoing = True
    valueBase = 0 if delta >= 0 else -1
    while (keepGoing):
      unit[unitSize - length] = value & 0xf
      value >>= 4
      length += 1
      if value == valueBase:
        keepGoing = ((unit[unitSize - length + 1] & 0x8) == (0x8 if delta >= 0 else 0x0))
      elif length >= unitSize:
        keepGoing = False

    unit[unitSize - length] = length
    p = 0
    while p <= length:
      if hasHalfByte:
        buffer.append(((halfByte << 4) | unit[unitSize - length + p]))
      else:
        halfByte = unit[unitSize - length + p]
      hasHalfByte = not hasHalfByte
      p += 1
  if (hasHalfByte):
    buffer.append(halfByte << 4)
  return bytes(buffer)

if __name__ == '__main__':
  print('DataBlock')

  numba.set_num_threads(10)

  import numpy as np
  import time

  testDataBlock = DataBlock.generate(
    {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
    {
      0: ['Period', 12345678],
      # 1: ['Period', 1234568],
      # 2: ['Period', 1234578],
      # 3: ['Period', 1234678],
      # 4: ['Period', 1235678],
      # 5: ['Period', 1234568],
      # 6: ['Period', 1234578],
      # 7: ['Period', 1234678],
      # 8: ['Period', 1235678],
      # 9: ['Period', 1245678],
    }
  )

  binary = testDataBlock.serialize()
  DataBlock.deserialize(binary)
  t1 = time.time()
  binary = testDataBlock.serialize()
  t2 = time.time()
  recovered = DataBlock.deserialize(binary)
  t3 = time.time()
  print(t2 - t1, t3 - t2)


  # bs = bytearray(100)
  # a = np.ndarray(shape=(100,), dtype='int8', buffer=bs)
  # print(a.shape)