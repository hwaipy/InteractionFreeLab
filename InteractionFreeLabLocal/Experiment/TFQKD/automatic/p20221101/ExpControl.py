import numpy as np
from worker_config import worker

tdc = worker.TFTDCServer


def showWaveform(waveforms, showRange=None):
    import matplotlib.pyplot as plt
    sampleCount = len(waveforms[0])
    times = np.linspace(0, 0.5 * (sampleCount - 1), sampleCount)

    fig, axs = plt.subplots(4, 1)
    fig.set_size_inches(18, 10)

    for i in range(len(waveforms)):
        axs[i].plot(times, waveforms[i])
        axs[i].grid()
        if showRange: axs[i].set_xlim(showRange[0], showRange[1])
    plt.show()


def testRandomNumbers1(seed=29, reversed=[1, 2]):
    from random import Random
    rnd = Random(seed)
    rndForAWG = []
    rndForTDC = []
    SignalForAWG = []
    SignalForTDC = []

    for i in range(10):
        rnsRef = [rnd.randint(0, 3) * 16 + 64 for i in range(140)]
        rndForAWG += rnsRef
        rndForTDC += rnsRef

        rnsGap = [rnd.randint(0, 63) for i in range(10)]
        rndForAWG += rnsGap
        rndForTDC += [r + 128 for r in rnsGap]

        rnsSignal = [rnd.randint(0, 63) for i in range(250)]
        # rnsSignal = [rnd.randint(0, 15) * 4 + 3 for i in range(250)]
        rnsSignalForAWG = [r for r in rnsSignal]
        rnsSignalForTDC = [r for r in rnsSignal]
        probability = 0.05
        for i in range(len(rnsSignal)):
            if rnsSignal[i] & 0b1000011 != 0b11: continue
            sending = rnd.random() < probability
            rnsSignalForTDC[i] &= 0b1000011
            if sending:
                rnsSignalForTDC[i] += 0b100
            else:
                rnsSignalForAWG[i] &= 0b1111100


        rndForAWG += rnsSignalForAWG
        rndForTDC += rnsSignalForTDC

        SignalForAWG += rnsSignalForAWG
        SignalForTDC += rnsSignalForTDC

    # 定义refrence反向
    rndForAWG = [refReverse(rns=rndForAWG[i]) if rndForAWG[i] >= 64 and (i % 4 in reversed) else rndForAWG[i] for i in range(len(rndForAWG))]

    return rndForAWG, rndForTDC, SignalForAWG, SignalForTDC


def refReverse(rns):
    phase = rns // 4
    state = (rns + 1) % 4
    rns = phase * 4 + state
    return rns


def testRandomNumbers2(seed=29):
    from random import Random
    rnd = Random(seed)
    rndForAWG = []
    rndForTDC = []

    for i in range(10):
        rnsRef = [rnd.randint(0, 3) * 16 + 64 for i in range(140)]
        rndForAWG += rnsRef
        rndForTDC += rnsRef

        rnsGap = [rnd.randint(0, 63) for i in range(10)]
        rndForAWG += rnsGap
        rndForTDC += [r + 128 for r in rnsGap]

        #         rnsSignal = [rnd.randint(0, 63) for i in range(250)]
        rnsSignal = [rnd.randint(0, 15) * 4 + 3 for i in range(250)]
        rnsSignalForAWG = [r for r in rnsSignal]
        rnsSignalForTDC = [r for r in rnsSignal]
        probability = 0.05
        for i in range(len(rnsSignal)):
            #             if rnsSignal[i]&0b11 != 0b11: continue
            #             sending = rnd.random() < probability
            #             if sending:
            if i % 4 == 2 or i % 4 == 3:
                rnsSignalForTDC[i] &= 0b1000011
                rnsSignalForTDC[i] += 0b100
            else:
                rnsSignalForAWG[i] &= 0b1111100
                rnsSignalForTDC[i] &= 0b1000011

        rndForAWG += rnsSignalForAWG
        rndForTDC += rnsSignalForTDC

    return rndForAWG, rndForTDC


