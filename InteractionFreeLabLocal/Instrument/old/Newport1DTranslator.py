import serial
import threading
import queue
import time


class Communicator:
    def __init__(self, channel, dataFetcher, dataSender):
        self.__channel = channel
        self.__dataFetcher = dataFetcher
        self.__dataSender = dataSender
        self.__sendQueue = queue.Queue()

    def start(self):
        self.__running = True
        t1 = threading.Thread(target=self.__receiveLoop, name="communicator_receive_loop")
        t1.setDaemon(False)
        t1.start()
        t2 = threading.Thread(target=self.__sendLoop, name="communicator_send_loop")
        t2.setDaemon(False)
        t2.start()

    def __receiveLoop(self):
        try:
            while self.__running:
                self.__dataFetcher(self.__channel)
        except BaseException as re:
            pass
        finally:
            self.__running = False

    def sendLater(self, message):
        self.__sendQueue.put(message)

    def __sendLoop(self):
        try:
            while self.__running:
                try:
                    message = self.__sendQueue.get(timeout=0.5)
                    self.__dataSender(self.__channel, message)
                except queue.Empty:
                    pass
        except BaseException as e:
            import traceback
            traceback.print_exc(e)
            pass
        finally:
            self.__running = False

    def isRunning(self):
        return self.__running

    def stop(self):
        self.__running = False


class BlockingCommunicator(Communicator):
    def __init__(self, channel, dataFetcher, dataSender):
        Communicator.__init__(self, channel, self.dataQueuer, dataSender)
        self.dataQueue = queue.Queue()
        self.dataFetcherIn = dataFetcher

    def dataQueuer(self, channel):
        data = self.dataFetcherIn(channel)
        self.dataQueue.put(data)

    def query(self, message):
        self.sendLater(message)
        return self.dataQueue.get()


class X:
    def __init__(self, port):
        def fetcher(c):
            line = c.readline()
            line = line.decode('UTF-8')
            return float(line[3:-2])

        def sender(c, data):
            c.write('{}\r\n'.format(data).encode('UTF-8'))

        self.position = 0
        ser = serial.Serial(port, 921600, timeout=5, xonxoff=True)
        self.communicator = BlockingCommunicator(ser, fetcher, sender)
        self.communicator.start()
        # communicator.sendLater('1ID?')
        # self.__setAndUpdatePosition(13.5086)
        # print(self.position)
        self.inMotion = False

    def __setPosition(self, x):
        self.communicator.sendLater('1PA{}'.format(x))

    def __getPosition(self):
        return self.communicator.query('1PA?')

    def __setAndUpdatePosition(self, x):
        self.__setPosition(x)
        self.position = self.__getPosition()

    def motion(self, start, stop, step, stepTime):
        if self.inMotion: raise RuntimeError('Already in motion.')
        self.inMotion = True

        def runner():
            stepCount = int((stop - start) / step)
            for i in range(stepCount):
                x = start + step * i
                self.__setAndUpdatePosition(x)
                time.sleep(stepTime)

        thread = threading.Thread(target=runner)
        thread.setDaemon(True)
        thread.start()


x = X('COM5')
x.motion(13.508, 13.509, 0.0001, 0.5)

while True:
    print(x.position)
    time.sleep(1)
