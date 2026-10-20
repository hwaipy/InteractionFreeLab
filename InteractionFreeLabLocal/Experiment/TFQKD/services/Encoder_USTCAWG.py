import math
import sys
from threading import Thread
from asyncio import Event, get_event_loop
import numpy as np
import msgpack
import time

class ModulatorConfig:
  def __init__(self, delay, waveformPeriodLength, waveformLength, sampleRate, reversePattern, randomNumberRange, waveformMod):
    self.delay = delay
    self.waveformPeriodLength = waveformPeriodLength
    self.waveformLength = waveformLength
    self.sampleRate = sampleRate
    self.randomNumberRange = randomNumberRange
    self.waveformMod = waveformMod
    self.reversePattern = reversePattern

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
    baseWaveform = np.array(a)
    waveformMap = {}
    for pattern in set(self.reversePattern):
      waveformMap[pattern] = (baseWaveform - bias) * pattern + bias
    return waveformMap


class AWGEncoder:
  def __init__(self, asyncInvoker, randonNumberRange=256):
    self.awg = asyncInvoker
    self.randonNumberRange = randonNumberRange
    self.config = {
      'sampleRate': 2e9,
      'randomNumbers': [i for i in range(randonNumberRange)],
      'waveformLength': None,
      'waveformUnitLength': 20,
      'widthAM1': [2.6, 5],
      'widthAM2': [2.6, 5],
      'widthPM1': 9.8,
      'widthPM2': 9.8,
      'delayAM1': 0,
      'delayAM2': 0,
      'delayPM1': 0,
      'delayPM2': 0,
      'ampAM1': [0.47, 0.618, 0.679, 0.73, 1],
      'ampAM2': [0.47, 0.618, 0.679, 0.73, 1],
      'ampPM1': [i / 15 for i in range(16)],
      'ampPM2': [i / 15 for i in range(16)],
      'ampPM1Refs': None,
      'ampPM2Refs': None,
      'biasAM1': [0.5] * 5,
      'biasAM2': [0.5] * 5,
      'biasPM1': [0 for i in range(16)],
      'biasPM2': [0 for i in range(16)],
      'reversePatternAM1': [1, -1],
      'reversePatternAM2': [1, -1],
      'reversePatternPM1': [1],
      'reversePatternPM2': [1],
      'precompensatePM1': ['None'],
      'precompensatePM2': ['None'],
    }

  def configure(self, key, value):
    if self.config.__contains__(key):
      self.config[key] = value
    else:
      raise RuntimeError('Bad configuration')

  def __modAM1(self, randomNumber):
    rRef = (randomNumber & 0b1000000) >> 6
    rDecoy = (randomNumber & 0b11)
    para = self.config['widthAM1'][rRef], self.config['ampAM1'][4 if rRef == 1 else rDecoy], self.config['biasAM1'][4 if rRef == 1 else rDecoy]
    return para

  def __modAM2(self, randomNumber):
    rRef = (randomNumber & 0b1000000) >> 6
    rDecoy = (randomNumber & 0b11)
    para = self.config['widthAM2'][rRef], self.config['ampAM2'][4 if rRef == 1 else rDecoy], self.config['biasAM2'][4 if rRef == 1 else rDecoy]
    return para

  def __modPM1(self, randomNumber):
    rRef = (randomNumber & 0b1000000) >> 6
    ampPM1 = self.config['ampPM1']
    ampPM1Refs = self.config['ampPM1Refs']
    if ampPM1Refs is None: ampPM1Refs = ampPM1
    rPhase = (randomNumber & 0b111100) >> 2
    return self.config['widthPM1'], (ampPM1 if rRef == 0 else ampPM1Refs)[rPhase], self.config['biasPM1'][rPhase]

  def __modPM2(self, randomNumber):
    rRef = (randomNumber & 0b1000000) >> 6
    ampPM2 = self.config['ampPM2']
    ampPM2Refs = self.config['ampPM2Refs']
    if ampPM2Refs is None: ampPM2Refs = ampPM2
    rPhase = (randomNumber & 0b111100) >> 2
    return self.config['widthPM2'], (ampPM2 if rRef == 0 else ampPM2Refs)[rPhase], self.config['biasPM2'][rPhase]

  def generateNewWaveform(self, returnWaveform=False, writeAWG=True):
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
        'AM1': ModulatorConfig(self.config['delayAM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.config['reversePatternAM1'], self.randonNumberRange, self.__modAM1),
        'AM2': ModulatorConfig(self.config['delayAM2'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.config['reversePatternAM2'],self.randonNumberRange, self.__modAM2),
        'PM1': ModulatorConfig(self.config['delayPM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.config['reversePatternPM1'], self.randonNumberRange, self.__modPM1),
        'PM2': ModulatorConfig(self.config['delayPM2'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.config['reversePatternPM2'], self.randonNumberRange, self.__modPM2),
    }

    waveforms = []
    for name in modulatorConfigs:
      config = modulatorConfigs[name]
      waveformUnits = config.generateWaveformUnits()
      wfs = [waveformUnits[randomNumbers[i]][config.reversePattern[i % (len(config.reversePattern))]] for i in range(len(randomNumbers))]
      wfs = np.array(wfs)
      wf = ((np.reshape(wfs, (len(wfs) * len(wfs[0]), )) * 2 - 1) * 32760).astype('int')
      if name == 'PM1' and self.config['precompensatePM1'][0] != 'None':
        wf = self.__preCompensatePM(wf, self.config['precompensatePM1'])
      if name == 'PM2' and self.config['precompensatePM2'][0] != 'None':
        wf = self.__preCompensatePM(wf, self.config['precompensatePM2'])
      delay = int(config.delay * (config.sampleRate / 1e9)) % waveformLength
      waveforms.append(list(wf[delay:]) + list(wf[:delay]))

    if self.awg is not None:
      self.awg.generateWaveform(waveforms)
    else:
      return waveforms

  def __preCompensatePM(self, waveform, config):
    if config[0] == 'linear':
      realChangingPoints = []
      for i in range(len(waveform)):
        if waveform[i] != waveform[i - 1]:
          realChangingPoints.append(i)
      changingUnit = self.config['waveformUnitLength']
      changingPoints = [i * changingUnit for i in range(len(self.config['randomNumbers']))]
      changingValues = [waveform[i] - waveform[i - 1] for i in changingPoints]
      for i in range(len(changingPoints)):
        addi = np.linspace(config[1], config[2], changingUnit, True) * changingValues[i]
        addi = addi.astype(waveform.dtype)
        waveform[changingPoints[i]: changingPoints[i] + changingUnit] += addi
      if np.max(waveform) > 32767 or np.min(waveform) < -32766: raise ArithmeticError('value out of range after pre compensation')
    else:
      raise ArgumentError('Bad configuration: ' + config)
    return waveform

  def __getGainCode(self, gain):
    if gain < 1 or gain > 2:
      raise ValueError('Gain should be in the range of [1, 2].')
    gainCode = int((gain - 1) * 1023)
    gainCode += 512
    gainCode %= 1024
    # print(f'gain {gain} as code {gainCode}')
    return gainCode

  def setGain(self, gain):
    self.awg.setGain(1, self.__getGainCode(gain))
    self.awg.setGain(2, self.__getGainCode(gain))
    self.awg.setGain(3, self.__getGainCode(gain))
    self.awg.setGain(4, self.__getGainCode(gain))


if __name__ == '__main__':
  from interactionfreepy import IFWorker, IFLoop
  import sys
  import requests

  serviceName = sys.argv[1] if len(sys.argv) > 1 else 'USTCAWG_Encoder_Test'
  brokerAddress = sys.argv[2] if len(sys.argv) > 2 else '10.1.1.1:224'
  devAddress = sys.argv[3] if len(sys.argv) > 3 else None

  from Instrument.WaveformGenerator.USTCDAC3.USTCAWGUDPServer import AWGUDPServer
  if devAddress: dev = AWGUDPServer(devAddress)
  else: dev = None
  encoder = AWGEncoder(dev, randonNumberRange=256)

  worker = IFWorker(brokerAddress, serviceName, encoder, force=True)
  print(f'Encoder Service ({serviceName}) started.')

  IFLoop.join()


  np.random.seed(100)
  encoder.configure('randomNumbers', np.random.randint(0, 127, 1000))
  # encoder.configure('randomNumbers', [int(i) for i in range(64)])
  encoder.configure('precompensatePM1', ['linear', 0.1, 0])
  encoder.configure('precompensatePM2', ['linear', 0.2, 0])

  V = 0.7
  encoder.configure('ampPM1', [(i - 7.5) / 16 * V + 0.5 for i in range(16)])
  encoder.configure('precompensatePM1', ['linear', 0, 0])
  encoder.configure('biasPM1', [0.5] * 16)
  encoder.configure('reversePatternPM1', [1] * 100 + [0.5] * 100)
  encoder.configure('ampPM2', [(i - 7.5) / 16 * V + 0.5 for i in range(16)])
  encoder.configure('precompensatePM2', ['linear', 0.2, 0])
  encoder.configure('biasPM2', [0.5] * 16)
  encoder.configure('reversePatternPM2', [1] * 100 + [0.5] * 100)

  t1 = time.time()
  w = encoder.generateNewWaveform()
  t2 = time.time()
  print(t2 - t1)
  print(max(w[0]), min(w[0]))

  import matplotlib.pyplot as plt
  # plt.plot(w[0])
  # plt.plot(w[1])
  plt.plot(w[2])
  plt.plot(w[3])
  # plt.show()
  plt.savefig('Encoder_USTCAWG.png', dpi=300)