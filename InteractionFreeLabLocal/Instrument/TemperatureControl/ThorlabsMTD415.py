__author__ = 'Hwaipy'
__version__ = 'v1.0.20220308'

import serial

class Thorlabs_MTD415:
    def __init__(self, port):
        self.port = port
        self.channel = serial.Serial(port, baudrate=115200)

    def __write(self, command, isQuery=False):
        cmd = command + ('?' if isQuery else '') + '\n'
        self.channel.write(cmd.encode('UTF-8'))

    def __query(self, command):
        self.__write(command, True)
        ret = b''
        while True:
            c = self.channel.read(1)
            if c == b'\n': break
            ret += c
        return ret.decode('UTF-8')

    def getCurrentTemperature(self):
        return int(self.__query('Te')) / 1000

if __name__ == '__main__':
    import sys

    mtd = Thorlabs_MTD415('COM3')
    print(mtd.getCurrentTemperature())