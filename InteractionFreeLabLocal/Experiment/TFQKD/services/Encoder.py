import math

class ModulatorConfig:
    def __init__(self, delay, waveformPeriodLength, waveformLength, sampleRate, randomNumberRange, waveformMod):
        self.delay = delay
        self.waveformPeriodLength = waveformPeriodLength
        self.waveformLength = waveformLength
        self.sampleRate = sampleRate
        self.randomNumberRange = randomNumberRange
        self.waveformMod = waveformMod

    def generateWaveform(self, randomNumbers):
        waveformPositions = [i * self.waveformPeriodLength for i in range(0, len(randomNumbers))]
        waveformPositionsInt = [math.floor(i) for i in waveformPositions + [self.waveformLength]]
        waveformLengthes = [waveformPositionsInt[i + 1] - waveformPositionsInt[i] for i in range(0, len(randomNumbers))]
        waveform = []
        waveformUnits = self.generateWaveformUnits()

        print(self.waveformLength)
        for i in range(0, len(randomNumbers)):
            rn = randomNumbers[i]
            length = waveformLengthes[i]
            waveform += waveformUnits[rn][:length]
            if len(waveform) >= self.waveformLength: break
        delaySample = -int(self.delay * (self.sampleRate / 1e9))
        waveform = waveform[delaySample:] + waveform[:delaySample]
        return waveform[:self.waveformLength]

    def generateWaveformUnits(self):
        waveforms = []
        for i in range(0, self.randomNumberRange):
            waveform = self._generateWaveformUnit(i)
            waveforms.append(waveform)
        return waveforms

    def _generateWaveformUnit(self, randomNumber):
        width, amp, bias = self.waveformMod(randomNumber)
        pulseSample = math.ceil((width) * 1e-9 * self.sampleRate)
        totalSample = math.ceil(self.waveformPeriodLength)
        leadingSample = math.ceil((self.waveformPeriodLength - pulseSample) / 2)
        a = [bias] * leadingSample + [amp] * pulseSample + [bias] * (totalSample - leadingSample - pulseSample)
        return a


