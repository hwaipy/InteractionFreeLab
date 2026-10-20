from pytimetag.Analyser import Analyser, Validator
import numpy as np
import tick
from numba import njit
import msgpack
from scipy import interpolate
from concurrent.futures import ThreadPoolExecutor
import time

class TFQKDQBERAnalyser(Analyser):
    def __init__(self, channelCount):
        super().__init__()
        self.channelCount = channelCount
        self.setConfiguration('TimeEachBlock', 1000000000000, lambda v: isinstance(v, int) and v > 0) # 每个block的时间，单位ps，目前就写死 1e12 ps
        self.setConfiguration('FrequencyFrame', 1000000000, lambda v: isinstance(v, int) and v > 0) # 多长时间的数据视作频率不变进行一次频率计算。默认 1ms
        self.setConfiguration('PhaseFrame', 200000000, lambda v: isinstance(v, int) and v > 0)  # 多长时间的数据视作全局相位不变进行一次相位计算。默认 0.2ms
        self.setConfiguration('IntensityFrame', 1000000000, lambda v: isinstance(v, int) and v > 0)  # 多长时间的数据视作强度不变进行一次强度匹配。默认 1ms
        self.setConfiguration('AliceRandomNumbers', np.ones(1, dtype='int'), lambda x: True)   # Alice 的随机数序列
        self.setConfiguration('BobRandomNumbers', np.ones(1, dtype='int'), lambda x: True)   # Bob 的随机数序列
        self.setConfiguration('Period', 10000, Validator.float(0))   # 每个脉冲的周期，单位ps
        self.setConfiguration('TriggerPeriod', 40000000, Validator.float(0))    # 触发脉冲的周期，单位ps   目前写死 40us，对应 25kHz
        self.setConfiguration('PulsePosition', 5000, Validator.int(1, 1000000000000))   # 脉冲周期内，脉冲的中心对应的时间，单位ps
        self.setConfiguration('Gate', 1000, Validator.float(0))    # 脉冲周期内，signal脉冲的门宽（全宽），单位ps
        self.setConfiguration('GateRef', 1000, Validator.float(0))   # 脉冲周期内，reference脉冲的门宽（全宽），单位ps
        self.setConfiguration('TriggerChannel', 0, Validator.int(0, channelCount - 1))   # 触发通道（25kHz）
        self.setConfiguration('Channel 1', 2, Validator.int(0, channelCount - 1))     # 数据通道1（SNSPD 1）
        self.setConfiguration('Channel 2', 3, Validator.int(0, channelCount - 1))     # 数据通道2（SNSPD 2）
        self.setConfiguration('SyncChannelAlice', 4, Validator.int(0, channelCount - 1))  # Alice 同步通道 （SNSPD 3）
        self.setConfiguration('SyncChannelBob', 5, Validator.int(0, channelCount - 1))    # Bob 同步通道 （SNSPD 4）
        self.setConfiguration('IntensityRatioThreshold', 3, Validator.float(0))  # 强度匹配阈值。对于每一个 IntensityFrame 内的数，只有当 Alice、Bob 同步路计数在该比例范围内时，才认为强度匹配成功  AliceCount < BobCount * Threshold 且 BobCount < AliceCount * Threshold
        self.setConfiguration('IntensityThreshold', 5, Validator.float(0))  # 强度匹配下限阈值。只有当 Alice、Bob 同步路计数都大于该值时，才认为强度匹配成功  AliceCount > Threshold 且 BobCount > Threshold
        self.setConfiguration('PhaseThreshold', 10, Validator.float(0))   # 相位误差判定阈值。对于每一个 IntensityFrame 内的数，只有当相位误差小于该阈值时，才认为相位无误差  相位误差 < Threshold
        self.setConfiguration('FrequencyUpperBound', 50e6, Validator.float(0))   # 频率差上限
        self.setConfiguration('FrequencyResolution', 500, Validator.float(0))   # 频率差计算目标分辨率
        # 可以考虑把 FrequancyFarme 和 PhaseFrame 也增加 Threshold 限制 。

    def analysis(self, dataBlock):
      dbp = DataBlockParser(dataBlock, self.getConfigurations())
      return dbp.parse()

