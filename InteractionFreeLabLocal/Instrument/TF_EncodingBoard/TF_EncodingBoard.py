import datetime
import socket
from threading import Thread
import time
from queue import Queue
import struct
import numpy as np

class EncodingBoard:
    def __init__(self, ip):
        self.ip = ip
        self.socket = socket.socket()
        self.socket.connect((self.ip, 1092))
        time.sleep(0.2)
        self.inBuffer = b''
        self.responseQueue = Queue()
        self.fastAIResponseQueue = Queue()
        self.fastAIResponseFrames = Queue()
        self.__closed = False
        Thread(target=self.__readLoop).start()
        Thread(target=self.__dealFastAIData).start()

    def version(self):
        ret = self.__query(0x10)
        return ret.decode('UTF-8')

    def sn(self):
        ret = self.__query(0x11)
        return ret.decode('UTF-8')

    def identity(self):
        ret = self.__query(0x12)
        return ret.decode('UTF-8')

    def startFastAI(self, ext=True):
        ret = self.__query(0x30, b'\x02' if ext else b'\xFF')

    def stopFastAI(self):
        ret = self.__query(0x31)

    def setFastAIDAC(self, channel, value):
        ret = self.__query(0x35, channel.to_bytes(1, 'big') + value.to_bytes(2, 'big'))

    def setFeedbackOn(self, on):
        ret = self.__query(0x33, b'\x01' if on else b'\x00')

    def setFeedbackRatio(self, ratioLow, ratioHigh):
        ratioLowD1000 = int(ratioLow * 1000)
        ratioHighD1000 = int(ratioHigh * 1000)
        ret = self.__query(0x36, ratioLowD1000.to_bytes(2, 'big') + ratioHighD1000.to_bytes(2, 'big'))

    def setFeedbackBound(self, lowerBound, higherBound, dangerBound):
        ret = self.__query(0x37, lowerBound.to_bytes(2, 'big') + higherBound.to_bytes(2, 'big') + dangerBound.to_bytes(2, 'big'))

    def getNextFrame(self):
        return self.fastAIResponseFrames.get()

    def loadFastAIFeedbackCalibrationFile(self, path):
        f = open(path, 'r', encoding='UTF-8')
        lines = f.readlines()[1:]
        items = [[float(i) for i in line.split(',')[:3]] for line in lines]

        xs = [i[0] for i in items]
        yss = [[i[1] / items[0][1] for i in items], [i[2] / items[0][2] for i in items]]

        # import matplotlib.pyplot as plt
        # plt.plot(xs, yss[0])
        # plt.plot(xs, yss[1])
        # plt.show()

        ratios = [i / 100 for i in range(0, 101, 1)]

        def searchForCode(ratio, ys):
            for i in range(len(ys) - 1):
                if ys[i] >= ratio and ys[i + 1] < ratio:
                    break
            xA = xs[i]
            xB = xs[i + 1]
            yA = ys[i]
            yB = ys[i + 1]
            code = int((xB - xA) / (yB - yA) * (ratio - yA) + xA)
            if code > 4095: code = 4095
            return code

        codes = []
        for ratio in ratios:
            codes.append([searchForCode(ratio, yss[0]), searchForCode(ratio, yss[1])])

        buffers = [b'\x00', b'\x01']
        for channel in range(2):
            for c in codes:
                code = c[channel]
                buffers[channel] += code.to_bytes(2, 'big')

        # for i in range(len(codes)):
        #     print(i, codes[i])

        for channel in range(2):
            ret = self.__query(0x34, buffers[channel])


    def close(self):
        self.__closed = True
        self.socket.close()

    def __query(self, cmd, data=b''):
        self.socket.send(cmd.to_bytes(1, 'big'))
        self.socket.send(len(data).to_bytes(1, 'big'))
        self.socket.send(data)
        while not self.__closed:
            response = self.responseQueue.get()
            if response['command'] != cmd: print(f'Bad response: {response}')
            return response['data']

    def __readLoop(self):
        try:
            while not self.__closed:
                r = self.socket.recv(1)
                self.inBuffer += r
                if len(self.inBuffer) >= 2 and len(self.inBuffer) >= self.inBuffer[1] + 2:
                    response = {
                        'command': self.inBuffer[0],
                        'size': self.inBuffer[1],
                        'data': self.inBuffer[2:self.inBuffer[1] + 2],
                        'fetchTime': time.time(),
                    }
                    if response['command'] == 0x3F:
                        self.fastAIResponseQueue.put(response)
                    else:
                        self.responseQueue.put(response)
                    self.inBuffer = self.inBuffer[self.inBuffer[1] + 2:]
        except BaseException as e:
            # print(e)
            pass

    def __dealFastAIData(self):
        currentFrame = None
        buffer = b''
        currentResponse = None
        while not self.__closed:
            if len(buffer) < 4:
                try:
                    currentResponse = self.fastAIResponseQueue.get(block=True, timeout=1)
                except:
                    if self.__closed: return
                    else: continue
                buffer += currentResponse['data']
            if len(buffer) >= 4:
                data = buffer[:4]
                buffer = buffer[4:]
                unit = struct.unpack('>HH', data)
                if unit[0] == 65535:
                    if currentFrame:
                        # ave1 = np.average(np.array(currentFrame["data1"]))
                        # std1 = np.std(np.array(currentFrame["data1"]))
                        # ave2 = np.average(np.array(currentFrame["data2"]))
                        # std2 = np.std(np.array(currentFrame["data2"]))
                        # print(currentFrame['count'], f'{ave1} ± {std1}', f'{ave2} ± {std2}')
                        # print(currentFrame['data1'])
                        # print(currentFrame['data2'])
                        self.fastAIResponseFrames.put(currentFrame)
                    currentFrame = {'count': unit[1], 'data1': [], 'data2': [], 'counts1': [], 'counts2': [], 'fetchTime': currentResponse['fetchTime']}
                else:
                    if currentFrame:
                        currentFrame['data1'].append(unit[0] & 0b1111111111)
                        currentFrame['data2'].append(unit[1] & 0b1111111111)
                        currentFrame['counts1'].append(unit[0] >> 10)
                        currentFrame['counts2'].append(unit[1] >> 10)

