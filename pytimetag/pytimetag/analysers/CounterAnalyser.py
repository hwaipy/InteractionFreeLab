__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

from pytimetag.Analyser import Analyser, Validator
import numpy as np
import numba


class CounterAnalyser(Analyser):
  def analysis(self, dataBlock):
    result = {}
    for ch in range(len(dataBlock.content)):
      result[str(ch)] = len(dataBlock.content[ch])
    return result


class FastCounterAnalyser(Analyser):
  def __init__(self):
    super().__init__()
    self.setConfiguration("Channels", [1], lambda x: True)
    self.setConfiguration("Frequency", 1000, Validator.int(1, 10000))

  def analysis(self, dataBlock):
    frequency = self.getConfiguration('Frequency')
    channels = self.getConfiguration('Channels')
    counts = {}
    for channel in channels:
      counts[str(channel)] = [int(c) for c in fastCountJIT(dataBlock.content[channel], frequency, dataBlock.dataTimeBegin, dataBlock.dataTimeEnd)]
    return {'CountSections': counts}

@numba.njit(cache=True)
def fastCountJIT(signalList, frequency, dataTimeBegin, dataTimeEnd):
  result = np.zeros(int(frequency), dtype='<i4')
  sectionIndices = ((signalList - dataTimeBegin) / (dataTimeEnd - dataTimeBegin) * frequency).astype('<i4')
  for i in sectionIndices:
    result[i] += 1
  return result