from Instrument.WaveformGenerator.USTCDAC.da_board import *

class USTCDACServer:
    def __init__(self, ip, port=80, sessionPermenent=False, singleBoard=False):
        self.ip = ip
        self.port = port
        self.dev = None
        self.sessionInited = False
        self.sessionPermenent = sessionPermenent
        self.beginSession()
        self.dev.set_loop(1, 1, 1, 1)
        self.dev.set_multi_board(0 if not singleBoard else 1)
        self.dev.set_trig_select(0)
        self.endSession()

    def beginSession(self):
        if (not self.sessionInited) or (not self.sessionPermenent):
            self.dev = DABoard(id='{}:{}'.format(self.ip, self.port), ip=self.ip, port=self.port, batch_mode=False)
            self.dev.connect()

    def endSession(self):
        if (not self.sessionPermenent):
            self.dev.disconnect()
            self.dev = None

    def turnOn(self, channel):
        assert channel >= 1 and channel <= 4
        self.dev.start_output_wave(channel)

    def turnOff(self, channel):
        assert channel >= 1 and channel <= 4
        self.dev.stop_output_wave(channel)

    def turnOnAllChannels(self):
        for i in range(1, 5):
            self.turnOn(i)

    def turnOffAllChannels(self):
        for i in range(1, 5):
            self.turnOff(i)

    def writeWaveform(self, channel, wave):
        print('writing waveform of ', channel, 'with length of ', len(wave), wave[0: 20])

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

        wave_addr = 0  # 波形存储在0地址开始的地方
        length = len(wave)  # 100k采样点，50us波形
        ctrl = 0x8 << 11
        seq_T = [wave_addr >> 3, length >> 3, 0, ctrl]
        loop_cnt = 4000  # 每一级循环都是10000次，4级就是10000的4次方，每一条序列都会输出50us波形
        seq_L1 = loop_start_seq(wave_addr, length, 0, loop_cnt)
        seq_L2 = loop_start_seq(wave_addr, length, 1, loop_cnt)
        seq_L3 = loop_start_seq(wave_addr, length, 2, loop_cnt)
        seq_L4 = loop_start_seq(wave_addr, length, 3, loop_cnt)
        seq_J1 = loop_stop_seq(wave_addr, length, 0, 1)
        seq_J2 = loop_stop_seq(wave_addr, length, 1, 2)
        seq_J3 = loop_stop_seq(wave_addr, length, 2, 3)
        seq_J4 = loop_stop_seq(wave_addr, length, 3, 4)
        ctrl = 0x8000
        seq_S = [wave_addr >> 3, length >> 3, 0, ctrl]
        seq = seq_T + seq_L1 + seq_L2 + seq_L3 + seq_L4 + seq_J4 + seq_J3 + seq_J2 + seq_J1 + seq_S

        self.dev.write_seq_fast(channel, seq=seq)
        self.dev.write_wave_fast(channel, wave=wave)

    def sendTrigger(self, interval1, count1, interval2, count2):
        self.dev.clear_trig_count()
        self.dev.set_trig_count_l1(count1)
        self.dev.set_trig_interval_l1(interval1)
        self.dev.set_trig_count_l2(count2)
        self.dev.set_trig_interval_l2(interval2)
        self.dev.send_int_trig()

class MergedUSTCDACServer:
    def __init__(self, awgs, channelMapping):
        self.awgs = awgs
        self.channelMapping = channelMapping

    def turnOn(self, channel):
        mappedChannel = self.channelMapping[channel]
        self.awgs[mappedChannel[0]].beginSession()
        self.awgs[mappedChannel[0]].turnOn(mappedChannel[1])
        self.awgs[mappedChannel[0]].endSession()

    def turnOff(self, channel):
        mappedChannel = self.channelMapping[channel]
        self.awgs[mappedChannel[0]].beginSession()
        self.awgs[mappedChannel[0]].turnOff(mappedChannel[1])
        self.awgs[mappedChannel[0]].endSession()

    def turnOnAllChannels(self):
        for awg in self.awgs:
            awg.beginSession()
            awg.turnOnAllChannels()
            awg.endSession()

    def turnOffAllChannels(self):
        for awg in self.awgs:
            awg.beginSession()
            awg.turnOffAllChannels()
            awg.endSession()

    def writeWaveform(self, channel, wave):
        mappedChannel = self.channelMapping[channel]
        self.awgs[mappedChannel[0]].beginSession()
        self.awgs[mappedChannel[0]].writeWaveform(mappedChannel[1], [(2 * v - 1) * 32765 for v in wave])
        self.awgs[mappedChannel[0]].endSession()

    def sendTrigger(self, awgIndex, interval1, count1, interval2, count2):
        dev = self.awgs[awgIndex]
        dev.beginSession()
        dev.sendTrigger(interval1, count1, interval2, count2)
        dev.endSession()


if __name__ == '__main__':
    from interactionfreepy import IFWorker
    from interactionfreepy import IFLoop

    aliceAwg = USTCDACServer('192.168.25.237', sessionPermenent=True)
    IFWorker('tcp://192.168.25.5:224', 'USTCAWG_Alice', aliceAwg, force=True)
    # aliceAwg.sendTrigger(1e-3, 60000, 1e-3, 60000)

    bobAwg = USTCDACServer('192.168.25.236', sessionPermenent=True)
    IFWorker('tcp://192.168.25.5:224', 'USTCAWG_Bob', bobAwg, force=True)
    # bobAwg.sendTrigger(1e-3, 60000, 1e-3, 60000)
    IFLoop.join()
