import time, socket, sys, threading, math, random
import numpy as np
import matplotlib.pyplot as plt
from math import isnan
from random import Random

exitHooks = []
from interactionfreepy import IFWorker

worker = IFWorker("tcp://172.16.60.199:224")

sys.path.append('D:\\GitHub\\Hydra\\Pydra')
import Pydra


class ExperimentControl:
    def __init__(self):
        self.session = Pydra.Session.newSession(('172.16.60.199', 20102), None, 'MDI-QKD-Controller-Test')
        self.currentTDCReportSize = -1
        self.syncService = self.session.blockingInvoker('SyncService')  # 获得对SyncService的引用
        self.exchanged = False

    def TDCServer_ini(self, mode, FPM=False):
        tdcserver = worker.MDIQKD_GroundTDC
        tdcserver.turnOnAnalyser("Counter")
        if FPM:
            tdcserver.turnOnAnalyser("MultiHistogram", {"Sync": 0, "Signals": [8], "ViewStart": -100000, "ViewStop": 100000,
                                                        "Divide": 1, "BinCount": 1000})
        else:
            tdcserver.turnOnAnalyser("MultiHistogram",
                                     {"Sync": 0, "Signals": [8], "ViewStart": 0, "ViewStop": 40000000, "Divide": 10000,
                                      "BinCount": 1000})

        tdcserver.turnOnAnalyser("CoincidenceHistogram",
                                 {"ChannelA": 8, "ChannelB": 9, "ViewStart": -200, "ViewStop": 200, "BinCount": 1000})

        def encodingRnds(mode):
            if len(mode) == 3: return self.randomNumbers
            if len(mode) == 2: return self.randomNumbers1

        tdcserver.turnOnAnalyser("MDIQKDEncoding",
                                 {"Period": 4000.0, "TriggerChannel": 0, "SignalChannel": 8, "TimeAliceChannel": 4,
                                  "TimeBobChannel": 5, "BinCount": 100,
                                  "RandomNumbers": encodingRnds(mode)})
        if mode in ['AB', 'AD', 'BD']:
            tdcserver.turnOnAnalyser("MDIQKDQBER",
                                     {"AliceRandomNumbers": self.randomNumbers1, "BobRandomNumbers": self.randomNumbers2, "Period": 4000.0,
                                      "Delay": 900.0, "PulseDiff": 2000.0, "Gate": 1000.0, "TriggerChannel": 0, "Channel 1": 8,
                                      "Channel 2": 9, "Channel Monitor Alice": 4, "Channel Monitor Bob": 5, "QBERSectionCount": 1000,
                                      "HOMSidePulses": [-100, -90, -80, 80, 90, 100], "ChannelMonitorSyncChannel": 2})

    def stop(self):
        self.session.stop()

    def configureAwgDavid(self, mode, randomNumbers):
        volX = [0.05, 0.08]  # 第一项对应AD干涉配置，第二项对应BD干涉配置
        volY = [0.12, 0.147]
        ampDecoyX = volX[0] if mode[:2] == 'AD' else volX[1]
        ampDecoyY = volY[0] if mode[:2] == 'AD' else volY[1]

        print('randomsDavid:\t', len(randomNumbers), randomNumbers)
        print("Configuring awg David!")
        r = Random(0)

        # worker = IFWorker('tcp://172.16.60.199:224')
        dev = worker.blockingInvoker('MDIQKD_AWGEncoder_David')
        dev.configure('sampleRate', 2.5e9)
        try:
            PRSlice, S0 = 16, int(100000 / len(randomNumbers))
            randomNumbersDavid = randomNumbers
            dev.configure('firstLaserPulseMode', False)
            dev.configure('phaseRandomizationSlice', PRSlice)
            dev.setPhaseRandomNumbers([r.randint(0, PRSlice - 1) for rnd in randomNumbersDavid])
            dev.configure('waveformLength', len(randomNumbersDavid) * S0)
            dev.configure("time2Reversed", True)
            dev.configure("time1Reversed", True)

            dev.configure('pulseDiff', 1.95)

            dev.configure('pulseWidthDecoy', 1.15)
            dev.configure('pulseWidthTime0', 1.15)
            dev.configure('pulseWidthTime1', 1.15)
            dev.configure('pulseWidthPM', 1.95)

            dev.configure('delayDecoy', 0.0)
            dev.configure('delayTime0', 14.0)
            dev.configure('delayTime1', 299.3)
            dev.configure('delayPM', 86.8)
            dev.configure('delayPR', -104.5)

            dev.configure('ampDecoyZ', 1.0)
            dev.configure('ampDecoyX', ampDecoyX)
            dev.configure('ampDecoyY', ampDecoyY)
            dev.configure('ampDecoyO', 0.0)
            dev.configure('ampTime', 1.0)
            dev.configure('ampPM', 0.285)
            dev.configure('ampPR', 0.6)

            dev.setRandomNumbers(randomNumbersDavid)
            waveforms = dev.generateNewWaveform(True)

            # for index, value in waveforms.items(): print(index, value)

            def selectChannels(choice):
                dev.stopAllChannels()
                if "All" in choice:
                    dev.startAllChannels()
                    print("Output All channels enabled!")
                else:
                    for channel in choice:
                        dev.startChannel(channel)
                        print("Output %s enabled!" % channel)

            def showwaveforms(Nperiods):
                fig = plt.figure(figsize=(10, 6))
                ax1 = fig.add_subplot(231)
                ax2 = fig.add_subplot(232)
                ax3 = fig.add_subplot(233)
                ax4 = fig.add_subplot(234)
                ax5 = fig.add_subplot(235)
                ax1.plot(waveforms["AMDecoy"][:Nperiods * S0], label="decoy")
                ax2.plot(waveforms["AMTime1"][:Nperiods * S0], label="AMI")
                ax3.plot(waveforms["AMTime2"][:Nperiods * S0], label="AMII")
                ax4.plot(waveforms["PM"][:Nperiods * S0], label="PM")
                ax5.plot(waveforms["PR"][:Nperiods * S0], label="PR")
                ax1.legend()
                ax2.legend()
                ax3.legend()
                ax4.legend()
                ax5.legend()
                print(len(waveforms["AMDecoy"]))
                plt.show()

            # showwaveforms(20)
            # selectChannels(["AMDecoy"])
        finally:
            worker.close()
            print("Awg David configuration finished!")

    def configureAwgAlice(self, mode, randomNumbers, delayAD=0.0):
        volX = [0.083, 0.086]  # 第一项对应AB干涉配置，第二项对应AD干涉配置
        volY = [0.18, 0.185]
        ampDecoyX = volX[0] if mode[:2] == 'AB' else volX[1]
        ampDecoyY = volY[0] if mode[:2] == 'AB' else volY[1]

        print("delayAD:\t", delayAD)
        print('randomsAlice:\t', len(randomNumbers), randomNumbers)

        print("Configuring awg Alice!")

        r = Random(0)
        # worker = IFWorker('tcp://172.16.60.199:224')
        dev = worker.blockingInvoker('MDIQKD_AWGEncoder_Alice')
        dev.configure("sampleRate", 2e9)
        try:
            PRSlice, S0 = 16, int(80000 / len(randomNumbers))
            randomNumbersAlice = randomNumbers
            dev.configure('firstLaserPulseMode', False)
            dev.configure('phaseRandomizationSlice', PRSlice)
            dev.configure('waveformLength', len(randomNumbersAlice) * S0)

            dev.configure('pulseWidthDecoy', 0.9)
            dev.configure('pulseWidthTime0', 1.4)
            dev.configure('pulseWidthTime1', 1.4)
            dev.configure('pulseWidthPM', 1.9)
            #
            dev.configure('pulseDiff', 1.9)

            dev.configure('ampDecoyZ', 1)
            dev.configure('ampDecoyX', ampDecoyX)
            dev.configure('ampDecoyY', ampDecoyY)
            dev.configure('ampDecoyO', 0)
            dev.configure('ampTime', 1)
            dev.configure('ampPM', 0.35)
            dev.configure('ampPR', 0.6)

            dev.configure('delayDecoy', 0.0 + delayAD)
            dev.configure('delayTime0', 41.0 + delayAD)
            dev.configure('delayTime1', 46.0 + delayAD)
            dev.configure('delayPM', 59.0 + delayAD)
            dev.configure('delayPR', 68.0 + delayAD)

            dev.setRandomNumbers(randomNumbersAlice)
            dev.setPhaseRandomNumbers([r.randint(0, PRSlice - 1) for rnd in randomNumbersAlice])
            waveforms = dev.generateNewWaveform(True)

            def showwaveforms(N1):
                fig = plt.figure(figsize=(10, 6))
                ax1 = fig.add_subplot(231)
                ax2 = fig.add_subplot(232)
                ax3 = fig.add_subplot(233)
                ax4 = fig.add_subplot(234)
                ax5 = fig.add_subplot(235)
                ax1.plot(waveforms["AMDecoy"][:N1 * S0], label="decoy")
                ax2.plot(waveforms["AMTime1"][:N1 * S0], label="AMI")
                ax3.plot(waveforms["AMTime2"][:N1 * S0], label="AMII")
                ax4.plot(waveforms["PM"][:N1 * S0], label="PM")
                ax5.plot(waveforms["PR"][:N1 * S0], label="PR")
                ax1.legend()
                ax2.legend()
                ax3.legend()
                ax4.legend()
                ax5.legend()
                plt.show()

            def selectChannels(choice):
                dev.stopAllChannels()
                if "All" in choice:
                    dev.startAllChannels()
                    print("Output All channels enabled!")
                else:
                    for channel in choice:
                        dev.startChannel(channel)
                        print("Output %s enabled!" % channel)

            selectChannels(["All"])
            # dev.stopAllChannels()
            # showwaveforms(20)
        finally:
            worker.close()

    def configureAwgBob(self, mode, randomNumbers, delayBD=0.0):
        volX = [0.075, 0.09]  # 第一项对应AB干涉配置，第二项对应BD干涉配置
        volY = [0.16, 0.17]
        ampDecoyX = volX[0] if mode[:2] == 'AB' else volX[1]
        ampDecoyY = volY[0] if mode[:2] == 'AB' else volY[1]
        print('randomsBob:\t\t', len(randomNumbers), randomNumbers)
        print("Configuring awg Bob!")
        print("delayBD:\t", delayBD)

        from IFWorker import IFWorker
        from IFCore import IFLoop
        r = Random(0)

        # worker = IFWorker('tcp://172.16.60.199:224')
        dev = worker.blockingInvoker('MDIQKD_AWGEncoder_Bob')
        try:
            PRSlice, S0 = 16, int(80000 / len(randomNumbers))
            randomNumbersBob = randomNumbers
            # dev.configure('firstLaserPulseMode', False)
            dev.configure('phaseRandomizationSlice', PRSlice)
            dev.configure('waveformLength', len(randomNumbersBob) * S0)

            dev.configure('pulseWidthDecoy', 0.9)
            dev.configure('pulseWidthTime0', 1.4)
            dev.configure('pulseWidthTime1', 1.4)
            dev.configure('pulseWidthPM', 1.9)
            dev.configure('pulseDiff', 1.9)

            dev.configure('ampDecoyZ', 1.0)
            dev.configure('ampDecoyX', ampDecoyX)
            dev.configure('ampDecoyY', ampDecoyY)
            dev.configure('ampDecoyO', 0)
            dev.configure('ampTime', 1.0)
            dev.configure('ampPM', 0.33)
            dev.configure('ampPR', 0.66)

            dev.configure('delayDecoy', 0.0 + delayBD)
            dev.configure('delayTime0', 29.55 + delayBD)  # 第一次延时错开后
            dev.configure('delayTime1', 40.05 + delayBD)
            dev.configure('delayPM', 23.5 + delayBD)
            dev.configure('delayPR', 4.5 + delayBD)

            dev.setRandomNumbers(randomNumbersBob)
            dev.setPhaseRandomNumbers([r.randint(0, PRSlice - 1) for rnd in randomNumbersBob])
            waveforms = dev.generateNewWaveform(True)

            # for index, value in waveforms.items(): print(index, value)

            def selectChannels(choice):
                dev.stopAllChannels()
                if "All" in choice:
                    dev.startAllChannels()
                    print("Output All channels enabled!")
                else:
                    for channel in choice:
                        dev.startChannel(channel)
                        print("Output %s enabled!" % channel)

            def showwaveforms(Nperiods):
                fig = plt.figure(figsize=(10, 6))
                ax1 = fig.add_subplot(231)
                ax2 = fig.add_subplot(232)
                ax3 = fig.add_subplot(233)
                ax4 = fig.add_subplot(234)
                ax5 = fig.add_subplot(235)
                ax1.plot(waveforms["AMDecoy"][:Nperiods * S0], label="decoy")
                ax2.plot(waveforms["AMTime1"][:Nperiods * S0], label="AMI")
                ax3.plot(waveforms["AMTime2"][:Nperiods * S0], label="AMII")
                ax4.plot(waveforms["PM"][:Nperiods * S0], label="PM")
                ax5.plot(waveforms["PR"][:Nperiods * S0], label="PR")
                ax1.legend()
                ax2.legend()
                ax3.legend()
                ax4.legend()
                ax5.legend()
                plt.show()

            selectChannels(["All"])
            # dev.stopAllChannels()
            # showwaveforms(20)
        finally:
            worker.close()

    def setTDCDelay(self, channel, delay):
        tdc = worker.MDIQKD_GroundTDC
        tdc.setDelay(channel, int(delay * 1000))

    def setMDIParserChannel(self):
        tdc = self.session.blockingInvoker('GroundTDCService')

        # def exchangedRND(rnd):
        #     eRND = [r for r in rnd]
        #     for i in range(len(rnd)):
        #         if eRND[i] == 2:
        #             eRND[i] = 4
        #         elif eRND[i] == 3:
        #             eRND[i] = 5
        #         elif eRND[i] == 4:
        #             eRND[i] = 2
        #         elif eRND[i] == 5:
        #             eRND[i] = 3
        #     return eRND
        # exchanged_rnd_Alice = exchangedRND(self.randomNumbersAlice)
        # exchanged_rnd_Bob = exchangedRND(self.randomNumbersBob)
        exchanged = self.exchanged
        if not exchanged:
            tdc.configureAnalyser("MDIQKDQBER", {"AliceRandomNumbers": self.randomNumbersBob, "BobRandomNumbers": self.randomNumbersDavid})
            print('tdc MDIQKDQBER configured.')
            # print(self.randomNumbersBob)
        else:
            raise ("Using exchanged RND")
            # tdc.configureAnalyser("MDIQKDQBER", {"AliceRandomNumbers": exchanged_rnd_Alice, "BobRandomNumbers": exchanged_rnd_Bob})

    def riseTimeFit(self, tList, sList):
        avgX, avgY = tList[2:-2], [sum(sList[i - 2:i + 2]) / 4 for i in range(2, len(sList) - 2)]
        upper, lower = max(avgY) * 0.8, max(avgY) * 0.1
        x, y = [], []
        for i in range(len(avgY) - 1):
            if lower < avgY[i] < upper:
                if avgY[i] < avgY[i + 1]:
                    x.append(avgX[i])
                    y.append(avgY[i])
        deltas = [x[i + 1] - x[i] for i in range(len(x) - 1)]
        if len(set(deltas)) == 2:
            x = x[:deltas.index(max(deltas)) + 1]
            y = y[:deltas.index(max(deltas)) + 1]
        if len(set(deltas)) == 3:
            x1 = np.array(x)[np.where(np.array(x) > 3000)] - 4000
            x2 = np.array(x)[np.where(np.array(x) < 1000)]
            y1 = np.array(y)[np.where(np.array(x) > 3000)]
            y2 = np.array(y)[np.where(np.array(x) < 1000)]
            x = list(x1) + list(x2)
            y = list(y1) + list(y2)
        a = np.polyfit(x, y, 1)
        return -a[1] / a[0]

    def fetchRecentDelay(self):
        worker = IFWorker('tcp://192.168.25.27:224')
        last = None

        while True:
            latest = worker.Storage.latest('MDIQKD_GroundTDC', after=last, filter={
                'FetchTime': 1,
                'Data.MDIQKDEncoding.Configuration.Period': 1,
                'Data.MDIQKDEncoding.Histogram Alice Time': 1,
                'Data.MDIQKDEncoding.Histogram Bob Time': 1,
            })
            if latest == None:
                continue
            else:
                last = latest['FetchTime']
                period = latest['Data']['MDIQKDEncoding']['Configuration']['Period']
                aliceYs = latest['Data']['MDIQKDEncoding']['Histogram Alice Time']
                bobYs = latest['Data']['MDIQKDEncoding']['Histogram Bob Time']
                xs = list(np.arange(0, period, period / len(aliceYs)))
                if max(aliceYs) < 50.0:
                    aliceRise = "noSignal"
                else:
                    aliceRise = self.riseTimeFit(xs, aliceYs) / 1000
                if max(bobYs) < 50.0:  # 无信号脉冲时
                    bobRise = "noSignal"  # worker.Algorithm_Fitting.riseTimeFit(xs, bobYs)
                else:
                    bobRise = self.riseTimeFit(xs, bobYs) / 1000
                yield aliceRise, bobRise

    def set_attenu_voltage(self, name, channel, voltage):  # 设置Alice或者Bob端某一通道电压
        dc = self.session.blockingInvoker('DC-MDI-' + name)
        dc.setVoltage(channel, voltage)

    def set_slip(self, name, t):
        HMCName = {name: "HMC7044Eval" + name}
        clock = self.session.blockingInvoker(HMCName[name])
        clock.setDelay(0, t)

    def time_sync_AB(self, time_limit=0.1, target_alice=0.0, target_bob=0.0, sync_period=5.0):
        maxstep = 0.1
        gen = self.fetchRecentDelay()
        while True:
            while True:
                delay = gen.__next__()
                if delay is not None:
                    break
            ta, tb, tc = delay[0] - target_alice, delay[1] - target_bob, 0
            print("{:.3f}\t{:.3f}\t{:.3f}\t{:.3f}".format(delay[0], delay[1], ta, tb))

            if abs(ta) > time_limit or abs(tb) > time_limit:
                if ta < tb < tc or tb < ta < tc:
                    self.session.blockingInvoker("HMC7044EvalAlice").setDelay(0, min(abs(ta - tc), maxstep))
                    self.session.blockingInvoker("HMC7044EvalBob").setDelay(0, min(abs(tb - tc), maxstep))
                elif ta < tc < tb or tb < tc < ta:
                    first = "HMC7044EvalCharlie"
                    second = "HMC7044EvalAlice" if ta < tb else "HMC7044EvalBob"
                    self.session.blockingInvoker(first).setDelay(0, min(abs(min(tc - ta, tc - tb)), maxstep))
                    self.session.blockingInvoker(second).setDelay(0, min(abs(ta - tb), maxstep))
                elif tc < ta < tb or tc < tb < ta:
                    first = 'HMC7044EvalCharlie'
                    second = 'HMC7044EvalAlice' if ta < tb else 'HMC7044EvalBob'
                    self.session.blockingInvoker(first).setDelay(0, min(max(ta - tc, tb - tc), maxstep))
                    self.session.blockingInvoker(second).setDelay(0, min(abs(ta - tb), maxstep))
                time.sleep(sync_period)
                continue
            time.sleep(sync_period)

    def time_sync_AD(self, time_limit=0.1, target_alice=0.0, target_david=0.0, sync_period=5.0):
        maxstep = 0.1
        gen = self.fetchRecentDelay()
        while True:
            while True:
                delay = gen.__next__()
                if delay is not None:
                    break
            ta, td, tc = delay[0] - target_alice, delay[1] - target_david, 0
            print("{:.3f}\t{:.3f}\t{:.3f}\t{:.3f}".format(delay[0], delay[1], ta, td))

            if abs(ta) > time_limit or abs(td) > time_limit:
                if ta < td < tc or td < ta < tc:
                    self.session.blockingInvoker("HMC7044EvalAlice").setDelay(0, min(abs(ta - tc), maxstep))
                    self.session.blockingInvoker("HMC7044EvalDavid").setDelay(0, min(abs(td - tc), maxstep))
                elif ta < tc < td or td < tc < ta:
                    first = "HMC7044EvalCharlie"
                    second = "HMC7044EvalAlice" if ta < td else "HMC7044EvalDavid"
                    self.session.blockingInvoker(first).setDelay(0, min(abs(min(tc - ta, tc - td)), maxstep))
                    self.session.blockingInvoker(second).setDelay(0, min(abs(ta - td), maxstep))
                elif tc < ta < td or tc < td < ta:
                    first = 'HMC7044EvalCharlie'
                    second = 'HMC7044EvalAlice' if ta < td else 'HMC7044EvalDavid'
                    self.session.blockingInvoker(first).setDelay(0, min(max(ta - tc, td - tc), maxstep))
                    self.session.blockingInvoker(second).setDelay(0, min(abs(ta - td), maxstep))
                time.sleep(sync_period)
                continue
            time.sleep(sync_period)

    def time_sync_BD(self, time_limit=0.1, target_bob=0.0, target_david=0.0, sync_period=3.0):
        gen = self.fetchRecentDelay()
        maxstep = 0.2
        while True:
            while True:
                delay = gen.__next__()
                if delay is not None:
                    break
            tb, td, tc = delay[0] - target_bob, delay[1] - target_david, 0
            print("{:.3f}\t{:.3f}\t{:.3f}\t{:.3f}".format(delay[0], delay[1], tb, td))
            if abs(tb) > time_limit or abs(td) > time_limit:
                if tb < td < tc or td < tb < tc:
                    self.session.blockingInvoker("HMC7044EvalBob").setDelay(0, min(abs(tb - tc), maxstep))
                    time.sleep(1.0)
                    self.session.blockingInvoker("HMC7044EvalDavid").setDelay(0, min(abs(td - tc), maxstep))
                elif tb < tc < td or td < tc < tb:
                    first = "HMC7044EvalCharlie"
                    second = "HMC7044EvalBob" if tb < td else "HMC7044EvalDavid"
                    self.session.blockingInvoker(first).setDelay(0, min(abs(min(tc - tb, tc - td)), maxstep))
                    time.sleep(1.0)
                    self.session.blockingInvoker(second).setDelay(0, min(abs(tb - td), maxstep))
                elif tc < tb < td or tc < td < tb:
                    first = 'HMC7044EvalCharlie'
                    second = 'HMC7044EvalBob' if tb < td else 'HMC7044EvalDavid'
                    self.session.blockingInvoker(first).setDelay(0, min(max(tb - tc, td - tc), maxstep))
                    time.sleep(1.0)
                    self.session.blockingInvoker(second).setDelay(0, min(abs(tb - td), maxstep))
                time.sleep(sync_period)
                continue
            time.sleep(sync_period)

    def syncCharlieDavid(self, limit=0.1, davidT0=0.0, period=3.0):
        maxSPD = 0.1
        gen = self.fetchRecentDelay()
        while True:
            while True:
                bobRise = gen.__next__()[-1]
                if bobRise is not None:
                    break
            dt = 0.0 if bobRise == "noSignal" else davidT0 - bobRise
            print(bobRise, dt)
            if abs(dt) > limit:
                if dt > 0:
                    self.session.blockingInvoker('HMC7044EvalDavid').setDelay(0, min(dt, maxSPD))
                else:
                    self.session.blockingInvoker('HMC7044EvalCharlie').setDelay(0, min(-dt, maxSPD))
            time.sleep(period)
            continue

    def syncCharlieAlice(self, limit=0.1, AliceT0=0.0, period=3.0):
        maxSPD = 0.3
        gen = self.fetchRecentDelay()
        while True:
            while True:
                aliceRise = gen.__next__()[0]
                if aliceRise is not None:
                    break
            dt = AliceT0 - aliceRise
            print(aliceRise, dt)
            if abs(dt) > limit:
                if dt > 0:
                    self.session.blockingInvoker('HMC7044EvalAlice').setDelay(0, min(dt, maxSPD))
                else:
                    self.session.blockingInvoker('HMC7044EvalCharlie').setDelay(0, min(-dt, maxSPD))
            time.sleep(period)
            continue

    def syncCharlieBob(self, mode, limit=0.1, bobT0=0.0, period=3.0):
        maxSPD = 0.3
        gen = self.fetchRecentDelay()
        while True:
            while True:
                bobRise = gen.__next__()[0] if mode[:2] == "BD" else gen.__next__()[-1]
                if bobRise is not None:
                    break
            dt = bobT0 - bobRise
            print(bobRise, dt)
            if abs(dt) > limit:
                if dt > 0:
                    self.session.blockingInvoker('HMC7044EvalBob').setDelay(0, min(dt, maxSPD))
                else:
                    self.session.blockingInvoker('HMC7044EvalCharlie').setDelay(0, min(-dt, maxSPD))
            time.sleep(period)
            continue

    def TimeAM_feedback(self, name, channel):
        dc = self.session.blockingInvoker('DC-MDI-' + name)
        if channel == 0:
            voltage_limit = 10
            voltage = dc.getVoltageSetPoint(channel)
            voltage_range = [-0.5 + 0.05 * i for i in range(20)]
            voltages = [voltage + delta for delta in voltage_range]
            for i in range(len(voltages)):
                if voltages[i] > voltage_limit:
                    voltages[i] = voltage_limit
            reports = []
            for voltage in voltages:
                dc.setVoltage(channel, voltage)
                time.sleep(4)
                report = self.getCurrentTDCReport()
                reports.append(report['Z 0 Error Rate'])  # + report['Z 1 Error Rate']
            dc.setVoltage(channel, voltages[reports.index(min(reports))])
        elif channel == 1:
            voltage_limit = 10
            voltage = dc.getVoltageSetPoint(channel)
            voltage_range = [-0.5 + 0.05 * i for i in range(20)]
            voltages = [voltage + delta for delta in voltage_range]
            for i in range(len(voltages)):
                if voltages[i] > voltage_limit:
                    voltages[i] = voltage_limit
            reports = []
            for voltage in voltages:
                dc.setVoltage(channel, voltage)
                time.sleep(4)
                report = self.getCurrentTDCReport()
                reports.append(report['Z 0 Error Rate'])  # + report['Z 1 Error Rate']
            dc.setVoltage(channel, voltages[reports.index(min(reports))])
        print("{} TimeAM voltages:{:.2f}\t{:.2f}".format(name, dc.getVoltageSetPoint(0), dc.getVoltageSetPoint(1)))

    def zErrorOptimization(self, name):
        print("Start optimizing Z basis error rate!")
        if name == "Alice-Time1":
            self.TimeAM_feedback(name, 1)
            time.sleep(3)
            self.TimeAM_feedback(name, 0)
            time.sleep(3)
        else:
            self.TimeAM_feedback(name, 0)
            time.sleep(5)
            self.TimeAM_feedback(name, 1)
        print("Z basis error rate optimization finished!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    def setDecoyVoltage(self, name, voltage):
        dcDecoy = self.session.blockingInvoker('DC-MDI-' + name + "-Decoy")
        dcDecoy.setVoltage(0, voltage)

    def getVoltages(self, name):
        dc = self.session.blockingInvoker(name)
        print("{} voltages: {}".format(name, [dc.getVoltageSetPoint(i) for i in range(3)]))

    def chooseHOMparties(self, mode, timesync=False):
        """Options for mode: AB, AD, BD, Alice, Bob, David. If only single party is selected,the optical switch does nothing."""
        osn = self.session.blockingInvoker("OpticalSwitch_Charlie")
        osn.chooseHOM(mode)

        syncparties = {"AB": self.time_sync_AB, "AD": self.time_sync_AD, "BD": self.time_sync_BD, "A": self.syncCharlieAlice, "B": self.syncCharlieBob, "D": self.syncCharlieDavid}
        syncargs = {"AB": (0.1, 0.0, 0.0, 5.0), "AD": (0.1, 0.0, 0.0, 5.0), "BD": (0.1, 0.2, 0.1, 5.0), "A": (0.1, 0.1, 5.0), "B": (0.1, 0.1, 5.0, "AB" if mode[:2] == 'AB' else 'BD'), "D": (0.1, 0.1, 5.0)}
        thread = threading.Thread(target=syncparties[mode], args=syncargs[mode]) if mode in ['AB', 'AD', 'BD'] else threading.Thread(target=syncparties[mode[-1]], args=syncargs[mode[-1]])
        if timesync:
            print('time syncing for %s starts!' % mode)
            thread.start()

    def setADCMonitorChannel(self, mode):
        worker = IFWorker("tcp://172.16.60.199:224")
        if mode[:2] == 'AB': worker.MDI_ADCMonitor.configStorage(0, 1)
        if mode[:2] == 'AD': worker.MDI_ADCMonitor.configStorage(0, -1)
        if mode[:2] == 'BD': worker.MDI_ADCMonitor.configStorage(1, -1)


if __name__ == '__main__':
    ec = ExperimentControl()


    def configureTDC(t0, mode, init=False, FPM=False):
        if init: ec.TDCServer_ini(mode, FPM)
        ec.setTDCDelay(0, t0)  # 通道0延时
        ec.setTDCDelay(4, 32.7)  # 监测通道5延时,alice250Mhz
        ec.setTDCDelay(5, 34.0)  # 监测通道6延时;david250Mhz
        ec.setTDCDelay(8, 0)  # 干涉通道9
        ec.setTDCDelay(9, -510.7)  # 干涉通道10
        print("TDC channel delays applied!")


    # def setATT(Alice_ATT, Bob_ATT, David_ATT):
    #     # ec.set_attenu_voltage("Alice-Time1", 2, Alice_ATT)  # 控制Alice端总发光光强03dB/0.1V
    #     ec.set_attenu_voltage("Bob-Time", 2, Bob_ATT)  # 控制Bob端总发光光强
    #     ec.set_attenu_voltage("David-Time", 2, David_ATT)  # 控制David端总发光光强
    #     print("Attenuation applied!")
    #
    #
    # def setTimeAM_Bob(DC_AMI, DC_AMII):
    #     if (DC_AMI < 9.0) and (DC_AMI < 9.0):
    #         pass
    #     else:
    #         print("One of the voltage exceeds 9V!")
    #         exit()
    #     ec.set_attenu_voltage("Bob-Time", 0, DC_AMI)  # 控制Bob端TIME1偏置
    #     ec.set_attenu_voltage("Bob-Time", 1, DC_AMII)  # 控制Bob端TIME2偏置
    #
    #
    # def setTimeAM_Alice(DC_AMI, DC_AMII):
    #     if (DC_AMI < 9.0) and (DC_AMI < 9.0):
    #         pass
    #     else:
    #         print("One of the voltage exceeds 9V!")
    #         exit()
    #     ec.set_attenu_voltage("Alice-Time1", 1, DC_AMI)  # 控制AliceTIME1偏置
    #     ec.set_attenu_voltage("Alice-Time1", 0, DC_AMII)  # 控制Alice端TIME2偏置
    #
    #
    # def setTimeAM_David(DC_AMI, DC_AMII):
    #     if (DC_AMI < 9.0) and (DC_AMII < 9.0):
    #         pass
    #     else:
    #         print("One of the voltage exceeds 9V!")
    #         exit()
    #     ec.set_attenu_voltage("David-Time", 0, DC_AMI)  # 控制David端Time1偏置
    #     ec.set_attenu_voltage("David-Time", 1, DC_AMII)  # 控制David端Time2偏置
    #
    #
    # def configureAWGs(mode, delayAD=0.0, delayBD=0.0):
    #     if mode in ["ADA", 'ADD', 'ABA', 'ABB', 'BDB', 'BDD']:
    #         if mode[-1] == 'A': ec.configureAwgAlice(mode, ec.randomNumbers, delayAD=delayAD)
    #         if mode[-1] == 'B': ec.configureAwgBob(mode, ec.randomNumbers, delayBD=delayBD)
    #         if mode[-1] == 'D': ec.configureAwgDavid(mode, ec.randomNumbers)
    #     elif mode == 'AB':
    #         ec.configureAwgAlice(mode, ec.randomNumbers1, delayAD)
    #         ec.configureAwgBob(mode, ec.randomNumbers2, delayBD)
    #     elif mode == 'AD':
    #         ec.configureAwgAlice(mode, ec.randomNumbers1, delayAD)
    #         ec.configureAwgDavid(mode, ec.randomNumbers2)
    #     elif mode == 'BD':
    #         ec.configureAwgBob(mode, ec.randomNumbers1, delayBD=delayBD)
    #         ec.configureAwgDavid(mode, ec.randomNumbers2)

    def confingureSingleAWG(name, mode, delay=0.0):
        if len(mode) == 2:
            if name == "Alice": ec.configureAwgAlice(mode, randomNumbers=ec.randomNumbers1, delayAD=delay)
            if name == "Bob":  ec.configureAwgBob(mode, randomNumbers=ec.randomNumbers2 if mode == "AB" else ec.randomNumbers1, delayBD=delay)
            if name == "David": ec.configureAwgDavid(mode, randomNumbers=ec.randomNumbers2)
        if len(mode) == 3:
            if name == "Alice": ec.configureAwgAlice(mode, randomNumbers=ec.randomNumbers, delayAD=delay)
            if name == "Bob":  ec.configureAwgBob(mode, randomNumbers=ec.randomNumbers, delayBD=delay)
            if name == "David": ec.configureAwgDavid(mode, randomNumbers=ec.randomNumbers)


    def setRandomNumbers(mode):
        singleRnd = {'ABA': [int(i) for i in list(np.load(r"E:/MDIQKD_Parse/RNDs/randomNumbersABA.npy"))], 'ABB': [int(i) for i in list(np.load(r"E:/MDIQKD_Parse/RNDs/randomNumbersABB.npy"))],  # random numbers for alice-bob
                     'ADA': [int(i) for i in list(np.load(r"E:/MDIQKD_Parse/RNDs/randomNumbersADA.npy"))], 'ADD': [int(i) for i in list(np.load(r"E:/MDIQKD_Parse/RNDs/randomNumbersADD.npy"))],  # random numbers for alice-david
                     'BDB': [int(i) for i in list(np.load(r"E:/MDIQKD_Parse/RNDs/randomNumbersBDB.npy"))], 'BDD': [int(i) for i in list(np.load(r"E:/MDIQKD_Parse/RNDs/randomNumbersBDD.npy"))]}  # random numbers for bob-david
        rndMode = {'AB': [singleRnd['ABA'], singleRnd['ABB']], 'AD': [singleRnd['ADA'], singleRnd['ADD']], 'BD': [singleRnd['BDB'], singleRnd['BDD']]}

        # 设置首脉冲模式以及其他测试随机数
        N0 = 10000
        FPM = ([6] * N0 + [0] * (10000 - N0))[:10000]
        rnd1 = ([2] * N0 + [0] * (10000 - N0))[:10000]
        rnd2 = ([2, 3] * N0 + [0] * (10000 - N0))[:10000]
        # np.random.shuffle(rnd2)
        rndMode[mode] = [rnd1, rnd2]
        # rndMode[mode][0] = rnd1
        # rndMode[mode] = [FPM, FPM]
        # singleRnd[mode] = FPM

        if mode in ["ADA", 'ADD', 'ABA', 'ABB', 'BDB', 'BDD']:
            ec.randomNumbers = singleRnd[mode]
            # return ec.randomNumbers

        if mode in ['AB', 'AD', 'BD']:
            ec.randomNumbers1, ec.randomNumbers2 = rndMode[mode]
            # return (ec.randomNumbers1, ec.randomNumbers2)

        rB = np.array(singleRnd['BDB'])
        rD = np.array(singleRnd['BDD'])
        rs = np.vstack((rB, rD)).transpose()
        for rb in range(0, 8):
            for rd in range(0, 8):
                print('[{}, {}]: {}'.format(rb, rd, np.where(rs == [rb, rd])[0].shape[0]))


    mode = "BD"  # 设置模式，生成对应随机数
    setRandomNumbers(mode)  # 设置随机数
    # ec.chooseHOMparties(mode, False)
    # ec.setADCMonitorChannel(mode)
    #
    # # configureAWGs(mode,0.0,0.0)       #配置AWG
    # # confingureSingleAWG("Alice",mode=mode, delay=-6103.0)
    # confingureSingleAWG("Bob", mode=mode, delay=-8757.0)
    # confingureSingleAWG("David", mode=mode, delay=0.0)
    #
    # configureTDC(-4360.5, mode=mode, init=True, FPM=False)  # 配置TDC参数，通道0延时与是否初始化，重启TDCServer后需要初始化
    # setATT(6.0, 3.1, 4.65)  # 控制发射端的总发射光强
    # # ec.scanDelay("Bob")
    # # ec.time_sync_AD(0.1,0.3,0.2,3.0)
    # # ec.time_sync_AB(0.1,0.1,0.1,5.0)
    #
    # # setTimeAM_Alice(3.2, 7.0)
    # # setTimeAM_Bob(4.6, 6.0)
    # # ec.setDecoyVoltage("Alice",5.7)
    # # ec.setDecoyVoltage("David",1.8)     #for x basis
    # # ec.setDecoyVoltage("Bob",5.4)       #实验随机数
    # # ec.setDecoyVoltage("Bob",6.4)       #全2随机数
    # # ec.setDecoyVoltage("Bob",4.5)       #全6随机数
    # # setTimeAM_David(3.5, 1.1)
    # # time.sleep(5.0)
    # # ec.setDecoyVoltage("David",3.6)     #for AD
    # # ec.setDecoyVoltage("David",3.2)     #实验随机数
    # # ec.setDecoyVoltage("David",4.0)     #23交替随机数
    # # ec.setDecoyVoltage("David",3.6)     #45交替随机数
    # # ec.setDecoyVoltage("David",2.4)     #全6随机数
    # # ec.setDecoyVoltage("David",3.2)     #[2,3]*5000+[6,7]*5000随机数
    # ec.getVoltages("DC-MDI-David-Decoy")
    # print("Configuration Applied!")
    #
    # # ec.syncCharlieAlice(0.1,0.2,5.0)
    # # ec.syncCharlieBob(mode, 0.1,0.2,5.0)
    # # ec.syncCharlieDavid(0.0,0.1,5.0)
    # ec.time_sync_BD(0.0, 0.3, 0.2, 5.0)
    # time.sleep(1000000)
    print('DONE')
