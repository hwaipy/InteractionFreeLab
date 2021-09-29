from Instrument.Instruments import DeviceException, VISAInstrument

class RTE(VISAInstrument):
    manufacturer = 'Rohde&Schwarz'
    model = 'RTE'

    def __init__(self, resourceID):
        super().__init__(resourceID, 4)

    def setVoltageOffset(self, channel, offset, awaitOperator=True):
        self.scpi.__getattr__('CHANnel{}'.format(channel)).OFFSet.write(offset)
        if awaitOperator:
            self.awaitOperation()

    def setVoltageRange(self, channel, range, awaitOperator=True):
        self.scpi.__getattr__('CHANnel{}'.format(channel)).RANGe.write(range)
        if awaitOperator:
            self.awaitOperation()

    def setVoltageLowAndHigh(self, channel, low, high, awaitOperator=True):
        self.setVoltageRange(channel, high - low, False)
        self.setVoltageOffset(channel, (high + low)/2, awaitOperator)

    def setVoltageRangeAndOffset(self, channel, range, offset, awaitOperator=True):
        self.setVoltageRange(channel, range, False)
        self.setVoltageOffset(channel, offset, awaitOperator)

    def setTimeOffset(self, offset, awaitOperator=True):
        self.scpi.TIMebase.HORizontal.POSition.write(offset)
        if awaitOperator:
            self.awaitOperation()

    def setTimeRange(self, range, awaitOperator=True):
        self.scpi.TIMebase.RANGe.write(range)
        if awaitOperator:
            self.awaitOperation()

    def setTimeStartAndStop(self, start, stop, awaitOperator=True):
        self.setTimeRange(stop - start, False)
        self.setTimeOffset((stop + start)/2, awaitOperator)

    def setTimeRangeAndOffset(self, range, offset, awaitOperator=True):
        self.setTimeRange(range, False)
        self.setTimeOffset(offset, awaitOperator)

    def turnOn(self, channel, awaitOperator=True):
        self.scpi.__getattr__('CHAN{}'.format(channel)).STAT.write('ON')
        if awaitOperator:
            self.awaitOperation()

    def turnOff(self, channel, awaitOperator=True):
        self.scpi.__getattr__('CHAN{}'.format(channel)).STAT.write('OFF')
        if awaitOperator:
            self.awaitOperation()

    def setCoupling(self, channel, coupling, awaitOperator=True):
        raise BaseException('Not Implemented.')

    def setTriggerMode(self, triggerMode, awaitOperator=True):
        raise BaseException('Not Implemented.')

    def setTriggerSource(self, triggerSource, awaitOperator=True):
        raise BaseException('Not Implemented.')

    def setTriggerCriteria(self, *args, awaitOperator=True):
        raise BaseException('Not Implemented.')

    def setAcquireLength(self, length, awaitOperator=True):
        raise BaseException('Not Implemented.')

    def setDataFormat(self, format, awaitOperator=True):
        self.scpi.FORMat.DATA.write('REAL', 32)
        if awaitOperator:
            self.awaitOperation()

    def single(self, awaitOperator=True):
        self.scpi.SINGLE.write()
        if awaitOperator:
            self.awaitOperation()

    def getWaveform(self, channel):
        raise BaseException('Not Implemented.')

    # def single(self, sampleCount, channels, awaitOperator=True):
    #     # self.scpi.ACQuire.POINts.AUTO.write('RECLength')
    #     self.scpi.ACQuire.POINts.write(sampleCount)
    #     self._awaitOperation()
    #     unitCount = 500
    #     waveforms = []
    #     for channel in channels:
    #         p1 = 0
    #         p2 = min(p1 + unitCount, sampleCount)
    #         w = []
    #         while p1 < p2:
    #             w += self.scpi.__getattr__('CHANnel{}'.format(channel)).DATA.queryBinary(p1, p2 - p1)
    #             p1 = p2
    #             p2 = min(p1 + unitCount, sampleCount)
    #         waveforms.append(w)
    #     return waveforms

