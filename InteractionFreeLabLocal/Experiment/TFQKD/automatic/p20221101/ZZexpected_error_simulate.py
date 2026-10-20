import numpy as np
from calculator import dB_to, to_dB

pi = np.pi


def dark_count(pulseTime, darkCount_1s):
    return pulseTime * darkCount_1s


def expectedZZerror(P_expectedZ1, keyperRN):
    a = (1 - P_expectedZ1) ** 2 * keyperRN[0]
    b = (1 - P_expectedZ1) * P_expectedZ1 * keyperRN[1]
    c = (1 - P_expectedZ1) * P_expectedZ1 * keyperRN[2]
    d = P_expectedZ1 ** 2 * keyperRN[3]
    return (a + d) / (a + b + c + d)


if __name__ == '__main__':
    # 产生ZZ光子对
    # ref比signal消光比 dB单位
    ref_signal = 8  # 7.8
    # 单边光子数
    Ncount = 200E3
    Zcount_1s = 470
    # signal中Z态比例
    PZ = 0.95268
    # Z发送概率x
    PZ1 = 1-0.720766
    # 暗计数
    darkCount_1s = 0
    # signal比真空消光比
    sig_vacuum = 30
    # 计算
    # 计算方法1
    miuA = 1 * 10 * 260 / (dB_to(ref_signal) * 100 * 140 + 1 * 10 * 260) * Ncount * (250 / 260) / (1E8 * 250 / 400 * PZ * PZ1)
    # miuA = 1 * 10 * 250 / (dB_to(ref_signal) * 100 * 140 + 1 * 10 * 260) * 185E3 / (1E8 * 250 / 400 * PZ * PZ1)
    print(miuA)
    # 计算方法2
    # miuA = Zcount_1s * 10 / (1E8 * 250 / 400 * PZ * PZ1)
    # miuA = 1000 * 10 / (1E8 * 250 / 400 * PZ * PZ1)
    print(miuA)
    # 计算方法3
    # miuA = 0.5 / dB_to(40)
    print(miuA)
    # 计算另一通道平均光子数
    miuB = miuA
    # miuB = miuA / 12 * 7
    miu0 = miuA / dB_to(sig_vacuum) / 2

    # Z0Z0光子数
    miuZ0Z0 = miu0 + miu0 - miu0 * miu0 / 2
    # Z1Z0光子数
    miuZ1Z0 = miuA + miu0 - miuA * miu0 / 2 + dark_count(1E-9, darkCount_1s) * 2
    # Z0Z1光子数
    miuZ0Z1 = miuB + miu0 - miuB * miu0 / 2 + dark_count(1E-9, darkCount_1s) * 2
    # Z1Z1光子数
    miuZ1Z1 = miuA + miuB - miuA * miuB / 2 + dark_count(1E-9, darkCount_1s) * 2

    li = [miuZ0Z0, miuZ1Z0, miuZ0Z1, miuZ1Z1]
    print(f'Z0Z0 Z1Z0 Z0Z1 Z1Z1 per RN = {[l*5 for l in li]}, expected error = {expectedZZerror(0.03, li)}')

    print(to_dB(0.003375/2/1.69E-6), 'dB')