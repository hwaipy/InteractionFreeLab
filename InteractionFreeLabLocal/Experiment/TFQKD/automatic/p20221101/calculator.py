import numpy as np
import math
pi = np.pi


def to_dB(N):
    return 10 * math.log10(N)


def dB_to(d):
    return 10 ** (d / 10)


if __name__ == '__main__':
    print(to_dB(9.5))
    print(dB_to(33))
    print((581710607+575602325) / 60 / 50 / 2)