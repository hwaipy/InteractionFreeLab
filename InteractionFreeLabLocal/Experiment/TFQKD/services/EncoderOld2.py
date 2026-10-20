import math
# import time
# from ctypes import *
# import platform
import sys
from rich.progress import Progress
from threading import Thread
from asyncio import Event, get_event_loop
import numpy as np
import msgpack
import numba


class ModulatorConfig:
  def __init__(self, delay, waveformPeriodLength, waveformLength, sampleRate, randomNumberRange, waveformMod):
    self.delay = delay
    self.waveformPeriodLength = waveformPeriodLength
    self.waveformLength = waveformLength
    self.sampleRate = sampleRate
    self.randomNumberRange = randomNumberRange
    self.waveformMod = waveformMod

  def generateWaveformUnits(self):
    waveforms = []
    for i in range(0, self.randomNumberRange):
      waveform = self._generateWaveformUnit(i)
      waveforms.append(waveform)
    return waveforms

  def _generateWaveformUnit(self, randomNumber):
    width, amp, bias = self.waveformMod(randomNumber)
    pulseSample = math.ceil((width) * 1e-9 * self.sampleRate)
    totalSample = math.ceil(self.waveformPeriodLength)
    leadingSample = math.ceil((self.waveformPeriodLength - pulseSample) / 2)
    a = [bias] * leadingSample + [amp] * pulseSample + [bias] * (totalSample - leadingSample - pulseSample)
    return a


class AWGEncoder:
  def __init__(self, asyncInvoker, randonNumberRange=256, phaseSlice=16):
    self.awg = asyncInvoker
    self.randonNumberRange = randonNumberRange
    self.phaseSlice = phaseSlice
    self.config = {
        'sampleRate': 2e9,
        'randomNumbers': [i for i in range(randonNumberRange)],
        'waveformLength': None,
        'waveformUnitLength': 20,
        'ampAM1': [0.0, 0.1, 0.1, 0.1, 0.9],
        'ampAM2': [0.0, 0.1, 0.1, 0.1, 0.9],
        'ampPM1': [i / phaseSlice for i in range(phaseSlice)],
        'ampPM2': [i / phaseSlice for i in range(phaseSlice)],
        'biasAM1': [0.0] * 5,
        'biasAM2': [0.0] * 5,
        'biasPM1': [0.0] * phaseSlice,
        'biasPM2': [0.0] * phaseSlice,
        'widthAM1': [2.6, 5],
        'widthAM2': [2.6, 5],
        'widthPM1': 5,
        'widthPM2': 9.8,
        'delayAM1': 0,
        'delayAM2': 0,
        'delayPM1': 0,
        'delayPM2': 0,
        'gainAM1': 1,
        'gainPM1': 1,
    }
    # self.massiveService = None

  def configure(self, key, value):
    if self.config.__contains__(key):
      self.config[key] = value
    else:
      raise RuntimeError('Bad configuration')

  def __modAM1(self, randomNumber):
    rRef = (randomNumber & 0b1000000) >> 6
    rRefRev = (randomNumber & 1)  # 0 for not reverse, 1 for reverse
    rDecoy = (randomNumber & 0b11)
    para = self.config['widthAM1'][rRef], self.config['ampAM1'][4 if rRef == 1 else rDecoy], self.config['biasAM1'][4 if rRef == 1 else rDecoy]
    return para if not rRef or rRefRev == 0 else (para[0], para[2], para[1])

#   # def __modAM2(self, randomNumber):
#   #     rRef = (randomNumber & 0b1000000) >> 6
#   #     rDecoy = (randomNumber & 0b11)
#   #     return self.config['widthAM2'][rRef], self.config['ampAM2'][4 if rRef == 1 else rDecoy], self.config['biasAM2'][4 if rRef == 1 else rDecoy]

  def __modPM1(self, randomNumber):
    rPhase = (randomNumber & 0b111100) >> 2
    return self.config['widthPM1'], self.config['ampPM1'][rPhase], self.config['biasPM1'][rPhase]

