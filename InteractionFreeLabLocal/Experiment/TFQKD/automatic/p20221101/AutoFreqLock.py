import matplotlib.pyplot as plt
import numpy
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
from astropy import modeling
import msgpack
pi = np.pi
storage = worker.Storage


class FreqLock:
    lastObject = None

    def __init__(self, phase_invariant_time=0.5E9, ndata=5, phaseThreshold=pi / 8 / 2, Gauss_amplitude_bound: tuple=(500, 3000), Gauss_stddev_bound:tuple=(60, 80), Gauss_mean_bound: tuple=None, targetFreq=50):
        if Gauss_mean_bound == None: Gauss_mean_bound = (0, int(1E12/phase_invariant_time/2))
        self.phase_invariant_time = phase_invariant_time
        self.ndata = ndata
        self.phaseThreshold = phaseThreshold
        self.Gauss_amplitude_bound = Gauss_amplitude_bound
        self.Gauss_stddev_bound = Gauss_stddev_bound
        self.Gauss_mean_bound = Gauss_mean_bound
        self.targetFreq = targetFreq
        self.direct = None
        self.delay = 10
        self.roundTime = 30
        self.freqLimit = 500
        self.adjustLimit = 10
        if self.roundTime <= self.ndata + self.delay: raise ValueError('"roundTime" is too short!')
        FreqLock.lastObject = self

    def loop(self):
        self.test_direct()
        while True:
            print('*' * 50, 'Round Start', '*' * 50)
            st = time.time()
            time.sleep(self.ndata + self.delay)
            self.eachLoop()
            et = time.time()
            print(f'本轮用时{et-st}s')
            print('*' * 50, 'Round End', '*' * 50)
            if et-st > self.roundTime: continue
            time.sleep(self.roundTime-(et-st))

    def eachLoop(self):
        freqNOW = self.FFT_for_recentdata()
        if freqNOW is np.nan: return
        AOMfreqNOW = self.getAOMfreq()
        deltaFreq = self.targetFreq - freqNOW
        if abs(deltaFreq) > self.freqLimit: raise ValueError(f'diff of freq = {abs(deltaFreq)}Hz > {self.freqLimit}Hz')
        if abs(deltaFreq) > 100: self.direct = -1 * self.direct

        print(f'freq_diff = {freqNOW}Hz, targetFreq = {self.targetFreq}Hz, deltaFreq = {deltaFreq}Hz')
        print(f'freqLimit = {self.freqLimit}Hz')
        print(f'adjust direction = {self.direct}')
        if abs(deltaFreq) > self.adjustLimit:
            self.setAOMfreq(AOMfreqNOW + np.sign(deltaFreq) * self.adjustLimit * self.direct)
            print(f'adjust freq of AOM :{np.sign(deltaFreq) * self.adjustLimit * self.direct}Hz')
        else:
            self.setAOMfreq(AOMfreqNOW + deltaFreq * self.direct)
            print(f'adjust freq of AOM :{deltaFreq * self.direct}Hz')

    def FFT_for_somedata(self, beginTime, endTime, multiprocess_YN=False, processes=40, jump:int=1, plotcountYN=False, plotEachYN=False, plotYN=True, saveYN=False, plotmaxline=False, plotSTD=False):
        count_histogram_list = FreqLock.getsomeData(beginTime=beginTime, endTime=endTime, phase_invariant_time=self.phase_invariant_time, phaseThreshold=self.phaseThreshold, multiprocess_YN=multiprocess_YN, processes=processes, jump=jump)
        self.histogram_fft(count_histogram_list, beginTime, endTime, plotcountYN=plotcountYN, plotEachYN=plotEachYN, plotYN=plotYN, saveYN=saveYN, plotmaxline=plotmaxline, plotSTD=plotSTD)

    def FFT_for_somedata_multiprocess(self, beginTime, endTime, processes=40, jump:int=1, plotcountYN=False, plotEachYN=False, plotYN=True, saveYN=True, plotmaxline=False, plotSTD=False):
        count_histogram_list = FreqLock.getsomeData(beginTime=beginTime, endTime=endTime, phase_invariant_time=self.phase_invariant_time, phaseThreshold=self.phaseThreshold, multiprocess_YN=True, processes=processes, jump=jump)
        self.histogram_fft(count_histogram_list, beginTime, endTime, plotcountYN=plotcountYN, plotEachYN=plotEachYN, plotYN=plotYN, saveYN=saveYN, plotmaxline=plotmaxline, plotSTD=plotSTD)

    def FFT_for_recentdata(self, plotcountYN=False, plotEachYN=False, plotYN=False, saveYN=False, plotmaxline=False, plotSTD=False):
        count_histogram_list, beginTime, endTime = FreqLock.getRecentData(ndata=self.ndata, phase_invariant_time=self.phase_invariant_time, phaseThreshold=self.phaseThreshold)
        freq_list = self.histogram_fft(count_histogram_list, beginTime, endTime, plotcountYN=plotcountYN, plotEachYN=plotEachYN, plotYN=plotYN, saveYN=saveYN, plotmaxline=plotmaxline, plotSTD=plotSTD)
        freq = np.average([i for i in freq_list if i > 0])
        print(f'freq = {freq}Hz')
        return freq

    def histogram_fft(self, count_histogram_list, beginTime, endTime, plotcountYN=False, plotEachYN=False, plotYN=False, saveYN=False, plotmaxline=False, plotSTD=False):
        fitting_f_max, fitting_f_Gauss, fitting_f_Gauss_std = [], [], []
        for count_histogram in count_histogram_list:
            if plotcountYN:
                plt.plot(count_histogram)
                plt.show()
                plt.close()
            f, f_power, fmax_x, fmax_y, Gauss_fitting, Gauss_para = self.fft_GaussFitting(count_histogram, time_of_data=1, flit0_YN=True)
            fitting_f_max.append(fmax_x)
            fitting_f_Gauss.append(Gauss_para[1])
            fitting_f_Gauss_std.append(Gauss_para[2])

            if plotEachYN:
                plt.plot(f, f_power)
                plt.plot(f, Gauss_fitting, label=f'amp={Gauss_para[0]}\nmiu={Gauss_para[1]}\nstd={Gauss_para[2]}')
                plt.plot([fmax_x], [fmax_y], "xr")
                plt.legend()
                plt.show()
                plt.close()

        if plotYN:
            # 多项式拟合
            x = [i for i in range(len(count_histogram_list))]
            z1 = np.polyfit(x, fitting_f_Gauss, 1)  # 曲线拟合，返回值为多项式的各项系数
            p1 = np.poly1d(z1)  # 返回值为多项式的表达式，也就是函数式子
            print(p1)
            y_pred = p1(x)
            error = np.average([abs(fitting_f_Gauss[i] - y_pred[i]) for i in range(len(count_histogram_list))])
            plt.plot(x, fitting_f_Gauss, label=f'error={error}\nstd={np.std(fitting_f_Gauss)}')
            if plotmaxline: plt.plot(x, fitting_f_max, label=f'max')
            plt.plot(x, y_pred, 'r', label=f'{p1}')
            plt.xlabel('Time(s)')
            plt.ylabel('freq_diff(Hz)')
            plt.title(f'{beginTime} to {endTime}')
            plt.legend()
            if saveYN:
                plt.savefig(f'freq_diff {beginTime} to {endTime}.png')
            else:
                plt.show()
            plt.close()
            if plotSTD:
                plt.plot(x, fitting_f_Gauss_std, label=f'STD')
                plt.legend()
                plt.show()
                plt.close()

        return fitting_f_Gauss

    def fft_GaussFitting(self, count_histogram, time_of_data=1, flit0_YN=True):
        """
        :param count_histogram: 光子数随时间的统计直方图
        :param time_of_data: 整段count_histogram的时间（单位s）
        :param flit0_YN: 是否过滤0频率分量, True:过滤, False:不过滤
        :return:
            f: fft后的频率横坐标（单位Hz）
            f_power: fft的频率份量大小
            fmax_x: fft最大分量的频率（单位Hz，受flit0_YN影响）
            fmax_y: fft的最大分量大小（受flit0_YN影响）
            Gauss_fitting: Gauss拟合曲线（list）
            Gauss_para: Gauss拟合曲线的参数(numpy.ndarray:([0]amplitude, [1]mean, [2]std))
        """
        f, f_power, fmax_x, fmax_y = FreqLock.DFT(count_histogram, time_of_data=time_of_data)
        if flit0_YN:
            # 去掉频率为0的分量
            f = f[1:]
            f_power = f_power[1:]
        # Gauss拟合
        Gauss_model, Gauss_para = FreqLock.Gauss_fitting(x=f, y=f_power, plotYN=False, amplitude_bound=self.Gauss_amplitude_bound, stddev_bound=self.Gauss_stddev_bound, mean_bound=self.Gauss_mean_bound)
        Gauss_fitting = list(Gauss_model(f))
        return f, f_power, fmax_x, fmax_y, Gauss_fitting, Gauss_para

    @classmethod
    def IDtoRNS(cls, id: str):
        return msgpack.unpackb(worker.TF_FileStorage.readMassive(id=id))

    @classmethod
    def getAOMfreq(cls):
        return worker.TF_LaserFrequencyShifter_Bob.getFrequencySetpoint()

    @classmethod
    def setAOMfreq(cls, freq):
        worker.TF_LaserFrequencyShifter_Bob.setFrequency(freq)

    @classmethod
    def getRecentData(cls, ndata=None, phase_invariant_time=None, phaseThreshold=None):
        if ndata is None: ndata = FreqLock.lastObject.ndata
        if phase_invariant_time is None: phase_invariant_time = FreqLock.lastObject.phase_invariant_time
        if phaseThreshold is None: phaseThreshold = FreqLock.lastObject.phaseThreshold
        storage = worker.Storage
        # 获取所有在范围内的数据的采集时间
        ranges = storage.latest('TFQKD_TDC', filter={'_id': 1}, length=ndata)
        print(f'{len(ranges)} seconds of data fetched...')

        resultlist = []
        for dataMeta in ranges[:]:
            fetchTime = dataMeta['FetchTime']
            dataBlock = FreqLock.getDataBlock(fetchTime)
            meta = storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1})  # meta里面是这一秒钟数据对应的配置信息，包括随机数等等，meta是一个map
            configs = meta['Data']['QKDQBER']['Configuration']
            result = FreqLock.range_to_result(fetchTime, dataBlock, configs, phase_invariant_time, phaseThreshold)
            resultlist.append(result)
        return resultlist, ranges[-1]['FetchTime'], ranges[0]['FetchTime']

    @classmethod
    def getsomeData(cls, beginTime, endTime, phase_invariant_time=None, phaseThreshold=None, multiprocess_YN=False, processes=40, jump:int=1):
        if phase_invariant_time is None: phase_invariant_time = FreqLock.lastObject.phase_invariant_time
        if phaseThreshold is None: phaseThreshold = FreqLock.lastObject.phaseThreshold
        storage = worker.Storage
        # 获取所有在范围内的数据的采集时间
        ranges = storage.range('TFQKD_TDC', beginTime, endTime, filter={'_id': 1}, limit=1000000)
        print(f'{len(ranges)} seconds of data fetched...')

        metas = []
        for dataMeta in ranges:
            metas.append(worker.Storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1}))


        config = worker.Storage.get('TFQKD_TDC', ranges[0]['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1})['Data']['QKDQBER']['Configuration']
        rnsAlice = FreqLock.IDtoRNS(config['AliceRandomNumbers']) if isinstance(config['AliceRandomNumbers'], str) else config['AliceRandomNumbers']
        rnsBob = FreqLock.IDtoRNS(config['BobRandomNumbers']) if isinstance(config['BobRandomNumbers'], str) else config['BobRandomNumbers']
        print('Loading RNS Done.')
        matchedRandomNumbers, rnStat = TDCDataParser.DataBlockParser.matchedRandomNumbers_fitting(rnsAlice, rnsBob)
        print('Process RNS Done.')

        resultlist = []
        n = 0
        if multiprocess_YN:
            multiresult = []
            with multiprocessing.Pool(processes=processes) as pool:
                for meta in metas:
                    n += 1
                    if n % jump != 0: continue
                    fetchTime = meta['FetchTime']
                    configs = meta['Data']['QKDQBER']['Configuration']
                    dataBlock = FreqLock.getDataBlock(fetchTime)
                    multiresult.append(pool.apply_async(FreqLock.range_to_result, (fetchTime, dataBlock, configs, phase_invariant_time, phaseThreshold, rnsAlice, rnsBob, matchedRandomNumbers, rnStat)))

                for result in multiresult:
                    result = result.get()
                    resultlist.append(result)
        else:
            for meta in metas:
                n += 1
                if n % jump != 0: continue
                fetchTime = meta['FetchTime']
                configs = meta['Data']['QKDQBER']['Configuration']
                dataBlock = FreqLock.getDataBlock(fetchTime)
                result = FreqLock.range_to_result(fetchTime, dataBlock, configs, phase_invariant_time, phaseThreshold, rnsAlice, rnsBob, matchedRandomNumbers, rnStat)
                resultlist.append(result)

        return resultlist

    @classmethod
    def range_to_result(cls, fetchTime, dataBlock, configs, phase_invariant_time, phaseThreshold, rnsAlice=None, rnsBob=None, matchedRandomNumbers=None, rnStat=None):
        if rnsAlice is None: rnsAlice = configs['AliceRandomNumbers']
        if rnsBob is None: rnsBob = configs['BobRandomNumbers']
        parser = TDCDataParser.DataBlockParser(dataBlock, rnsAlice, rnsBob, triggerChannel=configs['TriggerChannel'], data1Channel=configs['Channel 1'], data2Channel=configs['Channel 2'], pulsePeriod=configs['Period'], center=configs['PulsePosition'], gateSignal=configs['Gate'], phaseThreshold=phaseThreshold, phase_invariant_time=phase_invariant_time, matchedRandomNumbers=matchedRandomNumbers, rnStat=rnStat)

        result = parser.freq_diff()
        print('\n当前时间：', datetime.datetime.now())
        print('该秒数据时间：', fetchTime)
        return result

    @classmethod
    def getDataBlock(cls, fetchTime):
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

    @classmethod
    def DFT(cls, data, time_of_data=1):
        """
        :param data: 数据序列
        :param time_of_data: 整段数据的时间 (单位s)
        :return: 频谱变换的横坐标（频率，单位Hz）, 频谱变换的纵坐标（频率分量大小）, 去掉0与后半段频率 的最大分量频率（单位Hz）, 去掉0与后半段频率 的最大分量频率 对应的分量
        """
        N = len(data)
        # 离散傅里叶变换
        ft = np.fft.fft(data)  # 离散傅里叶变换
        ft_power = [abs(f) for f in ft]
        # 频谱横坐标
        f_list = [i*time_of_data for i in range(len(ft_power))]
        # 最大频率分量
        f_powermax_index = ft_power.index(np.max(ft_power[1:round(N / 2 + 1)]))
        # 绘制傅里叶变换的结果
        ft_show = list(ft_power[:round(N / 2 + 1)])
        f_list = f_list[:len(ft_show)]
        return f_list, ft_show, f_list[f_powermax_index], ft_power[f_powermax_index]

    @classmethod
    def Gauss_fitting(cls, x, y, plotYN=False, amplitude_bound:tuple=None, stddev_bound:tuple=None, mean_bound:tuple=None):
        """
        :param x: 数据x值
        :param y: 数据y值
        :param plotYN: 是否画图 True：画，False：不画
        :param amplitude_bound: Gauss拟合的幅度范围
        :param stddev_bound: Gauss拟合的标准差范围
        :param mean_bound: Gauss拟合的平均值范围
        :return: Gauss拟合的模型， Gauss拟合的模型参数 numpy.ndarray ([0]amplitude, [1]mean, [2]std)
        """
        if amplitude_bound is None: amplitude_bound = FreqLock.lastObject.Gauss_amplitude_bound
        if stddev_bound is None: stddev_bound = FreqLock.lastObject.Gauss_stddev_bound
        if mean_bound is None: mean_bound = FreqLock.lastObject.Gauss_mean_bound
        # 最大值
        f_max_index = y.index(np.max(y))
        f_max_x = x[f_max_index]
        f_max_y = y[f_max_index]
        # Gauss拟合
        fitter = modeling.fitting.LevMarLSQFitter()
        model = modeling.models.Gaussian1D(amplitude=(amplitude_bound[0] + amplitude_bound[1]) / 2, mean=f_max_x, stddev=(stddev_bound[0] + stddev_bound[1])/2, bounds={'amplitude': amplitude_bound, 'mean': mean_bound, 'stddev': stddev_bound})
        fitted_model = fitter(model, x, y)

        if plotYN:
            plt.plot(x, y)
            plt.plot(x, fitted_model(x), label=f'amp={fitted_model.parameters[0]}\nmiu={fitted_model.parameters[1]}\nstd={fitted_model.parameters[2]}')
            plt.plot([f_max_x], [f_max_y], "xr")
            plt.legend()
            plt.show()
            plt.close()

        return fitted_model, fitted_model.parameters

    @classmethod
    def find_peaks(cls, x, y, plotYN=False, bound_height:tuple=(700, 5000), min_distance=200):
        """
        :param x: 数据x值
        :param y: 数据y值
        :param plotYN: 是否画图
        :param bound_height: 峰高度的拟合范围
        :param min_distance: 拟合出来的峰与峰之间的最小距离
        :return: 峰所在的下标， 峰的x值， 峰的y值 （均为list）
        """
        from scipy.signal import find_peaks
        peaks, properties = find_peaks(y, height=bound_height, distance=min_distance)

        index = list(peaks)
        peak_x = [x[i] for i in index]
        peak_y = [y[i] for i in index]

        if plotYN:
            plt.plot(peak_x, peak_y, "x")
            plt.plot(x, y)
            plt.show()
            plt.close()
            print('peaks:', peaks, [y[p] for p in peaks])

        return index, peak_x, peak_y

    @classmethod
    def openPicture(cls, path):
        im = Image.open(path)
        im.show()

    def test_direct(self):
        print('*' * 30, 'test direction', '*' * 30)
        freq1 = self.FFT_for_recentdata()
        AOM_freq1 = FreqLock.getAOMfreq()
        if freq1 < 100:
            FreqLock.setAOMfreq(AOM_freq1 + 200)
            time.sleep(self.ndata + self.delay)
            freq1 = self.FFT_for_recentdata()
            AOM_freq1 = FreqLock.getAOMfreq()
        AOM_freq2 = AOM_freq1+50
        FreqLock.setAOMfreq(AOM_freq2)
        time.sleep(self.ndata + self.delay)
        freq2 = self.FFT_for_recentdata()

        if freq2 - freq1 > 0:
            self.direct = 1
        else:
            self.direct = -1
        delta = self.targetFreq - freq2
        FreqLock.setAOMfreq(AOM_freq2 + delta * self.direct)
        print(f'direction is {self.direct}')
        print('*' * 30, 'End testing direction', '*' * 30)
        return


if __name__ == '__main__':
    # 独立光源 0927 17:55-20:00
    # beginTime = '2022-09-27T17:54:00+08:00'
    # beginTime = '2022-09-27T17:56:00+08:00'
    # endTime = '2022-09-27T17:56:10+08:00'
    # beginTime = '2022-10-12T02:38:00+08:00'
    # endTime = '2022-10-12T02:38:10+08:00'

    # beginTime = '2022-10-13T01:30:00+08:00'
    # endTime = '2022-10-13T01:31:00+08:00'

    beginTime = '2022-10-13T01:30:00+08:00'
    endTime = '2022-10-13T01:40:00+08:00'
    # fl = FreqLock(phase_invariant_time=0.5E9)
    fl = FreqLock(phase_invariant_time=0.2E9, Gauss_amplitude_bound =(0, 5000), Gauss_stddev_bound=(420, 460))
    # fl.FFT_for_somedata(beginTime=beginTime, endTime=endTime, plotEachYN=True, multiprocess_YN=True, processes=4, plotcountYN=False, plotSTD=False)
    # fl.FFT_for_somedata_multiprocess(beginTime=beginTime, endTime=endTime, processes=40)
    # fl.loop()

    freq = fl.getAOMfreq()
    print(freq)
    fl.setAOMfreq(freq-500)
    print(fl.getAOMfreq())
