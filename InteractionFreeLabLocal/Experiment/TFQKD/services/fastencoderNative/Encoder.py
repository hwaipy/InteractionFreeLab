import math
import time
from ctypes import *
import platform
import sys
from rich.progress import Progress
from threading import Thread
from asyncio import Event, get_event_loop
import numpy as np
import msgpack
import os

nativeLib = cdll.LoadLibrary(f"{os.path.realpath(__file__)[:-10]}encoder.{'so' if platform.system() == 'Linux' else 'dll'}")

class ModulatorConfig:
  def __init__(self, delay, waveformPeriodLength, waveformLength, sampleRate, randomNumberRange, waveformMod):
    self.delay = delay
    self.waveformPeriodLength = waveformPeriodLength
    self.waveformLength = waveformLength
    self.sampleRate = sampleRate
    self.randomNumberRange = randomNumberRange
    self.waveformMod = waveformMod

  # def generateWaveform(self, randomNumbers):
  #     waveformUnits = self.generateWaveformUnits()
  #     waveformPositions = [i * self.waveformPeriodLength for i in range(0, len(randomNumbers))]
  #     waveformPositionsInt = [math.floor(i) for i in waveformPositions + [self.waveformLength]]
  #     waveformLengthes = [waveformPositionsInt[i + 1] - waveformPositionsInt[i] for i in range(0, len(randomNumbers))]
  #     waveform = []

  #     for i in range(0, len(randomNumbers)):
  #         rn = randomNumbers[i]
  #         length = waveformLengthes[i]
  #         waveform += waveformUnits[rn][:length]
  #         if len(waveform) >= self.waveformLength: break
  #     delaySample = -int(self.delay * (self.sampleRate / 1e9))
  #     waveform = waveform[delaySample:] + waveform[:delaySample]
  #     return waveform[:self.waveformLength]

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
        # 'ampAM2': [0.0, 0.1, 0.1, 0.1, 0.9],
        'ampPM1': [i / phaseSlice for i in range(phaseSlice)],
        # 'ampPM2': [i / phaseSlice for i in range(phaseSlice)],
        'biasAM1': [0.0] * 5,
        # 'biasAM2': [0.0] * 5,
        'biasPM1': [0.0] * phaseSlice,
        # 'biasPM2': [0.0] * phaseSlice,
        'widthAM1': [2.6, 5],
        # 'widthAM2': [2.6, 5],
        'widthPM1': 5,
        # 'widthPM2': 9.8,
        'delayAM1': 0,
        # 'delayAM2': 0,
        'delayPM1': 0,
        # 'delayPM2': 0,
        'gainAM1': 1,
        'gainPM1': 1,
    }
    self.isRef = False
    self.massiveService = None

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
    # return para if not rRef or rRefRev == 0 else (para[0], para[2], para[1])
    # 危险！临时
    # print('AM', randomNumber, para if not rRef or rRefRev == 0 else (para[0], 0, para[2]))
    return para if not rRef or rRefRev == 0 else (para[0], 0, para[2])

  # def __modAM2(self, randomNumber):
  #     rRef = (randomNumber & 0b1000000) >> 6
  #     rDecoy = (randomNumber & 0b11)
  #     return self.config['widthAM2'][rRef], self.config['ampAM2'][4 if rRef == 1 else rDecoy], self.config['biasAM2'][4 if rRef == 1 else rDecoy]

  def __modPM1(self, randomNumber):
    rPhase = (randomNumber & 0b111100) >> 2
    return self.config['widthPM1'], self.config['ampPM1'][rPhase], self.config['biasPM1'][rPhase]

  # def __modPM2(self, randomNumber):
  #     rPhase = (randomNumber & 0b111100) >> 2
  #     return self.config['widthPM2'], self.config['ampPM2'][rPhase], self.config['biasPM2'][rPhase]

  # def generateWaveforms(self):
  #     waveformPeriodLength = self.config['waveformLength'] / len(self.config['randomNumbers'])
  #     modulatorConfigs = {
  #         'PM1': ModulatorConfig(self.config['delayPM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modPM1),
  #         'AM1': ModulatorConfig(self.config['delayAM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modAM1),
  #         # 'AM2': ModulatorConfig(self.config['delayAM2'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modAM2),
  #         # 'PM2': ModulatorConfig(self.config['delayPM2'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modPM2),
  #     }
  #     waveforms = {}
  #     for waveformName in modulatorConfigs.keys():
  #         config = modulatorConfigs.get(waveformName)
  #         waveforms[waveformName] = config.generateWaveform(self.config['randomNumbers'])
  #     return waveforms

  def generateWaveformDataLocally(self, unitSize=6400000):
    randomNumbers = self.config['randomNumbers']
    if isinstance(randomNumbers, str):
      randomNumbers = msgpack.unpackb(self.massiveService.readMassive(randomNumbers))
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
        waveformUnits[i] = [int(d * 65535) for d in waveformUnits[i]]
      units = []
      for waveformUnit in waveformUnits:
        units += waveformUnit
      units = (c_ushort * len(units))(*units)
      waveformUnitsSet.append(units)

    buffer = bytes(int(waveformLength) * 4)

    nativeLib.setWaveformPattern(
        (c_int * len(randomNumbers))(*randomNumbers),
        (c_int * len(randomNumbers))(*randomNumbers),
        len(randomNumbers),
        c_int(waveformPeriodLength)
    )
    nativeLib.setWaveformUnits(0, waveformUnitsSet[0], len(waveformUnitsSet[0]))
    nativeLib.setWaveformUnits(1, waveformUnitsSet[1], len(waveformUnitsSet[1]))
    nativeLib.setDelay(0, delaySamples[0])
    nativeLib.setDelay(1, delaySamples[1])

    nativeLib.generateFullWaveformData(buffer)

    return buffer

  async def generateNewWaveform(self, address=0, returnWaveform=False, writeAWG=True):
    event = Event()
    loop = get_event_loop()
    result = None

    def func():
      nonlocal result
      progress = Progress()
      task = progress.add_task("Generating AWG waveforms...", total=100)
      progress.start()
      try:
        generatingWaveformDataLocally = True
        generatingWaveformDataAdvance = 0

        def fDL():
          nonlocal generatingWaveformDataAdvance
          while generatingWaveformDataLocally:
            progress.update(task, advance=1)
            generatingWaveformDataAdvance += 1
            time.sleep(1)
        tDL = Thread(target=fDL).start()
        data = self.generateWaveformDataLocally()
        generatingWaveformDataLocally = False
        progress.update(task, advance=(20 - generatingWaveformDataAdvance))
        if self.awg and writeAWG:
          self.awg.turnOffAllChannels()
          time.sleep(0.2)
          self.awg.setGain(1, self.__getGainCode(self.config['gainPM1']))
          time.sleep(0.2)
          self.awg.setGain(2, self.__getGainCode(self.config['gainAM1']))
          time.sleep(0.2)
          self.awg.writeWaveformsData(data, address, lambda p: progress.update(task, advance=(p * 80)))
          time.sleep(0.2)
          self.awg.configOutput(address, len(data))
          time.sleep(0.2)
        if returnWaveform:
          reved = np.frombuffer(data, dtype='u2')
          result = reved.reshape((int(reved.shape[0] / 2), 2))
          # result = [[int(d) for d in reved[:, 0]], [int(d) for d in reved[:, 1]]]
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

  def reconfigOutput(self, address):
    try:
      self.awg.turnOffAllChannels()
      time.sleep(0.2)
      self.awg.configOutput(address, self.config['waveformLength'] * 4)
    except BaseException as e:
      import logging
      logging.exception(e)

  def startAllChannels(self):
    self.awg.turnOnAllChannels()

  def stopAllChannels(self):
    self.awg.turnOffAllChannels()

  def startChannel(self, name):
    self.__setChannelStatus(name, True)

  def stopChannel(self, name):
    self.__setChannelStatus(name, False)

  def __getGainCode(self, gain):
    if gain < 1 or gain > 2:
      raise ValueError('Gain should be in the range of [1, 2].')
    gainCode = int((gain - 1) * 1023)
    gainCode += 512
    gainCode %= 1024
    # print(f'gain {gain} as code {gainCode}')
    return gainCode


