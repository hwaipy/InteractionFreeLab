__author__ = 'Hwaipy'

from Instrument.Instruments import DeviceException, VISAInstrument
import enum
import numpy as np


class KeySight_MultiMeter_34465A(VISAInstrument):
    manufacturer = 'Keysight Technologies'
    model = '34465A'

    def __init__(self, resourceID):
        super().__init__(resourceID)

    def setMeasureQuantity(self, mq, range=0, autoRange=True, aperture=0.001):
        if mq is MeasureQuantity.VoltageDC:
            self.scpi.CONF.VOLT.DC.write('AUTO' if autoRange else range)
            self.scpi.VOLT.APER.write(aperture)
        elif mq is MeasureQuantity.CurrentDC:
            self.scpi.CONF.CURR.DC.write('AUTO' if autoRange else range)
            self.scpi.CURR.APER.write(aperture)
        elif mq is MeasureQuantity.Resistance:
            self.scpi.CONF.RES.write('AUTO' if autoRange else range)
            self.scpi.RES.APER.write(aperture)
        else:
            raise DeviceException('MeasureQuantity {} can not be recognized.'.format(mq))

    def directMeasure(self, count=1):
        self.scpi.TRIG.SOURCE.write('BUS')
        self.scpi.SAMP.COUN.write(count)
        self.scpi.INIT.write()
        self.scpi._TRG.write()
        values = self.scpi.FETC.query()
        return [float(v) for v in values.split(',')]

    def directMeasureAndFetchLater(self, count=1):
        self.scpi.TRIG.SOURCE.write('BUS')
        self.scpi.SAMP.COUN.write(count)
        self.scpi.INIT.write()
        self.scpi._TRG.write()

        def fetch():
            values = self.scpi.FETC.query()
            return [float(v) for v in values.split(',')]

        return fetch


class KeySight_MultiMeter_34470A(KeySight_MultiMeter_34465A):
    manufacturer = 'Keysight Technologies'
    model = '34470A'

    def __init__(self, resourceID):
        super().__init__(resourceID)


class MeasureQuantity(enum.Enum):
    VoltageDC = 1
    CurrentDC = 2
    Resistance = 3


class MultiMeterServiceWrap:
    def __init__(self, dev):
        self.dev = dev

    def setDCVoltageMeasurement(self, range=0, autoRange=True, aperture=0.001):
        self.dev.setMeasureQuantity(MeasureQuantity.VoltageDC, range, autoRange, aperture)

    def setDCCurrentMeasurement(self, range=0, autoRange=True, aperture=0.001):
        self.dev.setMeasureQuantity(MeasureQuantity.CurrentDC, range, autoRange, aperture)

    def setResistanceMeasurement(self, range=0, autoRange=True, aperture=0.001):
        self.dev.setMeasureQuantity(MeasureQuantity.Resistance, range, autoRange, aperture)

    def directMeasure(self, count=1):
        return self.dev.directMeasure(count)

    def directMeasureAndFetchLater(self, count=1):
        return self.dev.directMeasureAndFetchLater(count)


if __name__ == '__main__':
    import pyvisa as visa

    print(visa.ResourceManager().list_resources())
    visaResource = 'TCPIP0::192.168.25.110::inst0::INSTR'
    dev = KeySight_MultiMeter_34465A(visaResource)

    wrap = MultiMeterServiceWrap(dev)
    wrap.setDCCurrentMeasurement(2, True, 0.005)
    while True:
        r = wrap.directMeasure(200)
        npr = np.array(r)

        print('{}, {}'.format(np.average(npr), np.std(npr)))
