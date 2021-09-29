import sys
from scipy.optimize import curve_fit
# from scipy import asarray as ar, exp
import numpy as np
import matplotlib.pyplot as plt

def riseTimeFitOld(xs, ys):
    # in case there is a large background
    bgs = ys[int(len(ys) * 0.8):-1]
    bg = sum(bgs) / len(bgs)
    ys = [y - bg for y in ys]

    SPD = [ys[0]]
    for y in ys[1:]:
        SPD.append(SPD[-1] + y)
    roughRise = 0
    for i in range(0, len(xs)):
        if SPD[i] > 0.04 * SPD[-1]:
            roughRise = xs[i]
            break

    fitXs = []
    fitYs = []
    for i in range(0, len(xs)):
        if xs[i] >= roughRise and xs[i] <= roughRise + 1.7:
            fitXs.append(xs[i])
            fitYs.append(SPD[i])

    def linear(x, a, b):
        return a * x + b

    expectA = (fitYs[0] - fitYs[-1]) / (fitXs[0] - fitXs[-1])
    expectB = fitYs[0] - expectA * fitXs[0]
    popt, pcov = curve_fit(linear, fitXs, fitYs, p0=[expectA, expectB])

    rise = -popt[1] / popt[0]
    return rise


def riseTimeFit(tList,sList):                      #设定最大值的(0.1-0.8)范围内且计数率增长的是有效数据，根据有效数据线性拟合
    x, y = [], []
    upper, lower = max(sList) * 0.8, max(sList) * 0.1
    for i in range(len(sList) - 1):
        if lower <= sList[i] <= upper:
            if sList[i] < sList[i + 1]:
                x.append(tList[i])
                y.append(sList[i])
    while True:  # 剔除不连续时间的数据
        deltas = []
        for i in range(len(x) - 1): deltas.append(x[i + 1] - x[i])
        if len(set(deltas)) > 1:
            x = np.delete(x, -1)
            y = np.delete(y, -1)
        else:
            break
    a = np.polyfit(x, y, 1)  # 计数率连续上升时间段的数据拟合
    return -a[1] / a[0]