import socket
import time
import struct
import numpy as np
from binascii import hexlify
import os, pickle
from ezq_driver.protocol.cmu_protocol import CMUProtocol
from ezq_driver.driver import EzqDevice
# from tqdm import tqdm
from ezq_driver.utils import bytes_to_int
import matplotlib.pyplot as plt
import time as time_
from datetime import datetime, timedelta
import time


# board_ip = '10.0.9.104'


import socket
import time
import struct
import numpy as np
from binascii import hexlify
import os, pickle
from ezq_driver.protocol.cmu_protocol import CMUProtocol
from ezq_driver.driver import EzqDevice
# from tqdm import tqdm
from ezq_driver.utils import bytes_to_int
import matplotlib.pyplot as plt
import time as time_


# board_ip = '10.0.9.104'


def connect_board(board_ip='10.0.9.151'):
    # ser=socket.inet_aton(board_ip)[2]
    # num=socket.inet_aton(board_ip)[3]

    print('INFO:{}'.format(board_ip))
    cmu = EzqDevice(ip=board_ip, dev_mode=True, batch_mode=False)

    return cmu


def function_enable(cmu, on_off=1):
    # 打开或关闭波形输出
    cmu[23, 0x050000, (0x3C << 2)] = on_off


# def Internal_trig(cmu):
#     cmu[23, 0x050000, (0x20 << 2)] = 0
#     cmu[23, 0x050000, (0x74 << 2)] = 1


def start_curve(cmu):
    Internal_trig(cmu)  # 一级触发，开始准备输出


def init_freq_set(cmu, freq_set=10000000.0):
    # DDS 125M时钟
    # freq_set = 10000000  #单位Hz
    M = freq_set * (2 ** 48) / 125000000
    print("INFO:频率参数为{}".format(M))
    int_M = int(M)
    freq_L = int_M & 0xFFFFFFFF
    freq_H = (int_M >> 32) & 0xFFFF
    # print("freq_L = {}, freq_H = {}".format(freq_L, freq_H))

    cmu[23, 0x050000, (0x40 << 2)] = freq_L
    cmu[23, 0x050000, (0x44 << 2)] = freq_H
    cmu[23, 0x050000, (0x48 << 2)] = 0
    cmu[23, 0x050000, (0x4C << 2)] = 0


def load_curve(cmu):
    # 频率改变数据
    savepath = os.path.join(os.path.dirname(__file__), 'Doppler_Timing12G.pkl')
    print('loading.,......')
    # 读取
    f_read = open(savepath, 'rb')
    # f_read = open('new_data.pkl', 'rb')
    dict2 = pickle.load(f_read)
    f_read.close()
    # print(dict2)
    time = dict2['T'][:-1]
    freq = dict2['f'][:-1]
    print(len(time), len(freq))
    # time = [t * 1E9 / 10 for t in time]  # 单位ns，从0开始，被8ns整除（如不能整除会在底层被取整）
    time = [t * 1E9 for t in time]  # 单位ns，从0开始，被8ns整除（如不能整除会在底层被取整）
    freq = [f for f in freq]  # 单位Hz
    # print(time[:100])
    # print(freq[:100])
    # plt.plot(time, freq)
    # plt.show()

    # time = dict2['T'][:-1]
    # freq = dict2['f'][:-1]
    # time = [t * 1E9  for t in time]  # 单位ns，从0开始，被8ns整除（如不能整除会在底层被取整）
    # freq = [f for f in freq]  # 单位Hz
    # print(time[:1000])
    # print(freq[:1000])

    # time = time[:10000]
    # freq = freq[:10000]
    
    # time = time[:1000]
    # freq = []
    # for i in range(1000):
    #     freq.append(i * 10000)

    # print(time)
    # print(freq)

    freq_change_set(cmu, time, freq)  # 必须按照时间顺序排序，从小到大
    # plt.plot(time, freq)
    # plt.show()


def is_list_ascending(lst):
    for i in range(1, len(lst)):
        if lst[i] <= lst[i - 1]:
            return 1
    return 0