class DataBlockParser:
  def __init__(self, dataBlock, configs):
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
    self.rnsAlice = np.array(configs['BobRandomNumbers'])
    self.rnsBob = np.array(configs['AliceRandomNumbers'])
    # matchedRandomNumbers 是一个 numpy array，dtype=np.int32，每个元素是一个随机数编码，见 generateMatchedRandomNumbers 函数说明
    # randomNumberBasisStat 是一个 numpy array，shape=(4, 4)，记录了不同 basis (O, X, Y, Z) * (O, X, Y, Z) 组合下的随机数组合数量统计
    self.matchedRandomNumbers, self.randomNumberBasisStat = self.generateMatchedRandomNumbers()
    self.intensityRatioThreshold = configs['IntensityRatioThreshold']
    self.intensityThreshold = configs['IntensityThreshold']
    self.phaseThreshold = configs['PhaseThreshold']
    self.frequencyUpperBound = configs['FrequencyUpperBound']
    self.frequencyResolution = configs['FrequencyResolution']

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

    self.pool = ThreadPoolExecutor(max_workers=10)

  def parse(self):
    # Alice、Bob同步路计数统计
    aliceSyncCounts = self.countStat(channelNum=self.syncAliceChannel)  # 返回值是 numpy array, shape=(intensityFrameNum, )
    bobSyncCounts = self.countStat(channelNum=self.syncBobChannel)  # 返回值是 numpy array, shape=(intensityFrameNum, )
    tick.tick('sync count statistics')
    
    # 获取探测事件信息
    # 把 Channel 1 和 Channel 2 的探测时间做分类，所有 signal 事件放在 signalDeltaMetas，所有 reference 事件放在 refDeltaMetas。 dtype=np.uint64
    # 返回值的每一个元素代表一个光子探测事件，= (time_in_1s << 24) | (channel << 16) | matchedRandomNumber
    signalDeltaMetas, refDeltaMetas, phaseFrameDivides, frequencyFrameDivides, intensityFrameDivides = self.getDeltaMetas()
    tick.tick('delta Metas')
    
    # 按照 basis 和 IntensityFrame 统计探测事件。结果是一个 numpy array，shape=(4, 4, intensityFrameNum)，dtype='int32'
    detectionStatistics = self.detectionStat(signalDeltaMetas)
    tick.tick('detection statistics')

    # 计算频差
    frequencies = self.calcFrequencies(refDeltaMetas, frequencyFrameDivides[:, 1])
    tick.tick('frequencies')

    # 用 Ref 探测事件来计算每一个 PhaseFrame 内的相位差。结果是一个 numpy array，shape=(phaseFrameNum, ), dtype='float'
    phaseDeltas = self.calcPhaseDelta(refDeltaMetas=refDeltaMetas, frequencies=frequencies)
    # print(phaseDeltas)
    tick.tick('phase deltas')

    # 用 Signal 探测事件和相位差来计算每一个 IntensityFrame 内的相位误差统计。结果是一个 numpy array，shape=(4, intensityFrameNum, statBin, 2)，dtype='int32'
    # 第一个维度是 OO, XX, YY, Z1Z1 四种 basis 配对
    # 第三个维度是不同的相位阈值的统计，第[i]个元素代表相位误差小于 i * (pi/2) / statBin 的统计。 statBin 写死了 64
    # 第四个维度是哪个探测器响应的信息
    phaseErrors = self.computePhaseErrors(signalDeltaMetas, phaseDeltas, frequencies, 64)
    tick.tick('end preprocessing')

    return DataBlockParseResult(
      syncCountsAlice=aliceSyncCounts,
      syncCountsBob=bobSyncCounts,
      randomNumberBasisStatistics=self.randomNumberBasisStat,
      detectionStatistics=detectionStatistics,
      phaseErrorStatistics=phaseErrors,
      phaseDeltas=phaseDeltas,
    ).statistics(self.intensityRatioThreshold, self.intensityThreshold, self.phaseThreshold)
  
  def generateMatchedRandomNumbers(self):
    # 限定：同一个时间点上，Alice 和 Bob 的随机数类型必须一致（都是 Ref / 都是 Gap / 都是 Signal）
    # RGPPPPAAABBB    RG 10 is Ref, 01 is Gap, 00 is Signal; PPPP is phase difference; AAA is Alice basis; BBB is Bob basis
    # basis: 00 is O, 01 is X, 10 is Y, 11 is Z, 1XX is undefined
    @njit(cache=True)
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
              assert (rnB & 0b1000000 > 0)
              matchedRandomNumbers[i] = 0b100000000000 | rn
            elif (rnA & 0b10000000 > 0): # isGap
              assert (rnB & 0b10000000 > 0)
              matchedRandomNumbers[i] = 0b010000000000 | rn
            else: # isSignal
              matchedRandomNumbers[i] = 0b000000000000 | rn
              basisStat[basisA][basisB] += 1
        return matchedRandomNumbers, basisStat

    return jit_mrn(self.rnsAlice, self.rnsBob)

  def countStat(self, channelNum):
    # TODO: 这里要跟 DopplerUtil 的处理方式结合看一下，是否能在那边直接把 - triggerList[0] 的问题解决掉
    return countStatJIT(self.dataBlock.content[channelNum] - self.dataBlock.content[0][0], self.intensityFrameNum, 0, self.timeEachBlock)

  # 将1s内所有探测事件处理成 deltametas
  def getDeltaMetas(self):
      triggerList = self.dataBlock.content[self.triggerChannel]
      data1List = self.dataBlock.content[self.data1Channel]
      data2List = self.dataBlock.content[self.data2Channel]
      return deltaMeta2JIT(
        dataList1=data1List - triggerList[0], # TODO: 这里要跟 DopplerUtil 的处理方式结合看一下，是否能在那边直接把 - triggerList[0] 的问题解决掉
        dataList2=data2List - triggerList[0], # TODO: 这里要跟 DopplerUtil 的处理方式结合看一下，是否能在那边直接把 - triggerList[0] 的问题解决掉
        rns=self.matchedRandomNumbers,
        triggerPeriod=self.triggerPeriod, 
        pulsePeriod=self.pulsePeriod, 
        center=self.center, 
        gateSignal=self.gateSignal, 
        gateRef=self.gateRef,
        timeEachBlock=self.timeEachBlock,
        phaseFrame=self.phaseFrame,
        frequencyFrame=self.frequencyFrame,
        intensityFrame=self.intensityFrame,
        deltaMetasSignalBuffer=np.zeros(((len(data1List) + len(data2List)), ), dtype='uint64'), # for performance
        deltaMetasRefBuffer=np.zeros(((len(data1List) + len(data2List)), ), dtype='uint64'), # for performance
      )

  def detectionStat(self, deltaMetas):
    return detectionStatJIT(deltaMetas, self.intensityFrame, self.intensityFrameNum)

  # 计算频差
  def calcFrequencies(self, refDeltaMetas, frequencyFrameDivides):
    tick.tick('begin calc freq')
    totalTime = self.frequencyFrame  # s
    timeBinSize = int(self.timeEachBlock / self.frequencyUpperBound / 2)
    phaseModulationNumber = 16
    timeBinCount = int(totalTime / timeBinSize)

    def calcFrequencyTask(frequencyFrameNum):
      I = statForFFTJIT(refDeltaMetas, frequencyFrameDivides[frequencyFrameNum], 
                      frequencyFrameDivides[frequencyFrameNum + 1], frequencyFrameNum * self.frequencyFrame, 
                      phaseModulationNumber, timeBinSize, np.zeros(shape=(timeBinCount), dtype='complex64'))

      fft = np.fft.fft(I, n=len(I))
      fft = fft.real ** 2 + fft.imag ** 2
      resolution = self.timeEachBlock / self.frequencyFrame
      maxI = np.where(fft == np.max(fft))[0][0]

      step = resolution / 2
      currentMaxFreq = maxI * resolution
      currentMaxValue = np.sqrt(fft[maxI])
      while step > self.frequencyResolution:
          vPlus = DFT_single(I, currentMaxFreq + step, len(I) * resolution, mod=True)
          vMinus = DFT_single(I, currentMaxFreq - step, len(I) * resolution, mod=True)
          currentMaxValue = max(vPlus, vMinus, currentMaxValue)
          if currentMaxValue == vPlus:
              currentMaxFreq += step
          elif currentMaxValue == vMinus:
              currentMaxFreq -= step
          step /= 2
      
      return currentMaxFreq

    futures = []
    for frequencyFrameNum in range(self.frequencyFrameNum):
      f = self.pool.submit(calcFrequencyTask, frequencyFrameNum)
      futures.append(f)
    tick.tick('submit freq tasks')
    frequencies = [f.result() for f in futures]
    tick.tick('calc freq')

    # import matplotlib.pyplot as plt
    # plt.plot(frequencies)
    # plt.savefig('freqs.png', dpi=300)
    # plt.close()

    x_old = np.linspace(0, 1, self.frequencyFrameNum)
    x_new = np.linspace(0, 1, self.phaseFrameNum)
    f = interpolate.interp1d(x_old, frequencies, kind='linear')  # 可以改为 'linear', 'quadratic' 等
    return f(x_new)

  # 计算相位
  def calcPhaseDelta(self, refDeltaMetas, frequencies):
    phaseDeltas = calcPhaseJIT(refDeltaMetas, self.phaseFrame, self.phaseFrameNum, frequencies)
    tick.tick(f'calc phase delta done, with {len(refDeltaMetas)} ref events.')
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
    tick.tick('serializing DataBlockParseResult')    
    data = []
    for array in [self.syncCountsAlice, self.syncCountsBob, self.randomNumberBasisStatistics, self.detectionStatistics, self.phaseErrorStatistics, self.phaseDeltas]:
      data.append(array.shape)
      data.append(array.dtype.str)
      data.append(array.flatten().tolist())
    data = msgpack.packb(data)
    tick.tick('serializing DataBlockParseResult')
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
    randomNumberBasisStatistics = result['RandomNumberBasisStatistics']
    Z = result['CountsZ']
    eX = result['PhaseErrorX']
    eY = result['PhaseErrorY']
    eZ1 = result['PhaseErrorZ1']
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
    
