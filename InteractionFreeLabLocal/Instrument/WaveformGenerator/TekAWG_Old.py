"""
import pyvisa as visa
import numpy as np
import enum
import time
import csv
import os


class Instrument:
    visa_resources = {'AWG70002A': 'GPIB8::1::INSTR'}

    def __init__(self, instr_name=""):
        self.instr_name = instr_name
        self.rm = visa.ResourceManager()
        self._inited = False
        if not instr_name in self.visa_resources:
            print("Open resource: No Resource Named:'", instr_name, "' Found")
            return
        self.instr_handle = self.rm.open_resource(self.visa_resources[instr_name])
        print("Open resource: Resource opened: ", self.instr_handle.query("*IDN?"))
        self._inited = True

    def __enter__(self):
        # we can initialize here, in #with
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        # if exc_tb is None:
        #    print '[Exit %s]: Exited without exception.' % self.tag
        # else:
        #    print '[Exit %s]: Exited with exception raised.' % self.tag
        #    return False   # 可以省略，缺省的None也是被看做是False

    def list_resource(self):
        resources = self.rm.list_resources()
        print("PyVISA have found the following resources:")
        for res in resources:
            print(res)

    def _is_valid(self):
        return self._inited

    def _query(self, msg):
        ans = ""
        if self._is_valid():
            try:
                ans = self.instr_handle.query(msg)
            except:
                ans = ""
        return ans

    def _query_ascii(self, msg):
        ''' Return List values queried'''
        if self._is_valid():
            return self.instr_handle.query_ascii_values(msg)
            # if we want numpy return, and hex format, with separater '$'
            # return self.instr_handle.query_ascii_values(msg, container=numpy.array, converter='x', separator='$')

    def _query_binary(self, msg, datatype='B'):
        ''' Return List values queried in binary'''
        if self._is_valid():
            return self.instr_handle.query_binary_values(msg, datatype)
            # if we have double 'd' in big endian:
            # return self.instr_handle.query_binary_values(msg, datatype='d', is_big_endian=True)

    def _write_ascii(self, msg, values):
        ''' write values (a list)'''
        if self._is_valid():
            self.instr_handle.write_ascii_values(msg, values)
            # if we want to convert to hex, and separate with '$'
            # default converter = 'f', separator = ','
            # self.instr_handle.write_ascii_values(msg, values, converter='x', separator='$')

    def _write_binary(self, msg, values, datatype='f', is_big_endian=False):
        ''' write values (a list)'''
        if self._is_valid():
            self.instr_handle.write_binary_values(msg, values, datatype, is_big_endian)
            # if we have double 'd' in big endian:
            # default converter = 'f', separator = ','
            # self.instr_handle.write_ascii_values(msg, values, datatype='d', is_big_endian=True)

    def _write_raw(self, msg):
        if self._is_valid():
            self.instr_handle.write(msg)

    def _read_raw(self):
        if self._is_valid():
            return self.instr_handle.read_raw()

    def close(self):
        if self._is_valid():
            print('Close Resource: ', self.instr_name)
            self.instr_handle.close()
        else:
            print('Close Resource: ', self.instr_name, '[Does not exist]')


class SCPI:
    def __init__(self, instrument):
        self.instrument = instrument
        self.query = self.instrument._query  # instr_handle.query
        self.write = self.instrument._write_raw  # instr_handle.write
        self.writeValue = self.instrument._write_binary  # instr_handle.write_binary_values
        self.queryValue = self.instrument._query_binary  # instr_handle.query_binary_values

    def __getattr__(self, item):
        return SCPI.Command(self, item)

    class Command:
        def __init__(self, scpi, cmd, parent=None):
            self.scpi = scpi
            self.parent = parent
            self.cmd = cmd
            # print(cmd, parent)
            if self.cmd[0] == '_':
                self.cmd = '*' + self.cmd[1:]
            if parent:
                self.fullCmd = parent.fullCmd + ":" + self.cmd
            else:
                self.fullCmd = self.cmd

        def query(self, *args):
            re = self.scpi.query(self.createCommand(True, [arg for arg in args]))
            if re is not None:
                if (len(re) > 0) and (re[-1] == '\n'):
                    re = re[:-1]
            return re

        def queryInt(self, *args):
            return int(self.query(*args))

        def queryString(self, *args):
            return self.query(*args)[1:-1]

        def write(self, *args):
            self.scpi.write(self.createCommand(False, [arg for arg in args]))

        def createCommand(self, isQuery, args=[]):
            cmd = self.fullCmd
            if isQuery:
                cmd += '?'
            if len(args) > 0:
                cmd += ' {}'.format(args[0])
                for i in range(1, len(args)):
                    cmd += ',{}'.format(args[i])
            return cmd

        def __getattr__(self, item):
            return SCPI.Command(self.scpi, item, self)

        def __str__(self):
            return '[SCPI]' + self.fullCmd

class AWG70002PM(AWG70002):
    ''' AWG70002A in Pulsed Mode'''

    def __init__(self):
        super(AWG70002PM, self).__init__("AWG70002A")
        self.clockRate = self._getIntClockRate()
        # self.maxSeqSteps = self._getMaxSequenceSteps()
        self._wfList = self._listWaveforms()
        self._idxseq = 1

    def _mkWaveformName(self, wfTime):
        return "wfPattern%03d" % (wfTime)

    def _mkMarkerName(self, mkTime, mkflag):
        return "mk%dPattern%03d" % (mkflag, mkTime)

    def writeWaveformPattern(self, wfHighBeg, wfHighWidth=200, wfLength=2400):  # name, data):
        ''' Generate the waveform with one pulse,
        starts at wfHighBeg, with wfHighWidth width,
        The total length is wfLength (points)
        '''
        name = self._mkWaveformName(wfHighBeg)
        data = [0] * wfLength
        wfHighBeg = wfHighBeg if wfHighBeg > 0 else 0
        wfHighEnd = wfHighBeg + wfHighWidth
        wfHighEnd = wfHighEnd if wfHighEnd < wfLength else wfLength
        data[wfHighBeg:wfHighEnd] = [1] * (wfHighEnd - wfHighBeg)

        self.writeWaveform(name, data)
        return name

    def writeMarkerPattern(self, mkHighBeg, mkFlag, mkHighWidth=200, mkLength=2400):
        name = self._mkMarkerName(mkHighBeg, mkFlag)
        marker = np.zeros([mkLength, 2], dtype='uint8')
        mkHighBeg = mkHighBeg if mkHighBeg > 0 else 0
        mkHighEnd = mkHighBeg + mkHighWidth
        mkHighEnd = mkHighEnd if mkHighEnd < mkLength else mkLength
        marker[int(mkHighBeg): int(mkHighEnd + 1), int(mkFlag - 1)] = 1
        self.writeMarker(name, marker)
        return name

    def setClock(self, rate=20E9):
        super(AWG70002PM, self).setClock(rate)
        self._waitCMD()
        self.clockRate = self._getIntClockRate()
        print("Set Clock Rate to %E" % self.clockRate)

    def isSeqEnd(self):
        return self._isSeqEnd()

    def isAWGready(self):
        return self._isAWGready()

    def isAWGend(self):
        return self._isAWGend()

    def getSysParams(self):
        params = {}
        params['sysClockRate'] = self.clockRate
        params['maxSequenceLength'] = self.maxSeqSteps
        return params

    def clearAll(self):
        self._deleteAllWaveforms()
        self._deleteAllSequence()
        self._wfList = []

    def AddWaveform(self, wfHighBeg, wfHighWidth=200, wfLength=2400):
        name = self._mkWaveformName(wfHighBeg)
        if name in self._wfList:
            return name  # do not need to add
        self.writeWaveformPattern(wfHighBeg, wfHighWidth, wfLength)
        self._wfList = self._listWaveforms()  # refresh list
        return name

    def AddMarker(self, mkHighBeg, mkFlag, mkHighWidth=200, mkLength=2400):
        name = self._mkMarkerName(mkHighBeg, mkFlag)
        if name in self._wfList:
            return name  # do not need to add
        self.writeMarkerPattern(mkHighBeg, mkFlag, mkHighWidth, mkLength)
        self._wfList = self._listWaveforms()  # refresh list
        return name

    def writePulseSequences(self, positions, waitMode=AWG70002.SequenceItem.TriggerMode.TriggerA):
        # Based on the WaveForm we generated, Here we generate the sequence
        # The input Sequences need to be in "ns??" units.
        if len(positions) > self.maxSeqSteps:
            raise Exception("Input Sequence too Large: ", positions,
                            ", Limit=", self.maxSeqSteps)
        seqlist = []
        self._wfList = self._listWaveforms()
        for wfBegPos in positions:
            wfname = self.AddWaveform(wfBegPos)
            seqlist.append(AWG70002.SequenceItem(wfname, waitMode))
        print(time.asctime() + " Seq pack OK.")
        seqname = "AutoWavSeq%d" % self._idxseq
        self.writeSequence(seqname, seqlist)
        print(time.asctime() + " Seq write OK.")
        self._assignSequence(1, seqname)
        self._idxseq += 1

    def writeMarkerSequences(self, positions, mkflag, waitMode=AWG70002.SequenceItem.TriggerMode.TriggerA):
        if len(positions) > self.maxSeqSteps:
            raise Exception("Input Sequence too Large: ", positions,
                            ", Limit=", self.maxSeqSteps)
        seqlist = []
        self._wfList = self._listWaveforms()
        for mkBegPos, mkchan in zip(positions, mkflag):
            mkname = self.AddMarker(mkBegPos, mkchan)
            seqlist.append(AWG70002.SequenceItem(mkname, waitMode))
        print(time.asctime() + " Seq pack OK.")
        seqname = "AutoMkSeq%d" % self._idxseq
        self.writeSequence(seqname, seqlist)
        print(time.asctime() + " Seq write OK.")
        self._assignSequence(1, seqname)
        self._idxseq += 1

    def GenerateSequenceCSV(self, positions, path='Seq.csv', waitMode=AWG70002.SequenceItem.TriggerMode.TriggerA):
        # You do not want to use this for large file, the loading is toooo slow.
        with open(path, 'w', newline='') as csvfile:
            scw = csv.writer(csvfile)
            seqname = "AutoSeq%d" % self._idxseq
            scw.writerow(['AWG Sequence Definition'])
            scw.writerow(['Sequence Name', seqname])
            scw.writerow(['Sample Rate', 1E10])
            scw.writerow(['Waveform Name Base', 'wfPattern'])
            scw.writerow('')
            scw.writerow(['Track', '1'])
            # scw.writerow('Wait','Repeat','Event Input','Event Jump to','Go To', 'Flags',
            #              'Waveform Name','Frequency','Length','Marker1','Marker2','Editor','Parameters')
            scw.writerow(['Wait', 'Waveform Name', 'Frequency', 'Length'])
            for wfBegPos in positions:
                wfname = self.AddWaveform(wfBegPos)
                scw.writerow(['TrigA', wfname, 1E10, '2400'])
"""

