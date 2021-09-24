# Control USTC AWGs
import math
import numpy as np

class ModulatorConfig:
    def __init__(self, duty, delay, diff, waveformPeriodLength, waveformLength, sampleRate, randomNumberRange, ampMod):
        self.duty = duty
        self.delay = delay
        self.diff = diff
        self.waveformPeriodLength = waveformPeriodLength
        self.waveformLength = waveformLength
        self.ampMod = ampMod
        self.sampleRate = sampleRate
        self.randomNumberRange = randomNumberRange

    def generateWaveform(self, randomNumbers, firstPulseMode):
        waveformPositions = [i * self.waveformPeriodLength for i in range(0, len(randomNumbers))]
        waveformPositionsInt = [math.floor(i) for i in waveformPositions + [self.waveformLength]]
        waveformLengthes = [waveformPositionsInt[i + 1] - waveformPositionsInt[i] for i in range(0, len(randomNumbers))]
        waveform = []
        waveformUnits = self.generateWaveformUnits()
        for i in range(0, len(randomNumbers)):
            rn = randomNumbers[i]
            length = waveformLengthes[i]
            if firstPulseMode and i > 0:
                waveform += [0] * length
            else:
                waveform += waveformUnits[rn][:length]
            if len(waveform) >= self.waveformLength: break
        delaySample = -int(self.delay * (self.sampleRate/1e9))
        waveform = waveform[delaySample:] + waveform[:delaySample]
        return waveform[:self.waveformLength]

    def generateWaveformUnits(self):
        waveforms = []
        for i in range(0, self.randomNumberRange):
            waveform = self._generateWaveformUnit(i)
            waveforms.append(waveform)
        return waveforms

    def _generateWaveformUnit(self, randomNumber):
        waveform = []
        for i in range(0, math.ceil(self.waveformPeriodLength)):
            position = i * 1.0 / self.waveformPeriodLength
            if (position <= self.duty):
                pulseIndex = 0
            elif (position >= self.diff and position <= (self.diff + self.duty)):
                pulseIndex = 1
            else:
                pulseIndex = -1
            amp = self.ampMod(pulseIndex, randomNumber)
            waveform.append(amp)
        return waveform


