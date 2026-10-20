import random
import numpy as np
from random import Random
import msgpack
from worker_config import worker


encoderA = worker.TF_AWGEncoder_Alice
encoder = worker.TF_AWGEncoder_Bob
tdc = worker.TFTDCServer


class LongWaveformGenerator:
    def __init__(self, waveformLength=int(2E7), part=400, Num_ref=140, Num_signal=250, PX=0.043215, PY=0.003492, PZ= 0.95268, PZ1=1-0.720766):
        self.waveformLength = waveformLength  # 200ms长度的波长
        self.part = part
        if self.waveformLength % self.part != 0: raise ValueError('The "waveformLength" must be an integer multiple of "part".')
        self.numPart = int(self.waveformLength / self.part)
        self.Num_ref = Num_ref
        self.Num_signal = Num_signal
        self.Num_gap = self.part - self.Num_ref - self.Num_signal
        self.PX = PX
        self.PY = PY
        self.PZ = PZ
        self.P0 = 1 - self.PX - self.PY - self.PZ
        self.PZ1 = PZ1  # Z发送的概率

    def __refGenerator(self, seed: int):
        rnd = Random(seed)
        rnsRef = [rnd.randint(0, 3) * 16 + 64 for i in range(self.Num_ref * self.numPart)]
        return rnsRef

    def __signalGenerator(self, seed: int):
        rnd = Random(seed)
        # 生成随机数
        numX = int(self.PX * self.numPart * self.Num_signal)
        numY = int(self.PY * self.numPart * self.Num_signal)
        numZ = int(self.PZ * self.numPart * self.Num_signal)
        num0 = self.numPart * self.Num_signal - numX - numY - numZ

        rnsX = [rnd.randint(0, 15) * 4 + 1 for i in range(numX)]
        rnsY = [rnd.randint(0, 15) * 4 + 2 for i in range(numY)]
        rnsZ = [rnd.randint(0, 15) * 4 + 3 for i in range(numZ)]
        rns0 = [0 for i in range(num0)]
        # Z态 发送or不发送
        random.seed(seed)
        Z1Z0 = [random.random() for i in range(numZ)]
        rnsZ = [rnsZ[zi] if Z1Z0[zi] <= self.PZ1 else -1 for zi in range(numZ)]
        # 拼接
        rns_signal = rns0 + rnsX + rnsY + rnsZ
        # 乱序
        random.shuffle(rns_signal)
        print(f'numX={numX}, numY={numY}, numZ={numZ}, num0={num0}, num={numX+numY+numZ+num0}')
        print(f'length of signal = {self.numPart} * {self.Num_signal} = {len(rns_signal)}')
        return rns_signal

    def __gapGenerator(self, seed: int):
        rnd = Random(seed)
        rnsGap_forAWG = [rnd.randint(0, 63) for i in range(self.Num_gap * self.numPart)]
        rnsGap_forTDC = [i + 128 for i in rnsGap_forAWG]
        return rnsGap_forAWG, rnsGap_forTDC

    def refillRNS(self, A, B):
        pairs = [[0, 0]]
        for rns in [[i * 4 + 1 for i in range(16)], [i * 4 + 2 for i in range(16)], [i * 4 + 3 for i in range(16)] + [-1]]:
            rns = self.set_pairs([[i, j] for i in rns for j in rns])
            pairs.extend(rns)

        length = self.numPart * self.Num_signal
        indexXX = [i for i in range(length) if 0 < A[i] < 64 and A[i] % 4 == 1 and 0 < B[i] < 64 and B[i] % 4 == 1]
        indexYY = [i for i in range(length) if 0 < A[i] < 64 and A[i] % 4 == 2 and 0 < B[i] < 64 and B[i] % 4 == 2]
        indexZ1Z1 = [i for i in range(length) if 0 < A[i] < 64 and A[i] % 4 == 3 and 0 < B[i] < 64 and B[i] % 4 == 3]

        def set_phase_diff(A, B, index):
            state = A[index[0]] % 4
            print(f'length of state {state} = {len(index)}')
            if len(index) < 16:
                print(f'length = {len(index)} <= 16')
                return A, B
            while True:
                phase = [(A[i]//4 - B[i]//4) % 16 for i in index]
                fill_diff = [p for p in range(16) if p not in phase]
                if len(fill_diff) == 0:
                    print(f'state {state} not need to fill.')
                    break
                rnd = [random.randint(0, 15) for i in fill_diff]
                fill_rns = [[(rnd[i] + fill_diff[i]) % 16 * 4 + state, rnd[i] * 4 + state] for i in range(len(rnd))]
                print(f'phase {fill_diff} not in ABpairs')
                replace_index = [index[random.randint(0, len(index)-1)] for i in range(len(fill_diff))]
                for i in range(len(fill_rns)):
                    pairs = fill_rns[i]
                    A[replace_index[i]] = pairs[0]
                    B[replace_index[i]] = pairs[1]
            return A, B

        A, B = set_phase_diff(A, B, indexXX)
        A, B = set_phase_diff(A, B, indexYY)
        A, B = set_phase_diff(A, B, indexZ1Z1)

        return A, B

    def random0(self, rns, seed: int):
        rnd = Random(seed)
        return [rnd.randint(0, 15) * 4 if i == 0 else i for i in rns]

    def set_pairs(self, pairs):
        pp = []
        for p in pairs:
            if p not in pp: pp.append(p)
        return pp

    def dosth2Z(self, rns_signal):
        rnsforAWG = [0 if i == -1 else i for i in rns_signal]
        rnsforTDC = []
        for r in rns_signal:
            if r == -1: rnsforTDC.append(3)
            elif r % 4 == 3: rnsforTDC.append(7)
            else: rnsforTDC.append(r)
        return rnsforAWG, rnsforTDC

    def joint(self, rns_ref, rns_gap, rns_signal):
        rns = []
        for i in range(self.numPart):
            rns.extend(rns_ref[i*self.Num_ref:(i+1)*self.Num_ref])
            rns.extend(rns_gap[i * self.Num_gap:(i + 1) * self.Num_gap])
            rns.extend(rns_signal[i * self.Num_signal:(i + 1) * self.Num_signal])
        return rns

    @classmethod
    def refReverse(cls, rns, negative=True):
        phase = rns // 4
        state = 1 if negative else 0
        rns = phase * 4 + state
        return rns

    def waveformGenerator(self, Alice_reversed, Bob_reversed):
        # 产生Alice与Bob的signal随机数
        Alice_rns_signal = self.__signalGenerator(seed=84)
        Bob_rns_signal = self.__signalGenerator(seed=75)
        # 补充不存在的随机数对
        Alice_rns_signal, Bob_rns_signal = self.refillRNS(Alice_rns_signal, Bob_rns_signal)
        # 分别生成AWG、TDC随机数
        Alice_rns_signal_forAWG, Alice_rns_signal_forTDC = self.dosth2Z(Alice_rns_signal)
        Bob_rns_signal_forAWG, Bob_rns_signal_forTDC = self.dosth2Z(Bob_rns_signal)
        # 对真空随机编码相位
        Alice_rns_signal_forAWG = self.random0(Alice_rns_signal_forAWG, seed=50)
        Bob_rns_signal_forAWG = self.random0(Bob_rns_signal_forAWG, seed=71)
        # 生成ref随机数
        Alice_rns_ref = self.__refGenerator(seed=28)
        Bob_rns_ref = self.__refGenerator(seed=29)
        # 定义reference反向
        Alice_rns_ref = [self.refReverse(rns=Alice_rns_ref[i]) if Alice_rns_ref[i] >= 64 and (i % 4 in Alice_reversed) else self.refReverse(Alice_rns_ref[i], negative=False) for i in range(len(Alice_rns_ref))]
        Bob_rns_ref = [self.refReverse(rns=Bob_rns_ref[i]) if Bob_rns_ref[i] >= 64 and (i % 4 in Bob_reversed) else self.refReverse(Bob_rns_ref[i], negative=False) for i in range(len(Bob_rns_ref))]
        # 生成gap随机数
        Alice_rnsGap_forAWG, Alice_rnsGap_forTDC = self.__gapGenerator(seed=66)
        Bob_rnsGap_forAWG, Bob_rnsGap_forTDC = self.__gapGenerator(seed=44)

        # 拼接随机数
        Alice_rns_forAWG = self.joint(Alice_rns_ref, Alice_rnsGap_forAWG, Alice_rns_signal_forAWG)
        Alice_rns_forTDC = self.joint(Alice_rns_ref, Alice_rnsGap_forTDC, Alice_rns_signal_forTDC)
        Bob_rns_forAWG = self.joint(Bob_rns_ref, Bob_rnsGap_forAWG, Bob_rns_signal_forAWG)
        Bob_rns_forTDC = self.joint(Bob_rns_ref, Bob_rnsGap_forTDC, Bob_rns_signal_forTDC)

        RNS = {
            'Alice': {
                'rns_forAWG': Alice_rns_forAWG,
                'rns_forTDC': Alice_rns_forTDC,
            },
            'Bob': {
                'rns_forAWG': Bob_rns_forAWG,
                'rns_forTDC': Bob_rns_forTDC,
            }
        }

        return RNS

    def simple_waveformGenerator(self, rns=None):
        if rns is None: rns = [1] * self.waveformLength

        RNS = {
            'Alice': {
                'rns_forAWG': rns,
                'rns_forTDC': rns,
            },
            'Bob': {
                'rns_forAWG': rns,
                'rns_forTDC': rns,
            }
        }

        return RNS

    def globalDelay_step1(self, length:int):
        rns = [1] * length + [0] * (self.waveformLength - length)

        RNS = {
            'Alice': {
                'rns_forAWG': rns,
                'rns_forTDC': rns,
            },
            'Bob': {
                'rns_forAWG': rns,
                'rns_forTDC': rns,
            }
        }

        return RNS

    def globalDelay_step2(self, length:int):
        if self.waveformLength % length != 0: raise ValueError('The "waveformLength" must be integer multiple of "length".')
        rns = [1] + [0] * (length-1)

        RNS = {
            'Alice': {
                'rns_forAWG': rns,
                'rns_forTDC': rns,
            },
            'Bob': {
                'rns_forAWG': rns,
                'rns_forTDC': rns,
            }
        }

        return RNS

    @classmethod
    def analyzeRNS(cls, rns_forTDC):
        ref, signal, signalX, signalY, signalZ, signalZ1, signalZ0, gap, signal0 = [], [], [], [], [], [], [], [], []
        length = len(rns_forTDC)
        for i in range(length):
            if 128 > rns_forTDC[i] >= 64: ref.append(i)
            elif rns_forTDC[i] < 64:
                signal.append(i)
                if rns_forTDC[i] % 4 == 0:
                    signal0.append(i)
                elif rns_forTDC[i] % 4 == 1:
                    signalX.append(i)
                elif rns_forTDC[i] % 4 == 2:
                    signalY.append(i)
                elif rns_forTDC[i] % 4 == 3:
                    signalZ.append(i)
                    if rns_forTDC[i] == 7:
                        signalZ1.append(i)
                    elif rns_forTDC[i] == 3:
                        signalZ0.append(i)
            elif rns_forTDC[i] >= 128:
                gap.append(i)

        result = {
            'count':f'ref={len(ref)}, gap={len(gap)}, signalX={len(signalX)}, signalY={len(signalY)}, signalZ={len(signalZ)}, signalZ1={len(signalZ1)}, signalZ0={len(signalZ0)}',
            'ref': ref,
            'gap': gap,
            'signal': signal,
            'signal0': signal0,
            'signalX': signalX,
            'signalY': signalY,
            'signalZ': signalZ,
            'signalZ1': signalZ1,
            'signalZ0': signalZ0
        }
        return result

    @classmethod
    def selectSame(cls, list1:list, list2:list):
        l1 = set(list1)
        l2 = set(list2)
        l = list(l1 & l2)
        return l

    @classmethod
    def analyzeAB_RNS(cls, Alice_rns_forTDC, Bob_rns_forTDC):
        result = dict()
        result['Alice'] = LongWaveformGenerator.analyzeRNS(Alice_rns_forTDC)
        print(result['Alice']['count'])
        result['Bob'] = LongWaveformGenerator.analyzeRNS(Bob_rns_forTDC)
        print(result['Bob']['count'])

        all00 = LongWaveformGenerator.selectSame(result['Alice']['signal0'], result['Bob']['signal0'])
        allref = LongWaveformGenerator.selectSame(result['Alice']['ref'], result['Bob']['ref'])
        allsig = LongWaveformGenerator.selectSame(result['Alice']['signal'], result['Bob']['signal'])
        sigXX = LongWaveformGenerator.selectSame(result['Alice']['signalX'], result['Bob']['signalX'])
        sigYY = LongWaveformGenerator.selectSame(result['Alice']['signalY'], result['Bob']['signalY'])
        sigZZ = LongWaveformGenerator.selectSame(result['Alice']['signalZ'], result['Bob']['signalZ'])
        sigZ0Z0 = LongWaveformGenerator.selectSame(result['Alice']['signalZ0'], result['Bob']['signalZ0'])
        sigZ0Z1 = LongWaveformGenerator.selectSame(result['Alice']['signalZ0'], result['Bob']['signalZ1'])
        sigZ1Z0 = LongWaveformGenerator.selectSame(result['Alice']['signalZ1'], result['Bob']['signalZ0'])
        sigZ1Z1 = LongWaveformGenerator.selectSame(result['Alice']['signalZ1'], result['Bob']['signalZ1'])
        print(f'reference对数：{len(allref)}, 占比：{len(allref)/len(Alice_rns_forTDC)}')
        print(f'signal对数：{len(allsig)}, 占比：{len(allsig)/len(Alice_rns_forTDC)}')
        print(f'00个数：{len(all00)}, 占比：{len(all00) / len(Alice_rns_forTDC)}, 占signal比：{len(all00) / len(result["Alice"]["signal"])}')
        print(f'XX个数：{len(sigXX)}, 占比：{len(sigXX)/len(Alice_rns_forTDC)}, 占signal比：{len(sigXX)/len(result["Alice"]["signal"])}')
        print(f'YY个数：{len(sigYY)}, 占比：{len(sigYY)/len(Alice_rns_forTDC)}, 占signal比：{len(sigYY)/len(result["Alice"]["signal"])}')
        print(f'ZZ个数：{len(sigZZ)}, 占比：{len(sigZZ)/len(Alice_rns_forTDC)}, 占signal比：{len(sigZZ)/len(result["Alice"]["signal"])}')
        lZZ = [len(sigZ0Z0), len(sigZ0Z1), len(sigZ1Z0), len(sigZ1Z1)]
        print(f'ZZ态(AB)[00, 01, 10, 11] 个数{lZZ}, 占比：{[i/len(Alice_rns_forTDC) for i in lZZ]}, 占signal比：{[i/len(result["Alice"]["signal"]) for i in lZZ]}, 占ZZ比：{[i/len(sigZZ) for i in lZZ]}')
        return

    @classmethod
    def RNStoID(cls, rns):
        return worker.TF_FileStorage.writeMassive(data=msgpack.packb(rns))

    @classmethod
    def IDtoRNS(cls, id:str):
        return msgpack.unpackb(worker.TF_FileStorage.readMassive(id=id))

    @classmethod
    def waveformID(cls):
        waveform_ID = dict()
        # [1] * 4000
        waveform_ID['simple_wave'] = '2022-10-06 00-11-56.784462 R149566'
        waveform_ID['All ref'] = dict()
        waveform_ID['All ref']['Alice'] = '2022-10-11 19-14-24.673885 R711914'
        waveform_ID['All ref']['Bob'] = '2022-10-11 19-14-24.757864 R495990'
        # 2E7长随机数
        waveform_ID['LongRNS'] = {'Alice': {}, 'Bob': {}}
        waveform_ID['LongRNS']['Alice']['rns_forTDC'] = '2022-10-06 23-38-26.449078 R552913'
        waveform_ID['LongRNS']['Bob']['rns_forTDC'] = '2022-10-06 23-38-28.714216 R501825'
        waveform_ID['LongRNS']['Alice']['rns_forAWG'] = '2022-10-06 23-38-30.907948 R402048'
        waveform_ID['LongRNS']['Bob']['rns_forAWG'] = '2022-10-06 23-38-33.109742 R199986'
        # sync = [64] * 140 + [128] * 10 + [1] * 250
        waveform_ID['LongRNS']['Alice']['rns_forSync'] = '2022-10-06 23-54-15.429917 R239858'
        waveform_ID['LongRNS']['Bob']['rns_forSync'] = '2022-10-06 23-54-15.429917 R239858'
        # Delay
        waveform_ID['Delay'] = {'step1': None, 'step2': None}
        # [64] * 400 + [0] * int(2E7 - 400)
        waveform_ID['Delay']['step1'] = '2022-10-07 00-27-49.098234 R798816'
        # [1] + [0] * (4000 - 1)
        waveform_ID['Delay']['step2'] = '2022-10-07 00-28-28.913120 R605477'

        return waveform_ID


def showWaveform(waveforms, showRange=None):
    import matplotlib.pyplot as plt
    sampleCount = len(waveforms[0])
    times = np.linspace(0, 0.5 * (sampleCount - 1), sampleCount)

    fig, axs = plt.subplots(4, 1)
    fig.set_size_inches(18, 10)

    for i in range(len(waveforms)):
        axs[i].plot(times, waveforms[i])
        axs[i].grid()
        if showRange: axs[i].set_xlim(showRange[0], showRange[1])
    plt.show()


def SyncRNS(rns):

    def allsigncheck(rns):
        n = 0
        for r in rns:
            if r >= 64: n += 1
        if n > 0:
            print('随机数中不全是signal')
            return False
        else:
            print('随机数中全是signal')
            return True

    def changeRNS(rns):
        end = False
        period = [0, 0, 0]
        for r in rns:
            if end and 64 <= r:
                break
            if 0 <= r < 64:
                period[2] += 1
            if 64 <= r < 128:
                period[0] += 1
            if r >= 128:
                end = True
                period[1] += 1
        rns = period[0] * [65] + period[1] * [129] + period[2] * [1]
        return rns

    if len(rns) <= 10000: return rns
    else:
        if allsigncheck(rns): return [1] * 4000
        else:
            rns = changeRNS(rns)
            if len(rns) > 10000: return [1] * 4000
            else: return rns


def control_Alice(rnsForAWG=([1] * 1 + [1] * 9) * 400, rnsForTDC=([1] * 1 + [1] * 9) * 400, globalDelay=0.0, onoff=[1, 0, 1, 0], V=0, rnsForSync=None):
    # Control: Alice
    # Encoder 的定义: AWG CH1 -> Reference AM; AWG CH2 -> Decoy & Z AM; AWG CH3 -> PM1; AWG CH4 -> PM2;
    encoder = worker.TF_AWGEncoder_Alice
    # globalDelay = -11223

    # if isinstance(rnsForAWG, str): rnsForAWG = LongWaveformGenerator.IDtoRNS(rnsForAWG)
    if not isinstance(rnsForAWG, str): globalDelay = globalDelay % (10 * len(rnsForAWG))
    encoder.configure('sampleRate', 2e9)  # 采样率  不动
    encoder.configure('waveformLength', None)
    encoder.configure('waveformUnitLength', 20)
    encoder.configure('randomNumbers', rnsForAWG)

    encoder.configure('ampAM1', [0.47, 0.592, 0.64, 0.70] + [1])  # 此处的小数是归一化数值
    encoder.configure('biasAM1', [0.47] * 4 + [0.0])

    encoder.configure('ampPM1', [(i / 16 * V) for i in range(16)])  # V=0.32 分通道通过率34.88%
    encoder.configure('widthAM1', [1.2, 10])  # [signal, reference]
    encoder.configure('widthPM1', 10)
    encoder.configure('delayAM1', globalDelay)
    encoder.configure('delayPM1', globalDelay + 35)  # -56.5
    encoder.configure('gainAM1', 1)
    encoder.configure('gainPM1', 1)

    if onoff[0] == 0:
        encoder.configure('ampAM1', [0] * 5)
        encoder.configure('biasAM1', [0] * 5)
    if onoff[2] == 0:
        encoder.configure('ampPM1', [0] * 16)

    waveforms = encoder.generateNewWaveform(returnWaveform=False)
    # showWaveform(waveforms, showRange=(30000, 33000))

    # 随机数上传处理
    if rnsForSync is None:
        rnsForSync = SyncRNS(rns=rnsForAWG)
    else:
        if isinstance(rnsForSync, str): rnsForSync = LongWaveformGenerator.IDtoRNS(rnsForSync)
        rnsForSync = SyncRNS(rns=rnsForSync)
    rnsForAWG = packRNS(rns=rnsForAWG)
    rnsForTDC = packRNS(rns=rnsForTDC)

    # 给随机数
    RandomNumberSetting('TFQKDEncoding', 'RandomNumbers', rnsForAWG)  # 网页Encoding
    RandomNumberSetting('TFQKDSyncAlice', 'RandomNumbers', rnsForSync)  # 给Alice同步路的随机数
    RandomNumberSetting('QKDQBER', 'AliceRandomNumbers', rnsForTDC)  # 给后处理

    # 通道配置
    tdc.configureAnalyser('TFQKDEncoding', {'SignalChannel': 2})  # 'SignalChannel':TDC通道号
    tdc.configureAnalyser('TFQKDSyncAlice', {'SignalChannel': 4})
    worker.TFTDCAdapter.configureAnalyser('TFQKDSyncAlice', {'RandomNumbers': rnsForAWG, 'SignalChannel': 4})


def control_Bob(rnsForAWG=([1] * 1 + [1] * 9) * 400, rnsForTDC=([1] * 1 + [1] * 9) * 400, globalDelay=0.0, onoff=[1, 0, 1, 0], V=0, rnsForSync=None):
    # Bob的相关控制
    # Encoder 的定义: AWG CH1 -> Reference AM; AWG CH2 -> Decoy & Z AM; AWG CH3 -> PM1; AWG CH4 -> PM2;
    encoder = worker.TF_AWGEncoder_Bob
    # globalDelay = -2178.5
    # if isinstance(rnsForAWG, str): rnsForAWG = LongWaveformGenerator.IDtoRNS(rnsForAWG)
    if not isinstance(rnsForAWG, str): globalDelay = globalDelay % (10 * len(rnsForAWG))
    encoder.configure('sampleRate', 2e9)  # 采样率  不动
    encoder.configure('waveformLength', None)
    encoder.configure('waveformUnitLength', 20)
    encoder.configure('randomNumbers', rnsForAWG)  # rnsBobForAWG)

    encoder.configure('ampAM1', [0.49, 0.63, 0.68, 0.74] + [1])  # 此处的小数是归一化数值
    encoder.configure('biasAM1', [0.49] * 4 + [0.0])

    encoder.configure('ampPM1', [(i / 16 * V) for i in range(16)])  # V=0.244
    encoder.configure('widthAM1', [1.2, 10])  # [signal, reference]
    encoder.configure('widthPM1', 10)
    encoder.configure('delayAM1', globalDelay)
    encoder.configure('delayPM1', globalDelay + 38.5)  # -56.5
    encoder.configure('gainAM1', 1)
    encoder.configure('gainPM1', 1)

    if onoff[0] == 0:
        encoder.configure('ampAM1', [0] * 5)
        encoder.configure('biasAM1', [0] * 5)
    if onoff[2] == 0:
        encoder.configure('ampPM1', [0] * 16)

    waveforms = encoder.generateNewWaveform()
    # showWaveform(waveforms, showRange=(0, 4000))

    # 随机数上传处理
    if rnsForSync is None:
        rnsForSync = SyncRNS(rns=rnsForAWG)
    else:
        if isinstance(rnsForSync, str): rnsForSync = LongWaveformGenerator.IDtoRNS(rnsForSync)
        rnsForSync = SyncRNS(rns=rnsForSync)
    rnsForAWG = packRNS(rns=rnsForAWG)
    rnsForTDC = packRNS(rns=rnsForTDC)

    # 给随机数
    RandomNumberSetting('TFQKDEncoding', 'RandomNumbers', rnsForAWG)  # 网页Encoding
    RandomNumberSetting('TFQKDSyncBob', 'RandomNumbers', rnsForSync)  # 给Bob同步路的随机数
    RandomNumberSetting('QKDQBER', 'BobRandomNumbers', rnsForTDC)  # 给后处理

    # 通道配置
    tdc.configureAnalyser('TFQKDEncoding', {'SignalChannel': 3})  # 前八张小图显示的通道数据
    tdc.configureAnalyser('TFQKDSyncBob', {'SignalChannel': 5})  # 用于时钟同步的通道数据
    worker.TFTDCAdapter.configureAnalyser('TFQKDSyncBob', {'RandomNumbers': rnsForAWG, 'SignalChannel': 5})


def RandomNumberSetting(analyser, key, value):
    worker.TFTDCServer.configureAnalyser(analyser, {key: value})


def packRNS(rns):
    value = rns if len(rns) < 100000 else LongWaveformGenerator.RNStoID(rns=rns)
    return value


def run(VA, VB):
    LRG = LongWaveformGenerator()
    # RNS = LRG.waveformGenerator([2, 3], [1, 2])
    # RNS = LRG.simple_waveformGenerator([1]*400)
    # RNS = LRG.globalDelay_step1(4000)
    # RNS = LRG.globalDelay_step2(5000)

    # rnsAliceForAWG = LRG.waveformID()['LongRNS']['Alice']['rns_forAWG']
    # rnsAliceForTDC = LRG.waveformID()['LongRNS']['Alice']['rns_forTDC']
    # rnsBobForAWG = LRG.waveformID()['LongRNS']['Bob']['rns_forAWG']
    # rnsBobForTDC = LRG.waveformID()['LongRNS']['Bob']['rns_forTDC']
    # rnsAliceForSync = LRG.waveformID()['LongRNS']['Alice']['rns_forSync']
    # rnsBobForSync = LRG.waveformID()['LongRNS']['Bob']['rns_forSync']

    # rnsAliceForAWG = LRG.waveformID()['simple_wave']
    # rnsAliceForTDC = LRG.waveformID()['simple_wave']
    # rnsBobForAWG = LRG.waveformID()['simple_wave']
    # rnsBobForTDC = LRG.waveformID()['simple_wave']
    # rnsAliceForSync = LRG.waveformID()['simple_wave']
    # rnsBobForSync = LRG.waveformID()['simple_wave']

    rnsAliceForAWG = LRG.waveformID()['All ref']['Alice']
    rnsAliceForTDC = LRG.waveformID()['All ref']['Alice']
    rnsBobForAWG = LRG.waveformID()['All ref']['Bob']
    rnsBobForTDC = LRG.waveformID()['All ref']['Bob']
    rnsAliceForSync = LRG.waveformID()['All ref']['Alice']
    rnsBobForSync = LRG.waveformID()['All ref']['Bob']

    print('Long Waveform Generated.')

    globalDelayA = worker.TF_Registry.get('Runtime.Alice.Time.GlobalDelay')
    onoffA = [0, 0, 0, 0]
    control_Alice(rnsForAWG=rnsAliceForAWG, rnsForTDC=rnsAliceForTDC, globalDelay=globalDelayA, onoff=onoffA, V=VA, rnsForSync=rnsAliceForSync)
    globalDelayB = worker.TF_Registry.get('Runtime.Bob.Time.GlobalDelay')
    onoffB = [0, 0, 0, 0]
    control_Bob(rnsForAWG=rnsBobForAWG, rnsForTDC=rnsBobForTDC, globalDelay=globalDelayB, onoff=onoffB, V=VB, rnsForSync=rnsBobForSync)

    #
    # TDC处理所需的配置信息
    tdc.turnOnAnalyser('DeltaMetaAnalyser', {'Channel1': 2, 'GroupBy': 250, 'Channel2': 3, 'SyncChannel': 0, 'Period': 10000, 'Center': 5000, 'GateWidth': 1200})


if __name__ == '__main__':
    run(VA=0.69, VB=0.70)
    print('Done')

    # print(LongWaveformGenerator.RNStoID([1] + [0] * (4000 - 1)))
    # rns = LongWaveformGenerator.IDtoRNS('2022-10-06 23-54-15.429917 R239858')
    # print(rns, len(rns))
    # Alice_rns_ref = [64] * 400
    # Bob_rns_ref = [64] * 400
    # Alice_rns_ref = [LongWaveformGenerator.refReverse(rns=Alice_rns_ref[i]) if Alice_rns_ref[i] >= 64 and (i % 4 in [2, 3]) else LongWaveformGenerator.refReverse(Alice_rns_ref[i], negative=False) for i in range(len(Alice_rns_ref))]
    # Bob_rns_ref = [LongWaveformGenerator.refReverse(rns=Bob_rns_ref[i]) if Bob_rns_ref[i] >= 64 and (i % 4 in [1, 2]) else LongWaveformGenerator.refReverse(Bob_rns_ref[i], negative=False) for i in range(len(Alice_rns_ref))]
    # print(LongWaveformGenerator.RNStoID(Alice_rns_ref))
    # print(LongWaveformGenerator.RNStoID(Bob_rns_ref))