def output_redirect():
    import os
    dirName = 'ChannelMonitor'
    if not os.path.exists(f'./{dirName}'):
        os.mkdir(f'./{dirName}')
    out = open(f'{dirName}\{datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")}out.log', 'a')
    err = open(f'{dirName}\{datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")}err.log', 'a')
    sys.stdout = out
    sys.stderr = err

if __name__ == '__main__':
    import sys
    from interactionfreepy import IFWorker, IFLoop

    if len(sys.argv) >= 5:
        ifserver = sys.argv[1]
        boardIP = sys.argv[2]
        serviceName = sys.argv[3]
        calibrationFile = sys.argv[4]
    else:
        ifserver = 'tcp://10.1.3.1:1061'
        boardIP = '192.168.0.100'
        serviceName = 'TF_ChannelMonitor'
        calibrationFile = 'C:\\Users\\13052\\Desktop\\TF\\TFEncodingBoard\\calibration.csv'

    eb = EncodingBoard(boardIP)
    print(eb.identity())
    if calibrationFile: eb.loadFastAIFeedbackCalibrationFile(calibrationFile)
    eb.startFastAI()
    eb.setFeedbackOn(False)
    # eb.setFeedbackRatio(0.19, 21.2)
    # eb.setFeedbackBound(10, 1000, 1023)

    worker = IFWorker(ifserver, serviceName, eb, force=True)

    print(f'Channel Monitor Service Started.')

    output_redirect()

    while True:
        f = eb.getNextFrame()
        # print(worker.Storage.latest('TFQKD_TDC', filter={'_id': 1, 'FetchTime': 1}))
        worker.Storage.append('ChannelMonitor', f, fetchTime=str(datetime.datetime.fromtimestamp(f['fetchTime'])) + '+08:00')
        # print(worker.Storage.latest('ChannelMonitor', filter={'_id': 1, 'FetchTime': 1}))
        # print('------')
        print(str(datetime.datetime.fromtimestamp(f['fetchTime'])))
        sys.stdout.flush()

    time.sleep(1)
    eb.close()
