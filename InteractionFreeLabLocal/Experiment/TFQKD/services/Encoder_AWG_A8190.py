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
      'sampleRate': 12e9,
      'startMode': 'TRIGGERED_CONTINUOUS',
      'randomNumbers': [i for i in range(randonNumberRange)],
      'waveformLength': None,
      'waveformUnitLength': 250,
      'widthAM1': [2.6, 5],
      'widthAM2': [2.6, 5],
      'widthPM1': 9,
      'widthPM2': 9.8,
      'delayAM1': 0,
      'delayAM2': 0,
      'delayPM1': 0,
      'delayPM2': 0,
      'ampAM1': [0.5, 0.618, 0.679, 0.73, 1],
      'ampAM2': [0.5, 0.618, 0.679, 0.73, 1],
      'ampPM1': [i / 15 for i in range(16)],
      'ampPM2': [i / 15 for i in range(16)],
      'biasAM1': [0.5] * 5,
      'biasAM2': [0.5] * 5,
      'biasPM1': [0 for i in range(16)],
      'biasPM2': [0 for i in range(16)],
      'reversePatternAM1': [1, -1],
      'reversePatternAM2': [1, -1],
      'reversePatternPM1': [1],
      'reversePatternPM2': [1],
      'precompensatePM1': ['None']
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
    rPhase = (randomNumber & 0b111100) >> 2
    return self.config['widthPM1'], self.config['ampPM1'][rPhase], self.config['biasPM1'][rPhase]

  def __modPM2(self, randomNumber):
    rPhase = (randomNumber & 0b111100) >> 2
    return self.config['widthPM2'], self.config['ampPM2'][rPhase], self.config['biasPM2'][rPhase]

  def generateNewWaveform(self, returnWaveform=False, writeAWG=True):
    print('generating new wf')
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
      'PM1': ModulatorConfig(self.config['delayPM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.config['reversePatternPM1'], self.randonNumberRange, self.__modPM1),
      'AM1': ModulatorConfig(self.config['delayAM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.config['reversePatternAM1'], self.randonNumberRange, self.__modAM1),
    }

    waveforms = []
    for name in modulatorConfigs:
      config = modulatorConfigs[name]
      waveformUnits = config.generateWaveformUnits()
      wfs = [waveformUnits[randomNumbers[i]][config.reversePattern[i % (len(config.reversePattern))]] for i in range(len(randomNumbers))]
      print('before do sth')
      print(type(wfs))
      print(len(wfs), len(wfs[0]), len(wfs[1]), len(wfs[-1]))
      wfs = np.array(wfs)
      print('done')
      wf = np.reshape(wfs, (len(wfs) * len(wfs[0]), )) * 2 - 1
      if name == 'PM1' and self.config['precompensatePM1'][0] != 'None':
        wf = self.__preCompensatePM(wf, self.config['precompensatePM1'])
      delay = int(config.delay * (config.sampleRate / 1e9)) % waveformLength
      waveforms.append(list(wf[delay:]) + list(wf[:delay]))

    if writeAWG and self.awg is not None:
      self.awg._stop()
      self.awg.clearAll()

      self.awg.writeWaveform("CH1", waveforms[0])
      self.awg.writeWaveform("CH2", waveforms[1])
      self.awg.assignOutput(1,"CH1")
      self.awg.assignOutput(2,"CH2")
      print(f"Start configuration: {self.awg.configure_start_mode(self.config['startMode'])}")
      self.awg._setOutput(1, True)
      self.awg._setOutput(2, True)
      self.awg._start()
    return waveforms
    # except BaseException as e:
    #   print(e)
    #   import traceback
    #   traceback.print_exc()

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
        waveform[changingPoints[i]: changingPoints[i] + changingUnit] += addi
      if np.max(waveform) > 1 or np.min(waveform) < -1: raise ArithmeticError('value out of range after pre compensation')
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

  serviceName = sys.argv[1] if len(sys.argv) > 1 else 'AWG_Encoder_Test'
  brokerAddress = sys.argv[2] if len(sys.argv) > 2 else '192.168.25.5:1061'
  devAddress = sys.argv[3] if len(sys.argv) > 3 else 'TCPIP0::192.168.25.37::hislip0::INSTR'
  outputMode = sys.argv[4].upper() if len(sys.argv) > 4 else 'DC'
  if outputMode not in ('DAC', 'DC'):
    outputMode = 'DC'

  from Instrument.WaveformGenerator.KeySightA8190 import M8190A, VisaTransport
  dev = M8190A(VisaTransport(devAddress, timeout=30))
  dev.open()
  dev.stop()
  dev.set_output(1, False)
  dev.set_output(2, False)

  # 1. Internal reference + internal sample clock at 12 GSa/s
  # clockConfig = dev.set_internal_sample_clock(12e9)

  # 2. External 10 MHz reference at REF CLK IN;
  #    internal synthesizer generates the 12 GSa/s sample clock
  # clockConfig = dev.set_external_reference_clock(10e6, 12e9)

  # 3. External 12 GHz sample clock at SAMPLE CLK IN
  clockConfig = dev.set_external_sample_clock(12e9)
  print(f'Clock configuration: {clockConfig}')

  outputAmplitude = 0.7 if outputMode == 'DAC' else 1.0
  for channel in (1, 2):
    dev.set_output_route(channel, outputMode)
    dev.write(f":{outputMode}{channel}:VOLT {outputAmplitude}")
    dev.write(f":{outputMode}{channel}:VOLT:OFFS 0")
  print(f'Output mode: {outputMode}, amplitude: {outputAmplitude} V')

  encoder = AWGEncoder(dev, randonNumberRange=256)

  worker = IFWorker(brokerAddress, serviceName, encoder, force=True)
  encoder.massiveService = worker.TF_FileStorage
  print(f'Encoder Service ({serviceName}) started.')

  IFLoop.join()

  np.random.seed(100)
  # encoder.configure('randomNumbers', np.random.randint(0, 127, 16000))
  encoder.configure('randomNumbers', [63] * 200 + [0] * (20000 - 200))
  encoder.configure('sampleRate', 12e9)  # 采样率  不动

  # Start immediately and repeat continuously
  # encoder.configure('startMode', 'AUTO')

  # Wait for one edge at TRIGGER IN, then repeat continuously until stopped
  encoder.configure('startMode', 'TRIGGERED_CONTINUOUS')

  encoder.configure('waveformLength', None)
  encoder.configure('waveformUnitLength', 60)
  encoder.configure('widthAM1', [1.0, 1.2])  # [signal, reference]
  encoder.configure('biasAM1', [0.5] * 5)
  encoder.configure('ampAM1', [0.5, 0.55, 0.6, 0.7, 1])

  V = 0.7
  encoder.configure('ampPM1', [(i - 7.5) / 16 * V + 0.5 for i in range(16)])
  # encoder.configure('precompensatePM1', ['linear', 0.1, 0])
  encoder.configure('biasPM1', [0.5] * 16)
  encoder.configure('widthPM1', 5)
  # encoder.configure('reversePatternPM1', [1] * 100 + [0.5] * 100)

  t1 = time.time()
  wfs = encoder.generateNewWaveform()
  t2 = time.time()
  print(t2 - t1)

  import matplotlib.pyplot as plt
  plt.plot(wfs[0])
  plt.plot(wfs[1])
  # plt.show()
  plt.savefig('Encoder_KeySightA8190.png', dpi=300)