def showWaveform(waveforms, showRange=None):
  import matplotlib.pyplot as plt
  sampleCount = len(waveforms[0])
  times = np.linspace(0, 0.5 * (sampleCount - 1), sampleCount)

  fig, axs = plt.subplots(4, 1)
  fig.set_size_inches(18, 10)

  for i in range(len(waveforms)):
    axs[i].plot(times, waveforms[i])
    axs[i].grid()
  plt.savefig('test.png')


def testAndBenchMark():
  import time
  from Experiment.TFQKD.services.Encoder import AWGEncoder as BaseLine
  from threading import Lock
  import asyncio

  async def test():
    encoder = AWGEncoder(None)
    baseline = BaseLine(None)
    rndsShort = [int(i/2) for i in range(256)]
    rndsLong = [i % 128 for i in range(1000000)]
    encoder.configure('sampleRate', 2e9)
    baseline.configure('sampleRate', 2e9)
    encoder.configure('delayAM1', -1.522)
    encoder.configure('delayPM1', 500.441)
    baseline.configure('delayAM1', -1.522)
    baseline.configure('delayPM1', 500.441)
    encoder.configure('ampAM1', [0.5, 0.6, 0.65, 0.7, 1])
    encoder.configure('biasAM1', [0.5, 0.5, 0.5, 0.5, 0])
    encoder.configure('widthAM1', [2.6, 1])
    baseline.configure('ampAM1', [0.5, 0.6, 0.65, 0.7, 1])
    baseline.configure('biasAM1', [0.5, 0.5, 0.5, 0.5, 0])
    baseline.configure('widthAM1', [2.6, 1])

    check = True
    click = False
    addressCheck = False
    refrev = False
    largeDelay = False

    if check:
      encoder.configure('randomNumbers', rndsShort)
      waveform = await encoder.generateNewWaveform(returnWaveform=True)
      baseline.configure('randomNumbers', rndsShort)
      baseline.configure('waveformLength', len(rndsShort) * 20)
      waveformBaseline = baseline.generateNewWaveform(returnWaveform=True)
      waveformsTBWBaseline = []
      for waveformName in waveformBaseline:
        waveformsTBWBaseline.append([int(d * 65535) for d in waveformBaseline[waveformName]])
      print(waveform == waveformsTBWBaseline)

    if refrev:
      encoder.configure('widthAM1', [2.6, 10])
      waveform = await encoder.generateNewWaveform(0, returnWaveform=True)
      showWaveform(waveform)

    if click:
      t1 = time.time()
      encoder.configure('randomNumbers', rndsLong)
      encoder.configure('waveformLength', len(rndsLong) * 20)
      waveform = await encoder.generateNewWaveform(1024000000)
      t2 = time.time()
      dataSizeMB = len(rndsLong) * 20 * 4 / 1000000
      print(f'{len(rndsLong)} pulses ({dataSizeMB:.1f} MB) done in {t2 - t1:.3f} s. Full time expected to be {(t2 - t1) / dataSizeMB * 1600:.3f} s.')

    if addressCheck:
      encoder.configure('randomNumbers', ([15] * 10 + [64] * 90) * 1000)
      encoder.configure('waveformLength', 100000 * 20)
      waveform = await encoder.generateNewWaveform(0)
      time.sleep(5)
      encoder.configure('randomNumbers', ([15] * 50 + [64] * 50) * 1000)
      encoder.configure('waveformLength', 100000 * 20)
      waveform = await encoder.generateNewWaveform(1024000000)
      time.sleep(5)
      while True:
        encoder.awg.turnOffAllChannels()
        time.sleep(0.2)
        encoder.awg.configOutput(0, 100000 * 20)
        time.sleep(10)
        encoder.awg.turnOffAllChannels()
        time.sleep(0.2)
        encoder.awg.configOutput(1024000000, 100000 * 20)
        time.sleep(10)

    if largeDelay:
      delay = -21
      encoder.configure('delayAM1', delay)
      encoder.configure('delayPM1', delay)
      baseline.configure('delayAM1', delay)
      baseline.configure('delayPM1', delay)
      rnds = [i for i in range(2)]
      encoder.configure('randomNumbers', rnds)
      encoder.configure('waveformLength', len(rnds) * 20)
      waveform = await encoder.generateNewWaveform(returnWaveform=True)
      baseline.configure('randomNumbers', rnds)
      baseline.configure('waveformLength', len(rnds) * 20)
      waveformBaseline = baseline.generateNewWaveform(returnWaveform=True)
      waveformsTBWBaseline = []
      for waveformName in waveformBaseline:
        waveformsTBWBaseline.append([int(d * 65535) for d in waveformBaseline[waveformName]])
      print(waveform == waveformsTBWBaseline)
      print(waveform[0] == waveformsTBWBaseline[0])
      print(waveform[1] == waveformsTBWBaseline[1])
      print(waveform[1])
      print(waveformsTBWBaseline[1])

  loop = asyncio.get_event_loop()
  loop.run_until_complete(test())


if __name__ == '__main__':
  # testAndBenchMark()
  # sys.exit(0)

  from interactionfreepy import IFWorker, IFLoop
  from Instrument.WaveformGenerator.USTCDAC.USTCAWGUDPServer import AWGUDPServer
  import sys

  serviceName = sys.argv[1]
  ip = sys.argv[2]

  dev = AWGUDPServer(ip)
  print(f'Device ({ip}) connected.')

  encoder = AWGEncoder(dev, randonNumberRange=256)  # {'AM1': 2, 'PM1': 1}

  worker = IFWorker('tcp://192.168.25.5:1061', serviceName, encoder, force=True)
  encoder.massiveService = worker.TF_FileStorage
  print(f'Encoder Service ({serviceName}) started.')

  IFLoop.join()
