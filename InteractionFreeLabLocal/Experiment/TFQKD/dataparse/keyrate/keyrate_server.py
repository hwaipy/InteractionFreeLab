from ctypes import *
import sys
import platform
import math
import numpy as np

lib7 = cdll.LoadLibrary(f"{sys.path[0]}/keyrate_1e-7.{'so' if platform.system() == 'Linux' else 'dll'}")
lib7.keyrate.restype = c_double
lib10 = cdll.LoadLibrary(f"{sys.path[0]}/keyrate_1e-10.{'so' if platform.system() == 'Linux' else 'dll'}")
lib10.keyrate.restype = c_double


def to_dB(N):
    """
    :param N: 倍数
    :return: N倍相当于多少dB
    """
    return 10 * math.log10(N)


def parameter(statistic, num_photons):
    # 基矢
    basis = ['signalZ0', 'signalZ1', 'signal0', 'signalX', 'signalY']
    # 每个基矢的单边发射比例
    P_rns = [statistic['signal'][key]['ratio'] for key in ['signal0', 'signalX', 'signalY', 'signalZ1', 'signalZ0']]
    # 理论上每脉冲平均光子数
    mean_photon_num_per_pulse = sum(np.multiply(P_rns[1:4], num_photons))
    # 实验探测到的总signal光子数
    detect_num = statistic['signal']['signal']['detector_count']
    # 发送总脉冲数(单边or双边？)
    pulses = statistic['signal']['signal']['count']
    # 单边透过率
    transmittance = detect_num / pulses / (mean_photon_num_per_pulse * 2)

    return basis, P_rns, pulses, transmittance


def calKeyRate(statistic, num_photons=[0.1, 0.264779, 0.499962], phaseSeletcedRatio=1 / 8, strict=False, scale=1):
    """
    :param statistic: 实验结果字典
    :param num_photons: X、Y、Z1基矢的平均每脉冲光子数
    :param phaseSeletcedRatio: 相位筛选比例（筛选门宽/pi）
    :return: {成码率、单边透过率、单边衰减}
    """

    # 获取参数
    basis, P_rns, pulses, transmittance = parameter(statistic, num_photons)

    # 计算keyrate
    # 0 - 4 X基真空光源、X基弱源、X基强光、Z基发射、Z基真空概率
    results = P_rns.copy()
    # 5 - 7   X基弱源强度、X基强光强度、Z基相关态光源强度, (每脉冲平均光子数)
    results += num_photons
    # 8    # 发送总脉冲数(单边or双边？)
    results += [pulses * scale]
    # 9 - 33 实际发送组合比例（随机数比例）
    for b1 in basis:
        for b2 in basis:
            results.append(statistic[b1][b2]['ratio'])
    # 34 - 58 实际引起有效响应个数（探测事件个数总数）
    for b1 in basis:
        for b2 in basis:
            results.append(statistic[b1][b2]['detector_count'] * scale)
    # 59 - 60
    results += [
        phaseSeletcedRatio,  # 筛选比例（筛选阈值/pi）
        statistic['Sifted Key']['XX']['incorrect'] * scale,  # X基错误计数
    ]
    # 计算成码率
    lib = lib10 if strict else lib7
    kr = lib.keyrate((c_double * len(results))(*results))

    # 输出结果
    # print(f'成码率：{kr}')
    # 单边透过率
    # print(f'单边透过率：{transmittance}')
    attenuation = to_dB(1 / transmittance)
    # print(f'单边衰减：{attenuation}  dB')

    return {'keyrate': kr, 'transmittance': transmittance, 'attenuation': attenuation, }

class Obj:
    def cal(self, statistic, num_photons=[0.1, 0.264779, 0.499962], phaseSeletcedRatio=1 / 8, strict=False, scale=1):
        return calKeyRate(statistic, num_photons, phaseSeletcedRatio, strict, scale)

class Lib7:
    def keyrate(self, results):
        return lib7.keyrate((c_double * len(results))(*results))

if __name__ == '__main__':
    from sampleResult import result
    import time
    # t1 = time.time()
    # for i in range(1000):
    #     calKeyRate(result, strict=False, scale=1) # 有限码长，置信度1e-7
    #     # print(calKeyRate(result, strict=True, scale=1)) # 有限码长，置信度1e-10
    #     # print(calKeyRate(result, scale=1e10)) # (接进)无限码长
    # t2 = time.time()
    # print(t2 - t1)

    from interactionfreepy import IFWorker, IFLoop

    worker = IFWorker('tcp://10.1.1.1:1061', 'KR', Obj(), force=True)
    worker = IFWorker('tcp://10.1.1.1:1061', 'KR_lib7', Lib7(), force=True)

    IFLoop.join()