def freq_change_set(cmu, time=[], freq=[]):
    check_list = is_list_ascending(time)
    if (check_list):
        print("ERROR:时间必须从小到大")
        return
    lenth = len(time) * 8
    if (lenth < 1024):
        data_len = 1024 * 4
    else:
        data_len = ((lenth // 1024) + 1) * 1024 * 2

    # print(data_len>>2)

    if (len(time) != len(freq)):
        print("ERROR:时间和频率个数不一致")
        return

    time_clock_cycle = []
    freq_dds = []
    for i in range(len(time)):
        # print(i)
        time_clock_cycle.append(int(time[i] / 8))
        freq_dds.append(int(freq[i] * (2 ** 48) / 125000000))
    # print(time_clock_cycle)
    # print(freq_dds)
    # data_len = 128*2

    data = np.linspace(0, data_len >> 2, data_len >> 2, dtype='uint32')
    # print(len(data))
    count = 0
    # print((len(time)))
    for i in range(len(time)):
        # print(count)
        data[count] = time_clock_cycle[i] & 0xFFFFFFFF
        count = count + 1
        data[count] = ((time_clock_cycle[i] >> 32) & 0xFFFF) + ((freq_dds[i] & 0xFFFF) << 16)
        count = count + 1
        data[count] = (freq_dds[i] >> 16) & 0xFFFFFFFF
        count = count + 1
        data[count] = 1 << 31
        count = count + 1

    '''
    最后需要两个128位作为结束标志，计划是{32'hffffffff, 96'h0}作为一次时间频率序列结束标志位，
    逻辑代码bug：逻辑上同时两个寄存器流水线判断当前时间是否到达设定值，当一个寄存处读到{32'hffffffff, 96'h0}时
    状态机跳到下一状态，因此时间频率序列最后一个时间频率无法触发，在上位机层面解决此bug，因此需要两个128位时间频率
    序列作为结束标志{1'd1, 127'd0}, {32'hffffffff, 96'h0}
    '''
    data[count] = 0
    count = count + 1
    data[count] = 0
    count = count + 1
    data[count] = 0
    count = count + 1
    data[count] = 1 << 31
    count = count + 1
    data[count] = 0
    count = count + 1
    data[count] = 0
    count = count + 1
    data[count] = 0
    count = count + 1
    data[count] = 0xffffffff
    count = count + 1
    # print((freq_dds[0] & 0xFFFF))
    # print(count, len(data))
    for i in range(count, len(data)):
        data[i] = 0
    # print(data[len(data)-200:len(data)])
    # # print(data[4000:])
    cmu.write_mem(0x00F0000, data.tobytes(), slot=23)
    rd_data = cmu.read_mem(0x00F0000, data_len, slot=23)
    # for i in range(0, len(data), 4):
    #     print((data[i]), (data[i+1]), (data[i+2]), (data[i+3]))

    # for i in range(0, len(data), 4):
    #     print(hex(data[i]), hex(data[i+1]), hex(data[i+2]), hex(data[i+3]))

    # print(rd_data)
    # print(data.tobytes())

    if rd_data == data.tobytes():
        print('下载成功')
    else:
        print('下载失败')

    cmu[23, 0x050000, (0x5C << 2)] = 0x00F0000  # fpga读ddr地址
    cmu[23, 0x050000, (0x60 << 2)] = data_len  # data_len        #fpga读ddr长度
    cmu[23, 0x050000, (0x64 << 2)] = 1


def Internal_trig2(cmu):
    cmu[23, 0x050000, (0x20 << 2)] = 1


def version_fpga(cmu):
    # 固件日期
    a = cmu[23, 'CPU.FIX_DATE']
    print('INFO:固件版本:{}'.format((bytes_to_int(a))))


def reset(cmu):
    cmu[23, 0x050000, (0x5C << 2)] = 0  # fpga读ddr地址
    cmu[23, 0x050000, (0x60 << 2)] = 0  # fpga读ddr长度
    cmu[23, 0x050000, (0x64 << 2)] = 0
    cmu[23, 0x050000, (0x54 << 2)] = 0
    cmu[23, 0x050000, (0x40 << 2)] = 0
    cmu[23, 0x050000, (0x44 << 2)] = 0
    cmu[23, 0x050000, (0x48 << 2)] = 0
    cmu[23, 0x050000, (0x4C << 2)] = 0
    cmu[23, 0x050000, (0x3C << 2)] = 0
    cmu[23, 0x050000, (0x20 << 2)] = 0


def initialize(cmu, freq_set):
    for i in range(3):
        reset(cmu)  # 复位
    version_fpga(cmu)  # 查询固件版本
    init_freq_set(cmu, freq_set=freq_set)
    function_enable(cmu, 1)  # 打开波形输出，1打开，0关闭


def dopplorStart(cmu):
    load_curve(cmu)
    start_curve(cmu)


def stop(cmu):
    cmu[23, 0x050000, (0x88 << 2)] = 0  # 中断输出
    time.sleep(0.5)
    cmu[23, 0x050000, (0x88 << 2)] = 0  # 中断输出


def again_initialize(cmu):
    cmu[23, 0x050000, (0x80 << 2)] = 1  # 设置初始频率后，再次输出初始频率


def Internal_trig(cmu):
    cmu[23, 0x050000, (0x20 << 2)] = 0
    cmu[23, 0x050000, (0x74 << 2)] = 1


def startDopplor(cmu, t="2024-11-22 19:50:00", microsecond=400000):
    load_curve(cmu)
    ##################
    # start in about 15 s
    # currentTime = datetime.now()
    format = "%Y-%m-%d %H:%M:%S"
    readyTime = datetime.strptime(t, format)
    startTime = readyTime.replace(microsecond=microsecond) + timedelta(seconds=15)

    print(f'Action will be started at {startTime}.')
    print(f'{startTime - datetime.now()} s remaining.')
    # prepare TDCServer
    # from interactionfreepy import IFWorker
    # worker = IFWorker('tcp://192.168.25.5:1061')
    # worker.TFTDCServer.startDopplerShift(int(startTime.timestamp()) + 1)
    from interactionfreepy import IFWorker
    worker = IFWorker('tcp://code.qpqi.group:1261')
    worker.TFTDCServer.startDopplerShift(int(startTime.timestamp()) + 1)

    while True:
        if datetime.now() < startTime:
            time_.sleep(0.02)
        else:
            break
    start_curve(cmu)


def changeFawhile(cmu, f1, f2, change_time):
    # DDS 125M时钟
    freq1_set = f1  # 单位Hz
    freq2_set = f2  # 单位Hz
    change_time = change_time  # 单位ns,8ns整数倍

    M = freq1_set * (2 ** 48) / 125000000
    int_M = int(M)
    freq_L = int_M & 0xFFFFFFFF
    freq_H = (int_M >> 32) & 0xFFFF

    cmu[23, 0x050000, (0x94 << 2)] = freq_L
    cmu[23, 0x050000, (0x98 << 2)] = freq_H

    M = freq2_set * (2 ** 48) / 125000000
    int_M = int(M)
    freq_L = int_M & 0xFFFFFFFF
    freq_H = (int_M >> 32) & 0xFFFF

    change_time = int(change_time / 8)

    cmu[23, 0x050000, (0x9C << 2)] = freq_L
    cmu[23, 0x050000, (0xA0 << 2)] = freq_H

    # 时间
    time_high_32 = (change_time >> 32) & 0xFFFFFFFF
    time_low_32 = change_time & 0xFFFFFFFF
    cmu[23, 0x050000, (0xA4 << 2)] = time_low_32
    cmu[23, 0x050000, (0xA8 << 2)] = time_high_32

    # 开始信号
    cmu[23, 0x050000, (0xAC << 2)] = 1


    return


def TryChangeFawhile(cmu, f1, f2, change_time):
    while True:
        try:
            changeFawhile(cmu, f1, f2, change_time)
            break
        except(BaseException):
            time.sleep(0.01)
            print("try again")


def changePosition(changeposition, f2):
    change_time = 10000000  # ns
    f1 = f2 * (1 + changeposition/change_time)  # Hz
    TryChangeFawhile(cmu, f1=f1, f2=f2, change_time=change_time)


if __name__ == '__main__':
    # Only this main block is added; all original functions above are unchanged.
    # Do not call reset() or initialize(): initialize() includes a reset.
    # TryChangeFawhile retries the complete hardware command with a 10 ms wait.
    import math
    import json
    import tempfile
    from pathlib import Path

    def correction_plan(delay_ps, frequency, direction=1):
        """Validate inputs and convert ps into the driver's Hz/ns arguments."""
        for name, value in (('delay_ps', delay_ps), ('frequency', frequency)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{name} must be a finite number')
        if direction not in (-1, 1):
            raise ValueError('direction must be +1 or -1')
        duration_ns = 10000000  # Fixed by the original changePosition().
        f1 = frequency * (1 + direction * delay_ps / (duration_ns * 1000))
        if any(not 125000000 / 2 ** 48 <= f < 125000000 for f in (frequency, f1)):
            raise ValueError('DDS frequencies must be between the tuning resolution and 125 MHz')
        return {'DelayPs': delay_ps, 'FrequencyHz': frequency,
                'TemporaryFrequencyHz': f1, 'DurationNs': duration_ns, 'Direction': direction}


    class DDSDelayService:
        """Correct measured delays in ps using a temporary DDS frequency offset."""
        def __init__(self, board_ip='10.0.9.51', frequency=10E6,
                     retry_interval=0.001,
                     settle_time=0.001, direction=1,
                     frequency_file=None):
            if not math.isfinite(retry_interval) or retry_interval <= 0:
                raise ValueError('retry_interval must be positive and finite')
            if not math.isfinite(settle_time) or settle_time < 0:
                raise ValueError('settle_time must be nonnegative and finite')
            self.frequency_file = None if frequency_file is None else Path(frequency_file)
            frequency_source = 'main/default'
            if self.frequency_file is not None and self.frequency_file.exists():
                try:
                    with self.frequency_file.open(encoding='utf-8') as f:
                        saved = json.load(f)
                    if saved['BoardIP'] != board_ip:
                        raise ValueError('saved DDS board IP does not match')
                    frequency = saved['FrequencyHz']
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f'Invalid DDS frequency file {self.frequency_file}: {exc}') from exc
                frequency_source = str(self.frequency_file)
            # Reject invalid configurations before entering an unlimited retry loop.
            correction_plan(0, frequency, direction)
            self.board_ip = board_ip
            self.frequency = frequency
            self.retry_interval = retry_interval
            self.settle_time = settle_time
            self.direction = direction
            self.cmu = None
            self._ready = False
            self._status = {'State': 'AwaitingStartup', 'LastError': None}
            print(f'DDS nominal frequency: {self.frequency:.12g} Hz, board={board_ip}, '
                  f'source={frequency_source}, persistence={self.frequency_file}', flush=True)

        def getStatus(self):
            return dict(self._status, FrequencyHz=self.frequency, Ready=self._ready)

        def start(self):
            """Apply the loaded nominal frequency before accepting corrections."""
            if self._ready:
                return self.getStatus()
            self._status = {'State': 'SynchronizingFrequency', 'LastError': None}
            print(f'DDS startup: applying nominal frequency {self.frequency:.12g} Hz '
                  f'to board {self.board_ip}; corrections disabled until success', flush=True)
            while True:
                try:
                    self.cmu = connect_board(self.board_ip)
                    # initialize() includes a reset; call only these setup functions.
                    version_fpga(self.cmu)
                    init_freq_set(self.cmu, freq_set=self.frequency)
                    function_enable(self.cmu, 1)
                    break
                except Exception as exc:
                    self._status['LastError'] = str(exc)
                    print(f'DDS startup initialization failed: {exc}; retrying', flush=True)
                    time.sleep(self.retry_interval)
            global cmu
            cmu = self.cmu
            changePosition(0, self.frequency)
            self._status['State'] = 'Settling'
            time.sleep(0.01 + self.settle_time)
            self._ready = True
            self._status.update(State='Ready', LastError=None)
            print(f'DDS startup synchronized: {self.frequency:.12g} Hz, '
                  f'board={self.board_ip}; ready for corrections', flush=True)
            return self.getStatus()

        def getFrequency(self):
            """Return the nominal frequency in Hz."""
            return self.frequency

        def _save_frequency(self):
            path = self.frequency_file
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                                 prefix=path.name + '.', suffix='.tmp', delete=False) as f:
                    temporary = Path(f.name)
                    json.dump({'BoardIP': self.board_ip, 'FrequencyHz': self.frequency,
                               'UpdatedAt': time.time()}, f, indent=2)
                    f.write('\n')
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()

        def setFrequency(self, frequencyHz):
            """Apply a new nominal frequency in Hz, then atomically persist it."""
            correction_plan(0, frequencyHz, self.direction)
            if self.frequency_file is None:
                raise RuntimeError('No frequency persistence file configured')
            old_frequency = self.frequency
            self._status = {'State': 'SettingFrequency',
                            'TargetFrequencyHz': frequencyHz, 'LastError': None}
            print(f'DDS nominal frequency change requested: {old_frequency:.12g} -> '
                  f'{frequencyHz:.12g} Hz, board={self.board_ip}', flush=True)
            # f1 == f2 applies the new frequency without an extra phase excursion.
            global cmu
            cmu = self.cmu
            changePosition(0, frequencyHz)
            self._status['State'] = 'Settling'
            time.sleep(0.01 + self.settle_time)
            self.frequency = frequencyHz
            self._status['State'] = 'SavingFrequency'
            try:
                self._save_frequency()
            except Exception as exc:
                self._status.update(State='PersistenceError', LastError=str(exc))
                print(f'DDS frequency applied: {frequencyHz:.12g} Hz, but saving to '
                      f'{self.frequency_file} failed: {exc}', flush=True)
                raise RuntimeError('DDS frequency applied but persistence failed; retry setFrequency') from exc
            self._status.update(State='Success', LastError=None)
            print(f'DDS nominal frequency changed: {old_frequency:.12g} -> '
                  f'{frequencyHz:.12g} Hz; saved to {self.frequency_file}', flush=True)
            return self.getStatus()

        def correctDelay(self, delayPs):
            """Block until correction completes; changePosition takes ns and lasts 10 ms."""
            plan = correction_plan(delayPs, self.frequency, self.direction)
            self._status = dict(plan, State='Correcting', LastError=None)
            if delayPs == 0:
                self._status['State'] = 'Success'
                return self.getStatus()
            global cmu
            cmu = self.cmu
            changePosition(self.direction * delayPs / 1000, self.frequency)
            self._status['State'] = 'Settling'
            time.sleep(0.01 + self.settle_time)
            self._status.update(State='Success', LastError=None)
            return self.getStatus()


    def main():
        # 服务连接与 DDS 参数直接在此处配置。
        broker = 'tcp://tf.qpqi.group:1161'
        service_name = 'DDSClock'
        board_ip = '10.0.9.51'
        frequency = 10E6              # 无持久化设置时使用的默认标称频率，Hz。
        frequency_file = Path(__file__).with_name(f'dds20261023_{board_ip}_frequency.json')
        retry_interval = 0.001       # 启动连接或初始化失败等待 1 ms；补偿由原函数重试，等待 10 ms。
        settle_time = 0.001          # 频偏过程结束后的额外等待时间，s。
        direction = 1               # +1：正延迟使 DDS 提前；-1：反转补偿方向。
        registration_timeout = 5    # IFWorker 注册超时，s。

        service = DDSDelayService(board_ip=board_ip, frequency=frequency,
                                  retry_interval=retry_interval,
                                  settle_time=settle_time, direction=direction,
                                  frequency_file=frequency_file)
        service.start()  # 同步设置标称频率，成功后再注册服务。
        from interactionfreepy import IFWorker, IFLoop
        worker = IFWorker(broker, service_name, service, timeout=registration_timeout)
        print(f'DDS service {service_name} registered at {broker}, board={board_ip}; hardware ready', flush=True)
        try:
            IFLoop.join()
        except KeyboardInterrupt:
            print('DDS service stopped.', flush=True)
        finally:
            worker.close()


    main()
