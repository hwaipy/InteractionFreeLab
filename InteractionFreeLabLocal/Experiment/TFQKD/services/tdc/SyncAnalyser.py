__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

from pytimetag.Analyser import Validator
from pytimetag.analysers.EncodingAnalyser import EncodingAnalyser
from numba import njit
import numpy as np

class SyncAnalyser(EncodingAnalyser):
  def __init__(self, channelCount, randomNumberLimit, debug=False):
    super().__init__(channelCount, randomNumberLimit)
    self.channelCount = channelCount
    self.randomNumberLimit = randomNumberLimit
    self.debug = debug
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

    histogramInPulse = histogramJIT(dataBlock.content[signalChannel], dataBlock.content[triggerChannel][0], period, resolution)  # TODO: 统一解决begin的问题
      # tick.tick('histogram computed')

    # check valid:
    extinctionRatio = max(histogramInPulse) / (np.mean(histogramInPulse) + 1e-9)
    counts = np.sum(dataBlock.content[signalChannel].shape[0])
    valid = extinctionRatio >= 3 and counts >= 1000
    if self.debug:
      print(extinctionRatio, counts)
      print(randomNumbers[:20])
    if valid:
      pulsePositionEstimated = histogramInPulse.argmax() * resolution + resolution / 2

      times = np.linspace(0, period, histogramInPulse.shape[0], endpoint=False)
      if np.abs(pulsePositionEstimated - pulsePosition) > period / 4:
        times[: int(binCount / 2)] += period
      validPulseIndices = np.where(histogramInPulse >= np.max(histogramInPulse) * 0.3)[0]
      pulsePositionEstimated = np.mean(times[validPulseIndices] * histogramInPulse[validPulseIndices]) / np.mean(histogramInPulse[validPulseIndices])

      deltaInPulse = pulsePositionEstimated - pulsePosition
      # tick.tick('estimating delta')
      pulseCounts = computePulseCountJIT(dataBlock.content[signalChannel], dataBlock.content[triggerChannel][0] + deltaInPulse, period, totalPeriod, len(randomNumbers))
      # tick.tick('computing pulse counts')
      # tick.tick('estimating pulse delta')
      pulseDeltaErrors = searchingPulseCountDip(pulseCounts, randomNumbers)

      # if self.debug:
      #   from pathlib import Path
      #   from uuid import uuid4
      #   from matplotlib.figure import Figure
      #   from matplotlib.backends.backend_agg import FigureCanvasAgg
      #   outputDirectory = Path('histograms')
      #   outputDirectory.mkdir(parents=True, exist_ok=True)
      #   figure = Figure(figsize=(10, 9), constrained_layout=True)
      #   FigureCanvasAgg(figure)
      #   axes = figure.subplots(3, 1)
      #   axes[0].plot(np.arange(histogramInPulse.size) * resolution, histogramInPulse)
      #   axes[0].set_title('histogramInPulse')
      #   axes[0].set_xlabel('Time in pulse')
      #   axes[0].set_ylabel('Counts')
      #   axes[1].plot(np.arange(pulseCounts.size), pulseCounts)
      #   axes[1].set_title('pulseCounts')
      #   axes[1].set_xlabel('Pulse index')
      #   axes[1].set_ylabel('Counts')
      #   axes[2].plot(np.arange(pulseDeltaErrors.size), pulseDeltaErrors)
      #   axes[2].set_title('pulseDeltaErrors')
      #   axes[2].set_xlabel('Pulse shift')
      #   axes[2].set_ylabel('Errors')
      #   figure.savefig(outputDirectory / f'syncAnalysis_{uuid4().hex}.png')

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
