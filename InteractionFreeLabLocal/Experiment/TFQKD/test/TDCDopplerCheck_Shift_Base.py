from pytimetag import DataBlock
import os
import numpy as np
import numba
import math
import pickle

with open('/home/coder/project/interactionfreelab/InteractionFreeLabLocal/Experiment/TFQKD/test/Doppler_Timing.pkl', 'rb') as file:
    dopplerTimings = pickle.load(file)
expectFrequencies = np.array(dopplerTimings['f'])[:-1]
# print(expectFrequencies, expectFrequencies.shape)

# expectedTimings = []
timingMap = [] # 左边多普勒前，右边多普勒后
expectedWavenumbers = [0]
for f in expectFrequencies:
  expectedWavenumbers.append(expectedWavenumbers[-1] + f * 0.01)
expectedWavenumbers = np.array(expectedWavenumbers)
for i in range(len(expectedWavenumbers) - 1):
  pulseIndex = math.ceil(expectedWavenumbers[i])
  expTiming = pulseIndex * 100000
  actTiming = int((i * 0.01 + (pulseIndex - expectedWavenumbers[i]) / expectFrequencies[i]) * 1e12)
  # expectedTimings.append([pulseIndex, timing])
  timingMap.append([expTiming, actTiming])

for e in timingMap[:10]:
  print(e)


# dir = '/home/coder/project/data/test11'
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
    # print(mappedEvent)
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

frequencies = []

ch5total = []

for i in range(3, 203):
  filename = filenames[i]
  print(i)
  with open(f'{dir}/{filename}', 'rb') as file:
    data = file.read()
    db = DataBlock.deserialize(data)
#     ddb = dopplerReshapingAdaptor(db)
#     print(ddb.dataTimeBegin, ddb.content[1][0] - ddb.dataTimeBegin, ddb.content[5][0] - ddb.dataTimeBegin)
#     sizes += np.array(db.sizes)
#     if not firstEntry: firstEntry = db
#     lastEntry = db
    ch0 = db.content[0]
    freqScale = (ch0[-1] - ch0[0]) / (ch0.size - 1) * 25000 / 1e12
    # print(db.content[5] - db.content[1][0])
    ch5 = ((db.content[5] - db.content[1][0]) / freqScale + i * 1e12).astype('int64')
    # print(ch5)
    ch5total.append(ch5)
    # for i in range(100):
    #   d = ch5[i * 100: (i + 1) * 100]
    #   period = (d[-1] - d[0]) - 9900000
    #   print(i, i * 100, (i + 1) * 100, period)
ch5total = np.hstack(ch5total)

# def delta(ch5, expects, offset):
#   diffs = []
#   for expect in expects:
#     pulseIndex, timing = expect
#     if pulseIndex + offset >= 0 and pulseIndex + offset < ch5.size:
#       diff = ch5[pulseIndex + offset] - timing
#       diffs.append(diff)
#   diffs = np.array(diffs)
#   print(diffs - np.average(diffs))
#   print(np.max(diffs - np.average(diffs)), np.min(diffs - np.average(diffs)))
#   return np.std(diffs)

def mapTiming(t, timingMap, offsetLeft, offsetRight):
  for ie in range(len(timingMap) - 1):
    tLeft1, tRight1 = timingMap[ie]
    tLeft2, tRight2 = timingMap[ie + 1]
    if t < tLeft1: return math.nan
    if t > tLeft2: continue
    # (t - tLeft1) / (tLeft2 - tLeft1) = (r - tRight1) / (tRight2 - tRight1)
    return (t - tLeft1) / (tLeft2 - tLeft1) * (tRight2 - tRight1) + tRight1


def delta(ch5, timingMap, offset):
  diffs = []
  for e in timingMap:
    pulseIndex, timing = e
    pulseIndex //= 100000
    if pulseIndex + offset >= 0 and pulseIndex + offset < ch5.size:
      diff = ch5[pulseIndex + offset] - timing
      diffs.append(diff)
  diffs = np.array(diffs)
  print(diffs - np.average(diffs))
  print(np.max(diffs - np.average(diffs)), np.min(diffs - np.average(diffs)))
  return np.std(diffs)

print(delta(ch5total, timingMap, 0))

randomPulseIndices = np.random.randint(0, ch5total.size, size = 50000)
print(randomPulseIndices)
ds = []
for randomPulseIndex in randomPulseIndices:
  tLeft = randomPulseIndex * 100000
  tRight = mapTiming(tLeft, timingMap, 0, 0)
  d = tRight - ch5total[randomPulseIndex]
  ds.append(d)
ds = np.array(ds)
print(ds - np.average(ds))
print(np.max(ds - np.average(ds)), np.min(ds - np.average(ds)))
print(np.std(ds))