@njit(cache=True)
def deltaMeta2JIT(dataList1, dataList2, rns, triggerPeriod, pulsePeriod, center, gateSignal, gateRef, timeEachBlock, phaseFrame, frequencyFrame, intensityFrame, deltaMetasSignalBuffer, deltaMetasRefBuffer): # the last two args are pre-allocated buffers (must be uint64), to inhence performance
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

    phaseFrameDivides = np.zeros((int(timeEachBlock / phaseFrame) + 1, 2), dtype='int32')
    frequencyFrameDivides = np.zeros((int(timeEachBlock / frequencyFrame) + 1, 2), dtype='int32')
    intensityFrameDivides = np.zeros((int(timeEachBlock / intensityFrame) + 1, 2), dtype='int32')
    phaseFrameNum, phaseFrameLimit = 1, phaseFrame
    frequencyFrameNum, frequencyFrameLimit = 1, frequencyFrame
    intensityFrameNum, intensityFrameLimit = 1, intensityFrame

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
            if time >= intensityFrameLimit:
              intensityFrameDivides[intensityFrameNum] = iSignal, iRef
              intensityFrameNum += 1
              intensityFrameLimit += intensityFrame
            if time >= frequencyFrameLimit:
              frequencyFrameDivides[frequencyFrameNum] = iSignal, iRef
              frequencyFrameNum += 1
              frequencyFrameLimit += frequencyFrame
            if time >= phaseFrameLimit:
              phaseFrameDivides[phaseFrameNum] = iSignal, iRef
              phaseFrameNum += 1
              phaseFrameLimit += phaseFrame

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

    intensityFrameDivides[intensityFrameNum] = iSignal, iRef
    frequencyFrameDivides[frequencyFrameNum] = iSignal, iRef
    phaseFrameDivides[phaseFrameNum] = iSignal, iRef
    return deltaMetasSignalBuffer[:iSignal], deltaMetasRefBuffer[:iRef], phaseFrameDivides, frequencyFrameDivides, intensityFrameDivides

