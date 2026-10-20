__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

from pytimetag.Analyser import Analyser, Validator
import numba
import numpy as np


class HistogramAnalyser(Analyser):
  def __init__(self, channelCount): 
    super().__init__()
    self.channelCount = channelCount
    self.setConfiguration("Sync", 0, Validator.int(0, channelCount - 1))
    self.setConfiguration("Signals", [1], Validator.intList(0, channelCount - 1))
    self.setConfiguration("ViewStart", -100000, Validator.float())
    self.setConfiguration("ViewStop", 100000, Validator.float())
    self.setConfiguration("BinCount", 1000, Validator.int(1, 100000))
    self.setConfiguration("Divide", 1, Validator.int(min=1))

  def analysis(self, dataBlock):
    syncChannel = self.getConfiguration("Sync")
    signalChannels = self.getConfiguration("Signals")
    viewStart = self.getConfiguration("ViewStart")
    viewStop = self.getConfiguration("ViewStop")
    binCount = self.getConfiguration("BinCount")
    divide = self.getConfiguration("Divide")
    tList = dataBlock.content[syncChannel]
    viewFrom = viewStart
    viewTo = viewStop

    triggerTooMuch = (len(tList) * (viewStop - viewStart) / (dataBlock.dataTimeEnd - dataBlock.dataTimeBegin)) > 100 # check if there is too much trigger
    if triggerTooMuch:
      histograms = [np.ones(binCount, dtype='<i8') * -1 for signalChannel in signalChannels]
    else:
      if len(signalChannels) == 0: histograms = []
      else:
        sLists = numba.typed.List([dataBlock.content[signalChannel] for signalChannel in signalChannels])
        histograms = analysisJIT(tList, sLists, viewFrom, viewTo, binCount, divide)
    return {'Histograms': [list([int(i) for i in h]) for h in histograms]}

@numba.njit(parallel=False, cache=True)
def analysisJIT(tList, sLists, viewFrom, viewTo, binCount, divide):
  histograms = [np.zeros(0, dtype='<i4') for s in sLists]
  for i in numba.prange(len(sLists)):
    histograms[i] = analysisOneListJIT(tList, sLists[i], viewFrom, viewTo, binCount, divide)
  return histograms

@numba.njit(cache=True)
def analysisOneListJIT(tList, sList, viewFrom, viewTo, binCount, divide):
  binSize = (viewTo - viewFrom) / binCount / divide
  yData = np.zeros(binCount, dtype='<i4')
  if len(tList) > 0 and len(sList) > 0:
    preStartT = 0
    lengthT = len(tList)
    sp = 0
    while sp < len(sList):
      s = sList[sp]
      cont = True
      while (preStartT < lengthT and cont):
        t = tList[preStartT]
        delta = s - t
        if (delta > viewTo):
          preStartT += 1
        else:
          cont = False
      tIndex = preStartT
      cont = True
      while (tIndex < lengthT and cont):
        t = tList[tIndex]
        delta = s - t
        if (delta >= viewFrom):
          if delta == viewTo:
            yData[binCount - 1] += 1
          elif delta < viewTo:
            bin = int((delta - viewFrom) / binSize) % binCount
            yData[bin] += 1
          tIndex += 1
        else:
          cont = False
      sp += 1

  return yData


if __name__ == '__main__':
  from pytimetag.datablock import DataBlock
  from pytimetag.analysers.HistogramAnalyser import HistogramAnalyser
  import time

  dataBlock = DataBlock.generate(
      {'CreationTime': 100, 'DataTimeBegin': 0, 'DataTimeEnd': 1000000000000}, 
      {0: ['Period', 25000], 2: ['Pulse', 100000000, 1000000, 100], 3: ['Pulse', 100000000, 1000000, 100], 4: ['Pulse', 100000000, 1000000, 100]}
  )
  mha = HistogramAnalyser(16)
  mha.turnOn({"Sync": 0, "Signals": [2, 3, 4], "ViewStart": 0, "ViewStop": 400000000, "BinCount": 100, "Divide": 1})

  mha.dataIncome(dataBlock)
  t1 = time.time()
  result = mha.dataIncome(dataBlock)
  t2 = time.time()
  result = mha.dataIncome(dataBlock)
  t3 = time.time()
  histos = result['Histograms']
  print((t2 - t1) * 1000, (t3 - t2) * 1000)