class RTB2004(RTE):
    manufacturer = 'Rohde&Schwarz'
    model = 'RTB2004'

    def __init__(self, resourceID):
        super().__init__(resourceID)

    def setTimeOffset(self, offset, awaitOperator=True):
        self.scpi.TIMebase.POSition.write(offset)
        if awaitOperator:
            self.awaitOperation()

    def setTimeRange(self, range, awaitOperator=True):
        self.scpi.TIMebase.ACQTime.write(range)
        if awaitOperator:
            self.awaitOperation()

    def setCoupling(self, channel, coupling, awaitOperator=True):
        cmd = self.scpi.__getattr__('CHAN{}'.format(channel)).COUPling
        if coupling == 'DC':
            cmd.write('DCLimit')
        elif coupling == 'AC':
            cmd.write('ACLimit')
        elif coupling == 'GND':
            cmd.write('GND')
        else:
            raise DeviceException('Invalid coupling:｛｝'.format(coupling))
        if awaitOperator:
            self.awaitOperation()

    def setTriggerMode(self, triggerMode, awaitOperator=True):
        cmd = self.scpi.TRIGger.A.MODE
        if triggerMode == 'AUTO':
            cmd.write('AUTO')
        elif triggerMode == 'NORMAL':
            cmd.write('NORM')
        else:
            raise DeviceException('Invalid triggerMode:｛｝'.format(triggerMode))
        if awaitOperator:
            self.awaitOperation()

    def setTriggerSource(self, triggerSource, awaitOperator=True):
        cmd = self.scpi.TRIGger.A.SOURce
        if triggerSource == 'MANUAL':
            cmd.write('EXTernanalog')
            return
        if isinstance(triggerSource, int) and triggerSource >=1 and triggerSource <= self.channelCount:
            cmd.write('CH{}'.format(triggerSource))
            return
        if triggerSource.startswith('CH'):
            try:
                ch = int(triggerSource[2:])
                if ch >= 1 and ch <= self.channelCount:
                    cmd.write('CH{}'.format(ch))
                    return
            except:
                pass
        raise DeviceException('Invalid triggerSource: {}'.format(triggerSource))
        if awaitOperator:
            self.awaitOperation()

    def setTriggerCriteria(self, *args, awaitOperator=True):
        triggerType = args[0]
        if triggerType == 'RAISE':
            self.scpi.TRIGger.A.TYPE.write('EDGE')
            self.scpi.TRIGger.A.EDGE.SLOPe.write('POS')
            self.scpi.TRIGger.A.LEVel.write(args[1])
        elif triggerType == 'FALL':
            self.scpi.TRIGger.A.TYPE.write('EDGE')
            self.scpi.TRIGger.A.EDGE.SLOPe.write('NEG')
            self.scpi.TRIGger.A.LEVel.write(args[1])
        else:
            raise DeviceException('Invalid triggerType:｛｝'.format(args))
        if awaitOperator:
            self.awaitOperation()

    def setAcquireLength(self, length='AUTO', awaitOperator=True):
        if length == 'AUTO':
            self.scpi.ACQuire.POINts.AUTomatic.write('ON')
        else:
            raise DeviceException('Invalid length:｛｝'.format(length))
        if awaitOperator:
            self.awaitOperation()

    def setDataFormat(self, format, awaitOperator=True):
        if format == 'REAL':
            self.scpi.FORMat.write('REAL')
            self.scpi.FORMat.BORDer.write('LSBF')
        else:
            raise DeviceException('Invalid Format:｛｝'.format(format))
        if awaitOperator:
            self.awaitOperation()

    def getWaveform(self, channel):
        heads = self.scpi.__getattr__('CHANnel{}'.format(channel)).DATA.HEADer.query().split(',')
        start = float(heads[0])
        stop = float(heads[1])
        length = int(heads[2])
        data = self.scpi.__getattr__('CHANnel{}'.format(channel)).DATA.queryBinary()
        return start, stop, length, data

if __name__ == '__main__':
    resource = 'TCPIP0::172.16.20.71::inst0::INSTR'
    rte = RTB2004(resource)
    # resource = 'TCPIP0::192.168.25.111::inst0::INSTR'
    # rte = RTE(resource)

    from IFWorker import IFWorker
    from IFCore import IFLoop
    IFWorker('tcp://localhost:224', 'EleOsc', rte, ['TekAWG'])
    IFLoop.join()

    # rte.setAcquireLength('AUTO')
    # rte.setDataFormat('REAL')
    # rte.turnOn(1, False)
    # [rte.turnOff(i, False) for i in range(2, 5)]
    # rte.setCoupling(1, 'DC')
    # rte.setVoltageLowAndHigh(1, -0.1, 0.6, False)
    # rte.setTimeRangeAndOffset(1e-6, 0, False)
    # rte.setTriggerMode('NORMAL', False)
    # rte.setTriggerSource('CH1', False)
    # rte.setTriggerCriteria('RAISE', 0.2, False)
    # rte.single()
    # print(rte.getWaveform(1))
    #
    # import time
    # time.sleep(1)
