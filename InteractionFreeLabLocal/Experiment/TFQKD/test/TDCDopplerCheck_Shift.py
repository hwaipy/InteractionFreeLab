from pytimetag import DataBlock
import os
import numpy as np
import numba
import math
import pickle
import time

with open('/home/coder/project/interactionfreelab/InteractionFreeLabLocal/Experiment/TFQKD/test/Doppler_Timing.pkl', 'rb') as file:
    dopplerTimings = pickle.load(file)
expectFrequencies = np.array(dopplerTimings['f'])[:-1]

timingMap = [] # 左边多普勒前，右边多普勒后
expectedWavenumbers = [0]
for f in expectFrequencies:
  expectedWavenumbers.append(expectedWavenumbers[-1] + f * 0.01)
expectedWavenumbers = np.array(expectedWavenumbers)
for i in range(len(expectedWavenumbers) - 1):
  pulseIndex = math.ceil(expectedWavenumbers[i])
  expTiming = pulseIndex * 100000
  actTiming = int((i * 0.01 + (pulseIndex - expectedWavenumbers[i]) / expectFrequencies[i]) * 1e12)
  timingMap.append([expTiming, actTiming])
timingMap = np.array(timingMap)

dir = '/home/coder/project/data/shift'
filenames = [f for f in os.listdir(dir) if f.endswith('.datablock')]
filenames.sort()


sizes = np.zeros((16,), dtype='int64')

firstEntry = None
lastEntry = None

dopplerTimingsF = expectFrequencies
dopplerShiftTimeStep = 0.01
dopplerShiftFs = np.array(dopplerTimingsF) / 10000000
dopplerShiftTimings = [0]
for i in range(len(dopplerShiftFs)):
    delta = dopplerShiftTimeStep / dopplerShiftFs[i] + dopplerShiftTimings[-1]
    dopplerShiftTimings.append(delta)
dopplerShiftTimings = np.array(dopplerShiftTimings) * 1e12
startDopplerShiftAt = 0
startDopplerShiftAtPS = 0

@numba.njit(cache=True)
def mapping(timings, timeStep, secondIndex, beginTime, endTime, events):
  mappedEvents = np.zeros(shape=events.shape, dtype=events.dtype)
  validEventCount = 0
  for event in events:
    timeFromStart = (event - beginTime) / 1000000000000 + secondIndex
    m_i = int(timeFromStart / timeStep)
    m_a = timings[m_i]
    m_b = timings[m_i + 1]
    mappedTime = m_a + (m_b - m_a) / timeStep * (timeFromStart - timeStep * m_i)
    mappedEvent = int((mappedTime - secondIndex) * 1000000000000 + beginTime)
    # print(m_i, m_a, m_b, timeFromStart, timeStep * m_i, mappedTime, mappedEvent)
    if mappedEvent >= beginTime and mappedEvent <= endTime:
      mappedEvents[validEventCount] = mappedEvent
      validEventCount += 1
  return mappedEvents[:validEventCount]

@numba.njit(cache=True)
def mapping_rev(timings, timeStep, secondIndex, beginTime, endTime, events):
  if len(events) > 1: assert (np.all(events[1:] - events[:-1] > 0))
  mappedEvents = np.zeros(shape=events.shape, dtype=events.dtype)
  validEventCount = 0
  m_p = 0
  for event in events:
    timeFromStart = (event - beginTime) / 1000000000000 + secondIndex
    while m_p < len(timings) - 1 and timings[m_p + 1] <= timeFromStart: m_p += 1
    if m_p >= len(timings) - 1: break
    m_a = timings[m_p]
    m_b = timings[m_p + 1]
    mappedTime = (timeFromStart - m_a) / (m_b - m_a) * timeStep + timeStep * m_p
    mappedEvent = int((mappedTime - secondIndex) * 1000000000000 + beginTime)
    if mappedEvent >= beginTime and mappedEvent <= endTime:
      mappedEvents[validEventCount] = mappedEvent
      validEventCount += 1
  return mappedEvents[:validEventCount]

@numba.njit(cache=True)
def mapping_rev2(timings, timeStep, dopplerShiftBeginPS, beginTime, endTime, events):
  if len(events) > 1: assert (np.all(events[1:] - events[:-1] > 0))
  mappedEvents = np.zeros(shape=events.shape, dtype=events.dtype)
  validEventCount = 0
  m_p = 0
  for event in events:
    timeFromStart = (event - dopplerShiftBeginPS)
    while m_p < len(timings) - 1 and timings[m_p + 1] <= timeFromStart: m_p += 1
    if m_p >= len(timings) - 1: break
    m_a, m_b = timings[m_p], timings[m_p + 1]
    mappedTime = ((timeFromStart - m_a) / (m_b - m_a) + m_p) * timeStep
    mappedEvent = int(mappedTime + dopplerShiftBeginPS)
    if mappedEvent >= beginTime and mappedEvent <= endTime:
      mappedEvents[validEventCount] = mappedEvent
      validEventCount += 1
  return mappedEvents[:validEventCount]

