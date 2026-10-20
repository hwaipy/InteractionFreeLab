__author__ = 'Hwaipy'
__version__ = 'v1.0.20211130'

import serial
from threading import Thread
from queue import Queue
import time
import ctypes
from datetime import datetime

class TriggerBoard:
    def __init__(self, port):
        self.port = port
        self.channel = serial.Serial(port, baudrate=115200)
        self.triggers = []

        def __readLoop():
            buf = b''
            while True:
                c = self.channel.read(1)
                if c == b'\r':
                    buf = buf.strip().decode('UTF-8')
                    # print(buf, time.time())
                    print(('Triggered' if buf == 'T' else '^Triggered') + ' at ' + str(datetime.now()))
                    self.triggers.append([buf, time.time()])
                    if len(self.triggers) > 20:
                        self.triggers = self.triggers[-20:]
                    buf = b''
                else:
                    buf += c

        Thread(target=__readLoop).start()

    def __write(self, command):
        self.channel.write(command.encode('UTF-8'))

    def getTriggers(self, after):
        ts = [t for t in self.triggers if not t[1] <= after]
        return ts

    def delayDividedTrigger(self, delay):
        self.triggers = []
        self.__write(f'D{int(delay)}\n')

    def start(self):
        self.__write(f'E1\n')

    def stop(self):
        self.__write(f'E0\n')

if __name__ == '__main__':
    import sys
    from interactionfreepy import IFWorker, IFLoop

    if len(sys.argv) < 2:
        sys.argv = [sys.argv[0], 'tcp://192.168.25.5:1061', '/dev/cu.usbserial-210', 'TF_TriggerBoard_Bob']

    ifserver = sys.argv[1]
    port = sys.argv[2]
    serviceName = sys.argv[3]

    tb = TriggerBoard(port)
    IFWorker(ifserver, serviceName, tb, force=True)

    IFLoop.join()
