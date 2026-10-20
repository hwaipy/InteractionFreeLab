import numpy as np
import time
from worker_config import worker_timeoutset as worker

# 优化：尽量减少与时钟以及服务器的通信（尤其是申请数据）


class MoMethod:
    lastObject = None

    def __init__(self, target):
        self.target = target
        MoMethod.lastObject = self

    # 获取MO当前值
    @classmethod
    def getMO(self, target=None):
        if not target: target = MoMethod.lastObject.target
        get = eval(f'worker.TF_AtomicClock_{target}.getMO')
        MO = get()
        return int(MO)

    # 设定MO值
    @classmethod
    def setMO(self, MO, target=None):
        if not target: target = MoMethod.lastObject.target
        set = eval(f'worker.TF_AtomicClock_{target}.setMO')
        MO = round(float(MO))
        set(MO)

    # 设定漂移-MO斜率
    @classmethod
    def setSlope(self, slope, target=None):
        if not target: target = MoMethod.lastObject.target
        worker.TF_Registry.set(f'{target}_MOslope', slope)

    # 获取最新的漂移-MO斜率
    @classmethod
    def getSlope(self, target=None):
        if not target: target = MoMethod.lastObject.target
        return worker.TF_Registry.get(f'{target}_MOslope')

    # 获取服务器最新MO_sync值
    @classmethod
    def latest_MOsync(self, target=None):
        if not target: target = MoMethod.lastObject.target
        return worker.TF_Registry.get(f'{target}_MOsync')

    # 设置MO_sync值存储至服务器
    @classmethod
    def set_MOsync(self, MO, target=None):
        if not target: target = MoMethod.lastObject.target
        worker.TF_Registry.set(f'{target}_MOsync', MO)