def dopplerReshapingAdaptor(dataBlock):
    dopplerShiftBegin = startDopplerShiftAt
    dopplerShiftDuration = dopplerShiftTimeStep * (len(dopplerShiftFs) - 1)
    dopplerShiftEnd = dopplerShiftBegin + dopplerShiftDuration
    dataBlockBeginTime = int(dataBlock.creationTime + 0.5)

    if dataBlockBeginTime < dopplerShiftBegin or dataBlockBeginTime >= dopplerShiftEnd: 
        raise BaseException('Useless')

    # print(f'Performing Doppler Shift @ second {dataBlockBeginTime - dopplerShiftBegin}.')
    content = dataBlock.content
    newContents = []
    newContents.append(content[0].copy())
    newContents.append(content[1].copy())
    for i in range(2, len(content)):
      if len(content[i]) > 0:
        # print(f'dopplerShiftBegin = {dopplerShiftBegin}')
        # newContent = mapping_rev(dopplerShiftTimings, dopplerShiftTimeStep, dataBlockBeginTime - dopplerShiftBegin, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, content[i])
        newContent = mapping_rev2(dopplerShiftTimings, dopplerShiftTimeStep * 1e12, startDopplerShiftAtPS, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, content[i])
        newContents.append(newContent)
      else:
        newContents.append(np.zeros(shape=(0,), dtype=content[i].dtype))


    newDataBlock = DataBlock.create(newContents, dataBlock.creationTime, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, dataBlock.resolution)

    return newDataBlock

# with open(f'{dir}/{filenames[0]}', 'rb') as file:
#   data = file.read()
#   db = DataBlock.deserialize(data)
#   startDopplerShiftAt = db.creationTime
#   startDopplerShiftAtPS = db.dataTimeBegin

# frequencies = []

# ch5total = []

# for i in range(3, 5):
#   filename = filenames[i]
#   print(i)
#   with open(f'{dir}/{filename}', 'rb') as file:
#     data = file.read()
#     db = DataBlock.deserialize(data)
#     ch0 = db.content[0]
#     freqScale = (ch0[-1] - ch0[0]) / (ch0.size - 1) * 25000 / 1e12
#     ch5 = ((db.content[5] - db.content[1][0]) / freqScale + i * 1e12).astype('int64')
#     ch5total.append(ch5)
# ch5total = np.hstack(ch5total)

def mapTiming(tLeft, timingMap):
  for ie in range(len(timingMap) - 1):
    tLeft1, tRight1 = timingMap[ie]
    tLeft2, tRight2 = timingMap[ie + 1]
    if tLeft < tLeft1: return math.nan
    if tLeft > tLeft2: continue
    return (tLeft - tLeft1) / (tLeft2 - tLeft1) * (tRight2 - tRight1) + tRight1

def mapTiming_rev(tRight, timingMap):
  for ie in range(len(timingMap) - 1):
    tLeft1, tRight1 = timingMap[ie]
    tLeft2, tRight2 = timingMap[ie + 1]
    if tRight < tRight1: return math.nan
    if tRight > tRight2: continue
    return (tRight - tRight1) / (tRight2 - tRight1) * (tLeft2 - tLeft1) + tLeft1

@numba.njit(cache=True)
def mapTiming_rev_array(tRights, timingMap):
  if len(tRights) > 1: assert (np.all(tRights[1:] - tRights[:-1] > 0))
  tLefts = np.zeros(shape=tRights.shape, dtype=tRights.dtype)
  validTLeftCount = 0
  m_p = 0
  for tRight in tRights:
    if m_p < len(timingMap) - 1 and timingMap[m_p][1] > tRight: continue
    while m_p < len(timingMap) - 1 and timingMap[m_p + 1][1] <= tRight: m_p += 1
    if m_p >= len(timingMap) - 1: break
    tLeft1, tRight1 = timingMap[m_p]
    tLeft2, tRight2 = timingMap[m_p + 1]
    tLeft = (tRight - tRight1) / (tRight2 - tRight1) * (tLeft2 - tLeft1) + tLeft1
    tLefts[validTLeftCount] = tLeft
    validTLeftCount += 1
  return tLefts[:validTLeftCount]

def delta(ch5, timingMap, offset):
  diffs = []
  for e in timingMap:
    pulseIndex, timing = e
    pulseIndex //= 100000
    if pulseIndex + offset >= 0 and pulseIndex + offset < ch5.size:
      diff = ch5[pulseIndex + offset] - timing
      diffs.append(diff)
  diffs = np.array(diffs)
  # print(diffs - np.average(diffs))
  print(np.max(diffs - np.average(diffs)), np.min(diffs - np.average(diffs)), np.std(diffs))

