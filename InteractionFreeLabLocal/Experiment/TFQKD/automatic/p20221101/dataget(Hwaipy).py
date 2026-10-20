from interactionfreepy import IFWorker
import numpy as np


# ip = '10.1.1.1'
ip = '172.16.60.200'  # 实验室外
# ip = '192.168.25.5'
# ip = 'interactionfree.cn'  # 研究院外
worker = IFWorker(f'tcp://{ip}:224')


def getLatestPulseRatio():
    data = worker.Storage.latest('TFQKD_TDC', 'FetchTime', None, {'Data.TFQKDEncoding': 1})
    data = data['Data']
    encoding = data['TFQKDEncoding']
    configuration = encoding['Configuration']
    allSignals = encoding['Histogram[All Signals]']

    markPoints = [[4.5, 5.5], [7, 9.0]]
    xs = np.linspace(0, configuration['Period'] / 1000.0, configuration['BinCount'] + 1)[:-1]
    xs = [x + (xs[1] - xs[0]) / 2 for x in xs]

    countInPulse = sum(
        [allSignals[i] for i in range(len(xs)) if xs[i] >= markPoints[0][0] and xs[i] <= markPoints[0][1]])
    countInVacuum = sum(
        [allSignals[i] for i in range(len(xs)) if xs[i] >= markPoints[1][0] and xs[i] <= markPoints[1][1]])
    return {
        'SignalVacuumRatio': countInPulse / (markPoints[0][1] - markPoints[0][0]) / countInVacuum * (markPoints[1][1] - markPoints[1][0]),
        'SignalCount': countInPulse,
        'SignalRange': f'{markPoints[0][1] - markPoints[0][0]} ns',
        'VacuumCount': countInVacuum,
        'VacuumRange': f'{markPoints[1][1] - markPoints[1][0]} ns',
    }


def playWithDCSource():
    dc = worker.TF_PowerSupply_Alice_2
    print(dc.getVoltageSetPoint(0), dc.getVoltageSetPoint(1), dc.getVoltageSetPoint(2))   # 当前的3路电压设置值
    dc.setVoltage(0, 4.251)
    print(dc.getVoltageSetPoint(0), dc.getVoltageSetPoint(1), dc.getVoltageSetPoint(2))   # 当前的3路电压设置值
    dc.setVoltage(0, 4.250)
    print(dc.getVoltageSetPoint(0), dc.getVoltageSetPoint(1), dc.getVoltageSetPoint(2))   # 当前的3路电压设置值

if __name__ == '__main__':
    print(getLatestPulseRatio())
    playWithDCSource()