def control_Alice(rnsForAWG=([1] * 1 + [1] * 9) * 400, rnsForTDC=([1] * 1 + [1] * 9) * 400, globalDelay=0.0, onoff=[1, 0, 1, 0], V=0):
    # Control: Alice

    # Encoder 的定义: AWG CH1 -> Reference AM; AWG CH2 -> Decoy & Z AM; AWG CH3 -> PM1; AWG CH4 -> PM2;
    encoder = worker.TF_AWGEncoder_Alice
    # globalDelay = -11223
    if not isinstance(rnsForAWG, str): globalDelay = globalDelay % (10 * len(rnsForAWG))
    encoder.configure('sampleRate', 2e9)  # 采样率  不动
    encoder.configure('waveformLength', None)
    encoder.configure('waveformUnitLength', 20)
    encoder.configure('randomNumbers', rnsForAWG)

    # encoder.configure('ampAM1', [0.46, 0.7, 0.79, 1] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.46] * 4 + [0.0])
    encoder.configure('ampAM1', [0.47, 0.592, 0.64, 0.70] + [1])  # 此处的小数是归一化数值
    encoder.configure('biasAM1', [0.47] * 4 + [0.0])
    # encoder.configure('ampAM2', [0.45, 0.6, 0.72, 1] + [1])
    # encoder.configure('biasAM2', [0.45] * 4 + [0.0])

    # encoder.configure('ampAM1', [0.46, 0.7, 0.6, 1] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.46] * 4 + [0.0])
    # encoder.configure('ampAM2', [0.45, 0.6, 0.6, 1] + [1])
    # encoder.configure('biasAM2', [0.45] * 4 + [0.0])

    encoder.configure('ampPM1', [(i / 16 * V) for i in range(16)])  # V=0.32 分通道通过率34.88%
    # encoder.configure('ampPM2', [(i / 16 * V) for i in range(16)])  # V=0.32
    encoder.configure('widthAM1', [1.2, 10])  # [signal, reference]
    # encoder.configure('widthAM2', [1.2, 4.9])
    encoder.configure('widthPM1', 10)
    # encoder.configure('widthPM2', 10)
    encoder.configure('delayAM1', globalDelay)
    # encoder.configure('delayAM2', globalDelay + 11)
    encoder.configure('delayPM1', globalDelay + 35)  # -56.5
    # encoder.configure('delayPM2', globalDelay + 42)
    encoder.configure('gainAM1', 1)
    encoder.configure('gainPM1', 1)

    # onoff = [1, 0, 0, 0]
    if onoff[0] == 0:
        encoder.configure('ampAM1', [0] * 5)
        encoder.configure('biasAM1', [0] * 5)
    if onoff[1] == 0:
        # encoder.configure('ampAM2', [0] * 5)
        # encoder.configure('biasAM2', [0] * 5)
        pass
    if onoff[2] == 0:
        encoder.configure('ampPM1', [0] * 16)
    if onoff[3] == 0:
        # encoder.configure('ampPM2', [0] * 16)
        pass

    waveforms = encoder.generateNewWaveform(returnWaveform=False)
    # showWaveform(waveforms, showRange=(30000, 33000))
    # awgA.turnOnAllChannels()
    # encoder.startAllChannels()

    tdc.configureAnalyser('TFQKDEncoding', {'RandomNumbers': rnsForAWG, 'SignalChannel': 2})  # 'SignalChannel':TDC通道号
    tdc.configureAnalyser('TFQKDSyncAlice', {'RandomNumbers': rnsForAWG, 'SignalChannel': 4})
    worker.TFTDCAdapter.configureAnalyser('TFQKDSyncAlice', {'RandomNumbers': rnsForAWG, 'SignalChannel': 4})
    tdc.configureAnalyser('QKDQBER', {'AliceRandomNumbers': rnsForTDC})


