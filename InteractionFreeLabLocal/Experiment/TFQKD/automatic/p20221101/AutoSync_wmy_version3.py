from interactionfreepy import IFWorker, IFLoop
from AutoSyncExra_wmy import MoMethod, SyncData
import numpy as np
import time
import traceback
from sympy import *
import sys
import datetime
from worker_config import worker_timeoutset as worker


################优化：尽量减少与时钟以及服务器的通信（尤其是申请数据）

def output_redirect():
    import os
    if not os.path.exists('./Autosync_OUTPUT'):
        os.mkdir('./Autosync_OUTPUT')
    out = open(f'Autosync_OUTPUT\{datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")}out.log', 'a')
    err = open(f'Autosync_OUTPUT\{datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")}err.log', 'a')
    sys.stdout = out
    sys.stderr = err


class AutoSync:
    lastObject = None

    def __init__(self, target, searchMOfirst=True, Nroundlimit=float('inf')):
        AutoSync.lastObject = self
        self.storage = worker.blockingInvoker('Storage')
        self.collection = 'TFQKD_TDC'
        self.clockManager = worker.blockingInvoker('TF_ClockManager')
        # target must be 'Alice' or 'Bob'
        if target != 'Alice' and target != 'Bob': raise ValueError("target should be 'Alice' or 'Bob'")
        self.target = target
        self.MoMethod = MoMethod(target=self.target)
        self.SyncData = SyncData(target=self.target)

        # 变量初始化
        self.adjust = 0
        self.driftspeed = 0
        self.fetchTime = np.nan
        self.centerList = np.nan
        self.lasttime = 0
        self.deltaMOList = []
        self.aliceOn = True
        self.bobOn = True
        self.fineScan = False
        self.adjust_yn = True
        self.getDataSleep = True
        self.MoMethod.setMO(self.MoMethod.latest_MOsync())
        self.printDSlist_ys = False
        self.delay_yn = False
        self.savedata = True
        self.searchMOfirst = searchMOfirst
        self.MOnow = self.MoMethod.getMO()
        print(f'MOnow = MO_sync = {self.MOnow}')
        self.MO_sync = self.MOnow

        # 系统参数设置
        self.nset = 10
        self.ndata = 10
        self.slope = self.MoMethod.getSlope()
        self.stableRange = 0.02
        # self.testtime = 8  # 单位s
        self.adjustTime = 4  # 单位s
        self.deltaMOnum = 3
        self.len_deltaMOList = 600
        self.range_deltaMOList = self.deltaMOnum * self.len_deltaMOList * 0.2
        self.adjustSpeed = 0.02  # 单位ns/s
        self.centerRange = 0.03  # 单位ns
        self.targetCenter = 5  # 单位s
        self.roundLimit = 4  # 粗寻MOsync时，循环超过多少轮，说明driftspeed-MO斜率不准，重测MO
        self.MO_sync_driftlimit = 0.01  # 单位ns/s
        self.delay = 1  # 改变参数到系统变化的时间差
        self.centerBalanceRange = 0.02
        self.blockLimit = 2  # 单位ns
        self.dynamic_adjLimit = 0.1  # 单位ns
        self.n = 0
        self.Nroundlimit = Nroundlimit  # 循环次数

    def setMO(self, MO):
        success = False
        while not success:
            try:
                self.MoMethod.setMO(MO)
                self.MOnow = MO
                success = True
            except BaseException as e:
                print(f'Error:{e}')
                print('这里timeout了  垃圾')

    def setMO_sync(self, MO):
        MO = round(MO)
        self.MoMethod.set_MOsync(MO)
        self.MO_sync = MO

    def loop(self):
        # 找到MO值使脉冲不漂移
        if self.searchMOfirst:
            self.adjust_MO_sync(self.nset)

        while True:
            self.n += 1
            if self.n > self.Nroundlimit: return
            try:
                self.control()
            except BaseException as e:
                print('.....Error....Error.....')
                print(e)
                traceback.print_exc()

    @classmethod
    def blockClockManager(self, delta, target=None):
        delta = delta % 10
        if not target: target = AutoSync.lastObject.target
        if delta is np.nan:
            print('NO PULSE')
            return
        print(f'delta = {delta}ns')
        if target == 'Alice':
            worker.blockingInvoker('TF_ClockManager').delay(alice=delta, bob=0)
        else:
            if target == 'Bob':
                worker.blockingInvoker('TF_ClockManager').delay(alice=0, bob=delta)
            else:
                raise ValueError("target should be 'Alice' or 'Bob'")

    def calc_slope(self, nset=None):
        if not nset: nset = AutoSync.lastObject.nset
        # MO设置为上次标定的MO_sync
        self.setMO(MO=self.MoMethod.latest_MOsync())
        MO = self.MOnow
        self.printDSlist_ys = True
        self.delay_yn = True

        # 将脉冲中心复位到0
        fetchtime, center = self.SyncData.getData(n=self.ndata)  # 最新0.3s脉冲位置
        print('aligning center of pulse…………')
        self.blockClockManager(delta=0 - center)
        time.sleep(self.delay+self.ndata*self.SyncData.dataTime)
        print(f'delta = {(0 - center) % 10}, set target of center = 0')

        # 循环采集
        x, y = np.linspace(-100, 100, 5), []
        for d in x:
            self.setMO(MO+round(d))
            self.getRecent(nset=nset)
            y.append(self.driftspeed)
            print(f'MO = {MO+round(d)}， driftspeed = {self.driftspeed}')
            print('aligning center of pulse…………')
            self.blockClockManager(delta=0 - self.centerList[0])
            self.setMO(MO + round(d))
            time.sleep(4)
            print(f'delta = {0 - self.centerList[0]}, set target of center = 0')
        # 将MO复位
        self.setMO(self.MO_sync)
        # 拟合x， y的斜率
        para = np.polyfit(x, y, 1)
        print(f'func = {np.poly1d(para)}')
        self.slope = para[0]
        self.MoMethod.setSlope(slope=self.slope)
        print(f'Slope of driftspeed-MO = {self.slope}')
        self.printDSlist_ys = False
        self.delay_yn = False
        return

    def collet_data(self, nset, ndata=None):
        if not ndata: ndata = self.ndata
        ftList, cList = [], []
        for i in range(nset):
            if self.getDataSleep:
                if self.delay_yn: time.sleep(self.delay + ndata * self.SyncData.dataTime)
                else: time.sleep(ndata * self.SyncData.dataTime)
            fetchtime, center = self.SyncData.getData(n=ndata)
            ftList.append(fetchtime)
            cList.append(center)
        return ftList, cList

    def calc_driftspeed(self, fetchTimeList, centerList):
        if centerList is np.nan or len(fetchTimeList) <= 1: return np.nan
        deltaT = [fetchTimeList[i]-fetchTimeList[i+1] for i in range(len(fetchTimeList)-1)]
        deltaC = [centerList[i]-centerList[i+1] for i in range(len(centerList)-1)]
        dsList = [deltaC[i]/deltaT[i] for i in range(len(deltaT))]
        dsl = [i for i in dsList if abs(i - np.mean(dsList)) < 2 * np.std(dsList)]
        dropped = [i for i in dsList if abs(i - np.mean(dsList)) >= 2 * np.std(dsList)]
        if len(dsl) < len(dsList):
            print(f'drop driftspeed:{len(dsList) - len(dsl)} of {len(dsList)}')
            print(f'driftspeed(ns/s):{dsList}\ndropped(ns/s):{dropped}')
        else:
            if self.printDSlist_ys: print(f'driftspeed(ns/s):{dsList}')
        driftspeed = np.average(dsl)
        return driftspeed

    def getRecent(self, nset=None, ndata=None):
        # 配置nset
        if not nset: nset = self.nset
        if not ndata: ndata = self.ndata

        ftList, cList = self.collet_data(nset, ndata)
        driftspeed = self.calc_driftspeed(ftList, cList)
        self.driftspeed = driftspeed

        if self.driftspeed is not np.nan:
            if abs(self.driftspeed) > self.stableRange:
                # print(f'driftspeed = {self.driftspeed} > {self.stableRange} = stableRange, adjust_yn = True')
                self.adjust_yn = True
            else:
                # print(f'driftspeed = {self.driftspeed} <= {self.stableRange} = stableRange, adjust_yn = False')
                self.adjust_yn = False
        else:
            self.adjust_yn = False
        self.adjust = -self.driftspeed / self.slope
        self.fetchTime = ftList
        self.centerList = cList
        return

    def adjust_MO_sync(self, nset=None):
        self.getDataSleep = True
        self.delay_yn = True
        # 配置nset
        if not nset: nset = AutoSync.lastObject.nset
        # 粗扫MO，调整MO值至漂移在{self.stableRange}ns/s范围内
        self.roughScanMO_sync(nset=self.nset)
        # 寻找0漂移MO
        self.fineScanMO_sync(nset=10)
        # 打印现在的状态
        print(f'MO_sync={self.MOnow}, |driftspeed|=|{self.driftspeed}| <= {self.stableRange}ns/s = stableRange')
        print(f'adjusting MO_sync…………Done!')
        self.delay_yn = False
        return

    def roughScanMO_sync(self, nset=None):
        # 配置nset
        if not nset: nset = self.nset
        n = 0
        while True:
            self.getRecent(nset)
            # 判断是否有脉冲
            if self.centerList is np.nan:
                return
            print(f'adjust_yn = {self.adjust_yn}')
            if self.adjust_yn:
                print(f'MO={self.MOnow}, |driftspeed|=|{self.driftspeed}| > {self.stableRange}ns/s = stableRange')
                print(f'adjusting MO_sync…………')
                self.setMO(MO=self.MOnow + round(self.adjust))
                n = n + 1
            else:
                print(f'MO={self.MOnow}, |driftspeed|=|{self.driftspeed}| <= {self.stableRange}ns/s = stableRange\nEnd rough scanning MO_sync')
                break
        # 如果达到driftspeed <= stableRange使用的轮数太多，说明driftspeed-MO斜率不准，自动测试斜率
        if n >= self.roundLimit:
            print(f'roughScanMO_sync uses {n} round >= {self.roundLimit} = roundLimit, please check slopr of driftspeed-MO = {self.slope}')
        if n >= 1: self.fineScan = True
        else: self.fineScan = False
        return

    def fineScanMO_sync(self, nset=None):
        # 配置nset
        if not nset: nset = AutoSync.lastObject.nset
        print('Start fine scanning MO_sync')
        delta = -(self.driftspeed * self.slope) / abs(self.driftspeed * self.slope)
        MO = self.MOnow
        while self.fineScan:
            ds0 = self.driftspeed
            MO = MO + delta
            self.setMO(MO)
            self.getRecent(nset=15)
            # 判断是否有脉冲
            if self.centerList is np.nan:
                return
            # 继续运行
            ds1 = self.driftspeed
            print(f'searching MO_sync:MO = {MO - delta}, driftspeed = {ds0}, MO = {MO}, driftspeed = {ds1}')
            if ds1 * ds0 > 0 and abs(ds1) > abs(ds0):
                # MO = MO - delta
                self.driftspeed = ds0
                print(f'change delta {delta} to {delta * (-1)}')
                delta = delta * (-1)
            if ds1 * ds0 < 0 and (abs(ds0) < self.MO_sync_driftlimit or abs(ds1) < self.MO_sync_driftlimit):
                self.fineScan = False
                if abs(ds0) < abs(ds1):
                    MO = MO - delta
                    self.driftspeed = ds0
                # 将满足阈值的MO值上传服务器
                self.setMO_sync(MO=MO)
                print('End fine scanning MO_sync')

    def aligning_center_fixAdjTime(self, delta):
        # delta += -self.driftspeed * (self.testtime / 2 + self.datadelay)
        # delta += -self.driftspeed * self.datadelay
        if abs(delta) > self.centerRange:
            print(f'delta = {delta}ns for {self.target}')
            # 获得当前 漂移率-MO 对应函数
            deltaMO = round(delta / self.adjustTime / self.slope)
            MO_adj = self.MO_sync + deltaMO
            print('MO_adj=', MO_adj, f'adjustTime = {self.adjustTime}s', f'expecting adjust speed = {deltaMO * self.slope}ns/s')
            # 开始改变MO，并计时
            st = time.time()
            print(f'set MO = MO_adj = {MO_adj}')
            self.setMO(MO_adj)
            print('sleeping……')
            time.sleep(self.adjustTime)
            print(f'set MO = MO_sync = {self.MO_sync}')
            self.setMO(self.MO_sync)
            et = time.time()
            if abs((et - st) - self.adjustTime) > 0.1: raise ValueError(f'The adjustment time {et - st}s doesn\'t match the setting {self.adjustTime}s !')
        else:
            print(f'|delta| = |{delta}| < {self.centerRange} = centerRange')
        print('Aligning center of pulses…………Done!')
        return

    def aligning_center_fixAdjSpeed(self, delta):
        print('Aligning center of pulses…………（fixAdjSpeed）')
        # delta += -self.driftspeed * (self.testtime / 2 + self.datadelay)
        # delta += -self.driftspeed * self.datadelay
        MOnow = self.MOnow
        if abs(delta) > self.centerBalanceRange:
            print(f'delta = {delta}ns for {self.target}')
            # 下面开始调整
            if self.driftspeed * delta > 0:  # 漂移方向与目标相同
                print(f'driftspeed = {self.driftspeed}ns/s, MO = {MOnow}, no change')
            else:
                deltaMO = np.sign(self.slope * delta) * self.deltaMOnum
                print(f'driftspeed = {self.driftspeed}s, change MO from {MOnow} to {self.MoMethod.latest_MOsync() + deltaMO}')
                MO = MOnow + deltaMO
                self.setMO(MO)
        else:
            self.setMO(self.MO_sync)
            print(f'|delta| = |{delta}|ns <= {self.centerBalanceRange}ns = centerBalanceRange')
        print('Aligning center of pulses…………Done!')
        return
    # self.adjustSpeed = 0.02  # 单位ns/s

    def control(self):
        self.delay_yn = False
        ndata = 10
        self.getRecent(nset=1, ndata=ndata)
        timeNow = time.time()
        Timedelay = timeNow - self.fetchTime[0]
        print(f'{time.strftime("%Y-%m-%d %H:%M:%S.000", time.localtime(timeNow))} Round delay = {timeNow - self.lasttime}s, Time delay = {Timedelay}s, dataTime = {self.fetchTime[0]}, center={self.centerList[0]}')
        if Timedelay > (2 * ndata / 10):
            print(f'time of 1 round = {ndata/10}s\nTimedelay = {Timedelay}s\nDid nothing......')
            return
        self.lasttime = timeNow
        # 如果有脉冲
        if self.centerList is not np.nan:
            delta = self.targetCenter - np.average(self.centerList)
            if abs(delta) > self.blockLimit:
                print(f'|delta| = |{delta}|ns > {self.blockLimit} 时钟板暂停调延时:')
                self.blockClockManager(delta=delta, target=self.target)
                time.sleep(3)
            else:
                # 精调方案1 fixtime
                if abs(delta) > self.dynamic_adjLimit:
                    print(f'|delta| = |{delta}|ns > {self.dynamic_adjLimit} Aligning center of pulses（fixAdjTime）:')
                    self.aligning_center_fixAdjTime(delta)
                # 精调方案2 fixspeed
                else:
                    print(f'|delta| = |{delta}|ns <= {self.dynamic_adjLimit} Dynamic aligning:')
                    self.dynamic_adj(delta)
        else:
            print('No Pulse')
        print('————————————————————————————————————————————————————————')

    def dynamic_adj(self, delta):
        if abs(delta) > self.centerBalanceRange:
            deltaMO = int(np.sign(self.slope * delta) * self.deltaMOnum)
            # deltaMO = int(np.sign(self.slope * delta) * (self.deltaMOnum + int(abs(delta)/self.centerBalanceRange) - 1))
            if (self.MO_sync+deltaMO) != self.MOnow:
                self.setMO(self.MO_sync+deltaMO)
            print(f'|delta| = |{delta}|ns > {self.centerBalanceRange}, setMO = {self.MO_sync}(MO_sync)+{deltaMO} = {self.MOnow}')
        else:
            deltaMO = 0
            if self.MO_sync != self.MOnow:
                self.setMO(self.MO_sync)
            print(f'|delta| = |{delta}|ns <= {self.centerBalanceRange}ns = centerBalanceRange, setMO = {self.MO_sync}(MO_sync)')
        self.process_deltaMO(deltaMO)
        print('Done!')

    def process_deltaMO(self, deltaMO):
        self.deltaMOList.append(deltaMO)
        if len(self.deltaMOList) > self.len_deltaMOList:
            self.deltaMOList = self.deltaMOList[-self.len_deltaMOList:]
        if len(self.deltaMOList) == self.len_deltaMOList:
            if abs(np.sum(self.deltaMOList)) >= self.range_deltaMOList:
                changed_MO_sync = self.MO_sync + np.sign(np.sum(self.deltaMOList))
                print('——————————————————————————————————————————————————————————————')
                print(f'|sum of deltaMOList| = |{np.sum(self.deltaMOList)}| >= {self.range_deltaMOList} = range_deltaMOList. Change MO_sync from {self.MO_sync} to {changed_MO_sync}')
                print('——————————————————————————————————————————————————————————————')
                self.setMO_sync(MO=changed_MO_sync)
                self.deltaMOList = []
            else:
                print(f'|sum of deltaMOList| = |{np.sum(self.deltaMOList)}| < {self.range_deltaMOList} = range_deltaMOList.  MO_sync no change')

        # if self.savedata:

        return

    def delayTest(self):
        lasttime = 0
        while True:
            self.getRecent(1)
            timeNow = time.time()
            print(f'Round delay = {timeNow-lasttime}s, Time delay = {timeNow - self.fetchTime[0]}s, dataTime = {self.fetchTime[0]}, center={self.centerList[0]}')
            lasttime = timeNow

    def test(self):
        pass


if __name__ == '__main__':
    print('Started!')
    # output_redirect()

    import sys
    target = 'Alice'
    # target = 'Bob'
    # target = sys.argv[1]
    a = AutoSync(target=target)
    # a.delayTest()
    a.loop()
    # a.calc_slope()



