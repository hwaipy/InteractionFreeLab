import random
import numpy as np
from random import Random
import msgpack
import sys, os
from interactionfreepy import IFWorker
import time

worker = IFWorker('tcp://172.20.8.33:1161')
tdc = worker.TFTDCServer


class LongWaveformGenerator:
    def __init__(self):
        # 从函数中获取参数
        waveformLength, part, Num_ref, Num_signal, PX, PY, PZ, PZ1 = LongWaveformGenerator.para()
        # 定义类参数
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

    @classmethod
    def para(cls):
        waveformLength = int(2E7)
        part = 400
        Num_ref = 140
        Num_signal = 255
        # PX = 0.043215
        # PY = 0.003492
        # PZ = 0.95268
        # PZ0 = 0.720766

        # PX = 0.0877885
        # PY = 0.177309
        # PZ = 0.07785
        # PZ1 = 1.0
        # PZ0 = 1 - PZ1

        # # miu=0.0541133       0.240645       0.498503
        # PX = 0.0470077
        # PY = 0.00323019
        # PZ = 0.264252
        # PZ1 = 1.0
        # PZ0 = 1 - PZ1

        # miu=0.0303853       0.482834       0.494035
        PX = 0.0626726
        PY = 0.209485
        PZ = 0.0531703
        PZ1 = 1.0
        PZ0 = 1 - PZ1
        return waveformLength, part, Num_ref, Num_signal, PX, PY, PZ, PZ1

    def __refGenerator(self, seed: int):
        rnd = Random(seed)
        rnsRef = [rnd.randint(0, 3) * 4 * 4 + 64 for i in range(self.Num_ref * self.numPart)]
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
        Z1Z0 = [rnd.random() for i in range(numZ)]
        rnsZ = [rnsZ[zi] if Z1Z0[zi] <= self.PZ1 else rnsZ[zi] + 0b1000000 for zi in range(numZ)]
        # 拼接
        rns_signal = rns0 + rnsX + rnsY + rnsZ
        # 乱序
        rnd.shuffle(rns_signal)
        print(f'numX={numX}, numY={numY}, numZ={numZ}, num0={num0}, num={numX+numY+numZ+num0}')
        print(f'length of signal = {self.numPart} * {self.Num_signal} = {len(rns_signal)}')
        return rns_signal

    def __gapGenerator(self, seed: int):
        rnd = Random(seed)
        rnsGap_forAWG = [rnd.randint(0, 63) for i in range(self.Num_gap * self.numPart)]
        rnsGap_forTDC = [i + 128 for i in rnsGap_forAWG]
        return rnsGap_forAWG, rnsGap_forTDC

    def refillRNS(self, A, B):

        length = self.numPart * self.Num_signal
        indexXX = [i for i in range(length) if 0 < A[i] < 64 and A[i] % 4 == 1 and 0 < B[i] < 64 and B[i] % 4 == 1]
        indexYY = [i for i in range(length) if 0 < A[i] < 64 and A[i] % 4 == 2 and 0 < B[i] < 64 and B[i] % 4 == 2]
        indexZ1Z1 = [i for i in range(length) if 0 < A[i] < 64 and A[i] % 4 == 3 and 0 < B[i] < 64 and B[i] % 4 == 3]

        def set_phase_diff(A, B, index):
            state = A[index[0]] % 4
            print(f'length of state {state} = {len(index)}')
            if len(index) < 16:
                print(f'length = {len(index)} < 16')
                return A, B
            while True:
                phase = [(A[i]//4 - B[i]//4) % 16 for i in index]
                fill_diff = [p for p in range(16) if p not in phase]
                if len(fill_diff) == 0:
                    print(f'state {state} no need to fill.')
                    break
                rnd = [random.randint(0, 15) for i in fill_diff]
                fill_rns = [[(rnd[i] + fill_diff[i]) % 16 * 4 + state, rnd[i] * 4 + state] for i in range(len(fill_diff))]
                print(f'phase {fill_diff} not in ABpairs')
                replace_index = [index[random.randint(0, len(index)-1)] for i in range(len(fill_diff))]
                for i in range(len(fill_diff)):
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
        # 若Z不发送，则将不发送的Z转化为对应相位编码的真空态
        rnsforAWG = [0 if (i % 4 == 3 and i >= 64) else i for i in rns_signal]
        rnsforTDC = rns_signal
        return rnsforAWG, rnsforTDC

    def joint(self, rns_ref, rns_gap, rns_signal):
        rns = []
        for i in range(self.numPart):
            rns.extend(rns_ref[i*self.Num_ref:(i+1)*self.Num_ref])
            rns.extend(rns_gap[i * self.Num_gap:(i + 1) * self.Num_gap])
            rns.extend(rns_signal[i * self.Num_signal:(i + 1) * self.Num_signal])
        return rns

    def waveformGenerator(self, Alice_reversed, Bob_reversed, fillYN=False):
        # 产生Alice与Bob的signal随机数
        Alice_rns_signal = self.__signalGenerator(seed=88)
        Bob_rns_signal = self.__signalGenerator(seed=56)
        # 补充不存在的随机数对
        if fillYN: Alice_rns_signal, Bob_rns_signal = self.refillRNS(Alice_rns_signal, Bob_rns_signal)
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
        Alice_rns_ref = [Alice_rns_ref[i] + 1 if (i % 2 in Alice_reversed) else Alice_rns_ref[i] for i in range(len(Alice_rns_ref))]
        Bob_rns_ref = [Bob_rns_ref[i] + 1 if (i % 2 in Bob_reversed) else Bob_rns_ref[i] for i in range(len(Bob_rns_ref))]
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
            if 128 > rns_forTDC[i] >= 64:
                if rns_forTDC[i] % 4 == 3:
                    signal.append(i)
                    signalZ.append(i)
                    signalZ0.append(i)
                else:
                    ref.append(i)
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
                    signalZ1.append(i)
            elif rns_forTDC[i] >= 128:
                gap.append(i)

        # 计算理论比例
        waveformLength, part, Num_ref, Num_signal, PX, PY, PZ, PZ1 = LongWaveformGenerator.para()
        numgap = part - Num_ref - Num_signal
        numpart = round(waveformLength/part)
        PZ0 = 1 - PZ1
        P0 = 1 - PX - PY - PZ

        result = {
            'count':f'ref={len(ref)}(理论：{numpart*Num_ref}), gap={len(gap)}(理论：{numpart*numgap}), signal={len(signal)}(理论：{numpart*Num_signal}), signal0={len(signal0)}(理论：{numpart*Num_signal*P0}), signalX={len(signalX)}(理论：{numpart*Num_signal*PX}), signalY={len(signalY)}(理论：{numpart*Num_signal*PY}), signalZ={len(signalZ)}(理论：{numpart*Num_signal*PZ}), signalZ1={len(signalZ1)}(理论：{numpart*Num_signal*PZ*PZ1}), signalZ0={len(signalZ0)}(理论：{numpart*Num_signal*PZ*PZ0})',
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

    @staticmethod
    def selectSame(list1: list, list2: list):
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

        # 计算理论比例
        waveformLength, part, Num_ref, Num_signal, PX, PY, PZ, PZ1 = LongWaveformGenerator.para()
        PZ0 = 1 - PZ1
        P0 = 1 - PX - PY - PZ

        state = ['signal', 'signal0', 'signalX', 'signalY', 'signalZ', 'signalZ1', 'signalZ0']
        P = {'signal': 1, 'signal0': P0, 'signalX': PX, 'signalY': PY, 'signalZ': PZ, 'signalZ1': PZ1*PZ, 'signalZ0': PZ0*PZ}
        Count = pd.DataFrame(columns=state, index=state)
        for sA in state:
            for sB in state:
                same = LongWaveformGenerator.selectSame(result['Alice'][sA], result['Bob'][sB])
                Count[sB][sA] = f'个数：{len(same)}(理论：{waveformLength*Num_signal/part*P[sA]*P[sB]})\n占比：{len(same) / len(Alice_rns_forTDC)}(理论：{Num_signal/part*P[sA]*P[sB]})\n占signal比：{len(same) / len(result["Alice"]["signal"])}(理论：{P[sA]*P[sB]})'



        allref = LongWaveformGenerator.selectSame(result['Alice']['ref'], result['Bob']['ref'])
        allsig = LongWaveformGenerator.selectSame(result['Alice']['signal'], result['Bob']['signal'])

        # all00 = LongWaveformGenerator.selectSame(result['Alice']['signal0'], result['Bob']['signal0'])
        # sigXX = LongWaveformGenerator.selectSame(result['Alice']['signalX'], result['Bob']['signalX'])
        # sigYY = LongWaveformGenerator.selectSame(result['Alice']['signalY'], result['Bob']['signalY'])
        # sigZZ = LongWaveformGenerator.selectSame(result['Alice']['signalZ'], result['Bob']['signalZ'])
        # sigZ0Z0 = LongWaveformGenerator.selectSame(result['Alice']['signalZ0'], result['Bob']['signalZ0'])
        # sigZ0Z1 = LongWaveformGenerator.selectSame(result['Alice']['signalZ0'], result['Bob']['signalZ1'])
        # sigZ1Z0 = LongWaveformGenerator.selectSame(result['Alice']['signalZ1'], result['Bob']['signalZ0'])
        # sigZ1Z1 = LongWaveformGenerator.selectSame(result['Alice']['signalZ1'], result['Bob']['signalZ1'])


        print(f'reference对数：{len(allref)}, 占比：{len(allref)/len(Alice_rns_forTDC)}(理论占比：{Num_ref/part})')
        print(f'signal对数：{len(allsig)}, 占比：{len(allsig)/len(Alice_rns_forTDC)}(理论占比：{Num_signal/part})')

        print(Count)

        # print(f'00个数：{len(all00)}(理论个数：{waveformLength*Num_signal/part*P0*P0}), 占比：{len(all00) / len(Alice_rns_forTDC)}(理论占比：{Num_signal/part*P0*P0}), 占signal比：{len(all00) / len(result["Alice"]["signal"])}(理论占比：{P0*P0})')
        # print(f'XX个数：{len(sigXX)}(理论个数：{waveform Length*Num_signal/part*PX*PX}), 占比：{len(sigXX) / len(Alice_rns_forTDC)}(理论占比：{Num_signal/part*PX*PX}), 占signal比：{len(sigXX) / len(result["Alice"]["signal"])}(理论占比：{PX*PX})')
        # print(f'YY个数：{len(sigYY)}(理论个数：{waveformLength*Num_signal/part*PY*PY}), 占比：{len(sigYY) / len(Alice_rns_forTDC)}(理论占比：{Num_signal/part*PY*PY}), 占signal比：{len(sigYY) / len(result["Alice"]["signal"])}(理论占比：{PY*PY})')
        # print(f'ZZ个数：{len(sigZZ)}(理论个数：{waveformLength*Num_signal/part*PZ*PZ}), 占比：{len(sigZZ) / len(Alice_rns_forTDC)}(理论占比：{Num_signal/part*PZ*PZ}), 占signal比：{len(sigZZ) / len(result["Alice"]["signal"])}(理论占比：{PZ*PZ})')
        #
        # lZZ = [len(sigZ0Z0), len(sigZ0Z1), len(sigZ1Z0), len(sigZ1Z1)]
        # pZZ = [PZ0*PZ0, PZ1*PZ0, PZ0*PZ1, PZ1*PZ1]
        # print(f'ZZ态(AB)[00, 01, 10, 11] 个数{lZZ}(理论个数：{[waveformLength*Num_signal/part*i*PZ*PZ for i in pZZ]}), 占比：{[i/len(Alice_rns_forTDC) for i in lZZ]}(理论占比：{[i*Num_signal/part*PZ*PZ for i in pZZ]}), 占signal比：{[i/len(result["Alice"]["signal"]) for i in lZZ]}(理论占比：{[i*PZ*PZ for i in pZZ]}), 占ZZ比：{[i/len(sigZZ) for i in lZZ]}(理论占比：{pZZ})')
        return

    @classmethod
    def RNStoID(cls, rns):
        return worker_main.TF_FileStorage.writeMassive(data=msgpack.packb(rns))

    @classmethod
    def IDtoRNS(cls, id: str):
        return msgpack.unpackb(worker_main.TF_FileStorage.readMassive(id=id))

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
        # Gap=10个 Z态老定义
        # waveform_ID['LongRNS']['Alice']['old_rns_forTDC'] = '2022-10-06 23-38-26.449078 R552913'
        # waveform_ID['LongRNS']['Bob']['old_rns_forTDC'] = '2022-10-06 23-38-28.714216 R501825'
        # waveform_ID['LongRNS']['Alice']['old_rns_forAWG'] = '2022-10-06 23-38-30.907948 R402048'
        # waveform_ID['LongRNS']['Bob']['old_rns_forAWG'] = '2022-10-06 23-38-33.109742 R199986'
        # # sync = [64] * 140 + [128] * 10 + [1] * 250
        # waveform_ID['LongRNS']['Alice']['old_rns_forSync'] = '2022-10-06 23-54-15.429917 R239858'
        # waveform_ID['LongRNS']['Bob']['old_rns_forSync'] = '2022-10-06 23-54-15.429917 R239858'

        # # Gap=3个 Z态新定义
        # waveform_ID['LongRNS']['Alice']['new_rns_forTDC'] = '2022-11-04 00-49-10.427711 R802708'
        # waveform_ID['LongRNS']['Bob']['new_rns_forTDC'] = '2022-11-04 00-49-12.299991 R742683'
        # waveform_ID['LongRNS']['Alice']['new_rns_forAWG'] = '2022-11-04 00-49-09.752811 R170226'
        # waveform_ID['LongRNS']['Bob']['new_rns_forAWG'] = '2022-11-04 00-49-11.622840 R520914'
        # # sync = [64] * 140 + [128] * 3 + [1] * 257
        # waveform_ID['LongRNS']['Alice']['new_rns_forSync'] = '2022-11-04 00-49-12.313843 R260683'
        # waveform_ID['LongRNS']['Bob']['new_rns_forSync'] = '2022-11-04 00-49-12.313843 R260683'

        # Gap=5个 Z态新定义
        # waveform_ID['LongRNS']['Alice']['rns_forTDC'] = '2022-11-04 00-58-30.211386 R307427'
        # waveform_ID['LongRNS']['Alice']['rns_forAWG'] = '2022-11-04 00-58-29.510779 R754880'
        # waveform_ID['LongRNS']['Bob']['rns_forTDC'] = '2022-11-04 00-58-31.589489 R881166'
        # waveform_ID['LongRNS']['Bob']['rns_forAWG'] = '2022-11-04 00-58-30.908357 R865179'
        # # sync = [64] * 140 + [128] * 5 + [1] * 255
        # waveform_ID['LongRNS']['Alice']['rns_forSync'] = '2022-11-04 00-58-31.623548 R776498'
        # waveform_ID['LongRNS']['Bob']['rns_forSync'] = '2022-11-04 00-58-31.623548 R776498'

        # # Gap=5个 Z态新定义 202304新优化参数   暗计数110 衰减35dB  误码5%  Z态新定义 yz成码
        # waveform_ID['LongRNS']['Alice']['rns_forTDC'] = '2023-05-30 02-32-37.243109 R101565'
        # waveform_ID['LongRNS']['Alice']['rns_forAWG'] = '2023-05-30 02-31-31.942126 R594694'
        # waveform_ID['LongRNS']['Bob']['rns_forTDC'] = '2023-05-30 02-34-40.358678 R323895'
        # waveform_ID['LongRNS']['Bob']['rns_forAWG'] = '2023-05-30 02-33-36.506440 R758595'
        # # sync = [64] * 140 + [128] * 5 + [1] * 255
        # waveform_ID['LongRNS']['Alice']['rns_forSync'] = '2023-05-30 02-34-40.382393 R484176'
        # waveform_ID['LongRNS']['Bob']['rns_forSync'] = '2023-05-30 02-34-40.382393 R484176'

        ##############################常用#################################

        # Gap=5个 新三四强度 暗计数40  衰减30  误码5%  Z态新定义 yz成码
        # waveform_ID['LongRNS']['Alice']['rns_forTDC'] = '2023-06-03 23-29-07.013601 R513371'
        # # waveform_ID['LongRNS']['Alice']['rns_forAWG'] = '2023-06-03 23-28-21.725000 R841964'  # 二正二负
        # waveform_ID['LongRNS']['Alice']['rns_forAWG'] = '2025-04-15 23-20-16.218211 R253350'  # 一正一负
        # waveform_ID['LongRNS']['Bob']['rns_forTDC'] = '2023-06-03 23-30-47.632215 R298145'
        # # waveform_ID['LongRNS']['Bob']['rns_forAWG'] = '2023-06-03 23-29-56.536549 R352735'  # 二正二负
        # waveform_ID['LongRNS']['Bob']['rns_forAWG'] = '2025-04-15 23-20-54.929196 R507772'  # 一正一负
        # # sync = [64] * 140 + [128] * 5 + [1] * 255
        waveform_ID['LongRNS']['Alice']['rns_forSync'] = '2023-06-03 23-30-47.659939 R119759'
        waveform_ID['LongRNS']['Bob']['rns_forSync'] = '2023-06-03 23-30-47.659939 R119759'
        ##############################常用#################################

        # 新长随机数
        # waveform_ID['LongRNS']['Alice']['rns_forTDC'] = '2025-04-16 02-36-50.424970 R691390'
        # waveform_ID['LongRNS']['Alice']['rns_forAWG'] = '2025-04-16 02-36-51.563367 R863972'  # 一正一负
        # waveform_ID['LongRNS']['Bob']['rns_forTDC'] = '2025-04-16 02-36-52.500498 R633848'
        # waveform_ID['LongRNS']['Bob']['rns_forAWG'] = '2025-04-16 02-36-53.487761 R572763'  # 一正一负

    # 短循环
        waveform_ID['LongRNS']['Alice']['rns_forTDC'] = '2025-04-16 01-46-14.516811 R477567'
        waveform_ID['LongRNS']['Alice']['rns_forAWG'] = '2025-04-16 01-46-14.516811 R477567'  # 一正一负
        waveform_ID['LongRNS']['Bob']['rns_forTDC'] = '2025-04-16 01-46-15.446382 R600977'
        waveform_ID['LongRNS']['Bob']['rns_forAWG'] = '2025-04-16 01-46-15.446382 R600977'  # 一正一负


        # Delay
        waveform_ID['Delay'] = {'step1': None, 'step2': None}
        # [64] * 400 + [0] * int(2E7 - 400)
        # waveform_ID['Delay']['step1'] = '2022-10-07 00-27-49.098234 R798816'
        # [64, 65] * 200 + [0] * int(2E7 - 400)
        waveform_ID['Delay']['step1'] = '2023-04-06 19-04-10.851159 R820892'
        # [1] + [0] * (4000 - 1)
        waveform_ID['Delay']['step2'] = '2022-10-07 00-28-28.913120 R605477'

        # 标半波电压用: rns = ([64, 65] * 70 + [128] * 5 + [3] * 255) * int(2E7 / 400)
        waveform_ID['LongRNS']['PMV0'] = '2024-03-13 00-33-23.077653 R936489'

        return waveform_ID


def generate_new_Longwaveform(generateID=True):
    lwg = LongWaveformGenerator()
    RNS = lwg.waveformGenerator(Alice_reversed=[1], Bob_reversed=[1])

    if generateID:
        print('Alice rns_forAWG', LongWaveformGenerator.RNStoID(RNS['Alice']['rns_forAWG']), len(RNS['Alice']['rns_forAWG']))
        print('Alice rns_forTDC', LongWaveformGenerator.RNStoID(RNS['Alice']['rns_forTDC']), len(RNS['Alice']['rns_forTDC']))
        print('Bob rns_forAWG', LongWaveformGenerator.RNStoID(RNS['Bob']['rns_forAWG']), len(RNS['Bob']['rns_forAWG']))
        print('Bob rns_forTDC', LongWaveformGenerator.RNStoID(RNS['Bob']['rns_forTDC']), len(RNS['Bob']['rns_forTDC']))
        print('rns_forSync', LongWaveformGenerator.RNStoID([64] * 140 + [128] * 5 + [1] * 255))

    return RNS


def check_new_Longwaveform(AliceRNSforTDC, BobRNSforTDC):
    if isinstance(AliceRNSforTDC, str): AliceRNSforTDC = LongWaveformGenerator.IDtoRNS(AliceRNSforTDC)
    if isinstance(BobRNSforTDC, str): BobRNSforTDC = LongWaveformGenerator.IDtoRNS(BobRNSforTDC)
    print('='*30, 'check RNS', '='*30)
    LongWaveformGenerator.analyzeAB_RNS(Alice_rns_forTDC=AliceRNSforTDC, Bob_rns_forTDC=BobRNSforTDC)


def SyncRNS(rns):

    def allsigncheck(rns):
        n = 0
        for r in rns:
            if r >= 64 and r % 4 != 3: n += 1
        if n > 0:
            print('随机数中不全是signal')
            return False
        else:
            print('随机数中全是signal')
            return True

    def changeRNS(rns):
        end = False
        period = [0, 0, 0]  # ref个数，gap个数，signal个数
        for r in rns:
            if end and 64 <= r:
                break
            if 0 <= r < 64 or r % 4 == 3:
                end = True
                period[2] += 1
            if 64 <= r < 128 and r % 4 != 3:
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


def control_Alice(rnsForAWG=([1] * 1 + [1] * 9) * 400, rnsForTDC=([1] * 1 + [1] * 9) * 400, globalDelay=0.0, onoff=[1, 0, 1, 0], V=0, rnsForSync=None, refSyncYN=False, rnsType=['ref']*140+['other']*260, syncChannel=4, encodingChannel=3):
    # Control: Alice
    # Encoder 的定义: AWG CH1 -> Reference AM; AWG CH2 -> Decoy & Z AM; AWG CH3 -> PM1; AWG CH4 -> PM2;
    encoder = worker.TF_AWGEncoder_Adi
    # globalDelay = -11223

    # if isinstance(rnsForAWG, str): rnsForAWG = LongWaveformGenerator.IDtoRNS(rnsForAWG)
    if not isinstance(rnsForAWG, str): globalDelay = globalDelay % (10 * len(rnsForAWG))
    encoder.configure('sampleRate', 2e9)  # 采样率  不动
    encoder.configure('waveformLength', None)
    encoder.configure('waveformUnitLength', 20)
    encoder.configure('randomNumbers', rnsForAWG)

    # ref/signal 8.5dB DC值AM1=4.73， AM2=3.29， AM3=7
    # encoder.configure('ampAM1', [0.47, 0.618, 0.679, 0.73] + [1] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.47] * 4 + [0.0])

    # ref/signal 18dB DC值AM1=3.61， AM2=2.64， AM3=7
    # encoder.configure('ampAM1', [0.47, 0.544, 0.57, 0.587] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.47] * 4 + [0.0])

    # ref/signal 11.66dB 新三四强度 31dB DC值AM1=4.49， AM2=3.26， AM3=7
    """
    X/Z: 0.07840145567975046
    Y/Z: 0.9692581232128932
    ref/signal: 11.656884431125025  dB
    """
    # encoder.configure('ampAM1', [0.47, 0.563, 0.672, 0.675] + [1] + [1])  # 此处的小数是归一化数值
    # encoder.configure('ampAM1', [0.47, 0.563, 0.68, 0.686] + [1] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.47] * 4 + [0.0])

    # ref/signal 15.08dB 新三四强度 35dB DC值AM1=4.83， AM2=3.22， AM3=7
    """
    X/Z: 0.07840145567975046
    Y/Z: 0.9692581232128932
    ref/signal: 15.08111123934709 dB
    """
    # encoder.configure('ampAM1', [0.47, 0.543, 0.623, 0.625] + [1] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.47] * 4 + [0.0])

    # ref/signal 22.66dB 新三四强度 31dB DC值AM1=4.29， AM2=2.149， AM3=7
    """
    X/Z: 0.07840145567975046
    Y/Z: 0.9692581232128932
    ref/signal: 11.656884431125025  dB
    """
    encoder.configure('ampAM1', [0.49, 0.593, 0.695, 0.695] + [1])  # 此处的小数是归一化数值  # DC值AM1=4.34， AM2=1.979， AM3=7
    # encoder.configure('ampAM1', [0.47, 0.495, 0.56, 0.561] + [1] + [1])  # 此处的小数是归一化数值  # DC值AM1=4.84， AM2=2.079， AM3=7

    encoder.configure('biasAM1', [0.49] * 4 + [0.49])

    encoder.configure('ampPM1', [(i / 16 * V) for i in range(16)])  # V=0.32 分通道通过率34.88%
    encoder.configure('widthAM1', [1.2, 8])  # [signal, reference]
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

    # 随机数上传处理
    if rnsForSync is None:
        rnsForSync = SyncRNS(rns=rnsForAWG)
    else:
        print(rnsForSync)
        if isinstance(rnsForSync, str): rnsForSync = LongWaveformGenerator.IDtoRNS(rnsForSync)
        rnsForSync = SyncRNS(rns=rnsForSync)
    rnsForSync = [64] * 140 + [128] * 5 + [3] * 255  #######
    rnsForAWG = packRNS(rns=rnsForAWG)
    rnsForTDC = packRNS(rns=rnsForTDC)

    # 给随机数
    RandomNumberSetting('TFQKDEncoding', {'RandomNumbers': rnsForAWG})  # 网页Encoding
    if refSyncYN:
        rnsType = [1 if rnsType[i] == 'ref' else 100 for i in range(len(rnsType)) if i % 2 == 0]
        RandomNumberSetting('TFQKDSyncAlice', {'SignalChannel': syncChannel, 'Period': 20000, 'RandomNumbers': rnsType, 'BinCount': 200})
    else:
        RandomNumberSetting('TFQKDSyncAlice', {'RandomNumbers': rnsForSync, 'Period': 10000})  # 给Alice同步路的随机数
    RandomNumberSetting('QKDQBER', {'AliceRandomNumbers': rnsForTDC})  # 给后处理

    # 通道配置
    tdc.configureAnalyser('TFQKDEncoding', {'SignalChannel': encodingChannel})  # 'SignalChannel':TDC通道号
    tdc.configureAnalyser('TFQKDSyncAlice', {'SignalChannel': syncChannel})
    tdc.configureAnalyser('TFQKDSyncAliceMonitor', {'SignalChannel': syncChannel})  # 用于时钟同步的通道数据
    tdc.configureAnalyser('TFQKDSyncAliceMonitor', {'RandomNumbers': rnsForSync, 'Period': 10000})  # 用于时钟同步的通道数据
    # worker.TFTDCAdapter.configureAnalyser('TFQKDSyncAlice', {'RandomNumbers': rnsForAWG, 'SignalChannel': 4})

    # worker.TFTDCServer.configureAnalyser('TFQKDSyncAlice', {'SignalChannel': 3, 'Period': 20000, 'RandomNumbers': [1] * 80 + [100] * 120, 'BinCount': 200})
    # worker.TFTDCAdapter.configureAnalyser('TFQKDSyncAlice', {'SignalChannel': 3, 'Period': 20000, 'RandomNumbers': [1] * 80 + [100] * 120, 'BinCount': 200})


def control_Bob(rnsForAWG=([1] * 1 + [1] * 9) * 400, rnsForTDC=([1] * 1 + [1] * 9) * 400, globalDelay=0.0, onoff=[1, 0, 1, 0], V=0, rnsForSync=None, refSyncYN=False, rnsType=['ref']*140+['other']*260, syncChannel=5, encodingChannel=3):
    # Bob的相关控制
    # Encoder 的定义: AWG CH1 -> Reference AM; AWG CH2 -> Decoy & Z AM; AWG CH3 -> PM1; AWG CH4 -> PM2;
    encoder = worker_main.TF_AWGEncoder_Bob
    # globalDelay = -2178.5
    # if isinstance(rnsForAWG, str): rnsForAWG = LongWaveformGenerator.IDtoRNS(rnsForAWG)
    if not isinstance(rnsForAWG, str): globalDelay = globalDelay % (10 * len(rnsForAWG))
    encoder.configure('sampleRate', 2e9)  # 采样率  不动
    encoder.configure('waveformLength', None)
    encoder.configure('waveformUnitLength', 20)
    encoder.configure('randomNumbers', rnsForAWG)  # rnsBobForAWG)
    encoder.configure('widthAM1', [1.2, 10])  # [signal, reference]
    encoder.configure('widthPM1', 10)
    encoder.configure('delayAM1', globalDelay)
    encoder.configure('delayPM1', globalDelay + 38.5)  # -56.5
    # encoder.configure('gainAM1', 1)
    # encoder.configure('gainPM1', 1)

    # 设置AWG的其他参数
    Bob_AWG_set(V=V, encoder=encoder, onoff=onoff)

    # 生成波形
    waveforms = encoder.generateNewWaveform()

    # 随机数上传处理
    if rnsForSync is None:
        rnsForSync = SyncRNS(rns=rnsForAWG)
    else:
        if isinstance(rnsForSync, str): rnsForSync = LongWaveformGenerator.IDtoRNS(rnsForSync)
        rnsForSync = SyncRNS(rns=rnsForSync)

    rnsForAWG = packRNS(rns=rnsForAWG)
    rnsForTDC = packRNS(rns=rnsForTDC)

    # 给随机数
    RandomNumberSetting('TFQKDEncoding', {'RandomNumbers': rnsForAWG})  # 网页Encoding
    if refSyncYN:
        rnsType = [1 if rnsType[i] == 'ref' else 100 for i in range(len(rnsType)) if i % 2 == 0]
        RandomNumberSetting('TFQKDSyncBob', {'SignalChannel': syncChannel, 'Period': 20000, 'RandomNumbers': rnsType, 'BinCount': 200})
    else:
        RandomNumberSetting('TFQKDSyncBob', {'RandomNumbers': rnsForSync, 'Period': 10000})  # 给Bob同步路的随机数
    RandomNumberSetting('QKDQBER', {'BobRandomNumbers': rnsForTDC})  # 给后处理

    # 通道配置
    tdc.configureAnalyser('TFQKDEncoding', {'SignalChannel': encodingChannel})  # 前八张小图显示的通道数据
    tdc.configureAnalyser('TFQKDSyncBob', {'SignalChannel': syncChannel})  # 用于时钟同步的通道数据
    tdc.configureAnalyser('TFQKDSyncBobMonitor', {'SignalChannel': syncChannel})  # 用于时钟同步的通道数据
    tdc.configureAnalyser('TFQKDSyncBobMonitor', {'RandomNumbers': rnsForSync, 'Period': 10000})  # 用于时钟同步的通道数据
    # worker.TFTDCAdapter.configureAnalyser('TFQKDSyncBob', {'RandomNumbers': rnsForAWG, 'SignalChannel': 5})


def Bob_AWG_set(V, encoder=worker.Encoder_Bob_Test, onoff=[1, 0, 1, 0]):

    #  ref/signal 8.53dB DC值AM1=3.05, AM2=9.8, AM3=14
    # encoder.setAmplitudes('ampAM1', O=0.49, X=0.64, Y=0.675, Z=0.74, Ref=1.0)
    # encoder.setAmplitudes('biasAM1', O=0.49, X=0.49, Y=0.49, Z=0.49, Ref=0.0)

    #  ref/signal 18dB DC值AM1=2.83， AM2=10.2， AM3=14
    # encoder.setAmplitudes('ampAM1', O=0.49, X=0.553, Y=0.564, Z=0.60, Ref=1.0)
    # encoder.setAmplitudes('biasAM1', O=0.49, X=0.49, Y=0.49, Z=0.49, Ref=0.0)

    #  ref/signal 11.66dB 新理论模型，三四强度  DC值AM1=2.7， AM2=9.49， AM3=14
    """
    X/Z: 0.07840145567975046
    Y/Z: 0.9692581232128932
    ref/signal: 11.656884431125025  dB
    """
    # encoder.setAmplitudes('ampAM1', O=0.49, X=0.582, Y=0.698, Z=0.698, Ref=1.0)
    encoder.setAmplitudes('ampAM1', O=0.49, X=0.599, Y=0.725, Z=0.727, Ref=1.0)

    encoder.setAmplitudes('biasAM1', O=0.49, X=0.49, Y=0.49, Z=0.49, Ref=0.0)

    #  ref/signal 15.08dBdB 新理论模型，三四强度  DC值AM1=2.8， AM2=9.8， AM3=14
    """
    X/Z: 0.07840145567975046
    Y/Z: 0.9692581232128932
    ref/signal: 15.08111123934709 dB
    """
    # encoder.setAmplitudes('ampAM1', O=0.49, X=0.556, Y=0.634, Z=0.635, Ref=1.0)
    # encoder.setAmplitudes('biasAM1', O=0.49, X=0.49, Y=0.49, Z=0.49, Ref=0.0)

    # PM
    # encoder.setV2Pi('PM1', V)
    encoder.setVoltages('ampPM1', [i / 16 * V for i in range(16)])

    # 关闭通道
    if onoff[0] == 0:
        encoder.configure('ampAM1', O=0, X=0, Y=0, Z=0, Ref=0)
        encoder.configure('biasAM1', O=0, X=0, Y=0, Z=0, Ref=0)
    if onoff[2] == 0:
        encoder.setV2Pi('PM1', 0)


def RandomNumberSetting(analyser, keyANDvalue):
    worker.TFTDCServer.configureAnalyser(analyser, keyANDvalue)


def packRNS(rns):
    value = rns if len(rns) < 100000 else LongWaveformGenerator.RNStoID(rns=rns)
    return value


def getRNS():
    LRG = LongWaveformGenerator()
    # RNS = LRG.waveformGenerator([2, 3], [1, 2])
    # RNS = LRG.simple_waveformGenerator([1]*400)
    # RNS = LRG.globalDelay_step1(4000)
    # RNS = LRG.globalDelay_step2(5000)

    rnsAliceForAWG = LRG.waveformID()['LongRNS']['Alice']['rns_forAWG']
    rnsAliceForTDC = LRG.waveformID()['LongRNS']['Alice']['rns_forTDC']
    rnsAliceForSync = LRG.waveformID()['LongRNS']['Alice']['rns_forSync']
    rnsBobForAWG = LRG.waveformID()['LongRNS']['Bob']['rns_forAWG']
    rnsBobForTDC = LRG.waveformID()['LongRNS']['Bob']['rns_forTDC']
    rnsBobForSync = LRG.waveformID()['LongRNS']['Bob']['rns_forSync']

    # rnsAliceForAWG = LRG.waveformID()['simple_wave']
    # rnsAliceForTDC = LRG.waveformID()['simple_wave']
    # rnsAliceForSync = LRG.waveformID()['simple_wave']
    # rnsBobForAWG = LRG.waveformID()['simple_wave']
    # rnsBobForTDC = LRG.waveformID()['simple_wave']
    # rnsBobForSync = LRG.waveformID()['simple_wave']

    # rnsAliceForAWG = LRG.waveformID()['All ref']['Alice']
    # rnsAliceForTDC = LRG.waveformID()['All ref']['Alice']
    # rnsAliceForSync = LRG.waveformID()['All ref']['Alice']
    # rnsBobForAWG = LRG.waveformID()['All ref']['Bob']
    # rnsBobForTDC = LRG.waveformID()['All ref']['Bob']
    # rnsBobForSync = LRG.waveformID()['All ref']['Bob']

    return rnsAliceForAWG, rnsAliceForTDC, rnsAliceForSync, rnsBobForAWG, rnsBobForTDC, rnsBobForSync


def run(VA, VB, wf: list = 'RNS', target=None, refSyncYN=False, rnsType=['ref']*140+['other']*260, AliceEncodingChannel=3, BobEncodingChannel=2, AliceSyncChannel=4, BobSyncChannel=5, globalDelayA=None, globalDelayB=None):
    onoffA = [1, 0, 1, 0]
    onoffB = [1, 0, 1, 0]
    if wf == 'PMV0':
        print(f'{target} PM V=0')
        wf = [64, 65] * 70 + [128] * 5 + [3] * 255
        rnsAliceForAWG, rnsAliceForTDC, rnsAliceForSync, rnsBobForAWG, rnsBobForTDC, rnsBobForSync = [wf for i in range(6)]
    else:
        # wf = [64, 65] * 70 + [128] * 5 + [3] * 255
        # wf = [3 + i * 4 for i in range(16)] * 25
        # wf = ([3] + [0] * 99) * 4

        # rl = [64, 65] * 70
        # for i in range(len(rl)):
        #     rl[i] += (int(i / 2) % 16) * 4
        # sl = [2] * 250
        # for i in range(len(sl)):
        #     sl[i] += (i % 16) * 4
        #
        # wf = rl + [128] * 5 + sl + [3, 0, 0, 3, 0]

        # wf =40+++
        rndalice = Random(10)
        rnsRefalice = [num for _ in range(70) for num in (rndalice.randint(0, 15)*4 + 64, rndalice.randint(0, 15)*4 + 65)]
        rnsSinalalice=[rndalice.randint(0,63) for _ in range(255)]
        # 140 ref  64 + i * 4 (i = 0 - 15)   65 + i * 4 (i = 0 - 15)
        # [128] * 5
        # [0-63] * 255
        wf = rnsRefalice+[128] * 5+rnsSinalalice
        # wf=[64,65]*70+[128]*5+[0]*75+[3]*60+[2]*60+[1]*60

        rnsAliceForAWG, rnsAliceForTDC, rnsAliceForSync = [wf for i in range(3)]
        # wf = [3 + i * 0 for i in range(16)] * 25
        rnsBobForAWG, rnsBobForTDC, rnsBobForSync = [wf for i in range(3)]
    print('Long Waveform Generated.')
    # 生成波形
    if target is None or target == 'Alice': control_Alice(rnsForAWG=rnsAliceForAWG, rnsForTDC=rnsAliceForTDC, globalDelay=0.0, onoff=onoffA, V=VA, rnsForSync=rnsAliceForSync, refSyncYN=refSyncYN, rnsType=rnsType, encodingChannel=AliceEncodingChannel, syncChannel=AliceSyncChannel)
    if target is None or target == 'Bob': control_Bob(rnsForAWG=rnsBobForAWG, rnsForTDC=rnsBobForTDC, globalDelay=0.0, onoff=onoffB, V=VB, rnsForSync=rnsBobForSync, refSyncYN=refSyncYN, rnsType=rnsType, encodingChannel=BobEncodingChannel, syncChannel=BobSyncChannel)
    # TDC处理所需的配置信息
    # tdc.turnOnAnalyser('DeltaMetaAnalyser', {'Channel1': 2, 'GroupBy': 250, 'Channel2': 3, 'SyncChannel': 0, 'Period': 10000, 'Center': 5000, 'GateWidth': 1200})



# run(VA=0.69, VB=0.715, target='Alice', refSyncYN=False, rnsType=['ref'] * 140 + ['other'] * 260, wf='PMV0')



#########################################################################################################################################################
# Random Numbers

def generateRandomNumbers(refCount, gapCount, signalCount, repeat, px, py, pz, seed=None):
    """
    随机数定义:
    -----------------------------------------
    |    |    |    |    |    |    |    |    |
    | R7 | R6 | R5 | R4 | R3 | R2 | R1 | R0 |
    |    |    |    |    |    |    |    |    |
    -----------------------------------------
    每个随机数占8bit。
    R5R4R3R2 代表16个相位值, 与另外四位完全独立。
    R7R6 = 0b01 时为 Ref, R1R0 应 = 0b00
    R7R6 = 0b00 为 Signal, R1R0 由小到大分别代表 O, X, Y, Z
    R7R6R1R0 = 0b1000 为 Gap, R1R0 应 = 0b00
    """
    assert px + py + pz < 1
    rand = random.Random(seed)
    rns = []
    for i in range(repeat):
        for iRef in range(refCount):
            rns.append(0b01000000 + (rand.randint(0, 15) << 2))
        for iGap in range(gapCount):
            rns.append(0b10000000 + (rand.randint(0, 15) << 2))
        for iSignal in range(signalCount):
            r = 0b00000000 + (rand.randint(0, 15) << 2)
            decoy = rand.random()
            if decoy < pz: r += 0b11
            elif decoy < pz + py: r += 0b10
            elif decoy < pz + py + px: r += 0b01
            else: r += 0b00
            rns.append(r)
    return rns

def decorateAWG(rns):
    rns = [rn for rn in rns]
    for i in range(len(rns)):
        rn = rns[i]
        if (rns[i] & 0b1000000) >> 6 == 1 and i % 2 == 0:
            rns[i] += 1
    return rns

#########################################################################################################################################################

if __name__ == '__main__':
    rnsAlice = generateRandomNumbers(refCount=140, gapCount=5, signalCount=255, repeat=25, px=0.063, py=0.209, pz=0.053, seed=25)

    ###### 配置 AWG ######

    ON = [1, 1, 1, 1]
    V_pi = 0.6

    encoder = worker.TF_AWGEncoder_Alice
    # encoder.configure('sampleRate', 2e9)  # 采样率
    # encoder.configure('waveformLength', None)
    # encoder.configure('waveformUnitLength', 20)
    # encoder.configure('randomNumbers', decorateAWG(rnsAlice))
    # encoder.configure('ampAM1', [0.5, 0.593, 0.695, 0.695, 1] if ON[0] else [0.5] * 5)
    # encoder.configure('ampAM2', [0.5, 0.593, 0.695, 0.695, 1] if ON[1] else [0.5] * 5)
    # encoder.configure('ampPM1', [(i / 16 * V_pi * ON[2]) for i in range(16)])
    # encoder.configure('ampPM2', [(i / 16 * V_pi * ON[2]) for i in range(16)])
    # encoder.configure('biasAM1', [0.5] * 5)
    # encoder.configure('biasAM2', [0.5] * 5)
    # encoder.configure('widthAM1', [1.2, 8])
    # encoder.configure('widthAM2', [1.2, 8])
    # encoder.configure('widthPM1', 10)
    # encoder.configure('widthPM2', 10)
    # encoder.configure('delayAM1', 0)
    # encoder.configure('delayAM2', 0)
    # encoder.configure('delayPM1', 0)
    # encoder.configure('delayPM2', 0)
    encoder.configure('reversePatternAM1', [1, 1, -1, -1])

    waveforms = encoder.generateNewWaveform(returnWaveform=False)

    ###### 配置 TDC ######
    
    # MultiHistogram 的设置直接影响 TDCViewer 页面行为，一般在网页上改
    # tdc.configureAnalyser('MultiHistogram', {'Sync': 0, 'Signals': [2, 3], 'ViewStart': 0, 'ViewStop': 40000000, 'BinCount': 1000, 'Divide': 1}) 
    
    # TFQKDEncoding 的设置影响 TDCEncoding 页面
    # tdc.configureAnalyser('TFQKDEncoding', {
    #     'Period': 10000,
    #     'TriggerChannel': 1,
    #     'SignalChannel': 2,
    #     'RandomNumbers': rnsAlice_raw,
    #     'PulsePerTrigger': 100000000,
    #     'Histograms': {
    #         'All Pulses': [i for i in range(128)],
    #         'All Signals': [i for i in range(64)],
    #         'All Ref': [64, 128],
    #         'Vacuum': [i for i in range(64) if i % 4 == 0],
    #         'X': [i for i in range(64) if i % 4 == 1],
    #         'Y': [i for i in range(64) if i % 4 == 2],
    #         'Z': [i for i in range(64) if i % 4 == 3],
    #     }
    # })

    # analysers['TFQKDSyncAlice'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': [0], 'Histograms': {'Sync Alice': [i for i in range(64)]}})
    # analysers['TFQKDSyncBob'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': [0], 'Histograms': {'Sync Bob': [i for i in range(64)]}})
    # analysers['TFQKDSyncAliceMonitor'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 4, 'RandomNumbers': [0], 'Histograms': {'Sync Alice Monitor': [i for i in range(64)]}})
    # analysers['TFQKDSyncBobMonitor'].turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': 5, 'RandomNumbers': [0], 'Histograms': {'Sync Bob Monitor': [i for i in range(64)]}})
    # analysers['QKDQBER'].turnOn({'AliceRandomNumbers': [0], 'BobRandomNumbers': [0], 'Period': 10000, 'PulsePosition': 5000, 'Gate': 1000, 'TriggerChannel': 0, 'Channel 1': 2, 'Channel 2': 3})