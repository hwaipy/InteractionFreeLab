__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

from pytimetag.Analyser import Analyser, Validator
import numba
import numpy as np
import sys


class DeltaMetaAnalyser(Analyser):
  def __init__(self, channelCount):
    super().__init__()
    self.channelCount = channelCount
    self.setConfiguration('SyncChannel', 0, Validator.int(0, channelCount - 1))
    self.setConfiguration('Channel1', 2, Validator.int(0, channelCount - 1))
    self.setConfiguration('Channel2', 3, Validator.int(0, channelCount - 1))
    self.setConfiguration('Period', 10000, Validator.float(0))
    self.setConfiguration('Center', 5000, Validator.float(0))
    self.setConfiguration('GateWidth', 1000, Validator.float(0))
    self.setConfiguration('GroupBy', 25, Validator.int(1, 25000))

  def analysis(self, dataBlock):
    syncChannel = self.getConfiguration('SyncChannel')
    channel1 = self.getConfiguration('Channel1')
    channel2 = self.getConfiguration('Channel2')
    period = self.getConfiguration('Period')
    center = self.getConfiguration('Center')
    gateWidth = self.getConfiguration('GateWidth')
    groupBy = self.getConfiguration('GroupBy')

    map = {}

    # triggerList = dataBlock.content[triggerChannel]
    # signalList = dataBlock.content[signalChannel]
    # if len(triggerList) < 2 or len(signalList) == 0:
    #   histograms = [np.zeros(binCount, dtype='<i4') for rn in range(self.randomNumberLimit)]
    # else:
    #   metaRNs, metaDeltas = metaJIT(triggerList, signalList, period, randomNumbers, pulsePerTrigger)
    #   histograms = statisticHistogramsJIT(metaRNs, metaDeltas, 0, period, binCount, self.randomNumberLimit)

    # if randomNumbers is not self.previousRandomNumber:
    #   self.previousRandomNumber = randomNumbers
    #   self.previousRandomNumberStatistic = statisticRandomNumbersJIT(self.randomNumberLimit, randomNumbers)
    # rnCounts = self.previousRandomNumberStatistic

    # for key in viewingHistograms:
    #   rns = viewingHistograms[key]
    #   mergedYData = np.sum([histograms[rn] for rn in rns], axis=0)
    #   map[f'Histogram[{key}]'] = [int(i) for i in mergedYData]
    #   map[f'PulseCount[{key}]'] = int(sum([rnCounts[rn] for rn in rns]))



    deltaMetas1 = deltaMeta(dataBlock.content[syncChannel], dataBlock.content[channel1], period) #.filter(z => z._3 > center - gateWidth / 2 && z._3 < center + gateWidth / 2)
#     val deltaMetas2 = deltaMeta(dataBlock.getContent(syncChannel), dataBlock.getContent(channel2), period).filter(z => z._3 > center - gateWidth / 2 && z._3 < center + gateWidth / 2)
#     val deltaMetas1A = deltaMetas1.filter(z => z._2 % 2 == 0)
#     val deltaMetas1B = deltaMetas1.filter(z => z._2 % 2 == 1)
#     val deltaMetas2A = deltaMetas2.filter(z => z._2 % 2 == 0)
#     val deltaMetas2B = deltaMetas2.filter(z => z._2 % 2 == 1)
#     val deltaMetas1AStat = metaStatByTrigger(deltaMetas1A, groupBy)
#     val deltaMetas1BStat = metaStatByTrigger(deltaMetas1B, groupBy)
#     val deltaMetas2AStat = metaStatByTrigger(deltaMetas2A, groupBy)
#     val deltaMetas2BStat = metaStatByTrigger(deltaMetas2B, groupBy)
#     Map[String, Any]("DeltaMetas1AStat" -> deltaMetas1AStat, "DeltaMetas1BStat" -> deltaMetas1BStat, "DeltaMetas2AStat" -> deltaMetas2AStat, "DeltaMetas2BStat" -> deltaMetas2BStat)


    return map

def deltaMeta(triggerList, signalList, period):
    pass
#     val triggerIterator = triggerList.iterator
#     var currentTrigger = if (triggerIterator.hasNext) triggerIterator.next() else 0
#     var nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
#     var iSignal = 0
#     var iTrigger = 0
#     val deltaMetas = new Array[Tuple3[Int, Int, Int]](signalList.size)
#     while (iSignal < signalList.size) {
#       val time = signalList(iSignal)
#       while (time >= nextTrigger) {
#         currentTrigger = nextTrigger
#         iTrigger += 1
#         nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
#       }
#       val pulseIndex = ((time - currentTrigger) / period).toInt
#       deltaMetas(iSignal) = (iTrigger, pulseIndex, (time - currentTrigger - period * pulseIndex).toInt) //(time - currentTrigger - period * pulseIndex).toLong
#       iSignal += 1
#     }
#     deltaMetas
#   }
# }

