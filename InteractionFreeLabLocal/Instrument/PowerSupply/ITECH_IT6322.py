__author__ = 'Hwaipy'
__version__ = 'v1.0.20180618'

from Instrument.Instruments import DeviceException, VISAInstrument


class IT6322(VISAInstrument):
    manufacturer = 'ITECH Ltd.'
    model = 'IT6322'

    def __init__(self, resourceID):
        super().__init__(resourceID, 3)
        self.__remote()
        self.voltageSetpoints = [float(v.strip()) for v in self.scpi.APP.VOLT.query().split(',')]
        self.currentLimitSetpoints = [float(v.strip()) for v in self.scpi.APP.CURR.query().split(',')]
        self.outputStatuses = [int(v.strip()) > 0 for v in self.scpi.APP.OUT.query().split(',')]
        self.voltageRanges = [30, 30, 6]
        self.currentLimitRanges = [3, 3, 3]

    def __remote(self):
        return self.scpi.SYSTem.REMote.write()

    def __checkChannel(self, channel):
        if channel < 0 or channel >= self.channelCount:
            raise DeviceException("channel can only be a Int in [0, {})".format(self.channelCount))

    def isAvailable(self):
        return True

    def getChannelNumber(self):
        return self.channelCount

    def getVoltageRange(self, channel):
        self.__checkChannel(channel)
        return self.voltageRanges[channel]

    def getCurrentLimitRange(self, channel):
        self.__checkChannel(channel)
        return self.currentLimitRanges[channel]

    def __trimVoltage(self, channel, voltage):
        if voltage < 0:
            return 0
        if voltage > self.voltageRanges[channel]:
            return self.voltageRanges[channel]
        return voltage

    def setVoltage(self, channel, voltage):
        self.__checkChannel(channel)
        voltage = self.__trimVoltage(channel, voltage)
        self.voltageSetpoints[channel] = voltage
        self.scpi.INST.NSEL.write(channel + 1)
        self.scpi.VOLT.write('{}V'.format(voltage))

    def setVoltages(self, voltages):
        if len(voltages) is not self.channelCount:
            raise DeviceException('Length of voltages do not match the channel number.')
        voltages = [self.__trimVoltage(c, voltages[c]) for c in range(0, self.channelCount)]
        outputCodeString = ['{}'.format(v) for v in voltages]
        outputCode = ', '.join(outputCodeString)
        self.scpi.APP.VOLT.write(outputCode)
        self.voltageSetpoints = voltages

    def getVoltageSetPoint(self, channel):
        self.__checkChannel(channel)
        return self.voltageSetpoints[channel]

    def __trimCurrent(self, channel, current):
        if current < 0:
            return 0
        if current > self.currentLimitRanges[channel]:
            return self.currentLimitRanges[channel]
        return current

    def setCurrentLimit(self, channel, current):
        self.__checkChannel(channel)
        current = self.__trimCurrent(channel, current)
        self.currentLimitSetpoints[channel] = current
        self.scpi.INST.NSEL.write(channel + 1)
        self.scpi.CURR.write('{}A'.format(current))

    def setCurrents(self, currents):
        if len(currents) is not self.channelCount:
            raise DeviceException('Length of voltages do not match the channel number.')
        currents = [self.__trimCurrent(c, currents[c]) for c in range(0, self.channelCount)]
        outputCodeString = ['{}'.format(v) for v in currents]
        outputCode = ', '.join(outputCodeString)
        self.scpi.APP.CURR.write(outputCode)
        self.currentLimitSetpoints = currents

    def getCurrentLimitSetpoints(self, channel):
        self.__checkChannel(channel)
        return self.voltageSetpoints[channel]

    def setOutputStatus(self, channel, status):
        self.__checkChannel(channel)
        self.scpi.INST.NSEL.write(channel + 1)
        self.scpi.OUTP.write(1 if status else 0)

    def setOutputStatuses(self, outputStatuses):
        if len(outputStatuses) != self.getChannelNumber():
            raise DeviceException("statuses should have length of {}".format(self.getChannelNumber()))
        outputCodeString = ['{}'.format(1 if v else 0) for v in outputStatuses]
        outputCode = ', '.join(outputCodeString)
        self.scpi.APP.OUT.write(outputCode)
        self.outputStatuses = [True if v else False for v in outputStatuses]

    def getOutputStatuses(self):
        ss = self.scpi.APP.OUT.query()
        ss = [int(s) for s in ss.split(',')]
        return [True if v else False for v in ss]

    #
    # def __measure(self, channel):
    #     self.__checkChannel(channel)
    #     VSet = self.voltageSetpoints[channel]
    #     load = self.loads[channel]
    #     ILimit = self.currentLimits[channel]
    #     IExpect = VSet / load
    #     if IExpect <= ILimit:
    #         return [VSet, ILimit]
    #     else:
    #         return [ILimit * load, ILimit]
    #
    # def measureVoltage(self, channel):
    #     self.__checkChannel(channel)
    #     return self.__measure(channel)[0]
    #
    # def measureVoltages(self):
    #     return [self.measureVoltage(c) for c in range(0, self.getChannelNumber())]
    #
    # def measureCurrent(self, channel):
    #     self.__checkChannel(channel)
    #     return self.__measure(channel)[1]
    #
    # def measureCurrents(self):
    #     return [self.measureCurrent(c) for c in range(0, self.getChannelNumber())]

    def beeper(self):
        self.scpi.SYSTem.BEEPer.write()
        self.getIdentity()

    def getIdentity(self):
        idn = self.scpi._IDN.query()
        if idn is None:
            return [''] * 4
        if len(idn) == 0:
            return [''] * 4
        idns = idn.split(',')
        idns = [idn.strip(' ') for idn in idns]
        while len(idns) < 4:
            idns.append('')
        return idns[:4]

    def getVersion(self):
        return self.scpi.SYSTem.VERSion.query()

    def measureVoltages(self):
        voltageString = self.scpi.MEAS.VOLT.ALL.query().split(', ')
        voltages = [float(vs) for vs in voltageString]
        return voltages

    def measureCurrents(self):
        currentString = self.scpi.MEAS.CURR.ALL.query().split(', ')
        currents = [float(vs) for vs in currentString]
        return currents

    def getVoltageSetpoints(self):
        vs = self.scpi.APP.VOLT.query()
        vs = vs.split(', ')
        self.voltageSetpoints = [float(v) for v in vs]
        return self.voltageSetpoints

    def getCurrentLimits(self):
        cs = self.scpi.APP.CURR.query()
        cs = cs.split(', ')
        self.currentLimits = [float(v) for v in cs]
        return self.currentLimits

    def setCurrentLimit(self, channel, currentLimit):
        self.checkChannel(channel)
        currentLimits = self.currentLimits.copy()
        currentLimits[channel] = currentLimit
        self.setCurrentLimits(currentLimits)

    def reset(self):
        self.scpi._RST.write()


if __name__ == '__main__':
    # import pyvisa as visa
    # print(visa.ResourceManager().list_resources())

    import sys
    from interactionfreepy import IFWorker, IFLoop

    configStrings = sys.argv[1:]
    configs = []

    for configString in configStrings:
        configs.append(configString.split(','))

    for config in configs:
        ps = IT6322('{}::INSTR'.format(config[0].replace('COM', 'ASRL')))
        assert ps.getSerialNumber() == config[1]
        config.append(ps)

    for config in configs:
        IFWorker('tcp://192.168.25.5:224', config[2], config[-1])

    print('DC Drive Started!')

    IFLoop.join()