class SyncData:
    lastObject = None

    def __init__(self, target):
        self.config()
        self.dataTime = 0.1  # 单位s
        self.target = target
        SyncData.lastObject = self

    @classmethod
    def config(cls):
        # 同样由于新的实时处理程序和老的TDC处理程序目前是独立运行的状态，需要把通道延时信息复制过来。
        delays = worker.TFTDCServer.getDelays()
        for i in range(len(delays)):
            worker.TFTDCAdapter.setDelay(i, delays[i])

    @classmethod
    def getData(cls, n, target=None, period=10000, binCount=100):
        # 配置target
        if not target: target = SyncData.lastObject.target
        # 获取数据，生成直方图
        data = worker.RealTimeTDC.getRecent(count=n, reversed=True)  # (count: Int, reversed: Boolean = False数据由老到新 True数据由新到老)
        fetchTime = np.average([d['FetchTime'] / 1000.0 for d in data])
        if len(data) == 0:
            print('未取到同步数据！')
            return fetchTime, np.nan
        each_histogram = [d[f'TFQKDSync{target}'][f'Histogram[Sync {target}]'] for d in data]
        histogram = np.sum(np.array(each_histogram), axis=0)
        # print('histogram=', histogram)
        print(f'共取{n / 10} s数据用于本轮时钟同步\n', '直方图光子数：', np.sum(histogram))
        histogram0 = [abs(np.mean(histogram) - h) for h in histogram]
        print(f'脉冲突出程度：{np.max(histogram0) / np.average(histogram0)}')
        # print('histogram================================', histogram)
        if np.min(histogram0) != 0:
            if np.min(histogram) == 0 and np.max(histogram) < 10:
                print('您的脉冲不够突出啊')
                return fetchTime, np.nan
            elif np.min(histogram) != 0:
                if np.max(histogram) / np.min(histogram) < 10:
                    print('您的脉冲不够突出啊')
                    return fetchTime, np.nan
            elif np.max(histogram0) / np.average(histogram0) < 3 or np.max(histogram) < 10:
                print('您的脉冲不够突出啊')
                return fetchTime, np.nan
            elif (np.sum(histogram) / len(histogram)) < 5:
                print('您的脉冲光子数太少啦')
                return fetchTime, np.nan
        elif np.max(histogram) < 10 or np.sum(histogram0) / len(data) < 2 and np.min(histogram0) == 0:
                return fetchTime, np.nan

        # 获取直方图参数
        config = data[0][f'TFQKDSync{target}']['Configuration']
        period = config['Period']
        binCount = config['BinCount']

        est_center = SyncData.e_center(histogram=histogram, period=period, binCount=binCount)

        return fetchTime, est_center

    @classmethod
    def e_center(cls, histogram, period=10000, binCount=100):
        # 考虑凸脉冲和凹脉冲
        mean = np.mean(histogram)
        histogram = [abs(mean - h) for h in histogram]

        # xs为每个bin的中心位置横坐标组成的list
        xs = np.linspace(0, period, binCount + 1)[:-1]
        xs += (xs[1] - xs[0]) / 2

        # 找脉冲中心
        maxValue = np.max(histogram)
        maxIndex = np.where(histogram == maxValue)[0][0]
        inPulseIndices = np.where(histogram > maxValue * 0.2)[0]
        maxIndexInPulse = np.where(inPulseIndices == maxIndex)[0][0]
        inPulseIndices = inPulseIndices[np.where(inPulseIndices == [i + maxIndex - maxIndexInPulse for i in range(len(inPulseIndices))])]
        est_center = sum([xs[i] * histogram[i] for i in inPulseIndices]) / sum([histogram[i] for i in inPulseIndices])
        return est_center/1000

    def getsomedata(self, st='2022-08-01 15:48:00.009', et='2022-08-01 16:20:30.009'):
        data = worker.RealTimeTDC.getRanged(st, et, reversed=True)
        # data = worker.RealTimeTDC.getRanged('2022-08-01 15:48:00.009', '2022-08-01 15:48:01.009', reversed=True)
        # 获取直方图参数
        config = data[0][f'TFQKDSync{target}']['Configuration']
        period = config['Period']
        binCount = config['BinCount']

        each_histogram = [d[f'TFQKDSync{self.target}'][f'Histogram[Sync {self.target}]'] for d in data]
        cl = [self.e_center(histogram=histogram, period=period, binCount=binCount) for histogram in each_histogram]
        ft = [d['FetchTime'] / 1000.0 for d in data]

        data_dic = dict()
        data_dic['histogram'] = each_histogram
        data_dic['fetchTime'] = ft
        data_dic['centerList'] = cl
        data_dic['data'] = data
        deltalist = [5 - i for i in cl]
        data_dic['deltalist'] = deltalist
        return data_dic

    def getRecentData(self, count):
        data = worker.RealTimeTDC.getRecent(count=count, reversed=True)
        # data = worker.RealTimeTDC.getRanged('2022-08-01 15:48:00.009', '2022-08-01 15:48:01.009', reversed=True)
        # 获取直方图参数
        config = data[0][f'TFQKDSync{target}']['Configuration']
        period = config['Period']
        binCount = config['BinCount']

        each_histogram = [d[f'TFQKDSync{self.target}'][f'Histogram[Sync {self.target}]'] for d in data]
        cl = [self.e_center(histogram=histogram, period=period, binCount=binCount) for histogram in each_histogram]
        ft = [d['FetchTime'] / 1000.0 for d in data]

        data_dic = dict()
        data_dic['histogram'] = each_histogram
        data_dic['fetchTime'] = ft
        data_dic['centerList'] = cl
        data_dic['data'] = data
        deltalist = [5 - i for i in cl]
        data_dic['deltalist'] = deltalist
        return data_dic


if __name__ == '__main__':
    import sys
    target = 'Alice'
    # cm = AutoSync(target, stableRange=0.03, centerRange=0.03)  # sys.argv[1]

    # a.test()
    # a.loop()

    # MoMethod.set_MOsync(MO=3040, target=target)

    st = time.time()
    # print(MoMethod.latest_MOsync(target=target))
    # # print(MoMethod.getSlope(target))
    # MoMethod.setSlope(-0.0035, target)
    # # print(MoMethod.getSlope(target))
    et = time.time()
    print('time=', et-st)
    print(SyncData.getData(1, target))