class AWGEncoder:
    def __init__(self, worker, awgName, channelMapping):
        self.worker = worker
        self.awgName = awgName
        self.awg = self.worker.asyncInvoker(awgName)
        self.sampleRate = 2e9
        self.waveformLength = 10 * 10 * 25
        self.randomNumbers = [0] * 10
        self.phaseRandomNumbers = [0] * 10
        self.phaseRandomizationSlice = 32
        self.firstPulseMode = False
        self.specifiedRandomNumber = -1
        self.ampDecoyZ = 1
        self.ampDecoyX = 0.4
        self.ampDecoyY = 0.8
        self.ampDecoyO = 0
        self.ampTime = 1
        self.ampPM = 0.7
        self.ampPR = 0.7
        self.pulseWidthDecoy = 1.99
        self.pulseWidthTime0 = 1.9
        self.pulseWidthTime1 = 1.9
        self.pulseWidthPM = 2
        self.pulseWidthPR = 4
        self.pulseDiff = 3
        self.delayDecoy = 0
        self.delayTime1 = 0
        self.delayTime2 = 0
        self.delayPM = 0
        self.delayPR = 0
        self.channelMapping = channelMapping

    def setRandomNumbers(self, rns):
        self.randomNumbers = rns

    def setPhaseRandomNumbers(self, rns):
        self.phaseRandomNumbers = rns

    def configure(self, key, value):
        if 'waveformLength'.__eq__(key):
            self.waveformLength = value
        elif 'delayDecoy'.__eq__(key):
            self.delayDecoy = value
        elif 'delayPM'.__eq__(key):
            self.delayPM = value
        elif 'delayPR'.__eq__(key):
            self.delayPR = value
        elif 'delayTime0'.__eq__(key):
            self.delayTime1 = value
        elif 'delayTime1'.__eq__(key):
            self.delayTime2 = value
        elif 'pulseWidthDecoy'.__eq__(key):
            self.pulseWidthDecoy = value
        elif 'pulseWidthTime0'.__eq__(key):
            self.pulseWidthTime0 = value
        elif 'pulseWidthTime1'.__eq__(key):
            self.pulseWidthTime1 = value
        elif 'pulseWidthPM'.__eq__(key):
            self.pulseWidthPM = value
        elif 'pulseWidthPR'.__eq__(key):
            self.pulseWidthPR = value
        elif 'pulseDiff'.__eq__(key):
            self.pulseDiff = value
        elif 'ampDecoyZ'.__eq__(key):
            self.ampDecoyZ = value
        elif 'ampDecoyX'.__eq__(key):
            self.ampDecoyX = value
        elif 'ampDecoyY'.__eq__(key):
            self.ampDecoyY = value
        elif 'ampDecoyO'.__eq__(key):
            self.ampDecoyO = value
        elif 'ampTime'.__eq__(key):
            self.ampTime = value
        elif 'ampPM'.__eq__(key):
            self.ampPM = value
        elif 'ampPR'.__eq__(key):
            self.ampPR = value
        elif 'phaseRandomizationSlice'.__eq__(key):
            self.phaseRandomizationSlice = value
        elif 'firstLaserPulseMode'.__eq__(key):
            self.firstPulseMode = value
        elif 'specifiedRandomNumber'.__eq__(key):
            self.specifiedRandomNumber = value
        else:
            raise RuntimeError('Bad configuration')

    def __ampModDecoy(self, pulseIndex, randomNumber):
        if pulseIndex >= 0:
            if randomNumber + pulseIndex != 7:
                return [self.ampDecoyO, self.ampDecoyX, self.ampDecoyY, self.ampDecoyZ][int(randomNumber / 2)]
        return 0

    def __ampModTime1(self, pulseIndex, randomNumber):  # decoy=0->vacuum->high level->pass
        if pulseIndex == -1: return 0
        decoy = int(randomNumber / 2)
        if decoy == 0:
            return 0
        elif decoy == 1 or decoy == 2:
            return 1
        else:
            return (pulseIndex == randomNumber % 2) * self.ampTime

    def __ampModTime2(self, pulseIndex, randomNumber):
        if pulseIndex == -1: return 0
        decoy = int(randomNumber / 2)
        if decoy == 0:
            return 1
        elif decoy == 1 or decoy == 2:
            return 0
        else:
            return (pulseIndex != randomNumber % 2) * self.ampTime

    def __ampModPhase(self, pulseIndex, randomNumber):
        if pulseIndex == -1:
            return 0
        else:
            return ((pulseIndex == 0) and (randomNumber % 2 == 1)) * self.ampPM
            # encode = randomNumber % 2
            # return 0.5 + self.ampPM / 2 * math.pow(-1, pulseIndex + encode)

    def __ampModPR(self, pulseIndex, randomNumber):
        return randomNumber / self.phaseRandomizationSlice * self.ampPR

    # Defination of Random Number:
    # parameter ``randomNumbers'' should be a list of RN
    # RN is an integer.
    # RN/2 can be one of {0, 1, 2, 3}, stands for O, X, Y ,Z
    # RN%2 represent for encoding (0, 1)
    def generateWaveforms(self):
        waveformPeriodLength = self.waveformLength / len(self.randomNumbers)
        waveformPeriod = waveformPeriodLength * 1e9 / self.sampleRate
        modulatorConfigs = {
            'AMDecoy': ModulatorConfig(self.pulseWidthDecoy / waveformPeriod, self.delayDecoy,
                                       self.pulseDiff / waveformPeriod, waveformPeriodLength,
                                       self.waveformLength, self.sampleRate, 8, self.__ampModDecoy),
            'AMTime1': ModulatorConfig(self.pulseWidthTime0 / waveformPeriod, self.delayTime1,
                                       self.pulseDiff / waveformPeriod, waveformPeriodLength,
                                       self.waveformLength, self.sampleRate, 8, self.__ampModTime1),
            'AMTime2': ModulatorConfig(self.pulseWidthTime1 / waveformPeriod, self.delayTime2,
                                       self.pulseDiff / waveformPeriod, waveformPeriodLength,
                                       self.waveformLength, self.sampleRate, 8, self.__ampModTime1),
            'PM': ModulatorConfig(self.pulseWidthPM / waveformPeriod, self.delayPM,
                                  self.pulseDiff / waveformPeriod, waveformPeriodLength, self.waveformLength,
                                  self.sampleRate, 8, self.__ampModPhase),
            'PR': ModulatorConfig(self.pulseWidthPR / waveformPeriod, self.delayPR,
                                  self.pulseDiff / waveformPeriod, waveformPeriodLength, self.waveformLength,
                                  self.sampleRate, self.phaseRandomizationSlice, self.__ampModPR)
        }
        waveforms = {}
        for waveformName in modulatorConfigs.keys():
            config = modulatorConfigs.get(waveformName)
            waveform = config.generateWaveform(self.randomNumbers if waveformName != 'PR' else self.phaseRandomNumbers, self.firstPulseMode)
            waveforms[waveformName] = waveform
        return waveforms

    async def generateNewWaveform(self, returnWaveform=False):
        await self.awg.turnOffAllChannels()
        waveforms = self.generateWaveforms()
        for waveformName in waveforms:
            waveform = waveforms[waveformName]
            channelIndex = self.channelMapping[waveformName]
            await self.awg.writeWaveform(channelIndex, waveform)
        if returnWaveform:
            return waveforms

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

    async def startTrigger(self):
        await self.awg.sendTrigger(0, 1e-3, 60000, 1e-3, 60000)
        print('Trigger started.')

    # old
    # async def generateNewWaveform(self, returnWaveform=False):
    #     for awg in self.awgs:
    #         await awg.beginSession()
    #         await awg.turnOffAllChannels()
    #     waveforms = self.generateWaveforms()
    #     for waveformName in waveforms:
    #         waveform = waveforms[waveformName]
    #         channelIndex = self.channelMapping[waveformName]
    #         await self.awgs[channelIndex[0]].writeWaveform(channelIndex[1], [(2 * v - 1) * 32765 for v in waveform])
    #     for awg in self.awgs:
    #         await awg.endSession()
    #     if returnWaveform:
    #         return waveforms
    #
    # async def startPlay(self):
    #     for awg in self.awgs:
    #         await awg.beginSession()
    #     for key in self.channelMapping:
    #         v = self.channelMapping[key]
    #         await self.awgs[v[0]].turnOn(v[1])
    #     for awg in self.awgs:
    #         await awg.endSession()
    #
    # async def startChannel(self, name):
    #     await self.__setChannelStatus(name, True)
    #
    # async def stopChannel(self, name):
    #     await self.__setChannelStatus(name, False)
    #
    # async def __setChannelStatus(self, name, on):
    #     if self.channelMapping.__contains__(name):
    #         v = self.channelMapping[name]
    #         await self.awgs[v[0]].beginSession()
    #         if on:
    #             await self.awgs[v[0]].turnOn(v[1])
    #         else:
    #             await self.awgs[v[0]].turnOff(v[1])
    #         await self.awgs[v[0]].endSession()
    #     else:
    #         raise RuntimeError('Channel {} not exists.'.format(name))
    #
    # async def startTrigger(self):
    #     awg = self.awgs[0]
    #     await awg.beginSession()
    #     await awg.sendTrigger(1e-3, 60000, 1e-3, 60000)
    #     await awg.endSession()
    #     print('Trigger started.')

