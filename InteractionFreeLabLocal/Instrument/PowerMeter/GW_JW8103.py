__author__ = 'Hwaipy'
__version__ = 'v1.0.20210702'

import serial

class GW_JW8103:
    def __init__(self, port):
        self.port = port
        self.channel = serial.Serial(port, baudrate=115200)

    def setWavelength(self, channel, wavelength):
        channelS = self.__getChannelCode(channel)
        wavelengthS = '{:.2f}'.format(wavelength).encode('UTF-8')
        self.__query(0x4a, channelS + wavelengthS)

    def readPower(self):
        ret = self.__query(0x4c, b'')
        res = ret[1][1:].decode('UTF-8').split('#')
        return float(res[0][1:]), float(res[4][1:]),

    def __buildCommand(self, command, data):
        length = len(data) + 3
        cmd = b'{' + length.to_bytes(1, 'big') + command.to_bytes(1, 'big') + data
        check = 256 - (sum(cmd) % 256)
        cmd += check.to_bytes(1, 'big') + b'}'
        return cmd

    def __query(self, command, data):
        self.channel.write(self.__buildCommand(command, data))
        ret = b''
        while True:
            c = self.channel.read(1)
            ret += c
            if len(ret) > 2 and len(ret) == ret[1] + 2:
                break
        return ret[2], ret[3:-2]

    def __getChannelCode(self, channel):
        if channel == 1 or channel == 'CH1':
            return b'\x01'
        if channel == 2 or channel == 'CH2':
            return b'\x02'
        raise ValueError('Channel not valid.')

    def test(self):
        self.setWavelength(1, 1550)
        self.setWavelength(2, 1550)
        p = self.readPower()
        print(p)


if __name__ == '__main__':
    import sys
    from interactionfreepy import IFWorker, IFLoop

    port = sys.argv[1]
    serviceName = sys.argv[2]

    ps = GW_JW8103(port)
    ps.setWavelength(1, 1550)
    ps.setWavelength(2, 1550)
    IFWorker('tcp://192.168.25.5:224', serviceName, ps)

    print('PowerMeter Started!')

    IFLoop.join()
