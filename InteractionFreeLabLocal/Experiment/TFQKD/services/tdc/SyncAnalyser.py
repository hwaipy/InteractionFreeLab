__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

from pytimetag.Analyser import Validator
from pytimetag.analysers.EncodingAnalyser import EncodingAnalyser
from numba import njit
import numpy as np

class SyncAnalyser(EncodingAnalyser):
  def __init__(self, channelCount, randomNumberLimit, debug=False, minimumCounts=1000, reportStatistics=False):
    super().__init__(channelCount, randomNumberLimit)
    self.channelCount = channelCount
    self.randomNumberLimit = randomNumberLimit
    self.debug = debug
    self.minimumCounts = minimumCounts
    self.reportStatistics = reportStatistics
    self.setConfiguration('PulsePosition', 5000, Validator.float(0))

  def analysis(self, dataBlock):
    result = super().analysis(dataBlock)
    # tick.tick('super analyzing done')
    randomNumbers = self.getConfiguration('RandomNumbers')
    period = self.getConfiguration('Period')
    pulsePosition = self.getConfiguration('PulsePosition')
    triggerChannel = self.getConfiguration('TriggerChannel')
    signalChannel = self.getConfiguration('SignalChannel')
    binCount = self.getConfiguration('BinCount')
    resolution = period / binCount

    totalPeriod = period * len(randomNumbers)

    counts = int(len(dataBlock.content[signalChannel]))
    statistics = None
    if self.reportStatistics:
      duration = float((dataBlock.dataTimeEnd - dataBlock.dataTimeBegin) * dataBlock.resolution)
      statistics = {
        'SignalChannel': signalChannel, 'TriggerChannel': triggerChannel,
        'TriggerCounts': int(len(dataBlock.content[triggerChannel])),
        'BlockDurationS': duration, 'InputCounts': counts,
        'InputCountRateHz': counts / duration if duration > 0 else None,
        'MinimumCounts': self.minimumCounts, 'MinimumPeakToMean': 3,
        'CentroidBinThresholdFraction': 0.3,
        'HistogramCounts': 0, 'AllInputHistogrammed': False,
        'CentroidCounts': 0, 'CentroidCountRateHz': 0 if duration > 0 else None,
        'CentroidFraction': 0 if counts else None,
        'ShiftCounts': 0, 'PeakToMean': None, 'Valid': False,
        'InvalidReason': 'no_trigger',
      }
      result['SyncStatistics'] = statistics
      if not statistics['TriggerCounts']:
        result['Delay'] = None
        return result

    histogramInPulse = histogramJIT(dataBlock.content[signalChannel], dataBlock.content[triggerChannel][0], period, resolution)  # TODO: 统一解决begin的问题
      # tick.tick('histogram computed')

    # check valid:
    extinctionRatio = max(histogramInPulse) / (np.mean(histogramInPulse) + 1e-9)
    valid = extinctionRatio >= 3 and counts >= self.minimumCounts
    if statistics is not None:
      histogramCounts = int(np.sum(histogramInPulse, dtype=np.uint64))
      statistics.update(HistogramCounts=histogramCounts, AllInputHistogrammed=histogramCounts == counts,
                        PeakToMean=float(extinctionRatio), Valid=bool(valid),
                        InvalidReason=None if valid else
                            ('insufficient_counts' if counts < self.minimumCounts else 'low_peak_to_mean'))
    if self.debug:
      print(extinctionRatio, counts)
      print(randomNumbers[:20])
    if valid:
      pulsePositionEstimated = histogramInPulse.argmax() * resolution + resolution / 2

      times = np.linspace(0, period, histogramInPulse.shape[0], endpoint=False)
      if np.abs(pulsePositionEstimated - pulsePosition) > period / 4:
        times[: int(binCount / 2)] += period
      validPulseIndices = np.where(histogramInPulse >= np.max(histogramInPulse) * 0.3)[0]
      if statistics is not None:
        centroidCounts = int(np.sum(histogramInPulse[validPulseIndices], dtype=np.uint64))
        statistics.update(CentroidCounts=centroidCounts,
                          CentroidCountRateHz=centroidCounts / duration if duration > 0 else None,
                          CentroidFraction=centroidCounts / counts if counts else None)
      pulsePositionEstimated = np.mean(times[validPulseIndices] * histogramInPulse[validPulseIndices]) / np.mean(histogramInPulse[validPulseIndices])

      deltaInPulse = pulsePositionEstimated - pulsePosition
      # tick.tick('estimating delta')
      pulseCounts = computePulseCountJIT(dataBlock.content[signalChannel], dataBlock.content[triggerChannel][0] + deltaInPulse, period, totalPeriod, len(randomNumbers))
      if statistics is not None:
        statistics['ShiftCounts'] = int(np.sum(pulseCounts, dtype=np.uint64))
      # tick.tick('computing pulse counts')
      # tick.tick('estimating pulse delta')
      pulseDeltaErrors = searchingPulseCountDip(pulseCounts, randomNumbers)
      pulseDelta = pulseDeltaErrors.argmin()
      if pulseDelta > len(randomNumbers) / 2:
        pulseDelta -= len(randomNumbers)
      # tick.tick('pulse delta estimated')

      result['Delay'] = -pulseDelta * period + pulsePositionEstimated - pulsePosition
    else:
      result['Delay'] = None
    return result

