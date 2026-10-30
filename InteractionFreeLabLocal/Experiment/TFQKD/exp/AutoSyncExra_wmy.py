import numpy as np
import sys, os
from interactionfreepy import IFWorker
worker = IFWorker(endpoint=f'tcp://tf.qpqi.group:1161')
worker_main = IFWorker(endpoint=f'tcp://tf.qpqi.group:1161')

setRefSyncYN = False
AliceRefAdjust = 0.0
BobRefAdjust = 0.0  # Bob旧板子 0.14059

import matplotlib.pyplot as plt
# from astropy.modeling import models, fitting

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
        get = eval(f'worker_main.TF_AtomicClock_{target}.getMO')
        MO = get()
        return int(MO)

    # 设定MO值
    @classmethod
    def setMO(self, MO, target=None):
        if not target: target = MoMethod.lastObject.target
        set = eval(f'worker_main.TF_AtomicClock_{target}.setMO')
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

    # 延迟原子钟秒信号
    @classmethod
    def delayClock(self, delay, target=None):
        if not target: target = MoMethod.lastObject.target
        set = eval(f'worker_main.TF_AtomicClock_{target}.delay1PPS')
        delay = round(float(delay))
        set(delay)


class SyncData:
    lastObject = None

    def __init__(self, target):
        self.dataTime = 0.1  # 单位s
        self.target = target
        SyncData.lastObject = self

    @classmethod
    def getData(cls, n, target=None, refSyncYN=setRefSyncYN, checkPlot=False, centerAdjust=None, jointType=None):
        """
        :param n: 一次取多少组数，每组100ms
        :param target: 对象，Alice or Bob
        :param refSyncYN: 是否是reference同步
        :param checkPlot: 是否需要通过画图检查脉冲中心计算得是否正确
        :param centerAdjust: 计算出的脉冲中心存在的固有偏差 ，单位ns
        :param jointType: 以哪种方式拼接ref数据（仅在refSyncYN=True时有效）
        :return: n组数获取时间的平均值（单位s），脉冲中心（单位ns）
        """
        # 配置target
        if not target: target = SyncData.lastObject.target
        if jointType is None: jointType = target
        # 获取数据，生成直方图
        data = worker.RealTimeTDC.getRecent(count=n, reversed=True)  # (count: Int, reversed: Boolean = False数据由老到新 True数据由新到老)
        # print('n=', data, len(data), n)
        # 检查是否获取到了数据
        fetchTime = np.average([d['FetchTime'] for d in data])
        lengthdata = len(data)
        if lengthdata == 0:
            print('未取到同步数据！')
            return fetchTime, np.nan
        # 脉冲中心调整
        if refSyncYN and (centerAdjust is None):
            if target == 'Alice':
                centerAdjust = AliceRefAdjust
            elif target == 'Bob':
                centerAdjust = BobRefAdjust
        elif centerAdjust is None: centerAdjust = 0.0
        # 计算脉冲中心
        fetchTime, est_center = SyncData.data2center(data=data, target=target, refSyncYN=refSyncYN, checkPlot=checkPlot, centerAdjust=centerAdjust, jointType=jointType)

        return fetchTime, est_center

    @staticmethod
    def data2center(data, target, refSyncYN, checkPlot=True, centerAdjust=0.0, jointType=None):
        if jointType is None: jointType = target
        fetchTime = np.average([d['FetchTime'] for d in data])

        # 将n组数据的直方图合而为一
        each_histogram = [d[f'TFQKDSync{target}'][f'Histogram[Sync {target}]'] for d in data]
        histogram = np.sum(np.array(each_histogram), axis=0)
        print(f'共取{len(each_histogram) / 10} s数据用于本轮时钟同步\n直方图光子数：', np.sum(histogram))

        # 脉冲判断
        histogram0 = [abs(np.mean(histogram) - h) for h in histogram]
        # pulseType = 1
        pulseType = 1 if histogram[histogram0.index(np.max(histogram0))] - np.mean(histogram) >= 0 else -1
        print(f'脉冲突出程度：{np.max(histogram0) / np.average(histogram0)}, 脉冲类型：{"凸" if pulseType >= 0 else "凹"}')

        # 对不同脉冲种类做不同基本判断
        # 凸脉冲
        if pulseType > 0:
            print('凸脉冲处理')
            if np.min(histogram) == 0 and np.max(histogram) < 10:
                print('您的脉冲不够突出啊, 脉冲高处不够高噢')
                return fetchTime, np.nan
            elif np.min(histogram) != 0:
                if np.max(histogram) / np.min(histogram) < 10:
                    print('您的脉冲不够突出啊, 脉冲峰谷之比不够哦')
                    return fetchTime, np.nan
            # elif (np.sum(histogram) / len(histogram)) < 3:
            #     print('您的脉冲光子数太少啦, 这段时间的总光子数不够哦')
            #     return fetchTime, np.nan
        # 凹脉冲
        else:
            print('凹脉冲处理')
            if np.min(histogram) == 0 and (np.sum(histogram) / len(histogram)) < 5:
                print('您的脉冲不够突出啊, 脉冲高处不够高噢')
                return fetchTime, np.nan
            elif np.min(histogram) != 0:
                if np.max(histogram) / np.min(histogram) < 1.3:
                    print('您的脉冲不够突出啊, 脉冲峰谷之比不够哦')
                    return fetchTime, np.nan
            bottom = max(histogram)
            histogram = [bottom - h for h in histogram]

        # reference同步时，挑出Alice或Bobreference波形中坑的位置，并做高通滤波
        if refSyncYN:
            print('ref')
            assert len(histogram) % 4 == 0
            if jointType == 'Alice':
                histogram = histogram[int(len(histogram) / 4 * 3):] + histogram[:int(len(histogram) / 4)]
            elif jointType == 'Bob':
                histogram = histogram[int(len(histogram) / 4):int(len(histogram) / 4 * 3)]
            # 高通滤波
            # b, a = signal.butter(8, 5 / len(histogram), btype='highpass')
            # histogram = signal.filtfilt(b, a, histogram)

        # 提取配置信息
        config = data[0][f'TFQKDSync{target}']['Configuration']
        period = config['Period']
        binCount = config['BinCount']
        # 得到bincount直方图中的脉冲中心
        est_center = SyncData.e_center(histogram, checkPlot=checkPlot)
        print(est_center)
        # 转换为时间轴上的脉冲中心，单位ns
        if est_center is not np.nan:
            est_center = est_center / binCount * period / 1000 + centerAdjust
        print('时间轴上的脉冲中心，单位ns', est_center)
        return fetchTime, est_center


    # 定义高斯函数
    @staticmethod
    def gaussian(x, mu, sigma, h):
        return 1 / (sigma * np.sqrt(2 * np.pi)) * np.exp(-(x - mu) ** 2 / (2 * sigma ** 2)) + h

        # # 生成示例数据
        # x = np.linspace(-10, 10, 100)
        # y = gaussian(x, 0, 1) + np.random.normal(0, 0.1, len(x))
        #
        # # 初始参数的猜测值
        # mu_guess = 0
        # sigma_guess = 1
        #
        # # 使用最小二乘法拟合
        # params, _ = np.optimize.curve_fit(gaussian, x, y, p0=[mu_guess, sigma_guess])
        # mu_fit, sigma_fit = params
        #
        # # 打印拟合结果
        # print("拟合结果：mu = {:.2f}, sigma = {:.2f}".format(mu_fit, sigma_fit))

    @staticmethod
    def func(x, center, width, height):
        return height * ((x >= (center - width / 2)) & (x <= (center + width / 2)))

    @staticmethod
    def e_center(histogram, checkPlot=True):
        # xs为每个bin的中心位置横坐标组成的list
        xs = [k + 0.5 for k in range(len(histogram))]
        print(len(histogram))

        from scipy.optimize import curve_fit
        #
        # # 初始参数的猜测值
        # mu_guess = 0
        # sigma_guess = 1
        #
        # # 使用最小二乘法拟合
        # params = curve_fit(SyncData.gaussian, xdata=xs, ydata=histogram)
        # print(params)
        # mu_fit, sigma_fit, h_fit = params[0]
        # center = mu_fit
        # print(mu_fit)
        #
        # # 打印拟合结果
        # print("拟合结果：mu = {:.2f}, sigma = {:.2f}".format(mu_fit, sigma_fit))

        # 找脉冲最高点
        maxValue = np.max(histogram)
        maxIndex = np.where(histogram == maxValue)[0][0]

        # 高斯拟合
        g_init = models.Gaussian1D(amplitude=maxValue, mean=maxIndex, stddev=9, bounds={'mean':(maxIndex - 10, maxIndex + 10), 'stddev':(8, 10.2), 'amplitude':(maxValue*0.9, maxValue*1.1)},)
        fit_g = fitting.LevMarLSQFitter()
        g = fit_g(g_init, xs, histogram)
        # print('高斯拟合参数', g.mean.value, g.stddev.value, maxIndex)
        center = g.mean.value

        # 方波最小二乘法拟合
        # params = curve_fit(SyncData.func, xdata=np.array(xs), ydata=np.array(histogram), bounds=([maxIndex - 10, 9.99, maxValue*0.8], [maxIndex + 10, 10.1, maxValue*1.1]), p0=[maxIndex, 10, maxValue])
        # center_fit, width_fit, h_fit = params[0]
        # center = center_fit
        # print(center_fit, width_fit, h_fit)

        #
        # # 左右搜索得到全脉冲
        # for right in range(maxIndex, len(histogram)):
        #     if histogram[right] < maxValue / 3:
        #         break
        # for left in range(maxIndex, 0, -1):
        #     if histogram[left] < maxValue / 3:
        #         break
        # if maxIndex == 0: left = 0
        #
        # # 加权平均算脉冲中心
        # weight = 0
        # count = 0
        # for i in range(left, right + 1):
        #     weight += xs[i] * histogram[i]
        #     count += histogram[i]
        # center = weight / count

        # 判断计算出的脉冲中心是否有效
        valid = True
        # valid = max(histogram[:left]) < maxValue * 0.7 and max(histogram[right + 1:]) < maxValue * 0.7
        # if not valid:
        #     print('计算的脉冲中心无效，存在疑似的脉冲')

        # 如需要检查计算的脉冲中心是否正确，将计算值画出来
        if checkPlot:
            plt.scatter(maxIndex + 0.5, maxValue, label='max point')
            plt.plot(xs, histogram)
            # plt.plot(xs[left:right + 1], histogram[left:right + 1], label='center range')
            plt.plot(xs, g(xs), label='fix Gauss')
            plt.plot(xs, SyncData.func(xs, center_fit, width_fit, h_fit), label='square')
            # plt.plot(xs, [SyncData.gaussian(xx, mu_fit, sigma_fit, h_fit) for xx in xs])
            plt.vlines(center, ymin=min(histogram), ymax=maxValue*1.1, linestyles='--', colors='black', alpha=0.4, label='center')
            plt.legend()
            plt.show()

        return center if valid else np.nan

    @staticmethod
    def getAllData(target, method='recent', nset=1, count=1, center=5, refSyncYN=setRefSyncYN, checkPlot=False, centerAdjust=None, st=None, et=None, jointType=None):
        # 填充缺省值
        if jointType is None: jointType = target
        # 校验输入参数
        assert method in ['recent', 'sometime']
        if method == 'sometime':
            assert (st is not None and et is not None)
            count = 10
        else:
            assert isinstance(count, int)
            assert isinstance(nset, int)
        # 脉冲中心调整
        if refSyncYN and (centerAdjust is None):
            if target == 'Alice':
                centerAdjust = AliceRefAdjust
            elif target == 'Bob':
                centerAdjust = BobRefAdjust
        elif centerAdjust is None: centerAdjust = 0.0
        # 获取数据方式
        data = worker.RealTimeTDC.getRecent(count=count*nset, reversed=True) if method == 'recent' else worker.RealTimeTDC.getRanged(st, et, reversed=True)
        if method == 'sometime': assert len(data) % count == 0
        # 检查是否获取到了数据
        lengthdata = len(data)
        if lengthdata == 0:
            print('未取到同步数据！')
            return None
        # 数据切分计算
        nset = int(len(data)/count)
        each_histogram = []
        ft = []
        cl = []
        for i in range(nset):
            data0 = data[i*count:(i+1)*count]
            each_histogram.append(list(np.sum(np.array([d[f'TFQKDSync{target}'][f'Histogram[Sync {target}]'] for d in data0]), axis=0)))
            cl.append(SyncData.data2center(data=data0, target=target, refSyncYN=refSyncYN, checkPlot=checkPlot, centerAdjust=centerAdjust, jointType=jointType)[1])
            ft.append(np.average([d['FetchTime'] for d in data0]))

        data_dic = dict()
        data_dic['histogram'] = each_histogram
        data_dic['fetchTime'] = ft
        data_dic['centerList'] = cl
        data_dic['data'] = data
        data_dic['nset'] = nset
        data_dic['count'] = count
        deltalist = [center - i for i in cl]
        data_dic['deltalist'] = deltalist
        data_dic['target'] = target
        data_dic['jointType'] = jointType
        return data_dic


if __name__ == '__main__':
    target = 'Bob'
    mo = MoMethod.getMO(target=target)  # 获取MO值
    print(mo)
    MoMethod.setMO(MO=2899, target=target)

    # data = worker.RealTimeTDC.getRecent(count=20, reversed=True, delayOnly=True)  # (count: Int, reversed: Boolean = False数据由老到新 True数据由新到老)
    # print(data)

    MoMethod.set_MOsync(2899, target=target)