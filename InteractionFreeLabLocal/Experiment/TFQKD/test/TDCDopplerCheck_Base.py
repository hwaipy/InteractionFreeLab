from pytimetag import DataBlock
import os
import numpy as np
import numba

dir = '/home/coder/project/data/test11'
expectFreq5 = 9999766.1123

filenames = os.listdir(dir)
filenames.sort()

sizes = np.zeros((16,), dtype='int64')

firstEntry = None
lastEntry = None

dopplerTimingsF = [9999766.1123] * 60001
dopplerShiftTimeStep = 0.01
dopplerShiftFs = np.array(dopplerTimingsF) / 10000000
dopplerShiftTimings = [0]
for i in range(len(dopplerShiftFs)):
    delta = dopplerShiftTimeStep / dopplerShiftFs[i] + dopplerShiftTimings[-1]
    dopplerShiftTimings.append(delta)
dopplerShiftTimings = np.array(dopplerShiftTimings)
# print(np.max(np.abs(self.dopplerShiftTimings - np.array([i for i in range(len(self.dopplerShiftTimings))]) * self.dopplerShiftTimeStep)))
startDopplerShiftAt = 0

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
        newContent = mapping_rev(dopplerShiftTimings, dopplerShiftTimeStep, dataBlockBeginTime - dopplerShiftBegin, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, content[i])
        newContents.append(newContent)

    newDataBlock = DataBlock.create(newContents, dataBlock.creationTime, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, dataBlock.resolution)

    return newDataBlock


for filename in filenames:
    with open(f'{dir}/{filename}', 'rb') as file:
        data = file.read()
    db = DataBlock.deserialize(data)
    if startDopplerShiftAt == 0: startDopplerShiftAt = db.creationTime
    # print(db.sizes, db.content[0][0], db.content[0][-1], db.content[5][0], db.content[5][-1])
    ddb = dopplerReshapingAdaptor(db)
    # print(ddb.sizes, ddb.content[0][0], ddb.content[0][-1], ddb.content[5][0], ddb.content[5][-1])
    print(ddb.dataTimeBegin, ddb.content[1][0] - ddb.dataTimeBegin, ddb.content[5][0] - ddb.dataTimeBegin)
    sizes += np.array(db.sizes)
    if not firstEntry: firstEntry = db
    lastEntry = db

print(sizes)
print('----')
print('----')
print('----')

freq0 = (sizes[0] - 1) / (lastEntry.content[0][-1] - firstEntry.content[0][0]) * 1e12
print(f'CH0: {sizes[0]} counts, from {firstEntry.content[0][0]} to {lastEntry.content[0][-1]}, freq0 = {freq0}')

freq5 = (sizes[5] - 1) / (lastEntry.content[5][-1] - firstEntry.content[5][0]) * 1e12
print(f'CH0: {sizes[5]} counts, from {firstEntry.content[5][0]} to {lastEntry.content[5][-1]}, freq0 = {freq5}')

actualFreq5 = freq5 / freq0 * 25000
print(f'freq5 / freq0 * 25k = {actualFreq5}')
print(f'expected freq5 = {expectFreq5}')
print(f'diff = {expectFreq5 - actualFreq5} Hz, corresponding to {(expectFreq5 - actualFreq5) / 10e6}')

#
# diff = 9999766.53615158 - 9,999,766.5366023562 = -0.0004507762 Hz   or 4.5e-11
#
