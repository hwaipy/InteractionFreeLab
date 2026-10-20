import numpy as np
from worker_config import worker
import math


def to_dB(ratio):
    return 10 * math.log10(ratio)


def datasum(ndata):
    if isinstance(ndata, list):
        allSignals = None
        for data in ndata:
            configuration = data['Data']['TFQKDEncoding']['Configuration']
            if allSignals is None:
                allSignals = data['Data']['TFQKDEncoding']['Histogram[All Signals]']
            else:
                signals = data['Data']['TFQKDEncoding']['Histogram[All Signals]']
                allSignals = [signals[i] + allSignals[i] for i in range(len(allSignals))]
    else:
        allSignals = ndata['Data']['TFQKDEncoding']['Histogram[All Signals]']
        configuration = ndata['Data']['TFQKDEncoding']['Configuration']

    return configuration, allSignals


def getLatestPulseRatio(nset=1):
    ndata = worker.Storage.latest('TFQKD_TDC', 'FetchTime', None, {'Data.TFQKDEncoding': 1}, length=nset)
    # 数据相加
    configuration, allSignals = datasum(ndata)
    # 计算消光比
    markPoints = [[4.5, 5.5], [7, 9.0]]
    xs = np.linspace(0, configuration['Period'] / 1000.0, configuration['BinCount'] + 1)[:-1]
    xs = [x + (xs[1] - xs[0]) / 2 for x in xs]

    countInPulse = sum(
        [allSignals[i] for i in range(len(xs)) if xs[i] >= markPoints[0][0] and xs[i] <= markPoints[0][1]])
    countInVacuum = sum(
        [allSignals[i] for i in range(len(xs)) if xs[i] >= markPoints[1][0] and xs[i] <= markPoints[1][1]])
    SignalVacuumRatio = countInPulse / (markPoints[0][1] - markPoints[0][0]) / countInVacuum * (markPoints[1][1] - markPoints[1][0])
    return {
        'SignalVacuumRatio': SignalVacuumRatio,
        'SignalVacuumRatio(dB)': to_dB(SignalVacuumRatio),
        'SignalCount': countInPulse,
        'SignalRange': f'{markPoints[0][1] - markPoints[0][0]} ns',
        'VacuumCount': countInVacuum,
        'VacuumRange': f'{markPoints[1][1] - markPoints[1][0]} ns',
    }


if __name__ == '__main__':
    getLatestPulseRatio(2)