@njit(cache=True)
def statForFFTJIT(refDeltaMetas, begin, end, offset, phaseModulationNumber, timeBinSize, I):
  for meta in refDeltaMetas[begin: end]:
    mergedModC = (((meta >> 6) & 0b1111) / phaseModulationNumber + ((meta >> 16) & 0b1) / 2)
    binIndex = int(((meta >> 24) - offset) / timeBinSize)
    I[binIndex] += np.exp(-1j * mergedModC * 2 * np.pi)
  return I

@njit(cache=True)
def countStatJIT(dataList, binNum, begin, end):
    counts = np.zeros((binNum,), dtype='int32')
    binWidth = (end - begin) / binNum
    for time in dataList:
        if begin <= time < end:
            index = int((time - begin) / binWidth)
            counts[index] += 1
    return counts

@njit(cache=True)
def detectionStatJIT(deltaMetas, intensityFrame, intensityFrameNum):
    detectionStatistics = np.zeros(shape=(4, 4, intensityFrameNum), dtype='int32')
    for deltaMeta in deltaMetas:
      index_minidata = int((deltaMeta >> 24) / intensityFrame)
      rn = deltaMeta & 0xFFFF
      detectionStatistics[(rn >> 3) & 0b111][rn & 0b111][index_minidata] += 1
    return detectionStatistics

