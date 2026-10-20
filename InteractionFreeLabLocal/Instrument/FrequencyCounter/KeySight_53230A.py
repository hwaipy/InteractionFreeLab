__author__ = 'Hwaipy'

from Instrument.Instruments import DeviceException, VISAInstrument

class KeySight_53230A(VISAInstrument):
    manufacturer = 'Agilent Technologies'
    model = '53230A'

    def __init__(self, resourceID):
        super().__init__(resourceID)

    def measureFrequency(self):
        return float(self.scpi.MEAS.FREQ.query())

    def test(self):
        return self.scpi.MEAS.FREQ.query()

if __name__ == '__main__':
    visaResource = 'TCPIP::192.168.25.154::INSTR'
    dev = KeySight_53230A(visaResource)

    print(dev.getIdentity())
    print(dev.test())
    # print(dev.getFrequency())
    # dev.setFrequency(42100002.6)
    # print(dev.getFrequency())