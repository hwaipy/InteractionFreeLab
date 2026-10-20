__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

from pytimetag.Analyser import Analyser, Validator
import numba
import numpy as np
import sys


class EncodingAnalyser(Analyser):
  def __init__(self, channelCount, randomNumberLimit):
    super().__init__()
    self.channelCount = channelCount
    self.randomNumberLimit = randomNumberLimit
    self.setConfiguration('RandomNumbers', np.ones(1, dtype='int'), lambda x: True)
    self.setConfiguration('Period', 10000, Validator.float(0))
    self.setConfiguration('TriggerChannel', 0, Validator.int(0, channelCount - 1))
    self.setConfiguration('SignalChannel', 1, Validator.int(0, channelCount - 1))
    self.setConfiguration('BinCount', 100, Validator.int(1, 1000))
    self.setConfiguration('PulsePerTrigger', 4000, Validator.int(1, 1000000000000))
    self.setConfiguration('Histograms', {}, lambda x: True)
    self.previousRandomNumber = None
    self.previousRandomNumberStatistic = None

  def analysis(self, dataBlock):
    viewingHistograms = self.getConfiguration('Histograms')
    period = self.getConfiguration('Period')
    triggerChannel = self.getConfiguration('TriggerChannel')
    signalChannel = self.getConfiguration('SignalChannel')
    binCount = self.getConfiguration('BinCount')
    pulsePerTrigger = self.getConfiguration('PulsePerTrigger')
    randomNumbers = self.getConfiguration('RandomNumbers')
    if isinstance(randomNumbers, list): randomNumbers = np.array(randomNumbers, dtype='<i4')
    map = {}

    triggerList = dataBlock.content[triggerChannel]
    signalList = dataBlock.content[signalChannel]
    if len(triggerList) == 0 or len(signalList) == 0:
      histograms = [np.zeros(binCount, dtype='<i4') for rn in range(self.randomNumberLimit)]
    else:
      metaRNs, metaDeltas = metaJIT(triggerList, signalList, period, randomNumbers, pulsePerTrigger)
      histograms = statisticHistogramsJIT(metaRNs, metaDeltas, 0, period, binCount, self.randomNumberLimit)

    if randomNumbers is not self.previousRandomNumber:
      self.previousRandomNumber = randomNumbers
      self.previousRandomNumberStatistic = statisticRandomNumbersJIT(self.randomNumberLimit, randomNumbers)
    rnCounts = self.previousRandomNumberStatistic

    for key in viewingHistograms:
      rns = viewingHistograms[key]
      mergedYData = np.sum([histograms[rn] for rn in rns], axis=0)
      map[f'Histogram[{key}]'] = [int(i) for i in mergedYData]
      map[f'PulseCount[{key}]'] = int(sum([rnCounts[rn] for rn in rns]))

    return map

@numba.njit(cache=True)
def metaJIT(triggerList, signalList, period, randomNumbers, pulsePerTrigger):
  currentTrigger = triggerList[0]
  nextTrigger = sys.maxsize if len(triggerList) <= 1 else triggerList[1]
  iTrigger = 0
  rnSize = len(randomNumbers)
  metaRNs = np.zeros(len(signalList), dtype='<i4')
  metaDeltas = np.zeros(len(signalList), dtype='<i4')
  for iSignal in range(len(signalList)):
    signalTime = signalList[iSignal]
    while signalTime >= nextTrigger:
      iTrigger += 1
      currentTrigger = nextTrigger
      nextTrigger = sys.maxsize if iTrigger + 1 >= len(triggerList) else triggerList[iTrigger + 1]
    pulseIndex = int((signalTime - currentTrigger) / period)
    randomNumberIndex = int((pulseIndex + iTrigger * pulsePerTrigger) % rnSize)
    metaRNs[iSignal] = randomNumbers[randomNumberIndex if randomNumberIndex >= 0 else randomNumberIndex + len(randomNumbers)]
    metaDeltas[iSignal] = int(signalTime - currentTrigger - period * pulseIndex)
  return (metaRNs, metaDeltas)

@numba.njit(cache=True)
def statisticHistogramsJIT(metaRNs, metaDeltas, viewFrom, viewTo, binCount, randomNumberLimit):
  results = [np.zeros(binCount, dtype='<i4') for rn in range(randomNumberLimit)]
  binSize = (viewTo - viewFrom) / binCount
  for i in range(len(metaRNs)):
    rn = metaRNs[i]
    delta = metaDeltas[i]
    if (delta >= viewFrom):
      if delta == viewTo:
        results[rn][binCount - 1] += 1
      elif delta < viewTo:
        bin = int((delta - viewFrom) / binSize) % binCount
        results[rn][bin] += 1
  return results

@numba.njit(cache=True)
def statisticRandomNumbersJIT(randomNumberLimit, randomNumbers):
  rnCounts = np.zeros(randomNumberLimit, dtype='<i4')
  for rn in randomNumbers:
    rnCounts[rn] += 1
  return rnCounts

if __name__ == '__main__':
  from pytimetag.datablock import DataBlock
  from pytimetag.analysers.HistogramAnalyser import HistogramAnalyser
  import time

  dataBlock = DataBlock.generate(
      {'CreationTime': 100, 'DataTimeBegin': 0, 'DataTimeEnd': 1000000000000},
      {0: ['Period', 25000], 2: ['Pulse', 100000000, 1000000, 100]}
  )
  mha = EncodingAnalyser(16, 256)
  mha.turnOn({"Period": 10000, "TriggerChannel": 0, "SignalChannel": 1, "RandomNumbers": np.linspace(0, 2000000 - 1, 2000000, dtype='<i4') % 256})
  result = mha.dataIncome(dataBlock)
  t1 = time.time()
  result = mha.dataIncome(dataBlock)
  t2 = time.time()
  print((t2 - t1) * 1000)