# delta(ch5total, timingMap, 0)

# randomPulseIndices = np.random.randint(0, ch5total.size, size = 50000)
# ds = []
# for randomPulseIndex in randomPulseIndices:
#   tLeft = randomPulseIndex * 100000
#   tRight = mapTiming(tLeft, timingMap)
#   d = tRight - ch5total[randomPulseIndex]
#   ds.append(d)
# ds = np.array(ds)
# print(ds - np.average(ds))
# print(np.max(ds - np.average(ds)), np.min(ds - np.average(ds)))
# print(np.std(ds))

# randomPulseIndices = np.random.randint(0, ch5total.size, size = 50000)
# ds = []
# for randomPulseIndex in randomPulseIndices:
#   tRight = ch5total[randomPulseIndex]
#   tLeft = mapTiming_rev(tRight, timingMap)
#   d = tLeft - randomPulseIndex * 100000
#   ds.append(d)
# ds = np.array(ds)
# print(ds - np.average(ds))
# print(np.max(ds - np.average(ds)), np.min(ds - np.average(ds)))
# print(np.std(ds))

# indices = np.linspace(0, 9999999, 10000000, dtype='int64')
# ds = []
# for index in indices:
#   tRight = ch5total[index]
#   tLeft = mapTiming_rev(tRight, timingMap)
#   d = tLeft - index * 100000
#   ds.append(d)
# ds = np.array(ds)
# print(np.max(ds - np.average(ds)), np.min(ds - np.average(ds)), np.std(ds))

# tRights = ch5total[0: 10000000]
# tLefts = mapTiming_rev_array(tRights, timingMap)
# ds = tLefts - indices * 100000
# print(np.max(ds - np.average(ds)), np.min(ds - np.average(ds)), np.std(ds))

# import time
# t1 = time.time()
# tLefts = mapTiming_rev_array(tRights, timingMap)
# t2 = time.time()
# print(t2 - t1)


with open(f'{dir}/{filenames[3]}', 'rb') as file:
  data = file.read()
  db = DataBlock.deserialize(data)
# dopplerShiftBegin = db.content[1][0]

@numba.njit(cache=True)
def rescaleChannel(ch, freqScale, offsetPre, offsetPost, copy=False):
  newCH = ch if not copy else np.zeros(shape=ch.shape, dtype=ch.dtype)
  for i in range(len(ch)):
    newCH[i] = (ch[i] - offsetPre) / freqScale + offsetPost
  return ch

def frequencyRescaleAdaptor(dataBlock):
  beginPoint = 0
  content = dataBlock.content
  freqScale = (content[0][-1] - content[0][0]) / (content[0].size - 1) * 25000 / 1e12
  newContents = []
  basePoint = content[1][0]
  for ch in content:
    newCH = rescaleChannel(ch, freqScale, basePoint, beginPoint, copy=False)
    newContents.append(newCH)
  newDataBlock = DataBlock.create(newContents, dataBlock.creationTime, beginPoint, beginPoint + 1000000000000, dataBlock.resolution)
  return newDataBlock

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

def dopplerReshapingAdaptor(dataBlock):
  startDopplerShiftAtPS = dataBlock.content[1][0]

  content = dataBlock.content
  newContents = []
  newContents.append(content[0])
  newContents.append(content[1])
  for i in range(2, len(content)):
    newContent = mapTiming_rev_array(content[i], timingMap, startDopplerShiftAtPS, copy=True)
    newContents.append(newContent)

  newDataBlock = DataBlock.create(newContents, dataBlock.creationTime, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, dataBlock.resolution)

  return newDataBlock

db = frequencyRescaleAdaptor(db)
binary = db.serialize()
dopplerReshapingAdaptor(DataBlock.deserialize(binary))
dbs = []
for i in range(10): dbs.append(DataBlock.deserialize(binary))
t1 = time.time()
for db in dbs:
  d = dopplerReshapingAdaptor(db)
t2 = time.time()
print(d.content[5])
print(d.content[5][100000])
print(d.content[5][100000] == 10000089783)
print(t2 - t1)

# for dopplerI in range(-1, 600):
#   filename = filenames[dopplerI + 3]
#   with open(f'{dir}/{filename}', 'rb') as file:
#     data = file.read()
#     db = DataBlock.deserialize(data)
#     ch0 = db.content[0]
#     freqScale = (ch0[-1] - ch0[0]) / (ch0.size - 1) * 25000 / 1e12
#     # ch0 rescale
#     ch5 = ((db.content[5] - db.content[1][0]) / freqScale + dopplerI * 1e12).astype('int64')
#   ch5 = mapTiming_rev_array(ch5, timingMap)
#   if len(ch5) > 0: print(dopplerI, ch5[0] % 100000)