class AWGEncoder:
    def __init__(self, asyncInvoker, channelMapping, randonNumberRange=128, phaseSlice=16):
        self.awg = asyncInvoker
        self.channelMapping = channelMapping
        self.randonNumberRange = randonNumberRange
        self.phaseSlice = phaseSlice
        self.config = {
            'sampleRate': 2e9,
            'randomNumbers': [i for i in range(randonNumberRange)],
            'waveformLength': randonNumberRange * 20,
            'ampAM1': [0.0, 0.1, 0.1, 0.1, 0.9],
            'ampAM2': [0.0, 0.1, 0.1, 0.1, 0.9],
            'ampPM1': [i / phaseSlice for i in range(phaseSlice)],
            'ampPM2': [i / phaseSlice for i in range(phaseSlice)],
            'biasAM1': [0.0] * 5,
            'biasAM2': [0.0] * 5,
            'biasPM1': [0.0] * phaseSlice,
            'biasPM2': [0.0] * phaseSlice,
            'widthAM1': [2.6, 5],
            'widthAM2': [2.6, 5],
            'widthPM1': 5,
            'widthPM2': 9.8,
            'delayAM1': 0,
            'delayAM2': 0,
            'delayPM1': 0,
            'delayPM2': 0,
        }

    def configure(self, key, value):
        if self.config.__contains__(key):
            self.config[key] = value
        else:
            raise RuntimeError('Bad configuration')

    def __modAM1(self, randomNumber):
        rRef = (randomNumber & 0b1000000) >> 6
        rDecoy = (randomNumber & 0b11)
        return self.config['widthAM1'][rRef], self.config['ampAM1'][4 if rRef == 1 else rDecoy], self.config['biasAM1'][4 if rRef == 1 else rDecoy]

    def __modAM2(self, randomNumber):
        rRef = (randomNumber & 0b1000000) >> 6
        rDecoy = (randomNumber & 0b11)
        return self.config['widthAM2'][rRef], self.config['ampAM2'][4 if rRef == 1 else rDecoy], self.config['biasAM2'][4 if rRef == 1 else rDecoy]

    def __modPM1(self, randomNumber):
        rPhase = (randomNumber & 0b111100) >> 2
        return self.config['widthPM1'], self.config['ampPM1'][rPhase], self.config['biasPM1'][rPhase]

    def __modPM2(self, randomNumber):
        rPhase = (randomNumber & 0b111100) >> 2
        return self.config['widthPM2'], self.config['ampPM2'][rPhase], self.config['biasPM2'][rPhase]

    def generateWaveforms(self):
        waveformPeriodLength = self.config['waveformLength'] / len(self.config['randomNumbers'])
        modulatorConfigs = {
            'AM1': ModulatorConfig(self.config['delayAM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modAM1),
            'AM2': ModulatorConfig(self.config['delayAM2'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modAM2),
            'PM1': ModulatorConfig(self.config['delayPM1'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modPM1),
            'PM2': ModulatorConfig(self.config['delayPM2'], waveformPeriodLength, self.config['waveformLength'], self.config['sampleRate'], self.randonNumberRange, self.__modPM2),
        }
        waveforms = {}
        for waveformName in modulatorConfigs.keys():
            config = modulatorConfigs.get(waveformName)
            waveform = config.generateWaveform(self.config['randomNumbers'])
            waveforms[waveformName] = waveform
        return waveforms

    async def generateNewWaveform(self, returnWaveform=False, writeAWG=True):
        try:
            if self.awg and writeAWG:
                await self.awg.turnOffAllChannels()
            waveforms = self.generateWaveforms()
            for waveformName in waveforms:
                waveform = waveforms[waveformName]
                channelIndex = self.channelMapping[waveformName]
                if self.awg and writeAWG: await self.awg.writeWaveform(channelIndex, [(d - 0.5) * 2 * 32765 for d in waveform])
            if returnWaveform:
                return waveforms
        except BaseException as e:
            import logging
            logging.exception(e)

    async def startAllChannels(self):
        await self.awg.turnOnAllChannels()

    async def stopAllChannels(self):
        await self.awg.turnOffAllChannels()

    async def startChannel(self, name):
        await self.__setChannelStatus(name, True)

    async def stopChannel(self, name):
        await self.__setChannelStatus(name, False)

    async def __setChannelStatus(self, name, on):
        if self.channelMapping.__contains__(name):
            v = self.channelMapping[name]
            if on:
                await self.awg.turnOn(v)
            else:
                await self.awg.turnOff(v)
        else:
            raise RuntimeError('Channel {} not exists.'.format(name))

# def showWaveform(waveforms, showRange=None):
#     import matplotlib.pyplot as plt
#     sampleCount = len(list(waveforms.values())[0])
#     times = np.linspace(0, 0.5 * (sampleCount - 1), sampleCount)
#
#     fig, axs = plt.subplots(4, 1)
#     fig.set_size_inches(18, 10)
#
#     for i in range(len(waveforms.keys())):
#         axs[i].plot(times, waveforms[list(waveforms.keys())[i]])
#         axs[i].grid()
#     plt.show()


if __name__ == '__main__':
    from interactionfreepy import IFWorker, IFLoop

    worker1 = IFWorker('tcp://192.168.25.5:224')
    worker1.bindService("TF_AWGEncoder_Alice", AWGEncoder(worker1.asyncInvoker("USTCAWG_Alice"), {'AM1': 1, 'AM2': 2, 'PM1': 3, 'PM2': 4}, randonNumberRange=256))
    worker2 = IFWorker('tcp://192.168.25.5:224')
    worker2.bindService("TF_AWGEncoder_Bob", AWGEncoder(worker2.asyncInvoker("USTCAWG_Bob"), {'AM1': 1, 'AM2': 2, 'PM1': 3, 'PM2': 4}, randonNumberRange=256))
    IFLoop.join()

    # from interactionfreepy import IFBroker
    # dev = AWGEncoder(None, {'AM1': 1, 'AM2': 2, 'PM1': 3, 'PM2': 4}, randonNumberRange=256)
    # broker = IFBroker('tcp://*:2224')
    # worker = IFWorker('tcp://localhost:2224', 'AWGEncoder', dev)
    # remoteDev = worker.AWGEncoder
    # # remoteDev = dev
    #
    # remoteDev.configure('sampleRate', 2e9)
    # remoteDev.configure('randomNumbers', [i for i in range(128)])
    # remoteDev.configure('waveformLength', 128 * 20)
    # remoteDev.configure('ampAM1', [0.5 + 0.1] * 4 + [0.9])
    # remoteDev.configure('biasAM1', [0.5] * 4 + [0.0])
    # remoteDev.configure('ampAM2', [0.3, 0.5, 0.7, 0.01, 0.3])
    # remoteDev.configure('ampsPM1', [i / 15 for i in range(16)])
    # remoteDev.configure('ampsPM2', [(15 - i) / 15 for i in range(16)])
    # remoteDev.configure('widthAM1', [1, 4.9])
    # remoteDev.configure('widthAM2', [7, 1])
    # remoteDev.configure('widthPM1', 5)
    # remoteDev.configure('widthPM2', 6)
    # # remoteDev.configure('delayAM1', 30)
    # # remoteDev.configure('delayAM2', 114)
    # # remoteDev.configure('delayPM1', 500)
    # # remoteDev.configure('delayPM2', -500)
    #
    # waveforms = remoteDev.generateNewWaveform(True)
    # showWaveform(waveforms)