if __name__ == '__main__':
    from interactionfreepy import IFWorker
    from interactionfreepy import IFLoop

    workerAlice = IFWorker('tcp://172.16.60.199:224')
    workerBob = IFWorker('tcp://172.16.60.199:224')

    devAlice = AWGEncoder(workerAlice, '_USTCAWG_Alice', {'AMDecoy': 2, 'AMTime1': 4, 'AMTime2': 6, 'PM': 1, 'PR': 0})
    # devBob = AWGEncoder(workerBob, 'USTCAWG_Bob', {'AMDecoy': 2, 'AMTime1': 4, 'AMTime2': 6, 'PM': 1, 'PR': 0})
    # workerAlice.bindService('MDIQKD_AWGEncoder_Alice_', devAlice)
    # workerBob.bindService('MDIQKD_AWGEncoder_Bob', devBob)

    import asyncio
    asyncio.get_event_loop().run_until_complete(devAlice.generateNewWaveform())
    print('done')

    # try:
    #     # randomNumbersAlice = [0, 1, 2, 3, 4, 5, 6, 7]
    #     # devBob.configure('firstLaserPulseMode', False)
    #     # devBob.configure('waveformLength', len(randomNumbersAlice) * 8)
    #     # devBob.configure('pulseWidthDecoy', 0.9)
    #     # devBob.configure('pulseWidthTime0', 1.9)
    #     # devBob.configure('pulseWidthTime1', 1.9)
    #     # devBob.configure('pulseWidthPM', 1.9)
    #     # devBob.configure('pulseDiff', 1.9)
    #     # devBob.configure('ampDecoyZ', 1)
    #     # devBob.configure('ampDecoyX', 0.4)
    #     # devBob.configure('ampDecoyY', 0.8)
    #     # devBob.configure('ampDecoyO', 0)
    #     # devBob.configure('ampTime', 1)
    #     # devBob.configure('ampPM', 1)
    #     # # dev.configure('ampPR', 1)
    #     # devBob.configure('delayDecoy', 0)
    #     # devBob.configure('delayTime0', 0)
    #     # devBob.configure('delayTime1', 0)
    #     # devBob.configure('delayPM', 0)
    #     # devBob.configure('delayPR', 0)
    #     # devBob.setRandomNumbers(randomNumbersAlice)
    #     # devBob.startPlay()
    #     from tornado.ioloop import IOLoop
    #     IOLoop.current().add_callback(devAlice.startTrigger)
    #     IOLoop.current().add_callback(devBob.startTrigger)
    #     IFLoop.join()
    # finally:
    #     workerAlice.close()
    #     workerBob.close()
