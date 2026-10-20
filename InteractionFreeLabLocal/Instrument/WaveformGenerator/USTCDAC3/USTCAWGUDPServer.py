import numpy as np
from Instrument.WaveformGenerator.USTCDAC3.driver import UstcAWG

class AWGUDPServer:
    def __init__(self, ip):
        self.da = UstcAWG(name=f'E{ip.split(".")[-1]}', ip=ip, console_log=True, batch_mode=False, dev_mode=False)
        self.da['CPU.PERMISSION'] = 1 # AWG写解锁
        self.da.set_multi_board(0) # 配置AWG板为“多板模式”，即，触发后才开始输出
        self.setGain(0, 1)
        print(f'AWG at [{ip}] inited.')

    def generateWaveform(self, waveforms=None):
        assert len(waveforms) == 4
        assert len(waveforms[0]) % 8 == 0
        self.turnOffAllChannels()

        seq = self.__generateSequence(0, len(waveforms[0]))
        for c in range(4):
            self.da.write_seq(c + 1, seq=seq, slot=self.da.slot)
            self.da.write_wave(c + 1, waveforms[c], slot=self.da.slot)
        self.turnOnAllChannels()

    def close(self):
        self.da.close()

    def __generateSequence(self, address, length, sampleWise=False):
        def loop_start_seq(wave_addr, wave_len, loop_level, loop_cnt):
            assert loop_level in [0, 1, 2, 3]
            assert wave_addr & 7 == 0
            assert wave_len & 7 == 0
            assert 0 < loop_cnt < 65536
            ctrl = (0x1 << 11) | (loop_level << 8)
            return [wave_addr >> 3, wave_len >> 3, loop_cnt, ctrl]

        def loop_stop_seq(wave_addr, wave_len, loop_level, jump_addr):
            assert loop_level in [0, 1, 2, 3]
            assert wave_addr & 7 == 0
            assert wave_len & 7 == 0
            assert 0 <= loop_cnt < 4095
            ctrl = (0x2 << 11) | (loop_level << 8)
            return [wave_addr >> 3, wave_len >> 3, jump_addr, ctrl]

        ctrl = 0x8 << 11
        seq_T = [address >> 3, length >> 3, 0, ctrl]
        loop_cnt = 4000  # 每一级循环都是10000次，4级就是10000的4次方，每一条序列都会输出50us波形
        seq_L1 = loop_start_seq(address, length, 0, loop_cnt)
        seq_L2 = loop_start_seq(address, length, 1, loop_cnt)
        seq_L3 = loop_start_seq(address, length, 2, loop_cnt)
        seq_L4 = loop_start_seq(address, length, 3, loop_cnt)
        seq_J1 = loop_stop_seq(address, length, 0, 1)
        seq_J2 = loop_stop_seq(address, length, 1, 2)
        seq_J3 = loop_stop_seq(address, length, 2, 3)
        seq_J4 = loop_stop_seq(address, length, 3, 4)
        ctrl = 0x8000
        seq_S = [address >> 3, length >> 3, 0, ctrl]
        seq = seq_T + seq_L1 + seq_L2 + seq_L3 + seq_L4 + seq_J4 + seq_J3 + seq_J2 + seq_J1 + seq_S
        return seq

    def setGain(self, channel, gain):
        assert channel >= 0 and channel <= 4
        assert gain >= 1 and gain <= 2
        channels = [1, 2, 3, 4] if channel == 0 else [channel]
        for channel in channels:
            self.da.set_gain(channel, self.__getGainCode(gain))

    def __getGainCode(self, gain):
        if gain < 1 or gain > 2:
            raise ValueError('Gain should be in the range of [1, 2].')
        gainCode = int((gain - 1) * 1023)
        gainCode += 512
        gainCode %= 1024
        # print(f'gain {gain} as code {gainCode}')
        return gainCode

    def turnOn(self, channel):
        assert channel >= 1 and channel <= 4
        self.da.start_output_wave(channel)

    def turnOff(self, channel):
        assert channel >= 1 and channel <= 4
        self.da.stop_output_wave(channel)

    def turnOnAllChannels(self):
        self.da.start_output_wave(0)

    def turnOffAllChannels(self):
        self.da.stop_output_wave(0)

if __name__ == '__main__':
    dev = AWGUDPServer('172.20.8.33')

    waveform = ([32000] * 2 * 20000 + [-32000] * 2 * 80000)
    waveforms = [waveform, waveform, waveform, waveform]

    dev.generateWaveform(waveforms)