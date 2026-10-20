from numba import njit
from datetime import datetime
import numpy as np
import pickle
import math
from pytimetag import DataBlock

class DopplerUtil:
  def __init__(self) -> None:
    self.latestOnePPSOriginalTime = None
    self.onePPSCount = 0
    self.startDopplerShiftAtPS = None
    self.startDopplerShiftAt = None
    
  def prepare(self, beginTime, curveFile):
    self.startDopplerShiftAt = int(datetime.fromisoformat(beginTime).timestamp())
    self.startDopplerShiftAtPS = None
    self.dopplerShiftTimeStep = 0.01
    with open(curveFile, 'rb') as file:
      self.dopplerTimings = pickle.load(file)
      self.dopplerShiftFs = self.dopplerTimings['f']
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
      return DataBlock.create([[] for i in range(len(datablock.sizes))], datablock.creationTime, -1, -1, datablock.resolution)
    if datablock.sizes[1] > 0:
      self.latestOnePPSOriginalTime = datablock.content[1][0]
      self.onePPSCount += 1

    datablock = self.frequencyRescaleAdaptor(datablock)
    datablock = self.dopplerReshapingAdaptor(datablock)
    datablock = self.ch1OffsetAdaptor(datablock)
    return datablock

  def frequencyRescaleAdaptor(self, dataBlock):
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
          # print('Doppler Shift Begins!')
          self.startDopplerShiftAtPS = dataBlock.content[1][0]
        else: return dataBlock
    dopplerShiftDuration = self.dopplerShiftTimeStep * (len(self.dopplerShiftFs) - 1)
    # print(f'Performing Doppler Shift @ second {int(dataBlock.creationTime + 0.5) - self.startDopplerShiftAt}.')
    content = dataBlock.content
    newContents = []
    newContents.append(content[0].copy())
    newContents.append(content[1].copy())
    for i in range(2, len(content)):
      newContent = mapTiming_rev_array(content[i], self.timingMap, self.startDopplerShiftAtPS, copy=False)
      newContents.append(newContent)
    
    dopplerShiftEnd = self.startDopplerShiftAt + dopplerShiftDuration
    if dataBlock.sizes[1] > 0 and int(dataBlock.creationTime + 0.5) >= dopplerShiftEnd and self.startDopplerShiftAtPS is not None:
      # print('Doppler Shift Ends!')
      self.startDopplerShiftAtPS = None
            
    newDataBlock = DataBlock.create(newContents, dataBlock.creationTime, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd, dataBlock.resolution)
    return newDataBlock

  def ch1OffsetAdaptor(self, dataBlock):
    if dataBlock.sizes[1] == 0: return dataBlock
    current1PPSTime = dataBlock.content[1][0]
    next25kTime = dataBlock.content[0][dataBlock.content[0] >= current1PPSTime]
    if len(next25kTime) == 0: return dataBlock
    dataBlock.content[1][0] += next25kTime[0] - current1PPSTime
    return dataBlock

@njit(cache=True)
def rescaleChannel(ch, freqScale, offset, copy=False):
  newCH = ch if not copy else np.zeros(shape=ch.shape, dtype=ch.dtype)
  for i in range(len(ch)):
    newCH[i] = ch[i] * freqScale + offset
  return ch

@njit(cache=True)
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
