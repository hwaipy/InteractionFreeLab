from pytimetag.Analyser import Analyser, Validator
import numpy as np
# import tick
# from util import RNManager
from numba import njit
import msgpack
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone, timedelta


class TFQKDQBERAnalyser(Analyser):
    def __init__(self, channelCount):
        super().__init__()
        self.channelCount = channelCount
        self.setConfiguration('TimeEachBlock', 1000000000000, lambda v: isinstance(v, int) and v > 0)
        self.setConfiguration('FrequencyFrame', 1000000000, lambda v: isinstance(v, int) and v > 0)
        self.setConfiguration('PhaseFrame', 200000000, lambda v: isinstance(v, int) and v > 0)
        self.setConfiguration('IntensityFrame', 1000000000, lambda v: isinstance(v, int) and v > 0)
        self.setConfiguration('AliceRandomNumbers', np.ones(1, dtype='int'), lambda x: True)
        self.setConfiguration('BobRandomNumbers', np.ones(1, dtype='int'), lambda x: True)
        self.setConfiguration('Period', 10000, Validator.float(0))
        self.setConfiguration('TriggerPeriod', 40000000, Validator.float(0))
        self.setConfiguration('PulsePosition', 5000, Validator.int(1, 1000000000000))
        self.setConfiguration('Gate', 1000, Validator.float(0))
        self.setConfiguration('GateRef', 1000, Validator.float(0))
        self.setConfiguration('TriggerChannel', 0, Validator.int(0, channelCount - 1))
        self.setConfiguration('Channel 1', 2, Validator.int(0, channelCount - 1))
        self.setConfiguration('Channel 2', 3, Validator.int(0, channelCount - 1))
        self.setConfiguration('SyncChannelAlice', 4, Validator.int(0, channelCount - 1))
        self.setConfiguration('SyncChannelBob', 5, Validator.int(0, channelCount - 1))
        self.setConfiguration('IntensityRatioThreshold', 3, Validator.float(0))
        self.setConfiguration('IntensityThreshold', 5, Validator.float(0))
        self.setConfiguration('PhaseThreshold', 10, Validator.float(0))

    def analysis(self, dataBlock):
      configs = self.getConfigurations()
      dbp = DataBlockParser(dataBlock, configs)
      intermediate = dbp.parseIntermediate()
      result = intermediate.statistics(dbp.intensityRatioThreshold, dbp.intensityThreshold, dbp.phaseThreshold)
      result['Intermediate'] = QKDIntermediate.fromParser(
          dbp, intermediate, configs, processing='tdc-adapted').pack()
      return result

