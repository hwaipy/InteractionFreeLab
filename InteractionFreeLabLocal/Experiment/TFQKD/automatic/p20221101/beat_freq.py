import matplotlib.pyplot as plt
import numpy as np
import time
import math
from urllib.request import urlopen
from pytimetag import DataBlock
import multiprocessing
from PIL import Image
from worker_config import worker, ip
import TDCDataParser
import datetime
pi = np.pi
storage = worker.Storage


def openPicture(*args):
    path = args[0]
    im = Image.open(path)
    im.show()


def DFT(data):
    N = len(data)
    # 离散傅里叶变换
    ft = np.fft.fft(data)  # 离散傅里叶变换
    ft_power = [abs(f) for f in ft]
    # 频谱横坐标
    f_list = [i for i in range(len(ft_power))]
    # 最大频率分量
    f_powermax_index = ft_power.index(np.max(ft_power[1:round(N / 2 + 1)]))
    phase_estimate_i = math.atan(ft[f_powermax_index].imag / ft[f_powermax_index].real) % (2 * pi)
    # 绘制傅里叶变换的结果
    ft_show = list(ft_power[:round(N / 2 + 1)])
    f_list = f_list[:len(ft_show)]
    return f_list, ft_show, f_list[f_powermax_index], ft_power[f_powermax_index]


def getDataBlock(fetchTime):
    while len(fetchTime) == 25: fetchTime = time.strftime('%Y-%m-%dT%H:%M:%S.000000+08:00', time.strptime(fetchTime, '%Y-%m-%dT%H:%M:%S+08:00'))

    res = urlopen(f'http://{ip}:1001/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock')
    data = res.read()
    res.close()
    dataBlock = DataBlock.deserialize(data)
    dataBlock = {
        'CreationTime': dataBlock.creationTime,
        'DataTimeBegin': dataBlock.dataTimeBegin,
        'DataTimeEnd': dataBlock.dataTimeEnd,
        'Sizes': dataBlock.sizes,
        'Resolution': dataBlock.resolution,
        'Content': dataBlock.content,
    }
    return dataBlock


def freq_calculate(beginTime, endTime):
    storage = worker.Storage

    # 获取所有在范围内的数据的采集时间
    # ranges = storage.range('TFQKD_TDC', beginTime.replace(' ', 'T') + '+08:00', endTime.replace(' ', 'T') + '+08:00', filter={'_id': 1})
    ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=100000)
    print(f'{len(ranges)} seconds of data fetched...')

    n = 0
    for dataMeta in ranges[:]:
        n += 1
        if n % 20 != 0: continue
        fetchTime = dataMeta['FetchTime']
        dataBlock = getDataBlock(fetchTime)
        meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
        configs = meta['Data']['QKDQBER']['Configuration']
        parser = TDCDataParser.DataBlockParser(dataBlock, configs['AliceRandomNumbers'], configs['BobRandomNumbers'], triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'], phaseThreshold=pi/8/2, phase_invariant_time=0.5 * 10 ** 9)

        result = parser.freq_diff()
        print('\n当前时间：', datetime.datetime.now())
        print('该秒数据时间：', fetchTime)

        f_list, ft_show, f_max, maxpower = DFT(result)

        # plt.plot(f_list[1:], ft_show[1:])
        Gauss_fitting(x=f_list[1:], y=ft_show[1:], plotYN=True)


def Gauss_fitting(x, y, plotYN=False):
    from astropy import modeling
    # 寻峰
    # peak_x_index = find_peaks(y)
    # peak_x = x[peak_x_index]
    # peak_y = y[peak_x_index]
    # 最大值
    f_max_index = y.index(np.max(y))
    f_max_x = x[f_max_index]
    f_max_y = y[f_max_index]
    # Gauss拟合
    fitter = modeling.fitting.LevMarLSQFitter()
    model = modeling.models.Gaussian1D(amplitude=1000, mean=f_max_x, stddev=80, bounds={'amplitude': (700, 3000), 'stddev': (60, 80), 'mean': (0, 1000)})
    fitted_model = fitter(model, x, y)
    # 多项式拟合
    # z1 = np.polyfit(x, y, 3)  # 曲线拟合，返回值为多项式的各项系数
    # p1 = np.poly1d(z1)  # 返回值为多项式的表达式，也就是函数式子
    # print(p1)
    # y_pred = p1(x)

    if plotYN:
        plt.plot(x, y)
        plt.plot(x, fitted_model(x), label=f'amp={fitted_model.parameters[0]}\nmiu={fitted_model.parameters[1]}\nstd={fitted_model.parameters[2]}')
        plt.plot([f_max_x], [f_max_y], "xr")
        # plt.plot(x, y_pred, 'r')
        plt.legend()
        plt.show()
        plt.close()

    return fitted_model.parameters[1]


def find_peaks(y, plotYN=False):
    from scipy.signal import find_peaks
    peaks, properties = find_peaks(y, height=(700, 5000), distance=200)

    if plotYN:
        plt.plot(peaks, [y[p] for p in peaks], "x")
        plt.plot(y)
        plt.show()
        plt.close()
        print('peaks:', peaks, [y[p] for p in peaks])
    return peaks[0]


if __name__ == '__main__':
    # 独立光源 0927 17:55-20:00
    # localtime_start_data = '2022-09-27T17:54:00+08:00'
    localtime_start_data = '2022-09-27T18:24:00+08:00'
    localtime_end_data = '2022-09-27T18:26:50+08:00'
    freq_calculate(localtime_start_data, localtime_end_data)