#   def __meta(self, triggerList, signalList, period, randomNumbers, pulsePerTrigger):
#     currentTrigger = triggerList[0]
#     nextTrigger = triggerList[1]
#     iTrigger = 0
#     rnSize = len(randomNumbers)
#     metaRNs = np.zeros(len(signalList), dtype='<i4')
#     metaDeltas = np.zeros(len(signalList), dtype='<i4')
#     for iSignal in range(len(signalList)):
#       signalTime = signalList[iSignal]
#       while signalTime >= nextTrigger:
#         currentTrigger = nextTrigger
#         nextTrigger = sys.maxsize if iTrigger >= len(triggerList) else triggerList[iTrigger]
#         iTrigger += 1
#       pulseIndex = int((signalTime - currentTrigger) / period)
#       randomNumberIndex = int((pulseIndex + iTrigger * pulsePerTrigger) % rnSize)
#       metaRNs[iSignal] = randomNumbers[randomNumberIndex if randomNumberIndex >= 0 else randomNumberIndex + len(randomNumbers)]
#       metaDeltas[iSignal] = int(signalTime - currentTrigger - period * pulseIndex)
#     return (metaRNs, metaDeltas)

# @numba.njit(cache=True)
# def metaJIT(triggerList, signalList, period, randomNumbers, pulsePerTrigger):
#   currentTrigger = triggerList[0]
#   nextTrigger = triggerList[1]
#   iTrigger = 0
#   rnSize = len(randomNumbers)
#   metaRNs = np.zeros(len(signalList), dtype='<i4')
#   metaDeltas = np.zeros(len(signalList), dtype='<i4')
#   for iSignal in range(len(signalList)):
#     signalTime = signalList[iSignal]
#     while signalTime >= nextTrigger:
#       currentTrigger = nextTrigger
#       nextTrigger = sys.maxsize if iTrigger >= len(triggerList) else triggerList[iTrigger]
#       iTrigger += 1
#     pulseIndex = int((signalTime - currentTrigger) / period)
#     randomNumberIndex = int((pulseIndex + iTrigger * pulsePerTrigger) % rnSize)
#     metaRNs[iSignal] = randomNumbers[randomNumberIndex if randomNumberIndex >= 0 else randomNumberIndex + len(randomNumbers)]
#     metaDeltas[iSignal] = int(signalTime - currentTrigger - period * pulseIndex)
#   return (metaRNs, metaDeltas)

# @numba.njit(cache=True)
# def statisticHistogramsJIT(metaRNs, metaDeltas, viewFrom, viewTo, binCount, randomNumberLimit):
#   results = [np.zeros(binCount, dtype='<i4') for rn in range(randomNumberLimit)]
#   binSize = (viewTo - viewFrom) / binCount
#   for i in range(len(metaRNs)):
#     rn = metaRNs[i]
#     delta = metaDeltas[i]
#     if (delta >= viewFrom):
#       if delta == viewTo:
#         results[rn][binCount - 1] += 1
#       elif delta < viewTo:
#         bin = int((delta - viewFrom) / binSize) % binCount
#         results[rn][bin] += 1
#   return results

# @numba.njit(cache=True)
# def statisticRandomNumbersJIT(randomNumberLimit, randomNumbers):
#   rnCounts = np.zeros(randomNumberLimit, dtype='<i4')
#   for rn in randomNumbers:
#     rnCounts[rn] += 1
#   return rnCounts

if __name__ == '__main__':
  from pytimetag.datablock import DataBlock
  from pytimetag.analysers.HistogramAnalyser import HistogramAnalyser
  import time

  dataBlock = DataBlock.generate(
      {'CreationTime': 100, 'DataTimeBegin': 0, 'DataTimeEnd': 1000000000000},
      {0: ['Period', 25000], 2: ['Pulse', 100000000, 1000000, 100], 3: ['Pulse', 100000000, 1000000, 100]}
  )
  mha = DeltaMetaAnalyser(16)
  mha.turnOn()
  result = mha.dataIncome(dataBlock)
  t1 = time.time()
  result = mha.dataIncome(dataBlock)
  t2 = time.time()
  print((t2 - t1) * 1000)


#   private def metaStatByTrigger(deltaMetas: Array[Tuple3[Int, Int, Int]], groupBy: Int) = deltaMetas.isEmpty match {
#     case true => Array[Int](0)
#     case false =>  {
#       val stat: Array[Int] = new Array[Int]((deltaMetas.last._1 / groupBy + 1).toInt)
#       deltaMetas.foreach(deltaMeta => stat((deltaMeta._1 / groupBy).toInt) += 1)
#       stat
#     }
#   }

#   private def deltaMeta(triggerList: Array[Long], signalList: Array[Long], period: Double) = {
#     val triggerIterator = triggerList.iterator
#     var currentTrigger = if (triggerIterator.hasNext) triggerIterator.next() else 0
#     var nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
#     var iSignal = 0
#     var iTrigger = 0
#     val deltaMetas = new Array[Tuple3[Int, Int, Int]](signalList.size)
#     while (iSignal < signalList.size) {
#       val time = signalList(iSignal)
#       while (time >= nextTrigger) {
#         currentTrigger = nextTrigger
#         iTrigger += 1
#         nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
#       }
#       val pulseIndex = ((time - currentTrigger) / period).toInt
#       deltaMetas(iSignal) = (iTrigger, pulseIndex, (time - currentTrigger - period * pulseIndex).toInt) //(time - currentTrigger - period * pulseIndex).toLong
#       iSignal += 1
#     }
#     deltaMetas
#   }
# }
