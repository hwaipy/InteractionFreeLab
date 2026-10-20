import numba
import numpy as np


@numba.njit(parallel=True, cache=True)
def serializeJIT(contents, fineness):
  serializedContent = [[np.zeros(0, dtype='int8')] for ch in range(len(contents))]
  sizeSuggestion = [[0] for ch in range(len(contents))]
  for channel in numba.prange(len(contents)):
    content = contents[channel]
    if len(content) != 0:
      sectionNum = int(np.ceil(len(content) / fineness))
      channelSC = [np.zeros(0, dtype='int8') for i in range(sectionNum)]
      sizes = [0] * sectionNum
      for i in range(sectionNum):
        begin = int(i * fineness)
        end = int((i + 1) * fineness)
        if end > len(content): end = len(content)
        sizes[i] = end - begin
        buffer = serializeSectionJIT(content, begin, end)
        channelSC[i] = buffer
    else:
      channelSC = [np.zeros(0, dtype='int8')]
      sizes = [0]
    serializedContent[channel] = channelSC
    sizeSuggestion[channel] = sizes
  return serializedContent, sizeSuggestion


# @numba.njit(parallel=True, cache=True)
# def serializeJIT(data, fineness):
#   sectionNum = int(np.ceil(len(data) / fineness))
#   result = [np.zeros(0, dtype='int8') for i in range(sectionNum)]
#   sizes = [0] * sectionNum
#   for i in numba.prange(sectionNum):
#     begin = int(i * fineness)
#     end = int((i + 1) * fineness)
#     if end > len(data): end = len(data)
#     sizes[i] = end - begin
#     buffer = serializeSectionJIT(data, begin, end)
#     result[i] = buffer
#   return result, sizes

@numba.njit(cache=True)
def serializeSectionJIT(data, begin, end):
  head = data[begin]
  buffer = np.zeros((end - begin) * 8, dtype='int8')
  for i in range(8):
    buffer[7 - i] = (head & 0xFF)
    head >>= 8
  unitSize = 15
  unit = np.zeros(16, dtype='int8')
  hasHalfByte = False
  halfByte = 0
  pBuffer = 8
  i = begin
  while (i < end - 1):
    delta = (data[i + 1] - data[i])
    i += 1
    if (delta > 1e16 or delta < -1e16):
      return np.zeros(0, dtype='int8')
    value = delta
    length = 0
    valueBase = 0 if delta >= 0 else -1
    for j in range(unitSize):
      unit[unitSize - length] = value & 0xf
      value >>= 4
      length += 1
      if value == valueBase and not ((unit[unitSize - length + 1] & 0x8) == (0x8 if delta >= 0 else 0x0)):
        break
    unit[unitSize - length] = length
    p = 0
    while p <= length:
      if hasHalfByte:
        buffer[pBuffer] = ((halfByte << 4) | unit[unitSize - length + p])
        pBuffer += 1
      else:
        halfByte = unit[unitSize - length + p]
      hasHalfByte = not hasHalfByte
      p += 1
  if hasHalfByte:
    buffer[pBuffer] = (halfByte << 4)
    pBuffer += 1
  return buffer[:pBuffer]


@numba.njit(parallel=True, cache=True)
def deserializeJIT(contents):
  result = [np.zeros(0, dtype='<i8') for i in range(len(contents))]
  for i in numba.prange(len(contents)):
    datas = contents[i]
    totalSize = sum([len(ch) for ch in datas])
    buffer = np.zeros(int(totalSize/2), dtype='<i8')
    pBuffer = 0
    for data in datas:
      pBuffer = deserializeSectionJIT(data, buffer, pBuffer)
    result[i] = buffer[:pBuffer]
  return result

@numba.njit(cache=True)
def deserializeSectionJIT(data, buffer, pBuffer):
  if len(data) > 0:
    offset = 0
    offset += data[0]
    if data[0] < 0: offset += 256
    for i in range(7):
      offset <<= 8
      offset += data[i + 1]
      if data[i + 1] < 0: offset += 256
    buffer[pBuffer] = offset
    pBuffer += 1
    previous = offset

    positionC = 8
    pre = 1

    def hasNext():
      return positionC < len(data)

    def getNext(pre):
      nonlocal positionC
      b = data[positionC]
      if pre:
        return (b >> 4) & 0x0f
      else:
        positionC += 1
        return b & 0x0f

    while (hasNext()):
      length = getNext(pre) - 1
      pre = 1 - pre
      if length >= 0:
        value = (getNext(pre) & 0xf)
        pre = 1 - pre
        if (value & 0x8) == 0x8:
          value |= -16
        while length > 0:
          value <<= 4
          value |= (getNext(pre) & 0xf)
          pre = 1 - pre
          length -= 1
        previous += value
        buffer[pBuffer] = previous
        pBuffer += 1
  return pBuffer