def control_Bob(rnsForAWG=([1] * 1 + [1] * 9) * 400, rnsForTDC=([1] * 1 + [1] * 9) * 400, globalDelay=0.0, onoff=[1, 0, 1, 0], V=0):
    # Bob的相关控制
    # Encoder 的定义: AWG CH1 -> Reference AM; AWG CH2 -> Decoy & Z AM; AWG CH3 -> PM1; AWG CH4 -> PM2;
    encoder = worker.TF_AWGEncoder_Bob

    # globalDelay = -2178.5
    if not isinstance(rnsForAWG, str): globalDelay = globalDelay % (10 * len(rnsForAWG))
    encoder.configure('sampleRate', 2e9)  # 采样率  不动
    encoder.configure('waveformLength', None)
    encoder.configure('waveformUnitLength', 20)
    encoder.configure('randomNumbers', rnsForAWG)  # rnsBobForAWG)

    # encoder.configure('ampAM1', [0.49, 0.68, 0.755, 0.87] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.49] * 4 + [0.0])
    encoder.configure('ampAM1', [0.49, 0.63, 0.68, 0.74] + [1])  # 此处的小数是归一化数值
    encoder.configure('biasAM1', [0.49] * 4 + [0.0])
    # encoder.configure('ampAM2', [0.47, 0.64, 0.8, 1] + [1])
    # encoder.configure('biasAM2', [0.47] * 4 + [0.0])

    # encoder.configure('ampAM1', [0.48, 0.7, 0.55, 1] + [1])  # 此处的小数是归一化数值
    # encoder.configure('biasAM1', [0.48] * 4 + [0.0])
    # encoder.configure('ampAM2', [0.47, 0.64, 0.6, 1] + [1])
    # encoder.configure('biasAM2', [0.47] * 4 + [0.0])

    encoder.configure('ampPM1', [(i / 16 * V) for i in range(16)])  # V=0.244
    # encoder.configure('ampPM2', [(i / 16 * V) for i in range(16)])  # V=0.244
    encoder.configure('widthAM1', [1.2, 10])  # [signal, reference]
    # encoder.configure('widthAM2', [1.2, 4.9])
    encoder.configure('widthPM1', 10)
    # encoder.configure('widthPM2', 10)
    encoder.configure('delayAM1', globalDelay)
    # encoder.configure('delayAM2', globalDelay)  # +16
    encoder.configure('delayPM1', globalDelay + 38.5)  # -56.5
    # encoder.configure('delayPM2', globalDelay + 38.5)
    encoder.configure('gainAM1', 1)
    encoder.configure('gainPM1', 1)

    # onoff = [1, 0, 0, 0]
    if onoff[0] == 0:
        encoder.configure('ampAM1', [0] * 5)
        encoder.configure('biasAM1', [0] * 5)
    if onoff[1] == 0:
        pass
        # encoder.configure('ampAM2', [0] * 5)
        # encoder.configure('biasAM2', [0] * 5)
    if onoff[2] == 0:
        encoder.configure('ampPM1', [0] * 16)
    if onoff[3] == 0:
        pass
        # encoder.configure('ampPM2', [0] * 16)

    waveforms = encoder.generateNewWaveform()
    # showWaveform(waveforms, showRange=(0, 4000))
    # awgB.turnOnAllChannels()
    # encoder.startAllChannels()

    tdc.configureAnalyser('TFQKDEncoding', {'RandomNumbers': rnsForAWG, 'SignalChannel': 3})  # 前八张小图显示的通道数据
    tdc.configureAnalyser('TFQKDSyncBob', {'RandomNumbers': rnsForAWG, 'SignalChannel': 5})  # 用于时钟同步的通道数据
    worker.TFTDCAdapter.configureAnalyser('TFQKDSyncBob', {'RandomNumbers': rnsForAWG, 'SignalChannel': 5})
    tdc.configureAnalyser('QKDQBER', {'BobRandomNumbers': rnsForTDC})


def run(VA, VB):
    rnsAliceForAWG, rnsAliceForTDC, SignalAliceForAWG, SignalAliceForTDC = testRandomNumbers1(100, [2, 3])
    rnsBobForAWG, rnsBobForTDC, SignaBobForAWG, SignalBobForTDC = testRandomNumbers1(89, [1, 2])  # [1, 2]
    # rnsAliceForAWG = [1] * 1 + [0] * int(2E7-1)
    # rnsAliceForTDC = rnsAliceForAWG

    # rnsAliceForAWG = ([1] * 1 + [1] * 1) * 2000
    # rnsAliceForAWG = ([33] * 1 + [1] * 15) * 250
    # rnsAliceForAWG = ([i * 4 + 1 for i in range(16)]) * 250

    # rnsBobForAWG = ([61] * 1 + [61] * 1) * 2000
    # rnsBobForAWG = ([1] * 1 + [1] * 1) * 2000
    # rnsBobForAWG = ([33] * 1 + [1] * 15) * 250
    # rnsBobForAWG = ([i * 4 + 1 for i in range(16)]) * 250

    if VA == 0:
        rnsAliceForAWG = ([1] * 1 + [1] * 1) * 2000
        rnsAliceForTDC = rnsAliceForAWG
        # rnsAliceForAWG = ([64, 64, 65, 65] * 35 + [3] * 260) * 10
    if VB == 0:
        rnsBobForAWG = ([1] * 1 + [0] * 1) * 2000

    globalDelayA = worker.TF_Registry.get('Runtime.Alice.Time.GlobalDelay')

    onoffA = [1, 0, 1, 0]
    # control_Alice(rnsForAWG=rnsAliceForAWG, rnsForTDC=rnsAliceForTDC, globalDelay=globalDelayA, onoff=onoffA, V=VA)
    globalDelayB = worker.TF_Registry.get('Runtime.Bob.Time.GlobalDelay')
    onoffB = [1, 0, 1, 0]
    control_Bob(rnsForAWG=rnsBobForAWG, rnsForTDC=rnsBobForTDC, globalDelay=globalDelayB, onoff=onoffB, V=VB)

    # tdc.configureAnalyser('TFQKDEncoding', {'RandomNumbers': rnsAliceForAWG, 'SignalChannel': 2})
    # tdc.configureAnalyser('TFQKDEncoding', {'RandomNumbers': rnsBobForAWG, 'SignalChannel': 3})
    #
    # TDC处理所需的配置信息
    tdc.turnOnAnalyser('DeltaMetaAnalyser', {'Channel1': 2, 'GroupBy': 250, 'Channel2': 3, 'SyncChannel': 0, 'Period': 10000, 'Center': 5000, 'GateWidth': 1200})


if __name__ == '__main__':
    run(VA=0, VB=0)
    # run(VA=0, VB=0)
    print('Done')