@njit(cache=True)
def calcPhaseJIT(refDeltaMetas, phaseFrame, phaseFrameNum, frequencies):
    Asins = np.zeros(shape=(phaseFrameNum,), dtype='float')
    Acoss = np.zeros(shape=(phaseFrameNum,), dtype='float')

    omega = 1 / 1E12 * 2 * np.pi
    npd8 = 1 / 16 * 2 * np.pi

    for deltaMeta in refDeltaMetas:
        encode = (((deltaMeta & 0xFFFF) >> 6) & 0b1111)
        time = deltaMeta >> 24
        phaseFrameIndex = int(time / phaseFrame)
        x = encode * npd8 + (time % phaseFrame) * frequencies[phaseFrameIndex] * omega
        v = 1 if (deltaMeta & 0x10000) > 0 else -1
        sinx, cosx = np.sin(x), np.cos(x)
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
        phaseFrameNum = int(time / phaseFrame)
        phaseDelta = phaseDeltas[phaseFrameNum]
        actualPhaseDelta = (encode / 16 * 2 * np.pi + phaseDelta + (time % phaseFrame) / 1E12 * frequencies[phaseFrameNum] * (2 * np.pi) + 2 * np.pi) % (2 * np.pi)

        deltaPhi = (actualPhaseDelta - np.pi / 2) % (np.pi * 2)
        deltaTo0 = deltaPhi if deltaPhi < np.pi else np.pi * 2 - deltaPhi
        deltaToPi = deltaPhi - np.pi
        if deltaToPi < 0: deltaToPi = -deltaToPi
        position = 0 if deltaTo0 < deltaToPi else 1
        delta = deltaTo0 if position == 0 else deltaToPi
        phaseErrors[basis][iIntensityFrame][int(np.floor(delta / np.pi * 2 * statBin)):, (ch + position) & 0b1] += 1
    return phaseErrors

def DFT_single(a, k, N, mod=False):
    assert N >= len(a)
    r = DFT_single_JIT(a, k, N)
    return r if not mod else np.sqrt(r.real ** 2 + r.imag ** 2).real

@njit(cache=True, fastmath=True)
def DFT_single_JIT(a, k, N):
    assert N >= len(a)
    ek = np.power(np.exp(-1j * 2 * np.pi / N), k)
    ekn = 1
    r = 0
    for n in range(len(a)):
        r += a[n] * ekn
        ekn *= ek
    return r
