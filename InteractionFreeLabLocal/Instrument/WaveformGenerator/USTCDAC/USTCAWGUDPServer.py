import sys
from Instrument.WaveformGenerator.USTCDAC.UDPBoard import UDPBoard
import itertools
import random
import numpy as np
import time
import logging
import time

class AWGUDPServer:
    def __init__(self, ip):
        self.da = UDPBoard(id=f'F{ip.split(".")[-1]}', ip=ip, data_offset=[0,0,0,0])
        # DAC   digital-analog convertor
        # AWG   arbitrary waveform generator  强调快速的DAC
        self.da.connect() # 连接AWG板
        self.da.init_device() # 初始化AWG板
        self.da.set_multi_board(0) # 配置AWG板为“多板模式”，即，触发后才开始输出
        print(f'AWG at [{ip}] inited.')

    def close(self):
        self.da.sockfd.close()

    def writeWaveforms(self, waveforms):
        assert len(waveforms) == 2
        waves = []
        for waveform in waveforms:
            if len(waveform) % 256 == 0: waves.append(waveform)
            else: 
                lenTBA = (int(len(waveform) / 256) + 1) * 256 - len(waveform)
                waveform = waveform + [0] * lenTBA
                waves.append(waveform)

        self.doWriteWaveform(waves[0], waves[1], 0)
        self.configOutput(0, len(waveforms[0]), sampleWise=True)

    def writeWaveformsData(self, waveformsData, address, progress=lambda p: None):
        # assert len(waveformsData) % 1024 == 0   # 写DDR最小单元是1024byte
        assert address % 1024 == 0   # 写DDR最小单元是1024byte
        assert len(waveformsData) + address <= (0x7FFFFFFF + 1) # 2G
        assert address >= 0

        UNIT_SIZE = 1024000  # = 2 ** 22 - 3 ，长度不超过32M = 2 ** 25
        position = 0
        while len(waveformsData) - position > 0:
            start = position
            stop = min((position + UNIT_SIZE), len(waveformsData))
            dataTBW = waveformsData[start: stop]
            if len(dataTBW) % 256 != 0:
                paddingLength = (int(len(dataTBW) / 256) + 1) * 256 - len(dataTBW)
                dataTBW = dataTBW + bytes(paddingLength)
            self.da.write_memory(address + position, dataTBW)
            progress(UNIT_SIZE / len(waveformsData))
            position += UNIT_SIZE

    # waveform1(2) 长度不超过500M, address + len(waveform) 不超过500M = 2 ** 29   address和波形长度是256的整数倍
    def doWriteWaveform(self, waveform1, waveform2, address):
        self.da.stop_output_wave(0) #停止所有输出
        self.da.clear_trig_count() #清空触发状态
        #以上是标准操作要求

        assert len(waveform1) == len(waveform2)
        assert len(waveform1) % 256 == 0   # 写DDR最小单元是1024byte
        assert address % 256 == 0   # 写DDR最小单元是1024byte
        assert len(waveform1) + address <= (0x1FFFFFFF + 1) # 2G/4
        assert address >= 0

        UNIT_SIZE = 32000  # = 2 ** 22 - 3 ，长度不超过32M = 2 ** 25
        position = 0
        while len(waveform1) - position > 0:
            start = position
            stop = min((position + UNIT_SIZE), len(waveform1))
            self.__writeWaveformUnit(waveform1[start: stop], waveform2[start: stop], address + position)
            position += UNIT_SIZE

    # waveform1(2) 长度不超过32M = 2 ** 25, address + len(waveform) 不超过500M
    def __writeWaveformUnit(self, waveform1, waveform2, address):
        assert len(waveform1) == len(waveform2)
        assert len(waveform1) % 256 == 0   # 写DDR最小单元是1024byte
        assert len(waveform1) + address <= (0x1FFFFFFF + 1) # 2G/4
        assert len(waveform1) <= 32<<20  # 单个波形的长度不能超过32M    1M = 1<<20  (2^20)

        # 把wave_i 和 wave_q 按要求的格式拼接，并转换为二进制数据
        wave_i = np.array(waveform1).astype('u2')
        wave_q = np.array(waveform2).astype('u2')
        wave = np.vstack((wave_i,wave_q))
        wave = wave.T
        data = wave.tobytes()

        self.da.write_memory(address * 4, data)

    def configOutput(self, address, length, sampleWise=False):
        if sampleWise:
            address *= 4
            length *= 4
        self.da.stop_output_wave(0) #停止所有输出
        self.da.clear_trig_count() #清空触发状态
        #以上是标准操作要求
        
        assert address + length <= (0x7FFFFFFF + 1) # 2G/4
        assert address % 1024 == 0
        assert length % 256 == 0

        # 指定 AWG 单次输出波形的起始地址和长度   （FPGA  field programable gate array 直接的逻辑门阵列，简单高速的操作 ；CPU 通用复杂）
        def gen_read_to_ddr(addr, _len):
            assert length & 0xFF == 0
            assert addr & 0x3F == 0
            cmd1 = [addr&0xFFFF, addr>>16, _len&0xFFFF, (0xB<<12) | (_len>>16)]
            ## 等待计数 800ns
            cmd2 = [200, 0, 0, 0x05<<12]
            ## 等待DDR
            wait_cnt = 50 #(length>>5) - 150
            cmd4 = [wait_cnt&0xFFFF, wait_cnt>>16, 0, 0x9 << 12]
            cmd = cmd1+cmd2+cmd4
            return cmd

        UNIT_SIZE = 2048000  # 单位为byte
        # UNIT_SIZE = 5120000000  # 单位为byte
        UNIT_SIZE_MAX = UNIT_SIZE * 2
        # 任意一次输出的长度 >= UNIT_SIZE,   <= UNIT_SIZE_MAX

        position = 0
        cmd = []
        while (length - position) > UNIT_SIZE_MAX:
            cmd += gen_read_to_ddr(address + position, UNIT_SIZE)
            # print(address + position, UNIT_SIZE)
            position += UNIT_SIZE
        cmd += gen_read_to_ddr(address + position, length - position)
        # print(address + position, length - position)
        
        # 构造（近似）无限循环
        loop_cnt = 50000
        cmd_trig = [50, 0, 0, 0x03<<12]
        cmd_ls1  = [0, 0, loop_cnt, 0x06<<12 | 0 << 8]
        cmd_ls2  = [0, 0, loop_cnt, 0x06<<12 | 1 << 8]
        cmd_ls3  = [0, 0, loop_cnt, 0x06<<12 | 2 << 8]
        cmd_ls4  = [0, 0, loop_cnt, 0x06<<12 | 3 << 8]
        cmd_le1  = [0, 0, 1, 0x07<<12 | 0 << 8]
        cmd_le2  = [0, 0, 2, 0x07<<12 | 1 << 8]
        cmd_le3  = [0, 0, 3, 0x07<<12 | 2 << 8]
        cmd_le4  = [0, 0, 4, 0x07<<12 | 3 << 8]
        cmd = cmd_trig+cmd_ls1+cmd_ls2+cmd_ls3+cmd_ls4+cmd+cmd_le4+cmd_le3+cmd_le2+cmd_le1

        # 把配置好的操作指令传给板子
        self.da.write_seq_fast(1,seq=cmd)
        self.da.write_seq_fast(2,seq=cmd)
        
        # 开始输出
        self.da.start_output_wave(1)
        self.da.start_output_wave(2)

    def setGain(self, channel, gain):
        assert channel >= 1 and channel <= 2
        assert gain >= 0 and gain <= 1023
        return self.da.set_gain(channel, gain)

    def turnOn(self, channel):
        assert channel >= 1 and channel <= 2
        self.da.start_output_wave(channel)

    def turnOff(self, channel):
        assert channel >= 1 and channel <= 2
        self.da.stop_output_wave(channel)

    def turnOnAllChannels(self):
        self.da.start_output_wave(0)

    def turnOffAllChannels(self):
        self.da.stop_output_wave(0)


