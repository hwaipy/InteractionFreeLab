__author__ = 'Hwaipy'
__version__ = 'v1.0.20241125'

import socket
import time
import struct
import numpy as np
from binascii import hexlify
from ezq_driver.protocol.cmu_protocol import CMUProtocol
from ezq_driver.driver import EzqDevice
from ezq_driver.utils import bytes_to_int

CMUProtocol.MAX_MEM_SEND_FRAMES = 64 * 1024

class Feedbacker:
    def __init__(self, ip):
        self.ip = ip
        self.work_mode = 2
        self.loop_duration = 1
        self.feedbackHigherBound = 800   # 补偿上限,下发会乘以loop_duration
        self.feedbackLowerBound = 10     # 补偿下限。下发会乘以loop_duration
        self.feedbackCenter = 1.2        # 补偿范围中间值。最多支持两位小数，下发会乘以100
        self.feedbackRatio = 1.8         # 补偿比例。最多支持两位小数，下发会乘以100
        self.feedbackMap1 = [8192] * 1001   # len = 1001
        self.feedbackMap2 = [8192] * 1001   # len = 1001
        self.bias1 = 0
        self.bias2 = 0
        ser = socket.inet_aton(ip)[2]
        num = socket.inet_aton(ip)[3]
        if 2 <= ser <= 20:
            s = chr(ord('A') + ser)
        elif 220 >= ser >= 26:
            s = '公司'
        else:
            s = 'A/B'
        board = s + str(num)
        print(ip, board)
        self.cmu = EzqDevice(ip=self.ip, name=board, dev_mode=True, batch_mode=False)
        fix_data = self.cmu[23, 0x050000, (0x24<<2)]
        print(hex(bytes_to_int(fix_data)))

    def start(self):
        self.cmu[23, 0x050000, (0x48<<2)] = 1

    def stop(self):
        self.cmu[23, 0x050000, (0x48<<2)] = 0

    def setWorkMode(self, work_mode):
        assert isinstance(work_mode, int)
        assert work_mode >= 0 and work_mode <= 2
        self.work_mode = work_mode

    def setLoopDuration(self, loop_duration):
        self.loop_duration = loop_duration

    def setFeedbackHigherBound(self, higherBound):
        self.feedbackHigherBound = higherBound   # 补偿上限,下发会乘以loop_duration

    def setFeedbackLowerBound(self, lowerBound):
        self.feedbackLowerBound = lowerBound     # 补偿下限。下发会乘以loop_duration

    def setFeedbackCenter(self, feedbackCenter):
        self.feedbackCenter = feedbackCenter        # 补偿范围中间值。最多支持两位小数，下发会乘以100

    def setFeedbackRatio(self, feedbackRatio):
        self.feedbackRatio = feedbackRatio         # 补偿比例。最多支持两位小数，下发会乘以100

    def setFeedbackMap(self, ch, feedbackMap):
        assert ch == 0 or ch == 1
        assert len(feedbackMap) == 1001
        if ch == 0: self.feedbackMap1 = feedbackMap
        if ch == 1: self.feedbackMap2 = feedbackMap

    def setBiasAlice(self, bias):
        self.bias1 = bias

    def setBiasBob(self, bias):
        self.bias2 = bias

    def applyAndStart(self):
        self.stop()

        feedbackCenter_multipy_feedbackRatio = self.feedbackCenter * self.feedbackRatio * 10000
        feedbackRatio_1000 = self.feedbackRatio * 100 * 1000
        self.cmu[23, 0x050000, (0x28<<2)] = self.work_mode
        self.cmu[23, 0x050000, (0x2C<<2)] = self.loop_duration
        self.cmu[23, 0x050000, (0x30<<2)] = int(self.feedbackHigherBound * self.loop_duration)
        self.cmu[23, 0x050000, (0x34<<2)] = int(self.feedbackLowerBound * self.loop_duration)
        self.cmu[23, 0x050000, (0x38<<2)] = int(self.feedbackCenter * 100)
        self.cmu[23, 0x050000, (0x3C<<2)] = int(self.feedbackRatio * 100)
        self.cmu[23, 0x050000, (0x40<<2)] = int(feedbackCenter_multipy_feedbackRatio)
        self.cmu[23, 0x050000, (0x44<<2)] = int(feedbackRatio_1000)
        self.cmu[23, 0x050000, (0x5c<<2)] = int(self.bias1 * self.loop_duration)
        self.cmu[23, 0x050000, (0x60<<2)] = int(self.bias2 * self.loop_duration)

        #a通道映射值地址为0-1001， b通道映射至放在2000-3001，
        #上位机下发格式为64位为一条映射值
        #bit[63] flag，1有效，0无效
        #bit[11:0] addr,a通道为0-1001，b通道为2000-3001，不能修改，逻辑里一块ram，固定b通道访问地址＋2000；
        #bit[25:12] data

        data_len = 8192*2

        data = np.linspace(0, data_len>>2, data_len>>2, dtype='uint32')
        count = 0
        for i in range(1001):
            data[count] = (i) + (self.feedbackMap1[i] << 12)
            count = count + 1
            data[count] = (1 << 31)
            count = count + 1
        # print(data[0:10])

        for i in range(1001):
            data[count] = (i+2000) + (self.feedbackMap2[i] << 12)
            count = count + 1
            data[count] = (1 << 31)
            count = count + 1
        # print(count, len(data))
        for i in range(count, len(data)):
            data[i] = 0
        # print(data[4000:])
        self.cmu.write_mem(0, data.tobytes(), slot = 23)
        rd_data = self.cmu.read_mem(0, data_len, slot = 23)
        # print(data.tobytes())

        if rd_data == data.tobytes():
            print('下载成功') 
        else: 
            print('下载失败') 


        if(bytes_to_int(self.cmu[23, 0x050000, (0x50<<2)]) == 1):
            print('先停止计算再加载映射表')
        elif(bytes_to_int(self.cmu[23, 0x050000, (0x50<<2)]) == 1):
            print('正在下载映射表')
        else:
            self.cmu[23, 0x050000, (0x54<<2)] = data_len     #读ddr长度
            self.cmu[23, 0x050000, (0x58<<2)] = 0        #读ddr地址
            self.cmu[23, 0x050000, (0x50<<2)] = 1        #读ddr标志位

        time.sleep(1)

        self.start()

    # def getMO(self):
    #     return self.__query('MO')

    # def setMO(self, MO):
    #     if MO < 2300 or MO > 3600: raise ValueError(f'MO={MO} out of range: [2300, 3600].')
    #     self.__write(f'MO {MO}')

    # def delay1PPS(self, delay):
    #     if delay <= 0 or delay > 999999999: raise ValueError(f'delay={delay} out of range: [1, 999999999].')
    #     self.__write(f'PP {int(delay)}')

if __name__ == '__main__':
    import sys
    from interactionfreepy import IFWorker, IFLoop

    ifserver = sys.argv[1]
    ip = sys.argv[2]
    serviceName = sys.argv[3]

    fb = Feedbacker(ip)
    fb.applyAndStart()
    IFWorker(ifserver, serviceName, fb, force=True)
    print(f'Atmosphere turbulent feecbacker started.')

    IFLoop.join()
