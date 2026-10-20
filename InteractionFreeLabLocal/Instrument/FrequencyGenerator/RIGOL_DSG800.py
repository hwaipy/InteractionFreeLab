__author__ = 'Hwaipy'

from Instrument.Instruments import DeviceException, VISAInstrument

class RIGOL_DSG800(VISAInstrument):
    manufacturer = 'Rigol Technologies'
    model = 'DSG815'

    def __init__(self, resourceID):
        super().__init__(resourceID)

    def getFrequencySetpoint(self):
        return float(self.scpi.FREQ.query())

    def setFrequency(self, frequency):
        self.scpi.FREQ.write(frequency)

    def test(self):
        return self.scpi.FREQ.query()

if __name__ == '__main__':
    # visaResource = 'TCPIP::192.168.25.148::INSTR'
    # dev = RIGOL_DSG800(visaResource)

    # print(dev.getIdentity())
    # print(dev.getFrequency())
    # dev.setFrequency(42100002.6)
    # print(dev.getFrequency())

    import sys
    from interactionfreepy import IFWorker, IFLoop

    ip = sys.argv[1]
    serviceName = sys.argv[2]

    dev = RIGOL_DSG800(f'TCPIP::{ip}::INSTR')

    IFWorker('tcp://192.168.25.5:224', serviceName, dev, force=True)
    print(f'RIGOL_DSG800 Frequency Generator {sys.argv[2]} Started!')

    IFLoop.join()