class get_waveform_tracingpointlist:
    # 定义脉冲的时间间隔pulse_interval，单位ns
    def __init__(self):
        self.pulse_interval = 10
        return

    # 定义单个脉冲,脉冲宽度width，单位ns，脉冲强度intensity，单位为“1”（归一化单位）
    def define_unit_pulse(self, width, intensity):

        # 条件：脉冲宽度小于等于脉冲时间间隔
        assert self.pulse_interval >= width

        # unit_pulse由数据点组成，每个数据点定义0.5ns的电平, 归一化的脉冲强度intensity乘电平精确度65536后四舍五入得到“以65536为满值的电平”
        unit_pulse = [ 0 for i in range(int((self.pulse_interval - width) / 2))] * 2 + [int(intensity * 65536 + 0.5) for i in range(width)] * 2 + [ 0 for i in range(int((self.pulse_interval - width) / 2))] * 2

        return unit_pulse

    # 此处定义的波形，脉宽是固定的
    def define_waveform(self, waveform_list, width):
        waveform_tracingpointlist = []
        for intensity_i in waveform_list:
            waveform_tracingpointlist += self.define_unit_pulse(width, intensity=intensity_i)
        return waveform_tracingpointlist



class MergedUSTCDACServer:
    def __init__(self, awgs):
        self.awgs = awgs
        self.channelMapping = {1: [0, 2], 2: [1, 2], 3: [0, 1], 4: [1, 1]}

    def turnOn(self, channel):
        assert channel >= 1 and channel <= 4
        mappedChannel = self.channelMapping[channel]
        self.awgs[mappedChannel[0]].turnOn(mappedChannel[1])

    def turnOff(self, channel):
        assert channel >= 1 and channel <= 4
        mappedChannel = self.channelMapping[channel]
        self.awgs[mappedChannel[0]].turnOff(mappedChannel[1])

    def turnOnAllChannels(self):
        for awg in self.awgs:
            awg.turnOnAllChannels()

    def turnOffAllChannels(self):
        for awg in self.awgs:
            awg.turnOffAllChannels()

    def writeWaveforms(self, waveforms):
        assert len(waveforms) == 4
        waves = []
        for waveform in waveforms:
            if len(waveform) % 256 == 0: waves.append(waveform)
            else: 
                lenTBA = (int(len(waveform) / 256) + 1) * 256 - len(waveform)
                waveform = waveform + [0] * lenTBA
                waves.append(waveform)

        self.awgs[0].writeWaveform(waves[2], waves[0], 0)
        self.awgs[1].writeWaveform(waves[3], waves[1], 0)
        self.awgs[0].configOutput(0, len(waveforms[0]))
        self.awgs[1].configOutput(0, len(waveforms[0]))

    def sendTrigger(self, awgIndex, interval1, count1, interval2, count2):
        pass

if __name__ == '__main__':
    from interactionfreepy import IFWorker, IFLoop

    serviceName1 = sys.argv[1]
    ip1 = sys.argv[2]
    serviceName2 = sys.argv[3]
    ip2 = sys.argv[4]

    dev1 = AWGUDPServer(ip1)
    print(f'Device 1 ({ip1}) connected.')
    dev2 = AWGUDPServer(ip2)
    print(f'Device 2 ({ip2}) connected.')

    # IFWorker('tcp://192.168.25.5:224', serviceName, MergedUSTCDACServer([dev1, dev2]), force=True)
    IFWorker('tcp://192.168.25.5:224', serviceName1, dev1, force=True)
    IFWorker('tcp://192.168.25.5:224', serviceName2, dev2, force=True)

    # IFWorker('tcp://192.168.25.5:224', 'USTCAWG_Alice', MergedUSTCDACServer([AWGUDPServer('192.168.25.230'), AWGUDPServer('192.168.25.231')]), force=True)
    # IFWorker('tcp://192.168.25.5:224', 'USTCAWG_Bob', MergedUSTCDACServer([AWGUDPServer('192.168.25.234'), AWGUDPServer('192.168.25.235')]), force=True)

    IFLoop.join()
