__author__ = 'Hwaipy'

from Instrument.Instruments import DeviceException, VISAInstrument

class Thorlabs_ITC4001(VISAInstrument):
    manufacturer = 'Thorlabs'
    model = 'ITC4001'

    def __init__(self, resourceID):
        super().__init__(resourceID)

    def setLaserCurrent(self, current):
        self.scpi.SOUR.CURR.write(current)

    def test(self):
        return self.scpi.SOUR.CURR.query()

if __name__ == '__main__':
    import pyvisa as visa

    print(visa.ResourceManager().list_resources())
    visaResource = 'USB0::0x1313::0x804A::M00532270::INSTR'
    dev = Thorlabs_ITC4001(visaResource)

    print(dev.getIdentity())
    print(dev.setLaserCurrent(0.012))
    print(dev.test())