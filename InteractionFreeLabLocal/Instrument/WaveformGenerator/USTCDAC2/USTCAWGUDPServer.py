import sys
from Instrument.WaveformGenerator.USTCDAC.UDPBoard import UDPBoard
import itertools
import random
import numpy as np
import time
import logging
import time
from Instrument.WaveformGenerator.USTCDAC2.driver import UstcAWG

class AWGUDPServer:
    def __init__(self, ip):
        self.da = UstcAWG(name=f'E{ip.split(".")[-1]}', ip=ip, console_log=True, batch_mode=False, dev_mode=False)
        self.da.init_device() # 初始化AWG板
        self.da.set_multi_board(0) # 配置AWG板为“多板模式”，即，触发后才开始输出
        print(f'AWG at [{ip}] inited.')

    def close(self):
        self.da.sockfd.close()

    def writeWaveformsData(self, waveformsData, address, progress=lambda p: None):
        self.da.write_mem(address, waveformsData, wait_response=True)

        # UNIT_SIZE = 1024000  # = 2 ** 22 - 3 ，长度不超过32M = 2 ** 25
        # position = 0
        # while len(waveformsData) - position > 0:
        #     start = position
        #     stop = min((position + UNIT_SIZE), len(waveformsData))
        #     dataTBW = waveformsData[start: stop]
        #     print('write mem')
        #     self.da.write_mem(address + position, dataTBW, wait_response=True)
        #     progress(UNIT_SIZE / len(waveformsData))
        #     position += UNIT_SIZE

    def configOutput(self, address, length):
        self.da.stop_output_wave(0) #停止所有输出
        self.da.clear_trig_count() #清空触发状态
        #以上是标准操作要求

        cmd = self.cmd_generator(3, length // 4, 0, address)

        # 把配置好的操作指令传给板子
        self.da.write_seq(1,seq=cmd)
        self.da.write_seq(2,seq=cmd)
        
        # 开始输出
        self.da.start_output_wave(1)
        self.da.start_output_wave(2)
        self.da.start_output_wave(3)
        self.da.start_output_wave(4)

    def setOutputLevel(self, channel, code, amplitude):
        assert channel > 0 and channel <= 4
        assert code >= 0 and code < 32
        assert amplitude >= 0 and amplitude <= 1
        self.da.write_lut_ram_TF(channel, code, int(amplitude * 65535))

    # 本段代码的目的是生成任意波形输出的控制序列
    # 单个数16bit，两个数共32bit=4Byte
    # 4个通道各200ms的波形共需要ddr_size = 16e8
    # 因单次读入数据量为24bit，故单个序列指令可写入数据长度应小于（1<<24）=16_777_216。此处设置单个指令写入数据长度single_len=10_000_000。
    # 单个周期为n次cmd_n波形(长wave_len_n)+1次cmd_m波形(长wave_len_m)，共loop_cnt**3个周期。
    # n不能为0。

    # 读出ddr中某一特定部分的数据的方法：令wave_len_m=0，addr为地址开头，wave_len_n为读出数据长度

    def cmd_generator(self, n, wave_len_n, wave_len_m, addr=0, loop_cnt=50000, single_len=int(1e7)):
        if ((wave_len_n + wave_len_m) >= (2000 * 1000 * 240)):
            return print("The data is too long!")
        addr = addr * 4
        w1_n = (wave_len_n * 4) // single_len
        w2_n = (wave_len_n * 4) % single_len
        if (w2_n == 0):
            w_n = w1_n
        else:
            w_n = w1_n + 1

        w1_m = (wave_len_m * 4) // single_len
        w2_m = (wave_len_m * 4) % single_len
        if (w2_m == 0):
            w_m = w1_m
        else:
            w_m = w1_m + 1

        # 写入波形数据的指令
        cmd_n = []
        cmd_m = []

        if (w1_n == 0):
            cmd_n = cmd_n + self.gen_read_to_ddr(addr, w2_n)
            addr = (addr + w2_n) & 0x7FFFFFFF
        else:
            for i in range(w1_n):
                cmd_n = cmd_n + self.gen_read_to_ddr(addr, single_len)
                addr = (addr + single_len) & 0x7FFFFFFF
                if ((i == (w1_n - 1)) and (w2_n != 0)):
                    cmd_n = cmd_n + self.gen_read_to_ddr(addr, w2_n)
                    addr = (addr + w2_n) & 0x7FFFFFFF

        if (w1_m == 0):
            cmd_m = cmd_m + self.gen_read_to_ddr(addr, w2_m)
        else:
            for i in range(w1_m):
                cmd_m = cmd_m + self.gen_read_to_ddr(addr, single_len)
                addr = (addr + single_len) & 0x7FFFFFFF
                if ((i == (w1_m - 1)) and (w2_m != 0)):
                    cmd_m = cmd_m + self.gen_read_to_ddr(addr, w2_m)

        cmd_trig = [50, 0, 0, 0x03 << 12]
        cmd_ls1 = [0, 0, loop_cnt, 0x06 << 12 | 0 << 8]
        cmd_ls2 = [0, 0, loop_cnt, 0x06 << 12 | 1 << 8]
        cmd_ls3 = [0, 0, loop_cnt, 0x06 << 12 | 2 << 8]
        cmd_le1 = [0, 0, 1, 0x07 << 12 | 0 << 8]
        cmd_le2 = [0, 0, 2, 0x07 << 12 | 1 << 8]
        cmd_le3 = [0, 0, 3, 0x07 << 12 | 2 << 8]

        if (n == 0):
            return print("please not 0!0!")
        elif (wave_len_m > 0):
            cmd_ls4 = [0, 0, n, 0x06 << 12 | 3 << 8]
            cmd_le4 = [0, 0, 4, 0x07 << 12 | 3 << 8]
            cmd = cmd_trig + cmd_ls1 + cmd_ls2 + cmd_ls3 + cmd_ls4 + cmd_n + cmd_le4 + cmd_m + cmd_le3 + cmd_le2 + cmd_le1
        elif (wave_len_m == 0):
            cmd_ls4 = [0, 0, loop_cnt, 0x06 << 12 | 3 << 8]
            cmd_le4 = [0, 0, 4, 0x07 << 12 | 3 << 8]
            cmd = cmd_trig + cmd_ls1 + cmd_ls2 + cmd_ls3 + cmd_ls4 + cmd_n + cmd_le4 + cmd_le3 + cmd_le2 + cmd_le1

        cmd = cmd + [0] * (32 - len(cmd) & 31)

        return cmd

    # 读DDR到FIFO
    # 等cnt
    # 等cnt
    # 等DDR
    # 重复1024次，每次最大16MB数据
    # 读取DDR到FIFO
    # 在控制序列中一个gen_read_to_ddr算3个指令

    def gen_read_to_ddr(self, addr, length):
        assert length & 0x3F == 0
        assert length < (1 << 24)
        assert addr & 0x3F == 0
        _len = length
        cmd1 = [addr & 0xFFFF, addr >> 16, _len & 0xFFFF, (0xB << 12) | (_len >> 16)]
        ## 等待计数 200ns
        cmd2 = [50, 0, 0, 0x05 << 12]
        ## 等待触发
        cmd3 = [0, 0, 0, 0x03 << 12]
        ## 等待DDR
        wait_cnt = 50  # (length>>5) - 150
        # print(wait_cnt)
        cmd4 = [wait_cnt & 0xFFFF, wait_cnt >> 16, 0, 0x9 << 12]
        # 直接输出
        cmd5 = [0, 4, 0, 0 << 12]
        cmd = cmd1 + cmd2 + cmd4
        return cmd

    def setGain(self, channel, gain):
        assert channel >= 1 and channel <= 4
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
    dev = AWGUDPServer('10.1.1.25')

    totalLength = 40000000
    pulseLength = 1000000

    wave1 = [31] * pulseLength + [0] * (totalLength - pulseLength)
    wave2 = [24] * pulseLength + [0] * (totalLength - pulseLength)
    wave3 = [15] * pulseLength + [0] * (totalLength - pulseLength)
    wave4 = [6] * pulseLength + [0] * (totalLength - pulseLength)

    wave = np.vstack((wave1, wave2, wave3, wave4)).astype(dtype='uint8').T
    data = wave.tobytes()
    print(len(data))

    t1 = time.time()
    dev.writeWaveformsData(data, 0)
    t2 = time.time()
    print(t2 - t1)
    dev.configOutput(0, len(data))

