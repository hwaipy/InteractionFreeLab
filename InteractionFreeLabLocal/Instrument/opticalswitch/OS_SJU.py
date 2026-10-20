__author__ = 'Hwaipy'
__version__ = 'v1.0.20220806'

import serial

class OS_SJU:
    def __init__(self, port):
        self.port = port
        self.channel = serial.Serial(port, baudrate=115200)

    def __write(self, command, isQuery=False):
        cmd = command + ('?' if isQuery else '') + '\r'
        self.channel.write(cmd.encode('UTF-8'))

    def __query(self, command):
        self.__write(command, True)
        ret = b''
        while True:
            c = self.channel.read(1)  # read(读取多少个字节)
            if c == b'\n' and len(ret) > 1: break
            ret += c
        return ret.decode('UTF-8').strip()

    def getPort(self):
        return self.__query('SW')

    def setPort(self, port):
        if port < 0 or port >= 100: raise ValueError(f'Port={port} out of range: [0, 99].')
        self.__write(f'SW {port}')

if __name__ == '__main__':
    os = OS_SJU('COM3')
    print(os.getPort())
    os.setPort(55)
    print(os.getPort())