import pyvisa as visa
from Instrument.Instruments import VISAInstrument, DeviceException


class TekAWG(VISAInstrument):
    manufacturer = 'TEKTRONIX'
    model = 'Virtual'

    codeValueLow = 0
    codeValueHigh = 16383

    def __init__(self, resourceID):
        super().__init__(resourceID)

    def getWaveformListSize(self):
        return int(self.scpi.WLISt.SIZE.query())

    def getWaveformName(self, index):
        assert isinstance(index, int)
        return self.scpi.WLISt.NAME.query(index)[1:-1]

    def listWaveforms(self):
        size = self.getWaveformListSize()
        return [self.getWaveformName(i) for i in range(size)]

    def isWaveformExist(self, name):
        assert isinstance(name, str)
        return self.listWaveforms().__contains__(name)

    def createWaveform(self, name, length, awaitOperation=True):
        assert isinstance(name, str)
        assert isinstance(length, int)
        self.scpi.WLIST.WAVEFORM.NEW.write('"{}"'.format(name), length, 'INT')
        if awaitOperation:
            self.awaitOperation()

    def deleteWaveform(self, name, awaitOperation=True):
        assert isinstance(name, str)
        self.scpi.WLISt.WAVeform.DELete.write('"{}"'.format(name))
        if awaitOperation:
            self.awaitOperation()

    def writeWaveformData(self, name, data, start=0, awaitOperation=True):
        if max(data) > 1 or min(data) < -1:
            raise DeviceException('Data out of range.')
        a = (self.codeValueHigh - self.codeValueLow) / 2
        b = (self.codeValueHigh + self.codeValueLow) / 2
        lsbData = [int(a * d + b) for d in data]
        msg = 'WLISt:WAVeform:DATA "{}",{},{},'.format(name, start, len(lsbData))
        self.resource.write_binary_values(msg, lsbData, 'h', False)
        if awaitOperation:
            self.awaitOperation()

    def setVoltageAmpAndOffset(self, channel, amp, offset, awaitOperation=True):
        cmd = self.scpi.__getattr__('SOURCE{}'.format(channel)).VOLTAGE
        cmd.AMPLITUDE.write(amp)
        cmd.OFFSet.write(offset)
        if awaitOperation:
            self.awaitOperation()

    def setVoltageHighAndLow(self, channel, low, high, awaitOperation=True):
        cmd = self.scpi.__getattr__('SOURCE{}'.format(channel)).VOLTAGE
        cmd.HIGH.write(high)
        cmd.LOW.write(low)
        if awaitOperation:
            self.awaitOperation()

    def assignOutput(self, channel, waveform, awaitOperation=True):
        self.scpi.__getattr__('SOURCE{}'.format(channel)).WAVeform.write('"{}"'.format(waveform))
        if awaitOperation:
            self.awaitOperation()

    def turnOn(self, channel, awaitOperation=True):
        self.scpi.__getattr__('OUTP{}'.format(channel)).write('ON')
        if awaitOperation:
            self.awaitOperation()

    def turnOff(self, channel, awaitOperation=True):
        self.scpi.__getattr__('OUTPUT{}'.format(channel)).STATE.write('OFF')
        if awaitOperation:
            self.awaitOperation()

    def start(self, awaitOperation=True):
        self.scpi.AWGControl.RUN.IMMediate.write()
        if awaitOperation:
            self.awaitOperation()

    def stop(self, awaitOperation=True):
        self.scpi.AWGControl.STOP.IMMediate.write()
        if awaitOperation:
            self.awaitOperation()

class TekAWG5014C(TekAWG):
    model = 'AWG5014C'
    def __init__(self, resourceID):
        super().__init__(resourceID)

if __name__ == "__main__":
    # awg = TekAWG5014C('TCPIP::172.16.20.111::INSTR')
    awg = TekAWG5014C('TCPIP::172.16.60.158::INSTR')

    from IFWorker import IFWorker
    from IFCore import IFLoop
    IFWorker('tcp://localhost:224', 'EleAWG', awg, ['TekAWG'])
    IFLoop.join()

    # import time
    # awg.deleteWaveform('TestWave')
    # awg.createWaveform('TestWave', 10)
    # import math
    # data = [math.sin(x/10*2*math.pi) for x in range(10)]
    # awg.writeWaveformData('TestWave', data)
    # awg.setVoltageAmpAndOffset(1, 0.5, 0.25)
    # awg.setVoltageHighAndLow(1, -2, 0)
    # awg.assignOutput(1, 'TestWave')
    # awg.turnOn(1)
    # awg.start()
