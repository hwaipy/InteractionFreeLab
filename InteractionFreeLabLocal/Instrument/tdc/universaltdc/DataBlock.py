# import time
# from random import Random
# import pickle
# from functional import seq
# import math
# import msgpack
# import numpy as np
# import numba
#
# class DataBlock:
#     FINENESS = 100000
#     PROTOCOL_V1 = "DataBlock_V1"
#     DEFAULT_PROTOCOL = PROTOCOL_V1
#
#     @classmethod
#     def create(cls, content, creationTime, dataTimeBegin, dataTimeEnd, resolution=1e-12):
#         dataBlock = DataBlock(creationTime, dataTimeBegin, dataTimeEnd, [len(channel) for channel in content], resolution)
#         dataBlock.content = content
#         return dataBlock
#
#     @classmethod
#     def generate(cls, generalConfig, channelConfig):
#         creationTime = generalConfig['CreationTime'] if generalConfig.__contains__('Creationtime') else time.time() * 1000
#         dataTimeBegin = generalConfig['DataTimeBegin'] if generalConfig.__contains__('DataTimeBegin') else 0
#         dataTimeEnd = generalConfig['DataTimeEnd'] if generalConfig.__contains__('DataTimeEnd') else 0
#         content = []
#         for channel in range(16):
#             channelData = []
#             if channelConfig.__contains__(channel):
#                 config = channelConfig[channel]
#                 if config[0] == 'Period':
#                     count = config[1]
#                     period = (dataTimeEnd - dataTimeBegin) / count
#                     channelData = [int(i * period) for i in range(count)]
#                 elif config[0] == 'Random':
#                     count = config[1]
#                     averagePeriod = (dataTimeEnd - dataTimeBegin) / count
#                     rnd = Random()
#                     randomGaussians = [(1 + rnd.gauss(0, 1) / 3) * averagePeriod for i in range(count)]
#                     randGaussSumRatio = (dataTimeEnd - dataTimeBegin) / sum(randomGaussians)
#                     randomDeltas = [rg * randGaussSumRatio for rg in randomGaussians]
#                     times = []
#                     suma = dataTimeBegin
#                     for delta in randomDeltas:
#                         suma += delta
#                         times.append(int(suma))
#                     channelData = times
#                 elif config[0] == 'Pulse':
#                     print('is Pulse')
#                     raise RuntimeError('Not Imped')
#                     #               val pulseCount: Int = config(1)
#                     #               val eventCount: Int = config(2)
#                     #               val sigma: Double = config(3)
#                     #               val period = (dataTimeEnd - dataTimeBegin) / pulseCount
#                     #               val random = new Random()
#                     #               Range(0, eventCount).toArray.map(_ => random.nextInt(pulseCount) * period + (random.nextGaussian() * sigma).toLong).sorted
#                 else:
#                     raise RuntimeError('Bad mode')
#             content.append(channelData)
#         return DataBlock.create(content, creationTime, dataTimeBegin, dataTimeEnd)
#
#     @classmethod
#     def deserialize(cls, data):
#         unpacker = msgpack.Unpacker(raw=False)
#         unpacker.feed(data)
#         recovered = unpacker.__next__()
#         protocol = recovered['Format']
#         if protocol != cls.PROTOCOL_V1: raise RuntimeError("Data format not supported: {}".format(recovered("Format")))
#         sizes = recovered['Sizes']
#         dataBlock = DataBlock(recovered['CreationTime'], recovered['DataTimeBegin'], recovered['DataTimeEnd'], sizes, recovered['Resolution'])
#         chDatas = recovered['Content']
#         if chDatas is not None:
#             content = []
#             for chData in chDatas:
#                 recoveredChannel = []
#                 for section in chData:
#                     recoveredChannel += DataBlockSerializer.instance(protocol).deserialize(section)
#                 content.append(recoveredChannel)
#             dataBlock.content = content
#         else:
#             dataBlock.content = None
#         return dataBlock
#
#     def __init__(self, creationTime, dataTimeBegin, dataTimeEnd, sizes, resolution=1e-12):
#         self.creationTime = creationTime
#         self.dataTimeBegin = dataTimeBegin
#         self.dataTimeEnd = dataTimeEnd
#         self.sizes = sizes
#         self.resolution = resolution
#         self.content = None
#
#     def release(self):
#         self.content = None
#
#     def isReleased(self):
#         return self.content is None
#
#     def serialize(self, protocol=DEFAULT_PROTOCOL):
#         if self.content is None:
#             serializedContent = None
#         else:
#             serializedContent = []
#             for ch in self.content:
#                 sectionNum = math.ceil(len(ch) / DataBlock.FINENESS)
#                 channelSC = []
#                 for i in range(sectionNum):
#                     dataSection = ch[i * DataBlock.FINENESS: (i + 1) * DataBlock.FINENESS]
#                     channelSC.append(DataBlockSerializer.instance(protocol).serialize(dataSection))
#                 serializedContent.append(channelSC)
#         result = {
#             "Format": DataBlock.PROTOCOL_V1,
#             "CreationTime": self.creationTime,
#             "Resolution": self.resolution,
#             "DataTimeBegin": self.dataTimeBegin,
#             "DataTimeEnd": self.dataTimeEnd,
#             "Sizes": self.sizes,
#             "Content": serializedContent
#         }
#         return msgpack.packb(result, use_bin_type=True)
#
#     def convertResolution(self, resolution):
#         ratio = self.resolution / resolution
#         newDB = DataBlock(self.creationTime, int(self.dataTimeBegin * ratio), int(self.dataTimeEnd * ratio), self.sizes, resolution)
#         if self.content is not None:
#             newDB.content = []
#             for ch in self.content:
#                 newDB.content.append([int(d * ratio) for d in ch])
#         else:
#             newDB.content = None
#         return newDB
#
#
# class DataBlockSerializer:
#     class DataBlockSerializerImp:
#         def serialize(self, data):
#             raise RuntimeError('Not Implemented')
#
#         def deserialize(self, data):
#             raise RuntimeError('Not Implemented')
#
#     class PV1DBS(DataBlockSerializerImp):
#         def __init__(self):
#             self.MAX_VALUE = 1e16
#
#         def serialize(self, data):
#             return serializeJIT(np.array(data))
#
#             # if len(data) == 0:
#             #     return b''
#             # buffer = bytearray(data[0].to_bytes(8, byteorder='big', signed=True))
#             # unitSize = 15
#             # unit = bytearray([0] * (unitSize + 1))
#             # hasHalfByte = False
#             # halfByte = 0
#             # i = 0
#             # while (i < len(data) - 1):
#             #     delta = (data[i + 1] - data[i])
#             #     i += 1
#             #     if (delta > self.MAX_VALUE or delta < -self.MAX_VALUE):
#             #         raise RuntimeError("The value to be serialized exceed MAX_VALUE: {}".format(delta))
#             #     value = delta
#             #     length = 0
#             #     keepGoing = True
#             #     valueBase = 0 if delta >= 0 else -1
#             #     while (keepGoing):
#             #         unit[unitSize - length] = value & 0xf
#             #         value >>= 4
#             #         length += 1
#             #         if value == valueBase:
#             #             keepGoing = ((unit[unitSize - length + 1] & 0x8) == (0x8 if delta >= 0 else 0x0))
#             #         elif length >= unitSize:
#             #             keepGoing = False
#
#             #     unit[unitSize - length] = length
#             #     p = 0
#             #     while p <= length:
#             #         if hasHalfByte:
#             #             buffer.append(((halfByte << 4) | unit[unitSize - length + p]))
#             #         else:
#             #             halfByte = unit[unitSize - length + p]
#             #         hasHalfByte = not hasHalfByte
#             #         p += 1
#             # if (hasHalfByte):
#             #     buffer.append(halfByte << 4)
#             # return bytes(buffer)
#
#         def deserialize(self, data):
#             if len(data) == 0:
#                 return []
#             offset = int.from_bytes(data[:8], byteorder='big', signed=True)
#             longBuffer = [offset]
#             previous = offset
#
#             positionC = 8
#             positionF = 0
#
#             def hasNext():
#                 return positionC < len(data)
#
#             def getNext():
#                 nonlocal positionC, positionF
#                 b = data[positionC]
#                 if positionF == 0:
#                     positionF = 1
#                     return (b >> 4) & 0xf
#                 else:
#                     positionF = 0
#                     positionC += 1
#                     return b & 0xf
#
#             while (hasNext()):
#                 length = getNext() - 1
#                 if length >= 0:
#                     value = (getNext() & 0xf)
#                     if (value & 0x8) == 0x8:
#                         value |= -16
#                     while length > 0:
#                         value <<= 4
#                         value |= (getNext() & 0xf)
#                         length -= 1
#                     previous += value
#                     longBuffer.append(previous)
#
#             return longBuffer
#
#     DBS = {DataBlock.PROTOCOL_V1: PV1DBS()}
#
#     @classmethod
#     def instance(cls, name):
#         return cls.DBS[name]
#
#
# @numba.jit(nopython=True)
# def serializeJIT(data):
#     buffer = numba.float32[:]
#     # if len(data) == 0:
#     #     return b''
#     # bytearray(data[0].to_bytes(8, byteorder='big', signed=True))
#     # unitSize = 15
#     # unit = bytearray([0] * (unitSize + 1))
#     # hasHalfByte = False
#     # halfByte = 0
#     # i = 0
#     # while (i < len(data) - 1):
#     #     delta = (data[i + 1] - data[i])
#     #     i += 1
#     #     if (delta > self.MAX_VALUE or delta < -self.MAX_VALUE):
#     #         raise RuntimeError("The value to be serialized exceed MAX_VALUE: {}".format(delta))
#     #     value = delta
#     #     length = 0
#     #     keepGoing = True
#     #     valueBase = 0 if delta >= 0 else -1
#     #     while (keepGoing):
#     #         unit[unitSize - length] = value & 0xf
#     #         value >>= 4
#     #         length += 1
#     #         if value == valueBase:
#     #             keepGoing = ((unit[unitSize - length + 1] & 0x8) == (0x8 if delta >= 0 else 0x0))
#     #         elif length >= unitSize:
#     #             keepGoing = False
#
#     #     unit[unitSize - length] = length
#     #     p = 0
#     #     while p <= length:
#     #         if hasHalfByte:
#     #             buffer.append(((halfByte << 4) | unit[unitSize - length + p]))
#     #         else:
#     #             halfByte = unit[unitSize - length + p]
#     #         hasHalfByte = not hasHalfByte
#     #         p += 1
#     # if (hasHalfByte):
#     #     buffer.append(halfByte << 4)
#     # return bytes(buffer)
#     pass