#   # def __modPM2(self, randomNumber):
#   #     rPhase = (randomNumber & 0b111100) >> 2
#   #     return self.config['widthPM2'], self.config['ampPM2'][rPhase], self.config['biasPM2'][rPhase]

  def generateWaveformData(self, unitSize=6400000):
    randomNumbers = self.config['randomNumbers']
    if isinstance(randomNumbers, str):
      randomNumbers = msgpack.unpackb(self.massiveService.readMassive(randomNumbers))
    if isinstance(randomNumbers, list):
      randomNumbers = np.array(randomNumbers)
    if self.config['waveformLength'] and self.config['waveformUnitLength']:
      raise f'waveformLength and waveformUnitLength can not both be configed.'
    if self.config['waveformLength']:
      waveformLength = self.config['waveformLength']
      waveformPeriodLength = waveformLength / len(randomNumbers)
    else:
      waveformPeriodLength = self.config['waveformUnitLength']
      waveformLength = waveformPeriodLength * len(randomNumbers)
    if (waveformPeriodLength != int(waveformPeriodLength)):
      raise f'除不尽'
    waveformPeriodLength = int(waveformPeriodLength)
    modulatorConfigs = {
        'PM1': ModulatorConfig(self.config['delayPM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modPM1),
        'AM1': ModulatorConfig(self.config['delayAM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modAM1),
    }
    waveforms = {}
    waveformUnitsSet = []
    delaySamples = []
    for waveformName in modulatorConfigs.keys():
      config = modulatorConfigs.get(waveformName)
      delaySamples.append(int(config.delay * (config.sampleRate / 1e9)) % waveformLength)

      waveformUnits = config.generateWaveformUnits()
      for i in range(len(waveformUnits)):
        waveformUnits[i] = np.array([int(d * 65535) for d in waveformUnits[i]], dtype='int16')
      units = np.vstack(waveformUnits)
      waveformUnitsSet.append(units)

    buffer = generateFullWaveformDataJIT(randomNumbers, numba.typed.List(waveformUnitsSet), np.array(delaySamples))
    return buffer

  async def generateNewWaveform(self, address=0, returnWaveform=False, writeAWG=True):
    event = Event()
    loop = get_event_loop()
    result = None

    def func():
      nonlocal result
      try:
#         generatingWaveformDataLocally = True
#         generatingWaveformDataAdvance = 0

#         def fDL():
#           nonlocal generatingWaveformDataAdvance
#           while generatingWaveformDataLocally:
#             progress.update(task, advance=1)
#             generatingWaveformDataAdvance += 1
#             time.sleep(1)
#         tDL = Thread(target=fDL).start()
#         generatingWaveformDataLocally = False
#         progress.update(task, advance=(20 - generatingWaveformDataAdvance))
        progress = Progress()
        task = progress.add_task("Generating AWG waveforms...", total=100)
        progress.start()
        data = self.generateWaveformData()
        if self.awg and writeAWG:
          self.awg.turnOffAllChannels()
          time.sleep(0.2)
          self.awg.setGain(1, self.__getGainCode(self.config['gainPM1']))
          time.sleep(0.2)
          self.awg.setGain(2, self.__getGainCode(self.config['gainAM1']))
          time.sleep(0.2)
          self.awg.writeWaveformsData(data, address, lambda p: progress.update(task, advance=(p * 100)))
          time.sleep(0.2)
          self.awg.configOutput(address, len(data))
          time.sleep(0.2)
        if returnWaveform:
          reved = np.frombuffer(data, dtype='u2')
          result = reved.reshape((int(reved.shape[0] / 2), 2))
      except BaseException as e:
        import logging
        logging.exception(e)
      finally:
        progress.update(task, advance=100)
        progress.stop()

        loop.call_soon_threadsafe(event.set)

    Thread(target=func).start()
    await event.wait()
    return result

#   def reconfigOutput(self, address):
#     try:
#       self.awg.turnOffAllChannels()
#       time.sleep(0.2)
#       self.awg.configOutput(address, self.config['waveformLength'] * 4)
#     except BaseException as e:
#       import logging
#       logging.exception(e)

#   def startAllChannels(self):
#     self.awg.turnOnAllChannels()

#   def stopAllChannels(self):
#     self.awg.turnOffAllChannels()

#   def startChannel(self, name):
#     self.__setChannelStatus(name, True)

#   def stopChannel(self, name):
#     self.__setChannelStatus(name, False)

#   def __getGainCode(self, gain):
#     if gain < 1 or gain > 2:
#       raise ValueError('Gain should be in the range of [1, 2].')
#     gainCode = int((gain - 1) * 1023)
#     gainCode += 512
#     gainCode %= 1024
#     # print(f'gain {gain} as code {gainCode}')
#     return gainCode

# def generateFullWaveformDataJIT(randomNumbers, waveformUnits, delaySamples):
#   buffer = np.zeros(int(randomNumbers.shape[0] * waveformUnits[0].shape[1]) * 4, dtype='int8')
#   waveformLength = randomNumbers.shape[0] * waveformUnits[0].shape[1]
#   waveformPeriodLength = len(waveformUnits[0][0])

#   for channel in range(2):
#     waveformPosition = delaySamples[channel]
#     waveformUnit = waveformUnits[channel]
#     channelForBuffer = channel * 2
#     if (waveformPosition >= waveformLength): waveformPosition -= waveformLength
#     if (waveformPosition < 0): waveformPosition += waveformLength
#     iRN = int(waveformPosition / waveformPeriodLength)
#     positionOfPeriod = int(waveformPosition % waveformPeriodLength)

#     for p in range(waveformLength):
#       if (waveformPosition >= waveformLength): waveformPosition -= waveformLength
#       if (waveformPosition < 0): waveformPosition += waveformLength
#       rn = randomNumbers[iRN]
#       w = waveformUnit[rn][positionOfPeriod]
#       pByte = p * 4
#       buffer[pByte + channelForBuffer] = (w & 0xFF)
#       buffer[pByte + 1 + channelForBuffer] = (w >> 8)
#       waveformPosition += 1
#       positionOfPeriod += 1
#       if (positionOfPeriod >= waveformPeriodLength):
#         positionOfPeriod = 0
#         iRN += 1
#         if (iRN >= len(randomNumbers)): iRN = 0

#     return buffer

@numba.njit(parallel=True, cache=True)
def generateFullWaveformDataJIT(randomNumbers, waveformUnits, delaySamples):
  sectionSize = 10000000
  sectionNum = int(np.ceil(len(randomNumbers) * waveformUnits[0].shape[1] / sectionSize))
  waveformLength = randomNumbers.shape[0] * waveformUnits[0].shape[1]
  buffer = np.zeros(waveformLength * 4, dtype='int8')
  for iSection in numba.prange(sectionNum):
    begin = int(iSection * sectionSize)
    end = int((iSection + 1) * sectionSize)
    if end > waveformLength: end = waveformLength
    generateFullWaveformDataSectionJIT(begin, end, randomNumbers, waveformUnits, delaySamples, buffer)
  return buffer

@numba.njit(cache=True)
def generateFullWaveformDataSectionJIT(begin, end, randomNumbers, waveformUnits, delaySamples, buffer):
  waveformPeriodLength = len(waveformUnits[0][0])
  waveformLength = randomNumbers.shape[0] * waveformUnits[0].shape[1]
  for channel in range(2):
    # waveformPosition = delaySamples[channel]
    waveformUnit = waveformUnits[channel]
    delaySample = delaySamples[channel]
    channelForBuffer = channel * 2
    # if (waveformPosition >= waveformLength): waveformPosition -= waveformLength
    # if (waveformPosition < 0): waveformPosition += waveformLength
    # iRN = int(waveformPosition / waveformPeriodLength)
    # positionOfPeriod = int(waveformPosition % waveformPeriodLength)
    for p in range(begin, end):
      realP = p - delaySample
      if (realP >= waveformLength): realP -= waveformLength
      if (realP < 0): realP += waveformLength
      iRN = int(realP / waveformPeriodLength)
      positionOfPeriod = int(realP % waveformPeriodLength)
      rn = randomNumbers[iRN]
      w = waveformUnit[rn][positionOfPeriod]
      pByte = p * 4
      buffer[pByte + channelForBuffer] = (w & 0xFF)
      buffer[pByte + 1 + channelForBuffer] = (w >> 8)

# @numba.njit(cache=True)
# def generateFullWaveformDataSectionJIT(randomNumbers, waveformUnits, delaySamples, buffer, pBuffer, pBufferLimit):
#   print(randomNumbers.shape, delaySamples, buffer.shape, pBuffer)
#   waveformLength = randomNumbers.shape[0] * waveformUnits[0].shape[1]
#   waveformPeriodLength = len(waveformUnits[0][0])
#   for channel in range(2):
#     waveformPosition = delaySamples[channel]
#     waveformUnit = waveformUnits[channel]
#     channelForBuffer = channel * 2
#     if (waveformPosition >= waveformLength): waveformPosition -= waveformLength
#     if (waveformPosition < 0): waveformPosition += waveformLength
#     iRN = int(waveformPosition / waveformPeriodLength)
#     positionOfPeriod = int(waveformPosition % waveformPeriodLength)
#     for p in range(waveformLength):
#       if (waveformPosition >= waveformLength): waveformPosition -= waveformLength
#       if (waveformPosition < 0): waveformPosition += waveformLength
#       rn = randomNumbers[iRN]
#       if (pBuffer == 264000000):
#         print('ready to error')
#         print(iRN, rn, positionOfPeriod)
#       w = waveformUnit[rn][positionOfPeriod]
#       if (pBuffer == 264000000):
#         print('no error')
#       pByte = p * 4
#       if (pBuffer == 264000000):
#         print(p)
#       if (pBuffer == 264000000):
#         print(pBuffer + pByte + channelForBuffer)
#       buffer[pBuffer + pByte + channelForBuffer] = (w & 0xFF)
#       buffer[pBuffer + pByte + 1 + channelForBuffer] = (w >> 8)
#       waveformPosition += 1
#       positionOfPeriod += 1
#       if (positionOfPeriod >= waveformPeriodLength):
#         positionOfPeriod = 0
#         iRN += 1
#         if (iRN >= len(randomNumbers)): iRN = 0

# def showWaveform(waveforms, showRange=None):
#   import matplotlib.pyplot as plt
#   sampleCount = len(waveforms[0])
#   times = np.linspace(0, 0.5 * (sampleCount - 1), sampleCount)

#   fig, axs = plt.subplots(4, 1)
#   fig.set_size_inches(18, 10)

#   for i in range(len(waveforms)):
#     axs[i].plot(times, waveforms[i])
#     axs[i].grid()
#   plt.savefig('test.png')


def testAndBenchMark():
  import time
  from Experiment.TFQKD.services.fastencoderNative.Encoder import AWGEncoder as BaseLine
  import asyncio

  async def test():
    encoder = AWGEncoder(None)
    baseline = BaseLine(None)
    rndsShort = np.array([int(i/2) for i in range(256)])
    rndsLong = np.array([i % 128 for i in range(20000000)])

    checkShort = True
    checkLong = True
    click = True
#     addressCheck = False
    largeDelay = True
    real = True

    if checkShort:
      encoder.configure('randomNumbers', rndsShort)
      waveform = await encoder.generateNewWaveform(returnWaveform=True)
      baseline.configure('randomNumbers', rndsShort)
      waveformBaseline = await baseline.generateNewWaveform(returnWaveform=True)
      print(f'Check short random numbers: {np.all(waveform == waveformBaseline)}')

    if checkLong:
      encoder.configure('randomNumbers', rndsLong)
      waveform = await encoder.generateNewWaveform(returnWaveform=True)
      baseline.configure('randomNumbers', rndsLong)
      waveformBaseline = await baseline.generateNewWaveform(returnWaveform=True)
      print(f'Check long random numbers: {np.all(waveform == waveformBaseline)}')

    if click:
      dataSizeMB = len(rndsLong) * 20 * 4 / 1000000
      t1 = time.time()
      encoder.configure('randomNumbers', rndsLong)
      waveform = await encoder.generateNewWaveform(1024000000, returnWaveform=False)
      t2 = time.time()
      t3 = time.time()
      print(f'{len(rndsLong)} pulses ({dataSizeMB:.1f} MB) done in {t2 - t1:.3f} s. (Baseline {t3 - t2:.3f} s.)')

#     if addressCheck:
#       encoder.configure('randomNumbers', ([15] * 10 + [64] * 90) * 1000)
#       encoder.configure('waveformLength', 100000 * 20)
#       waveform = await encoder.generateNewWaveform(0)
#       time.sleep(5)
#       encoder.configure('randomNumbers', ([15] * 50 + [64] * 50) * 1000)
#       encoder.configure('waveformLength', 100000 * 20)
#       waveform = await encoder.generateNewWaveform(1024000000)
#       time.sleep(5)
#       while True:
#         encoder.awg.turnOffAllChannels()
#         time.sleep(0.2)
#         encoder.awg.configOutput(0, 100000 * 20)
#         time.sleep(10)
#         encoder.awg.turnOffAllChannels()
#         time.sleep(0.2)
#         encoder.awg.configOutput(1024000000, 100000 * 20)
#         time.sleep(10)

    if real:
      encoder.configure('sampleRate', 2e9)
      encoder.configure('waveformLength', None)
      encoder.configure('waveformUnitLength', 20)
      encoder.configure('randomNumbers', rndsLong)

      encoder.configure('biasAM1', [0.47] * 4 + [0.0])
      encoder.configure('ampPM1', [(i / 16 * 0.69) for i in range(16)])  # V=0.32 分通道通过率34.88%
      encoder.configure('widthAM1', [1.2, 10])  # [signal, reference]
      encoder.configure('widthPM1', 10)
      globalDelay = 112154930.0
      encoder.configure('delayAM1', globalDelay)
      encoder.configure('delayPM1', globalDelay + 35)  # -56.5
      encoder.configure('gainAM1', 1)
      encoder.configure('gainPM1', 1)

      delays = [-78334234, 168837212.4]
      encoder.configure('delayAM1', delays[0])
      encoder.configure('delayPM1', delays[1])
      waveform = await encoder.generateNewWaveform(returnWaveform=True)
      print(f'Check delay done, no exception.')

    if largeDelay:
      delays = [-21, 78]
      encoder.configure('randomNumbers', rndsShort)
      encoder.configure('delayAM1', delays[0])
      encoder.configure('delayPM1', delays[1])
      waveform = await encoder.generateNewWaveform(returnWaveform=True)
      extDelay = -200 * len(rndsShort)
      encoder.configure('delayAM1', extDelay + delays[0])
      encoder.configure('delayPM1', extDelay + delays[1])
      waveformDelayed = await encoder.generateNewWaveform(returnWaveform=True)
      print(f'Check large delay: {np.all(waveform == waveformDelayed)}')

  loop = asyncio.get_event_loop()
  loop.run_until_complete(test())


if __name__ == '__main__':
  testAndBenchMark()
  sys.exit(0)

  from interactionfreepy import IFWorker, IFLoop
  from Instrument.WaveformGenerator.USTCDAC.USTCAWGUDPServer import AWGUDPServer
  import sys

  serviceName = sys.argv[1]
  ip = sys.argv[2]

  dev = AWGUDPServer(ip)
  print(f'Device ({ip}) connected.')

  encoder = AWGEncoder(dev, randonNumberRange=256)  # {'AM1': 2, 'PM1': 1}

  worker = IFWorker('tcp://192.168.25.5:224', serviceName, encoder, force=True)
  encoder.massiveService = worker.TF_FileStorage
  print(f'Encoder Service ({serviceName}) started.')

  IFLoop.join()