class DataBlockParser:
  def __init__(self, dataBlock, configs):
    ############## ⬇️ DEBUG ONLY  ##############
    # configs['AliceRandomNumbers'] = RNManager.getInstance().aliceRN
    # configs['BobRandomNumbers'] = RNManager.getInstance().bobRN
    # if RNManager.getInstance().matchedRandomNumbersLab is None:
    #   self.rnsAlice = configs['AliceRandomNumbers']
    #   self.rnsBob = configs['BobRandomNumbers']
    #   RNManager.getInstance().matchedRandomNumbersLab = self.generateMatchedRandomNumbers()
    # self.matchedRandomNumbers, self.randomNumberBasisStat = RNManager.getInstance().matchedRandomNumbersLab
    ############## ⬆️ DEBUG ONLY  ##############
    
    self.dataBlock = dataBlock

    # 系统参数
    self.timeEachBlock = configs['TimeEachBlock']  # 每个block的时间，单位ps
    self.frequencyFrame = configs['FrequencyFrame']  # 多长时间的数据视作频率不变进行一次频率计算
    self.phaseFrame = configs['PhaseFrame']  # 多长时间的数据视作全局相位不变进行一次相位计算
    self.intensityFrame = configs['IntensityFrame']  # 多长时间的数据视作强度不变进行一次强度匹配
    self.pulsePeriod = configs['Period']  # 每个脉冲的周期，单位ps
    self.triggerPeriod = configs['TriggerPeriod']  # 触发脉冲的周期，单位ps
    self.center = configs['PulsePosition']  # 脉冲周期内，脉冲的中心对应的时间，单位ps
    self.gateSignal = configs['Gate']  # 脉冲周期内，signal脉冲的门宽（全宽），单位ps
    self.gateRef = configs['GateRef']  # 脉冲周期内，reference脉冲的门宽（全宽），单位ps
    self.triggerChannel = configs['TriggerChannel']
    self.data1Channel = configs['Channel 1']
    self.data2Channel = configs['Channel 2']
    self.syncAliceChannel = configs['SyncChannelAlice']
    self.syncBobChannel = configs['SyncChannelBob']
    self.rnsAlice = np.array(configs['AliceRandomNumbers'])
    self.rnsBob = np.array(configs['BobRandomNumbers'])
    self.matchedRandomNumbers, self.randomNumberBasisStat = self.generateMatchedRandomNumbers()
    self.intensityRatioThreshold = configs['IntensityRatioThreshold']
    self.intensityThreshold = configs['IntensityThreshold']
    self.phaseThreshold = configs['PhaseThreshold']

    # 三个 Frame 参数应有互相整除关系
    if not isinstance(self.frequencyFrame, int): raise TypeError("FrequencyFrame must be an integer")
    if not isinstance(self.phaseFrame, int): raise TypeError("PhaseFrame must be an integer")
    if not isinstance(self.intensityFrame, int): raise TypeError("IntensityFrame must be an integer")
    if self.timeEachBlock % self.frequencyFrame != 0: raise ValueError("TimeEachBlock must be divisible by FrequencyFrame")
    if self.timeEachBlock % self.phaseFrame != 0: raise ValueError("TimeEachBlock must be divisible by PhaseFrame")
    if self.timeEachBlock % self.intensityFrame != 0: raise ValueError("TimeEachBlock must be divisible by IntensityFrame")
    if self.intensityFrame >= self.frequencyFrame: 
      if self.intensityFrame % self.frequencyFrame != 0: raise ValueError("IntensityFrame must be divisible by FrequencyFrame")
    else:
      if self.frequencyFrame % self.intensityFrame != 0: raise ValueError("FrequencyFrame must be divisible by IntensityFrame")
    if self.frequencyFrame % self.phaseFrame != 0: raise ValueError("FrequencyFrame must be divisible by PhaseFrame")
    if self.intensityFrame % self.phaseFrame != 0: raise ValueError("IntensityFrame must be divisible by PhaseFrame")

    self.frequencyFrameNum = int(self.timeEachBlock / self.frequencyFrame)
    self.phaseFrameNum = int(self.timeEachBlock / self.phaseFrame)
    self.intensityFrameNum = int(self.timeEachBlock / self.intensityFrame)
    if dataBlock is not None:
      self.dataBlock, self.analysisWindowInfo = self.analysisWindow(dataBlock, configs)

  def pulseCountStat(self):
    """Exact cyclic-RN signal pulse counts, indexed [Alice, Bob, intensity frame]."""
    rns = self.matchedRandomNumbers
    codes = np.where((rns & 0xC00) == 0, ((rns >> 3) & 7) * 4 + (rns & 7), -1)
    edges = np.arange(self.intensityFrameNum + 1, dtype=np.int64) * self.intensityFrame
    limits = np.maximum(0, (edges - self.center + self.pulsePeriod - 1) // self.pulsePeriod)
    starts, ends = limits[:-1], limits[1:]
    counts = np.zeros((4, 4, self.intensityFrameNum), dtype=np.int64)
    for a in range(4):
      for b in range(4):
        prefix = np.concatenate(([0], np.cumsum(codes == a * 4 + b, dtype=np.int64)))
        def cumulative(indices):
          return (indices // len(rns)) * prefix[-1] + prefix[indices % len(rns)]
        counts[a, b] = cumulative(ends) - cumulative(starts)
    return counts

  @staticmethod
  def rescaleTDCClock(block, frequency=25000, clockChannel=0, ppsChannel=1):
    """Reproduce the server's frequencyRescaleAdaptor on historical Raw.

    Raw storage is after channel delays but BEFORE the online adaptors. The
    clock reference is 25 kHz for this server, independent of TriggerPeriod.
    A per-block PPS origin is sufficient: the QBER parser uses relative times.
    """
    from pytimetag import DataBlock
    if not np.isfinite(frequency) or frequency <= 0:
      raise ValueError('Clock reference frequency must be positive and finite')
    clocks, pps = block.content[clockChannel], block.content[ppsChannel]
    if len(clocks) < 2 or not len(pps):
      raise ValueError('TDC clock correction requires at least two clock events and a PPS event')
    if np.any(clocks[1:] <= clocks[:-1]):
      raise ValueError('Clock events must be strictly increasing')
    measuredPeriod = (int(clocks[-1]) - int(clocks[0])) / (len(clocks) - 1)
    scale = 1 / (measuredPeriod * frequency / 1e12)
    if abs(scale - 1) > .01:
      raise ValueError('Clock scale differs by over 1%; check reference frequency or missing clock pulses')
    offset = -int(pps[0]) * scale
    content = [_rescaleClockChannel(ch, scale, offset) for ch in block.content]
    corrected = DataBlock.create(content, block.creationTime, block.dataTimeBegin * scale + offset,
                                 block.dataTimeEnd * scale + offset, block.resolution)
    return corrected, {'method': 'tdc-clock-v1', 'reference_frequency_hz': frequency,
        'clock_channel': clockChannel, 'pps_channel': ppsChannel, 'scale': scale}

  @staticmethod
  def analysisWindow(block, configs):
    """Keep detector/sync events in trigger-relative [0, TimeEachBlock), without mutation."""
    from pytimetag import DataBlock
    trigger = block.content[configs['TriggerChannel']]
    if not len(trigger):
      raise ValueError('No trigger events')
    origin = int(trigger[0])
    end = origin + configs['TimeEachBlock']
    content = list(block.content)
    excluded = {}
    for channel in set(configs[k] for k in ('Channel 1', 'Channel 2', 'SyncChannelAlice', 'SyncChannelBob')):
      events = content[channel]
      if np.any(events[1:] < events[:-1]):
        raise ValueError(f'Channel {channel} timestamps are not sorted')
      left = int(np.searchsorted(events, origin, side='left'))
      right = int(np.searchsorted(events, end, side='left'))
      content[channel] = events[left:right]
      excluded[str(channel)] = {'before': left, 'after': len(events) - right}
    windowed = DataBlock.create(content, block.creationTime, block.dataTimeBegin, block.dataTimeEnd, block.resolution)
    return windowed, {'origin_ps': origin, 'end_exclusive_ps': end,
        'acquisition_begin_ps': int(block.dataTimeBegin), 'acquisition_end_ps': int(block.dataTimeEnd),
        'excluded_events': excluded}

  def parse(self):
    return self.parseIntermediate().statistics(self.intensityRatioThreshold, self.intensityThreshold, self.phaseThreshold)

  def parseIntermediate(self):
    """Return unsifted per-frame arrays for offline parameter scans."""
    # Alice、Bob同步路计数统计
    aliceSyncCounts = self.countStat(channelNum=self.syncAliceChannel)
    bobSyncCounts = self.countStat(channelNum=self.syncBobChannel)
    # tick.tick('sync count statistics')
    
    # 获取探测事件信息
    signalDeltaMetas, refDeltaMetas = self.getDeltaMetas()
    # tick.tick('delta Metas')
    
    detectionStatistics = self.detectionStat(signalDeltaMetas)
    # tick.tick('detection statistics')

    # 计算频差
    #### 🔽 TODO: DEBUGING  should replace this to a realtime calc. ####   
    frequencies = np.array([0] * self.phaseFrameNum)
    # binNumInFrame = int(self.frequencyFrame / 1000)
    # refStatsCounts = np.zeros(shape=(self.frequencyFrameNum, binNumInFrame, 16), dtype='int32')
    # print('frequencies calculated')
    # refCountsForFreq = statRefCountsForFreqJIT(refDeltaMetas, self.frequencyFrame, self.frequencyFrameNum, 1000)
    # tick.tick('frequencies')
    # tick.tick('frequencies')
    #### 🔼 TODO: DEBUGING  ####

    phaseDeltas = self.calcPhaseDelta(refDeltaMetas=refDeltaMetas, frequencies=frequencies)
    # print(phaseDeltas)
    # tick.tick('phase deltas')

    phaseErrors = self.computePhaseErrors(signalDeltaMetas, phaseDeltas, frequencies, 64)
    # tick.tick('end preprocessing')

    return DataBlockParseResult(
      syncCountsAlice=aliceSyncCounts,
      syncCountsBob=bobSyncCounts,
      randomNumberBasisStatistics=self.randomNumberBasisStat,
      detectionStatistics=detectionStatistics,
      phaseErrorStatistics=phaseErrors,
      phaseDeltas=phaseDeltas,
    )
  
  def generateMatchedRandomNumbers(self):
    # RGPPPPAAABBB    RG 10 is Ref, 01 is Gap, 00 is Signal; PPPP is phase difference; AAA is Alice basis; BBB is Bob basis
    # basis: 00 is O, 01 is X, 10 is Y, 11 is Z, 1XX is undefined
    # @njit(cache=True)
    def jit_mrn(rnsAlice, rnsBob):
        matchedRandomNumbers = np.zeros(rnsAlice.shape, dtype=np.int32)
        basisStat = np.zeros(shape=(4, 4), dtype=np.int32)
        for i in range(len(rnsAlice)):
            rnA = rnsAlice[i]
            rnB = rnsBob[i]
            basisA = rnA & 0b11
            basisB = rnB & 0b11
            basis = (basisA << 3) | basisB
            encodeA = ((rnA & 0b111100) >> 2)
            encodeB = ((rnB & 0b111100) >> 2)
            encode = (encodeA - encodeB) % 16  # 编码相位差
            rn = (encode << 6) | basis

            if (rnA & 0b1000000 > 0): # isRef
              if not (rnB & 0b1000000 > 0): raise ValueError('Random number not match: a Ref can only match an other Ref.')
              matchedRandomNumbers[i] = 0b100000000000 | rn
            elif (rnA & 0b10000000 > 0): # isGap
              if not (rnB & 0b10000000 > 0): raise ValueError('Random number not match: a Gap can only match an other Gap.')
              matchedRandomNumbers[i] = 0b010000000000 | rn
            else: # isSignal
              matchedRandomNumbers[i] = 0b000000000000 | rn
              basisStat[basisA][basisB] += 1
        return matchedRandomNumbers, basisStat

    return jit_mrn(self.rnsAlice, self.rnsBob)

  def countStat(self, channelNum):
    # TODO: 这里要跟 DopplerUtil 的处理方式结合看一下，是否能在那边直接把 - triggerList[0] 的问题解决掉
    return np.histogram(self.dataBlock.content[channelNum] - self.dataBlock.content[self.triggerChannel][0], bins=self.intensityFrameNum, range=(0, self.timeEachBlock))[0]

  # 对齐时序(对数据综合处理)
  # 将1s内所有探测事件处理成 deltametas
  # deltaMetas 每个元素包含7项，分别是[0]重整时序后，事件在这1s内的到达时间，[1]invariant_time内的脉冲序号，[2]在脉冲周期内的时间，[3]探测器编号(0 / 1)，[4]对应的invariant_time序号,[5]对应的matchedRandomNumbers序列的随机数序号, [6]invariant_time内的到达时间
  def getDeltaMetas(self):
      triggerList = self.dataBlock.content[self.triggerChannel]
      data1List = self.dataBlock.content[self.data1Channel]
      data2List = self.dataBlock.content[self.data2Channel]
      return deltaMeta2JIT(
        dataList1=data1List - triggerList[0], # TODO: 这里要跟 DopplerUtil 的处理方式结合看一下，是否能在那边直接把 - triggerList[0] 的问题解决掉
        dataList2=data2List - triggerList[0], # TODO: 这里要跟 DopplerUtil 的处理方式结合看一下，是否能在那边直接把 - triggerList[0] 的问题解决掉
        rns=self.matchedRandomNumbers,
        phaseFrame=self.phaseFrame,
        triggerPeriod=self.triggerPeriod, 
        pulsePeriod=self.pulsePeriod, 
        center=self.center, 
        gateSignal=self.gateSignal, 
        gateRef=self.gateRef,
        deltaMetasSignalBuffer=np.zeros(((len(data1List) + len(data2List)), ), dtype='uint64'), # for performance
        deltaMetasRefBuffer=np.zeros(((len(data1List) + len(data2List)), ), dtype='uint64'), # for performance
      )

  def detectionStat(self, deltaMetas):
    return detectionStatJIT(deltaMetas, self.intensityFrame, self.intensityFrameNum)

  # 计算相位
  def calcPhaseDelta(self, refDeltaMetas, frequencies):
      freq = frequencies[0]
      phaseDeltas = calcPhaseJIT(refDeltaMetas, self.phaseFrame, self.phaseFrameNum, freq)
      # tick.tick('calc phase delta done')
      phaseDeltas = np.array(phaseDeltas)
      return phaseDeltas

  def computePhaseErrors(self, signalDeltaMetas, phaseDeltas, frequencies, statBin): # statBin divice errors 0 to pi/2
    return computePhaseErrorsJIT(signalDeltaMetas, phaseDeltas, self.phaseFrame, frequencies, self.intensityFrame, self.intensityFrameNum, statBin)
  
class DataBlockParseResult:
  def __init__(self, syncCountsAlice, syncCountsBob, randomNumberBasisStatistics, detectionStatistics, phaseErrorStatistics, phaseDeltas):
    self.syncCountsAlice = syncCountsAlice
    self.syncCountsBob = syncCountsBob
    self.randomNumberBasisStatistics = randomNumberBasisStatistics
    self.detectionStatistics = detectionStatistics
    self.phaseErrorStatistics = phaseErrorStatistics
    self.phaseDeltas = phaseDeltas

  def serialize(self):
    # tick.tick('serializing DataBlockParseResult')    
    data = []
    for array in [self.syncCountsAlice, self.syncCountsBob, self.randomNumberBasisStatistics, self.detectionStatistics, self.phaseErrorStatistics, self.phaseDeltas]:
      data.append(array.shape)
      data.append(array.dtype.str)
      data.append(array.flatten().tolist())
    data = msgpack.packb(data)
    # tick.tick('serializing DataBlockParseResult')
    return data

  def toSerialable(self):
    result = {}
    for key in ['syncCountsAlice', 'syncCountsBob', 'randomNumberBasisStatistics', 'detectionStatistics', 'phaseErrorStatistics', 'phaseDeltas']:
      value = getattr(self, key)
      result['__shape__' + key] = value.shape
      result['__dtype__' + key] = value.dtype.str
      result[key] = value.flatten().tolist()
    return result

  def statistics(self, intensityRatioThreshold, intensityThreshold, phaseThreshold):
    eX = [0, 0]
    eY = [0, 0]
    eZ1 = [0, 0]
    phaseThreshold = int(phaseThreshold)
    Z = [0, 0, 0, 0]
    valid = 0

    aliceSyncCounts = self.syncCountsAlice
    bobSyncCounts = self.syncCountsBob
    XX = self.phaseErrorStatistics[1]
    YY = self.phaseErrorStatistics[2]
    Z1Z1 = self.phaseErrorStatistics[3]
    for i in range(len(aliceSyncCounts)):
      ca = aliceSyncCounts[i]
      cb = bobSyncCounts[i]
      if ca > intensityThreshold and cb > intensityThreshold and ca < cb * intensityRatioThreshold and cb < ca * intensityRatioThreshold:
        valid += 1
        eX += XX[i][phaseThreshold]
        eY += YY[i][phaseThreshold]
        eZ1 += Z1Z1[i][phaseThreshold]
        Z[0] += self.detectionStatistics[0][0][i]
        Z[1] += self.detectionStatistics[0][3][i]
        Z[2] += self.detectionStatistics[3][0][i]
        Z[3] += self.detectionStatistics[3][3][i]
    
    E_Z00 = Z[0] / self.randomNumberBasisStatistics[0, 0]
    E_Z01 = Z[1] / self.randomNumberBasisStatistics[0, 3]
    E_Z10 = Z[2] / self.randomNumberBasisStatistics[3, 0]
    E_Z11 = Z[3] / self.randomNumberBasisStatistics[3, 3]

    return {
      'RandomNumberBasisStatistics': self.randomNumberBasisStatistics.tolist(),
      'CountsZ': [int(z) for z in Z],
      'PhaseErrorX': [int(e) for e in eX],
      'PhaseErrorY': [int(e) for e in eY],
      'PhaseErrorZ1': [int(e) for e in eZ1],
      'Valid': [valid, len(aliceSyncCounts)],
      'PhaseThreshold': phaseThreshold,
    }

  @classmethod
  def toString(cls, result):
    randomNumberBasisStatistics = np.array(result['RandomNumberBasisStatistics'])
    Z = np.array(result['CountsZ'])
    eX = np.array(result['PhaseErrorX'])
    eY = np.array(result['PhaseErrorY'])
    eZ1 = np.array(result['PhaseErrorZ1'])
    phaseThreshold = result.get('PhaseThreshold')
    
    E_Z00 = Z[0] / randomNumberBasisStatistics[0][0]
    E_Z01 = Z[1] / randomNumberBasisStatistics[0][3]
    E_Z10 = Z[2] / randomNumberBasisStatistics[3][0]
    E_Z11 = Z[3] / randomNumberBasisStatistics[3][3]

    s = f'Result for 1s: E_Z=({E_Z00 / E_Z11:.5f}, {E_Z01 / E_Z11:.2f}, {E_Z10 / E_Z11:.2f}) with {sum(Z)} counts.  E_X={eX[1] / sum(eX) * 100:.2f}% ({sum(eX)}),  E_Y={eY[1] / sum(eY) * 100:.2f}% ({sum(eY)}),  E_Z1={eZ1[1] / sum(eZ1) * 100:.2f}% ({sum(eZ1)}) @ threshold {phaseThreshold / 64 * np.pi / 2:.3f} rad.'
    return s

  @classmethod
  def deserialize(cls, data):
    data = msgpack.unpackb(data)
    def resolveArray(arg):
      return np.array(arg[2], dtype=np.dtype(arg[1])).reshape(arg[0])
    return cls(
      resolveArray(data[0:3]), 
      resolveArray(data[3:6]), 
      resolveArray(data[6:9]), 
      resolveArray(data[9:12]), 
      resolveArray(data[12:15]), 
      resolveArray(data[15:18])
    )
  
  @classmethod
  def fromSerialable(cls, data):
    def resolveArray(key):
      shape = data['__shape__' + key]
      dtype = np.dtype(data['__dtype__' + key])
      array = np.array(data[key], dtype=dtype).reshape(shape)
      return array
    return cls(
      resolveArray('syncCountsAlice'),
      resolveArray('syncCountsBob'),
      resolveArray('randomNumberBasisStatistics'),
      resolveArray('detectionStatistics'),
      resolveArray('phaseErrorStatistics'),
      resolveArray('phaseDeltas'),
    )
    
class QKDIntermediate:
  """Versioned lossless offline statistics; codec is shared by TDC and local tools.

  No pickle or raw events. Phase bins are noncumulative on disk; public
  phaseErrorStatistics restores the original cumulative counts exactly.
  """
  VERSION = 1
  ALGORITHM = 'TFQKDQBER-frequency-zero-v1'
  ARRAY_NAMES = ('syncCountsAlice', 'syncCountsBob', 'pulseCounts',
                 'detectionStatistics', 'phaseHistogram')

  def __init__(self, metadata, arrays):
    self.metadata = metadata
    for name in self.ARRAY_NAMES:
      setattr(self, name, arrays[name])
    self.validate()
    self.phaseErrorStatistics = np.cumsum(self.phaseHistogram, axis=2, dtype=np.uint64)

  @staticmethod
  def compactCounts(array):
    array = np.asarray(array)
    if array.dtype.kind not in 'iu' or np.any(array < 0):
      raise ValueError('Counts must be nonnegative integers')
    maximum = int(array.max()) if array.size else 0
    return array.astype(np.uint32 if maximum <= np.iinfo(np.uint32).max else np.uint64)

  @classmethod
  def fromParser(cls, parser, result, configs, processing):
    # int64 subtraction prevents unsigned wraparound and detects nonmonotonic statistics.
    cumulative = result.phaseErrorStatistics.astype(np.int64)
    histogram = np.diff(cumulative, axis=2, prepend=np.zeros_like(cumulative[:, :, :1, :]))
    fixed = {k: v for k, v in configs.items() if k not in (
        'AliceRandomNumbers', 'BobRandomNumbers', 'PhaseThreshold', 'IntensityThreshold', 'IntensityRatioThreshold')}
    digest = hashlib.sha256()
    for rns in (parser.rnsAlice, parser.rnsBob):
      digest.update(np.asarray(rns, dtype='<i8').tobytes())
    metadata = {'format_version': cls.VERSION, 'algorithm': cls.ALGORITHM, 'phase_bins': 64,
        'basis_order': ['O', 'X', 'Y', 'Z'], 'configuration': fixed,
        'random_numbers_sha256': digest.hexdigest(), 'processing': processing,
        'FetchTime': datetime.fromtimestamp(float(parser.dataBlock.creationTime),
            tz=timezone(timedelta(hours=8))).isoformat(),
        'analysis_window': parser.analysisWindowInfo}
    arrays = {'syncCountsAlice': result.syncCountsAlice, 'syncCountsBob': result.syncCountsBob,
        'pulseCounts': parser.pulseCountStat(), 'detectionStatistics': result.detectionStatistics,
        'phaseHistogram': histogram}
    return cls(metadata, {k: cls.compactCounts(v) for k, v in arrays.items()})

  def validate(self):
    m = self.metadata
    if m.get('format_version') != self.VERSION or m.get('algorithm') != self.ALGORITHM:
      raise ValueError('Unsupported intermediate version or algorithm')
    if m.get('phase_bins') != 64 or m.get('basis_order') != ['O', 'X', 'Y', 'Z']:
      raise ValueError('Unsupported phase bins or basis order')
    config = m['configuration']
    duration, frame = config['TimeEachBlock'], config['IntensityFrame']
    if not isinstance(duration, int) or not isinstance(frame, int) or frame <= 0 or duration <= 0 or duration % frame:
      raise ValueError('Invalid intermediate duration/frame')
    frames = duration // frame
    expected = {'syncCountsAlice': (frames,), 'syncCountsBob': (frames,),
        'pulseCounts': (4, 4, frames), 'detectionStatistics': (4, 4, frames),
        'phaseHistogram': (4, frames, 64, 2)}
    for name, shape in expected.items():
      array = getattr(self, name)
      if array.shape != shape or array.dtype.kind != 'u' or array.dtype.itemsize not in (4, 8):
        raise ValueError(f'Invalid intermediate array {name}: {array.shape}, {array.dtype}')
    if not isinstance(m.get('processing'), str) or not m['processing']:
      raise ValueError('Missing processing provenance')
    if datetime.fromisoformat(m['FetchTime']).tzinfo is None:
      raise ValueError('Intermediate FetchTime must have a timezone')
    if m['analysis_window']['end_exclusive_ps'] - m['analysis_window']['origin_ps'] != duration:
      raise ValueError('Invalid intermediate analysis window')

  def compatibilityKey(self):
    """Allow RN changes, but reject mixing different gates, frame sizes or corrections."""
    return json.dumps({k: self.metadata[k] for k in (
        'format_version', 'algorithm', 'phase_bins', 'basis_order', 'configuration', 'processing')}, sort_keys=True)

  def pack(self):
    self.validate()
    out = io.BytesIO()
    metadata = np.frombuffer(json.dumps(self.metadata, sort_keys=True).encode('utf-8'), dtype=np.uint8)
    np.savez_compressed(out, metadata=metadata, **{k: getattr(self, k) for k in self.ARRAY_NAMES})
    return out.getvalue()

  @classmethod
  def unpack(cls, payload):
    if not isinstance(payload, (bytes, bytearray, memoryview)):
      raise ValueError('Intermediate must be binary bytes')
    try:
      with zipfile.ZipFile(io.BytesIO(payload)) as z:
        expected = {k + '.npy' for k in (*cls.ARRAY_NAMES, 'metadata')}
        if len(z.infolist()) != len(expected) or set(z.namelist()) != expected:
          raise ValueError('Invalid intermediate archive fields')
        if sum(item.file_size for item in z.infolist()) > 128 * 1024 * 1024:
          raise ValueError('Intermediate archive exceeds 128 MiB decoded size')
      with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        header = archive['metadata']
        if header.dtype != np.uint8 or header.ndim != 1:
          raise ValueError('Invalid intermediate metadata')
        metadata = json.loads(header.tobytes().decode('utf-8'))
        arrays = {k: archive[k] for k in cls.ARRAY_NAMES}
      return cls(metadata, arrays)
    except (KeyError, TypeError, OSError, zipfile.BadZipFile, UnicodeError) as exc:
      raise ValueError(f'Invalid intermediate archive: {exc}') from exc


@njit(cache=True)
def _rescaleClockChannel(channel, scale, offset):
    # Same arithmetic order as rescaleChannel in TF_TDCServer, but never mutate Raw.
    output = np.empty_like(channel)
    for i in range(len(channel)):
        output[i] = channel[i] * scale + offset
    return output


@njit(cache=True)
def deltaMeta2JIT(dataList1, dataList2, rns, phaseFrame, triggerPeriod, pulsePeriod, center, gateSignal, gateRef, deltaMetasSignalBuffer, deltaMetasRefBuffer): # the last two args are pre-allocated buffers (must be uint64), to inhence performance
    assert isinstance(phaseFrame, int)
    assert isinstance(pulsePeriod, int)

    iSignal = 0
    iRef = 0
    pulseBeginSignal = center - gateSignal / 2
    pulseEndSignal = center + gateSignal / 2
    pulseBeginRef = center - gateRef / 2
    pulseEndRef = center + gateRef / 2

    dl1Len = len(dataList1)
    dl2Len = len(dataList2)
    i1 = 0
    i2 = 0

    while True:
        dm1Valid = i1 < dl1Len
        dm2Valid = i2 < dl2Len
        if dm1Valid:
            if dm2Valid:
                time1 = dataList1[i1]
                time2 = dataList2[i2]
                if time1 <= time2:
                    time = time1
                    ch = 0
                    i1 += 1
                else:
                    time = time2
                    ch = 1
                    i2 += 1
            else:
                time = dataList1[i1]
                ch = 0
                i1 += 1
        else:
            if dm2Valid:
                time = dataList2[i2]
                ch = 1
                i2 += 1
            else:
                break

        delta = time % triggerPeriod  # 相对trigger的到达时间
        time_in_pulsePeriod = delta % pulsePeriod  # 事件在脉冲周期内的时间
        index_in_mrn = time / pulsePeriod % len(rns)  # 事件对应的matchedRandomNumbers序列的随机数序号

        if time > 0:
            rn = rns[int(index_in_mrn)]
            meta = (time << 24) | (ch << 16) | rn
            if (rn & 0b110000000000) == 0: # signal
                if pulseBeginSignal <= time_in_pulsePeriod <= pulseEndSignal:
                    deltaMetasSignalBuffer[iSignal] = meta
                    iSignal += 1
            elif (rn & 0b110000000000) == 0b100000000000: # ref
                if pulseBeginRef <= time_in_pulsePeriod <= pulseEndRef:
                    deltaMetasRefBuffer[iRef] = meta
                    iRef += 1
    return deltaMetasSignalBuffer[:iSignal], deltaMetasRefBuffer[:iRef]

@njit(cache=True)
def detectionStatJIT(deltaMetas, intensityFrame, intensityFrameNum):
    detectionStatistics = np.zeros(shape=(4, 4, intensityFrameNum), dtype='int32')
    for deltaMeta in deltaMetas:
      index_minidata = int((deltaMeta >> 24) / intensityFrame)
      rn = deltaMeta & 0xFFFF
      detectionStatistics[(rn >> 3) & 0b111][rn & 0b111][index_minidata] += 1
    return detectionStatistics

@njit(cache=True)
def statRefCountsForFreqJIT(refDeltaMetas, frequencyFrame, frequencyFrameNum, resolution):
    binNumInFrame = int(frequencyFrame / resolution)
    # print(frequencyFrameNum, binNumInFrame, 16)
    refStatsCounts = np.zeros(shape=(frequencyFrameNum, binNumInFrame, 16), dtype='int32')
    # print('initted')
    # for deltaMeta in refDeltaMetas:
    #     mrn = matchedRandomNumbers[deltaMeta[5]]
    #     if mrn & 0b110000000000 == 0b100000000000:
    #         time = deltaMeta[0]
    #         binOverall = int(time / resolution)
    #         frameIndex = int(binOverall / frequencyFrame)
    #         binInFrame = binOverall % frequencyFrame
    #         encode = ((mrn >> 6) & 0b1111)
    #         channel = deltaMeta[3]
    #         if channel == 1: encode = (encode + 8) % 16
    #         refStatsCounts[frameIndex][binInFrame][encode] += 1
    return refStatsCounts

@njit(cache=True)
def calcPhaseJIT(refDeltaMetas, phaseFrame, phaseFrameNum, freq):
    Asins = np.zeros(shape=(phaseFrameNum,), dtype='float')
    Acoss = np.zeros(shape=(phaseFrameNum,), dtype='float')

    omega = freq / 1E12 * 2 * np.pi
    npd8 = 1 / 16 * 2 * np.pi

    for deltaMeta in refDeltaMetas:
        encode = (((deltaMeta & 0xFFFF) >> 6) & 0b1111)
        time = deltaMeta >> 24
        x = encode * npd8 + (time % phaseFrame) * omega
        v = 1 if (deltaMeta & 0x10000) > 0 else -1
        sinx, cosx = np.sin(x), np.cos(x)
        phaseFrameIndex = int(time / phaseFrame)
        ##### Algorithm #####
        # for each:
            # delta0s[phaseFrameIndex] += (sinx - v) ** 2
            # delta90s[phaseFrameIndex] += (cosx - v) ** 2
            # delta180s[phaseFrameIndex] += (-sinx - v) ** 2
        # Bs = (delta0s + delta180s) / 2
        # Asins = delta0s - Bs
        # Acoss = delta90s - Bs
        #####           #####
        Asins[phaseFrameIndex] += sinx * v
        Acoss[phaseFrameIndex] += -0.5 + cosx * v + (sinx ** 2)

    phi0s = -np.arctan2(Asins, Acoss) - 0.5 * np.pi
    return phi0s

@njit(cache=True)
def computePhaseErrorsJIT(signalDeltaMetas, phaseDeltas, phaseFrame, frequencies, intensityFrame, intensityFrameNum, statBin):
    phaseErrors = np.zeros(shape=(4, intensityFrameNum, statBin, 2), dtype='int32')
    for deltaMeta in signalDeltaMetas:
      mrn = deltaMeta & 0xFFFF
      time = deltaMeta >> 24
      if (mrn & 0b110000000000 == 0) and ((mrn >> 3) & 0b111) == (mrn & 0b111): # isSignal, and basis match
        basis = mrn & 0b111
        ch = (deltaMeta >> 16) & 0b1
        iIntensityFrame = int(time / intensityFrame)
        encode = ((mrn >> 6) & 0b1111)
        phaseDelta = phaseDeltas[int(time / phaseFrame)]
        actualPhaseDelta = (encode / 16 * 2 * np.pi + phaseDelta + (time % phaseFrame) / 1E12 * frequencies[0] * (2 * np.pi) + 2 * np.pi) % (2 * np.pi)

        deltaPhi = (actualPhaseDelta - np.pi / 2) % (np.pi * 2)
        deltaTo0 = deltaPhi if deltaPhi < np.pi else np.pi * 2 - deltaPhi
        deltaToPi = deltaPhi - np.pi
        if deltaToPi < 0: deltaToPi = -deltaToPi
        position = 0 if deltaTo0 < deltaToPi else 1
        delta = deltaTo0 if position == 0 else deltaToPi
        phaseErrors[basis][iIntensityFrame][int(np.floor(delta / np.pi * 2 * statBin)):, (ch + position) & 0b1] += 1
    return phaseErrors