@njit(cache=True)
def histogramJIT(signalList, begin, period, resolution):
  histogramInPulse = np.zeros(int(np.ceil(period / resolution)), dtype='uint32')
  for signal in signalList:
    timeInPeriod = (signal - begin) % period
    histogramInPulse[int(timeInPeriod / resolution)] += 1
  return histogramInPulse

@njit(cache=True)
def computePulseCountJIT(signalList, begin, period, totalPeriod, randomNumberNum):
  pulseCounts = np.zeros(randomNumberNum, dtype='uint32')
  for signal in signalList:
    timeInTotalPeriod = (signal - begin) % totalPeriod
    pulseIndex = int(timeInTotalPeriod / period)
    pulseCounts[pulseIndex] += 1
  return pulseCounts

def searchingPulseCountDip(pulseCounts, randomNumbers):
  size = len(randomNumbers)
  if size == 0:
    return np.zeros(0, dtype='uint32')
  isVacuum = (np.asarray(randomNumbers) & 0b11000011) == 0
  # errors[d] = sum(pulseCounts[i] * isVacuum[(i + d) % size]).
  # Conjugating the counts spectrum preserves the original shift direction.
  countsSpectrum = np.fft.rfft(np.asarray(pulseCounts[:size], dtype='float64'))
  vacuumSpectrum = np.fft.rfft(isVacuum)
  errors = np.fft.irfft(np.conj(countsSpectrum) * vacuumSpectrum, n=size)
  # Remove FFT roundoff and preserve the original uint32 overflow behavior.
  return np.maximum(np.rint(errors), 0).astype('uint64').astype('uint32')

# Original O(N**2) implementation, retained for reference:
# @njit(cache=True)
# def searchingPulseCountDip(pulseCounts, randomNumbers):
#   vacuumMarks = np.zeros(len(randomNumbers), dtype='uint8')
#   for i in range(len(randomNumbers)):
#     if randomNumbers[i] & 0b11000011 != 0:
#       vacuumMarks[i] = 1   # 0为真空，1为非真空
#   pulseDeltaErrors = np.zeros(len(randomNumbers), dtype='uint32')
#   for pulseNum in range(len(randomNumbers)):
#     pulseCount = pulseCounts[pulseNum]
#     for delay in range(len(randomNumbers)):
#       delayedPulseNum = pulseNum + delay
#       if delayedPulseNum >= len(randomNumbers):
#         delayedPulseNum -= len(randomNumbers)
#       if vacuumMarks[delayedPulseNum] == 0:
#         pulseDeltaErrors[delay] += pulseCount
#   return pulseDeltaErrors
