__author__ = 'Hwaipy'
__version__ = 'v1.0.20211130'

import serial

class FS725:
    def __init__(self, port):
        self.port = port
        self.channel = serial.Serial(port, baudrate=9600)

    def __write(self, command, isQuery=False):
        cmd = command + ('?' if isQuery else '') + '\r'
        self.channel.write(cmd.encode('UTF-8'))

    def __query(self, command):
        self.__write(command, True)
        ret = b''
        while True:
            c = self.channel.read(1)  # read(读取多少个字节)
            if c == b'\r': break
            ret += c
        return ret.decode('UTF-8')

    def getMO(self):
        return self.__query('MO')

    def setMO(self, MO):
        if MO < 2300 or MO > 3600: raise ValueError(f'MO={MO} out of range: [2300, 3600].')
        self.__write(f'MO {MO}')

    def getSF(self):
        return self.query('SF')

    def setSF(self, SF:int):
        # set frequency offset by 1e-12, relative to the calibration value
        if SF < -2000 or SF > 2000:
            raise ValueError(f'SF={SF} out of range: [-2000, 2000].')
        return self.write(f'SF {SF}')

    def delay1PPS(self, delay):
        if delay <= 0 or delay > 999999999: raise ValueError(f'delay={delay} out of range: [1, 999999999].')
        self.__write(f'PP {int(delay)}')

if __name__ == '__main__':
    import sys
    from interactionfreepy import IFWorker, IFLoop

    ifserver = sys.argv[1]
    port = sys.argv[2]
    serviceName = sys.argv[3]
    # port = 'COM9'
    # serviceName = 'TF_AtomicClock_Alice'

    fs = FS725(port)
    IFWorker(ifserver, serviceName, fs, force=True)
    print(f'FS725 Services Started. Current MO = {fs.getMO()}.')

    IFLoop.join()
