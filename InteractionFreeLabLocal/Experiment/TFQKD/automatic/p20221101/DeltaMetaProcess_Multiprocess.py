from interactionfreepy import IFWorker
import matplotlib.pyplot as plt
import numpy as np
import time
import math
from functools import reduce
from urllib.request import urlopen
from pytimetag import DataBlock
import multiprocessing

pi = np.pi

# ip = '10.1.1.1'
ip = '172.16.60.200'  # 实验室外
# ip = '192.168.25.5'
# ip = 'interactionfree.cn'  # 研究院外

worker = IFWorker(f'tcp://{ip}:224')
storage = worker.Storage

part_time = 0.5 * 1E9
part_num = round(1E12 / part_time)
period = 10000


def config():
    tdc = worker.TFTDCServer
    tdc.turnOnAnalyser('DeltaMetaAnalyser', {'Channel1': 2, 'GroupBy': 250, 'Channel2': 3, 'SyncChannel': 0, 'Period': 10000, 'Center': 5000, 'GateWidth': 1200})


def dosomething(triggerList, dataList):
    def deltaMeta(triggerList, dataList):
        # [1秒内到达时间，属于第几个part_time，属于第几个脉冲周期，脉冲内到达时间， 奇/偶数脉冲]
        List = [time0 - triggerList[0] for time0 in dataList if time0 >= triggerList[0]]
        deltaMetas = [[time0, int(time0 // part_time), time0 // period, time0 % period, time0 // period % 2] for time0 in List]
        return deltaMetas

    def counter(deltaMetaList):
        oddList = [0 for i in range(part_num)]
        evenList = [0 for i in range(part_num)]

        center = 5000
        gate = 10000
        for dm in deltaMetaList:
            if dm[3] >= (center - gate / 2) and dm[3] <= (center + gate / 2) and dm[4] == 0: evenList[dm[1]] += 1
            if dm[3] >= (center - gate / 2) and dm[3] <= (center + gate / 2) and dm[4] == 1: oddList[dm[1]] += 1
        odd_tuple = tuple(oddList)
        even_tuple = tuple(evenList)
        return odd_tuple, even_tuple

    odd_tuple, even_tuple = counter(deltaMeta(triggerList, dataList))
    return odd_tuple, even_tuple


def get_s_func(time_start, time_end):
    r = storage.range('TFQKD_TDC', time_start, time_end, filter={'_id': 1})
    print(f'{len(r)} seconds of data fetched.')

    DataMap = {'odd1': [], 'even1': [], 'odd2': [], 'even2': []}

    beginTime = time.time()
    resultlist = []
    with multiprocessing.Pool(processes=40) as pool:
        for dataMeta in r:
            meta = worker.Storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
            resultlist.append(pool.apply_async(parseDataBlock, (meta,)))
        pool.close()
        pool.join()

        for result in resultlist:
            result = result.get()
            DataMap['odd1'].extend(result[0])
            DataMap['even1'].extend(result[1])
            DataMap['odd2'].extend(result[2])
            DataMap['even2'].extend(result[3])

        endTime = time.time()

        print(f'{len(r)} results parsed in {endTime - beginTime} s. ({(endTime - beginTime) / len(r)} s/DataBlock).')

    if min(DataMap['odd1']) != 0:
        print('干涉对比度：', max(DataMap['odd1']) / min(DataMap['odd1']))
    else:
        print('最小光子计数为0，无法计算干涉对比度')
    return DataMap['odd1'], DataMap['even1'], DataMap['odd2'], DataMap['even2']


def parseDataBlock(meta):
    try:
        fetchTime = meta['FetchTime']
        print(fetchTime)
        while len(fetchTime) == 25: fetchTime = time.strftime('%Y-%m-%dT%H:%M:%S.000000+08:00', time.strptime(fetchTime, '%Y-%m-%dT%H:%M:%S+08:00'))
        dataBlock = getDataBlock(fetchTime)
        data = dataBlock['Content']

        result = [dosomething(data[0], data[2])[0], dosomething(data[0], data[2])[1], dosomething(data[0], data[3])[0], dosomething(data[0], data[3])[1]]

        return result
    except BaseException as e:
        import traceback
        print(e)
        # traceback.print_stack(e)


def plot(localtime_start_data, localtime_end_data):
    for i in range(len(localtime_start_data)):
        s1A, s1B, s2A, s2B = get_s_func(localtime_start_data[i], localtime_end_data[i])
        print('开始画图')

        plt.plot([i for i in range(len(s1A))], s1A, label='Detector1 odd')  # 蓝
        plt.plot([i for i in range(len(s1B))], s1B, label='Detector1 even')  # 黄
        plt.plot([i for i in range(len(s2A))], s2A, label='Detector2 odd')  # 绿
        plt.plot([i for i in range(len(s2B))], s2B, label='Detector2 even')  # 红

        plt.legend()
        plt.savefig('sixian.png')
        plt.close()
        # plt.show()


def FFTplot(localtime_start_data, localtime_end_data):
    for i in range(len(localtime_start_data)):
        s1A, s1B, s2A, s2B = get_s_func(localtime_start_data[i], localtime_end_data[i])
        print('开始画图')
        s1 = [s1A[i] + s1B[i] for i in range(len(s1A))]
        s2 = [s2A[i] + s2B[i] for i in range(len(s1A))]
        plt.plot([i for i in range(len(s1))], s1, label='Detector1')  # 蓝
        plt.plot([i for i in range(len(s2))], s2, label='Detector2')  # 绿

        plt.legend()
        plt.savefig('detector.png')
        plt.close()

        f_list, ft_show, f_max = DFT(data=s1)
        plt.plot(f_list[1:200], ft_show[1:200], label='DFT')
        plt.xlabel('f(Hz)')
        plt.legend()
        plt.title(f'f_max={f_max}')
        plt.savefig('DFT_detector 100Hz.png')
        plt.close()

        # plt.show()


def DFT(data):
    N = len(data)
    # 离散傅里叶变换
    ft = np.fft.fft(data)  # 离散傅里叶变换
    ft_power = [abs(f) for f in ft]
    # 频谱横坐标
    f_list = [i for i in range(len(ft_power))]
    # 最大频率分量
    f_powermax_index = ft_power.index(np.max(ft_power[1:round(N / 2 + 1)]))
    f_powermax = f_list[f_powermax_index]
    phase_estimate_i = math.atan(ft[f_powermax_index].imag / ft[f_powermax_index].real) % (2 * pi)
    # 绘制傅里叶变换的结果
    ft_show = list(ft_power[:round(N / 2)])
    f_list = f_list[:len(ft_show)]
    return f_list, ft_show, f_list[f_powermax_index]


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


def dosomethingmore(data, divideTime, binNum=1000, from_time=0, to_time=40000 * 1E3):
    binTime = round(divideTime / binNum)

    # 对齐Trigger,保留从from_time到to_time时间到达的光子事件
    def deltaMeta(triggerList, dataList):
        currentTriggerIndex = 0
        deltaMetas = []
        for time in dataList:
            for i in range(currentTriggerIndex, len(triggerList)):
                if triggerList[i] < time:
                    currentTriggerIndex = i
                else:
                    break
            delta = time - triggerList[currentTriggerIndex]
            deltaList = [currentTriggerIndex, delta, delta // divideTime, delta % divideTime // binTime]
            if from_time <= deltaList[1] <= to_time: deltaMetas.append(deltaList)
        return deltaMetas

    def counter(triggerList, dataList):
        # 对齐Trigger,deltaMetas每个元素为[0]对应的trigger序号，[1]相对trigger的到达时间，[2]事件在trigger内的divide序号，[3]光子在此divide片段的bin序号]
        deltaMetas = deltaMeta(triggerList, dataList)
        # 计算每个bin内的光子数
        binCount = [0 for i in range(binNum)]
        for each in deltaMetas:
            binCount[each[3]] += 1
        return binCount

    triggerList = data[0]  # 25000
    data1List = data[2]
    data2List = data[3]

    binCount1 = counter(triggerList, data1List)
    binCount2 = counter(triggerList, data2List)

    Time = [i * binTime for i in range(binNum)]
    plt.plot(Time, binCount1)
    plt.plot(Time, binCount2)
    plt.grid()
    plt.show()


# 脉冲画图
def interaction_plot(localtime_start_data, localtime_end_data, Divide=250, from_time=0, to_time=40000, binNum=1000):
    to_time = to_time * 1E3
    period = 40000 * 1E3
    divideTime = round(period / Divide)

    for i in range(len(localtime_start_data)):
        r = storage.range('TFQKD_TDC', localtime_start_data[i], localtime_end_data[i], filter={'_id': 1})
        print(f'{len(r)} seconds of data fetched.')

        for dataMeta in r:
            fetchTime = dataMeta['FetchTime']
            while len(fetchTime) == 25: fetchTime = time.strftime('%Y-%m-%dT%H:%M:%S.000000+08:00', time.strptime(fetchTime, '%Y-%m-%dT%H:%M:%S+08:00'))
            dataBlock = getDataBlock(fetchTime)
            # dataBlock = worker.TDCRawDataServer.fetchRawDataBlock('http://192.168.25.5:1001', fetchTime.replace('T', ' ').replace(':', '-')[:-9])
            data = dataBlock['Content']
            dosomethingmore(data, divideTime, binNum, from_time, to_time)


if __name__ == '__main__':
    # localtime_start_data = ['2022-03-21T01:10:31+08:00']
    # localtime_end_data = ['2022-03-21T01:10:40+08:00']

    # 以下为干涉对比度好的时候的数据
    # localtime_start_data = ['2022-02-15T16:28:00+08:00']
    # localtime_end_data = ['2022-02-15T16:28:05+08:00']

    localtime_start_data = ['2022-09-27T17:58:40+08:00']
    localtime_end_data = ['2022-09-27T17:58:41+08:00']
    # config()
    # 画图
    # plot(localtime_start_data, localtime_end_data)
    # interaction_plot(localtime_start_data, localtime_end_data, Divide=250, from_time=0, to_time=40000, binNum=1000)
    FFTplot(localtime_start_data, localtime_end_data)
