# -*- coding: utf-8 -*-
import ctypes
import time
import numpy as np
import math
import struct
import socket
from Instrument.WaveformGenerator.USTCDAC.logging_util import logger

def get_host_ip():
    addrs = socket.getaddrinfo(socket.gethostname(), None)
    for item in addrs:
        if item[-1][0].find('10.0') > -1:
            return item[-1][0]
    return '10.0.255.255'

class VirtualDll:
    def __init__(self, da_id):
        self.da_id = da_id

    def __getattr__(self, name):
        def func(*args, **kargs):
            return 0

        return func


#   函数类型抽象
class FuncType(object):
    def __init__(self, func_type, ins, para1, para2, desc):
        self.func_type = func_type
        self.ins = ins
        self.para1 = para1
        self.para2 = para2
        self.desc = desc


#   返回结果抽象
class RetResult(object):
    OK = 0
    ERROR = 1

    def __init__(self, resp_stat, resp_data, data):
        self.resp_stat = resp_stat
        self.resp_data = resp_data
        self.data = data


#   DA板的抽象
#   调用DA板驱动进行设备操作、DA板参数配置、DA通道参数配置

def format_data(data_in):
    length = len(data_in)
    data = [0 for x in range(0, length)]
    for i in range(0, length):
        data[i] = data_in[i]
    if not ((divmod(length, 32))[1] == 0):  # 补齐32bit
        length = int((math.floor(length / 32) + 1) * 32)
        data = [0 for x in range(0, length)]
        temp_len = len(data_in)
        for i in range(0, temp_len):
            data[i] = data_in[i]
    return data


operation_dic = {'none': 0, 'para': 1, 'data': 2, 'para fast': 3, 'data fast': 4}


class RawBoard(object):
    def __init__(self):
        self.id = None
        self.connect_status = 0
        self.ip = '127.0.0.1'
        self.port = 80
        self.timeout = 2
        self.timeout_cnt = 0
        self.para_addr_list = []
        self.para_data_list = []
        self.sockfd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sockfd.settimeout(self.timeout)
        self.commiting = operation_dic['none']

    def connect(self):
        """Connect to Server, 如果设备通信超时计数累计到5次时，重配置FPGA
        2020 04 21 上海市电力局进行断电实验，209实验室设备瞬时断电重启，
        部分AWG FPGA逻辑会出现通信故障率高的情况，此时对AWG设备进行FPGA重启后通信故障现象消失
        """
        if self.timeout_cnt >= 5:
            logger.critical(f'{self.ip} timeout count reach 5, will repogram the fpga.')
            self.DA_reprog()
        count = 5
        while count > 0:
            try:
                if self.sockfd is None:
                    self.sockfd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sockfd.settimeout(self.timeout)
                self.sockfd.connect((self.ip, self.port))
                logger.info(f'{self.ip} connect sucessful.')
                self.connect_status = 1
                return 0
            except:
                self.connect_status = 0
                self.sockfd.close()
                self.sockfd = None
            count -= 1
            logger.info("DAC {} connect {} failed".format(self.id, 5 - count))
            time.sleep(1)
        if self.sockfd is None:
            logger.error("DAC %s connect failed!", self.id)
            return 1

    def disconnect(self):
        """Close the connection to the server."""
        if self.connect_status == 1:
            self.connect_status = 0
            self.sockfd.close()
            self.sockfd = None
        else:
            logger.error("DAC %s already disconnected!", self.id)
        return 0

    def init_tcp(self):
        '''重置AWG TCP连接，防止上一个TCP连接未完成时，新的TCP连接不是重新开始的情况'''
        init_cmd = struct.pack('I', 0xDEADBEEF)
        try:
            self.sockfd.send(init_cmd * 3)
            self.sockfd.recv(8)
        except:
            logger.error(f'{self.id} init tcp failed')
            pass

    def DA_reprog(self):
        """AWG FPGA 逻辑重配置"""
        self.timeout_cnt = 0
        wait_time = 15
        print(f'da reprog please wait {wait_time} seconds')
        packet = struct.pack("LLL", 0x00000105, 2, 1)
        self.send_data(packet)
        self.disconnect()
        for i in range(int(wait_time)):
            time.sleep(1)
        self.connect()
        # print('da reprog done')
        return 0

    def send_data(self, msg):
        """Send data over the socket."""
        totalsent = 0
        sent = 0
        exc_cnt = 0
        while totalsent < len(msg):
            try:
                sent = self.sockfd.send(msg)
            except:
                self.timeout_cnt += 1
                # print(f'{self.id} send faild msg: {len(msg)}, {msg}')
                self.connect()
                print(self.para_addr_list)
                self.init_tcp()
                exc_cnt += 1
                if exc_cnt > 5:
                    return -1
                continue
            totalsent = totalsent + sent
        return 0

    def receive_data(self):
        """Read received data from the socket."""
        chunks = []
        bytes_recd = 0
        try:
            while bytes_recd < 8:
                # I'm reading my data in byte chunks
                chunk = self.sockfd.recv(min(8 - bytes_recd, 4))
                if chunk == '':
                    raise RuntimeError("Socket connection broken")
                chunks.append(chunk)
                bytes_recd = bytes_recd + len(chunk)
        except:
            # self.sockfd.settimeout(8)
            self.timeout_cnt += 1
            print(f'{self.id} recv faild')
            # print(self.para_addr_list)
            self.connect()
            self.init_tcp()
            return -1, -1
        stat_tuple = struct.unpack('L', chunks[0])
        data_tuple = struct.unpack('L', chunks[1])
        stat = stat_tuple[0]
        data = data_tuple[0]
        return stat, data

    def receive_RAM(self, length):
        """Read received data from the socket after a read RAM command."""
        ram_data = b''
        bytes_recd = 0
        # self.sockfd.settimeout(self.timeout)
        while bytes_recd < length:
            # I'm reading my data in byte chunks
            chunk = self.sockfd.recv(min(length - bytes_recd, 1024))
            # Unpack the received data
            ram_data += chunk
            if chunk == '':
                raise RuntimeError("Socket connection broken")
            bytes_recd = bytes_recd + len(chunk)
        return ram_data

    def Write_Reg(self, bank, addr, data):
        """Write to register command."""
        cmd = 0x02
        # I need to pack bank into 4 bytes and then only use the 3
        packedBank = struct.pack("l", bank)
        unpackedBank = struct.unpack('4b', packedBank)

        packet = struct.pack("4bLL", cmd, unpackedBank[0], unpackedBank[1], unpackedBank[2], addr, data)
        # Next I need to send the command
        self.send_data(packet)
        # print(f'{self.id} receive Write_Reg')
        stat, data = self.receive_data()
        if stat != 0x0:
            logger.info(f'{self.id} Write_Reg Issue with Write Command stat: {stat}')
            return -1

        return 0

    def Read_Reg(self, bank, addr, data=0xFAFAFAFA):
        """Read from register command."""
        # data is used for spi write
        cmd = 0x01

        # I need to pack bank into 4 bytes and then only use the 3
        packedBank = struct.pack("l", bank)
        unpackedBank = struct.unpack('4b', packedBank)

        packet = struct.pack("4bLi", cmd, unpackedBank[0], unpackedBank[1], unpackedBank[2], addr, data)
        # Next I need to send the command
        self.send_data(packet)
        stat, data = self.receive_data()
        if stat != 0x0:
            logger.info(f'{self.id} Read_Reg Issue with Write Command stat: {stat}')
            return -1
        return data

    def read_memory(self, addr, length):
        """Read from RAM command."""
        cmd = 3
        pad = 0xFAFAFA

        # I need to pack bank into 4 bytes and then only use the 3
        packedPad = struct.pack("l", pad)
        unpackedPad = struct.unpack('4b', packedPad)

        packet = struct.pack("4bLL", cmd, unpackedPad[0], unpackedPad[1], unpackedPad[2], addr, length)
        # Next I need to send the command
        self.send_data(packet)
        # next read from the socket
        recv_stat, _ = self.receive_data()
        if recv_stat != 0x0:
            logger.info(f'{self.id}: read_memory Issue with Reading RAM stat: {recv_stat}')
            return recv_stat
        ram_data = self.receive_RAM(round(length))
        return ram_data

    def write_memory(self, start_addr, wave):
        """Write to RAM command."""
        count = 5
        while count > 0:
            cmd = 0x04
            pad = 0xFFFFFF
            # I need to pack bank into 4 bytes and then only use the 3
            packedPad = struct.pack("L", pad)
            unpackedPad = struct.unpack('4b', packedPad)
            length = len(wave) << 1  # short 2 byte
            packet = struct.pack("4bLL", cmd, unpackedPad[0], unpackedPad[1], unpackedPad[2], start_addr, length)
            # Next I need to send the command
            self.send_data(packet)
            # next read from the socket
            recv_stat, _ = self.receive_data()
            if recv_stat != 0x0:
                logger.info(f'{self.id} write_memory send cmd Error stat={recv_stat}!!!')
                return recv_stat
            # method 1
            format = "{0:d}H".format(len(wave))
            packet = struct.pack(format, *wave)
            self.send_data(packet)
            # next read from the socket to ensure no errors occur
            recv_stat, recv_data = self.receive_data()
            if recv_stat == -1 and recv_data == -1:
                logger.info("重连%d............" % (5 - count))
                self.disconnect()
                self.timeout_cnt += 1
                self.connect()
                count -= 1
                continue
            if recv_stat != 0x0:
                logger.info(f'{self.id} write_memory send data Error stat={recv_stat}!!!')
                return recv_stat
            return 0
        return 1

    def write_command(self, ctrl, data0, data1):
        """write command."""
        packet = struct.pack("LLL", ctrl, data0, data1)
        self.send_data(packet)
        stat, data = self.receive_data()
        if stat != 0x0:
            logger.error(f'{self.id}: write_command Error, cmd: {hex(ctrl)}, error stat={stat}!')
        return stat


class DABoard(RawBoard):
    is_block = 0  # is run in a block mode
    channel_amount = 4  # DA板通道个数，依次为X、Y、DC、Z

    def __init__(self, id="E08", ip="10.0.4.8", port=80, connect_status=0, trig_interval_l1=200e-6,
                 trig_interval_l2=0.001,
                 trig_count_l1=10, trig_count_l2=1, output_delay=0, channel_gain=None,
                 channel_default_voltage=None, data_offset=None, trig_out_delay_step=None,
                 output_delay_step=None, sample_rate=0.5e-9, sync_delay=None, channel_sampling_ratio=None,
                 batch_mode=True):
        super(DABoard, self).__init__()
        if channel_gain is None:
            channel_gain = [511 for x in range(0, self.channel_amount)]
        if channel_default_voltage is None:
            channel_default_voltage = [32768 for x in range(0, self.channel_amount)]
        if data_offset is None:
            data_offset = [0 for x in range(0, self.channel_amount)]
        if trig_out_delay_step is None:
            trig_out_delay_step = [4 for x in range(0, self.channel_amount)]
        if output_delay_step is None:
            output_delay_step = [4 for x in range(0, self.channel_amount)]
        if sync_delay is None:
            sync_delay = [0 for x in range(0, self.channel_amount)]
        if channel_sampling_ratio is None:
            channel_sampling_ratio = [1 for x in range(0, self.channel_amount)]
        # 赋值

        self.host_ip = get_host_ip()
        self.id = id  # DA板配置表标识
        self.ip = ip.encode()  # DA板IP
        self.port = port  # DA板端口号
        self.connect_status = connect_status  # DA板连接状态
        self.batch_mode = batch_mode
        self.waves = [None] * 4
        self.seqs = [None] * 4

        self.f_id = 0  # DA板文件句柄

        self.da_trig_delay_offset = 0  # DA板触发延时偏置
        self.channel_voltage_offset = [0 for x in range(0, self.channel_amount)]  # voltage offset
        # 记录数据库中需初始化的信息
        self.channel_gain_info = channel_gain
        self.channel_default_voltage_info = channel_default_voltage
        self.trig_interval_l1_info = trig_interval_l1  # DA板默认触发间隔
        self.trig_interval_l2_info = trig_interval_l2  # DA板默认触发间隔
        self.trig_count_l1_info = trig_count_l1
        self.trig_count_l2_info = trig_count_l2
        self.trig_source = 0  ## 选择触发模块通道做触发输出
        self.output_delay_info = output_delay  # DA板输出延时
        self.data_offset = data_offset
        self.trig_out_delay_step = trig_out_delay_step
        self.output_delay_step = output_delay_step
        self.sample_rate = sample_rate
        self.sync_delay = sync_delay  # DA板同步延时
        self.channel_sampling_ratio = channel_sampling_ratio  # DA板超采样
        # 记录配置到板子的信息
        self.channel_gain = [None for x in range(0, self.channel_amount)]
        self.channel_default_voltage = channel_default_voltage
        self.trig_interval_l1 = None  # DA板默认触发间隔
        self.trig_interval_l2 = None  # DA板默认触发间隔
        self.trig_count_l1 = trig_count_l1
        self.trig_count_l2 = None
        self.trig_delay = None  # DA板触发延时
        self.trig_delay_width = None
        self.output_delay = None  # DA板输出延时

    @property
    def is_mock(self):
        return 'mock' in self.id.lower()

    def block(self):
        if self.is_block == 1:
            self.get_return(1)

    def set_para(self, bank, addr, data=0):
        self.para_addr_list.append((bank << 16) | addr)
        self.para_data_list.append(data)
        if len(self.para_addr_list) > 128:
            logger.error("set para addr length out of range")
            self.para_addr_list.clear()
            self.para_data_list.clear()
            return -1

    def commit_para(self):
        if not self.batch_mode:
            return 0
        cmd_cnt = len(self.para_data_list)
        if cmd_cnt == 0:
            return 0
        msg = struct.pack('BBBB', 0x06, 0, 0, cmd_cnt)
        for addr, data in zip(self.para_addr_list, self.para_data_list):
            msg = msg + struct.pack('LL', addr, data)
        self.commiting = operation_dic['para']
        ret = self.send_data(msg)
        if ret == 0:
            return ret
        return -1

    def commit_mem(self):
        if not self.batch_mode:
            return 0
        cmd = [0x07, 1, 2, 3]
        packet = b''
        for wave, seq in zip(self.waves, self.seqs):
            if wave is None:
                cmd.append(0)
                cmd.append(0)
                cmd.append(0)
                cmd.append(0)
            else:
                cmd.append(0)
                cmd.append(len(wave) << 1)
                packet += struct.pack(f'{len(wave)}H', *wave)
                cmd.append(0)
                cmd.append(len(seq) << 1)
                packet += struct.pack(f'{len(seq)}H', *seq)

        format = "4B16I"
        _head = struct.pack(format, *cmd)
        packet = _head + packet
        self.commiting = operation_dic['data']
        ret = self.send_data(packet)
        if ret == 0:
            return ret
        return -1

    def commit_mem_fast(self):
        if not self.batch_mode:
            return 0
        cmd = [0x07, 1, 2, 3]
        packet = b''
        ch = 0
        for wave, seq in zip(self.waves, self.seqs):
            ch += 1
            if wave is None:
                cmd.append(0)  # wave start addr
                cmd.append(0)  # wave len
                cmd.append(0)  # seq start addr
                cmd.append(0)  # seq len
            else:
                cmd.append(0)
                cmd.append(len(wave) << 0)
                packet += wave  # struct.pack(f'{len(wave)}H', *wave)
                cmd.append(0)
                cmd.append(len(seq) << 0)
                packet += seq  # struct.pack(f'{len(seq)}H', *seq)

        if len(packet) == 0:
            return 0
        format = "4B16I"
        _head = struct.pack(format, *cmd)
        packet = _head + packet
        self.commiting = operation_dic['data fast']
        ret = self.send_data(packet)
        if ret == 0:
            return ret
        return -1

    def wave_calc_fast(self, channel, wave=None):
        '''
        波形写入时，末尾先补20ns的默认电压数据，再按64字节对齐进行补齐
        :param channel: AWG 通道
        :param wave: 波形数据，波形数据要求为numpy数组类型，取值范围[0，65535]
        :return: uint16 类型 numpy array
        '''
        # import matplotlib.pyplot as plt
        # plt.plot(wave[:200])
        # plt.show()
        data_offset = self.data_offset[channel - 1] + 32768
        pad_cnt = 40 + (32 - ((len(wave) + 40) & 31))
        data = np.pad(wave, [0, pad_cnt], 'constant', constant_values=(0, 0))  # 补齐64字节0
        data = data + data_offset  # 校准后的偏置
        data = np.clip(data.astype('<u2'), 0, 65535)
        return data

    def write_wave_fast(self, channel, offset=0, wave=None):
        '''
        写入波形数据
        :param channel: AWG通道，[1,2,3,4]
        :param offset: 起始地址，目前只支持0
        :param wave: 波形数据, 每通道波形长度小于100,000采样点
        :return:
        '''
        if channel < 1 or channel > self.channel_amount:
            logger.error(f"[{self.id}] wrong channel: {channel}")
            return 3
        if len(wave) > 10e4:
            logger.error("DAC %s write wave failed, wave length:%d out of range 100k!", self.id, len(wave))
            return 3
        # t1 = time.time()
        data = self.wave_calc_fast(channel, wave)
        # t2 = time.time()
        # print(f'{self.id} {channel} wave calc time {round(t2-t1, 5)} {len(data)}')
        start_addr = ((channel - 1) << 19) + 2 * offset
        if self.batch_mode:
            # 无波形长度限制
            self.waves[channel - 1] = data.tobytes()
            return 0
        else:
            ret = self.write_memory(start_addr, data)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s write wave failed, return is: %d!", self.id, ret)
        return ret

    def write_seq_fast(self, channel, offset=0, seq=None):
        '''
        写入波形数据
        :param channel: AWG通道，[1,2,3,4]
        :param offset: 起始地址，目前只支持0
        :param seq: 序列数据，每通道序列数据长度<16384, 序列数据长度为4的整数倍
        :return:
        '''
        if len(seq) & 0x3 != 0 or len(seq) > 16384:
            logger.error('DAC %s length of seq %s shuld be multipule of 4 and less than 16384', self.id, len(seq))
            return 3

        if channel < 1 or channel > self.channel_amount:
            logger.error(f"[{self.id}] wrong channel: {channel}")
            return 3
        # 将序列数据补齐成64字节整数倍
        pad_cnt = (32 - (len(seq) & 31)) & 31
        seq = np.pad(seq, [0, pad_cnt], 'constant', constant_values=(0, 0))  # 补齐64字节0
        seq = seq.astype('uint16')
        start_addr = ((channel * 2 - 1) << 18) + offset * 8  # 序列的内存起始地址，单位是字节
        if self.batch_mode:
            self.seqs[channel - 1] = seq.tobytes()
            return 0
        else:
            ret = self.write_memory(start_addr, seq)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s write seq failed!", self.id)
        return ret

    def init_device(self):
        #   初始化设备
        #   1、硬件状态检测，读取状态寄存器，若状态异常，则进行硬件初始化（init_board），初始化后重新检测硬件状态；
        #   重复该步骤知道硬件状态正常或达到最大尝试次数，若最终状态为异常，则报错并推出初始化流程
        #   2、默认参数配置
        #   3、设置通道增益、通道默认电压值
        #   4、打开DA芯片
        is_ready = self.is_mock
        try_count = 10
        while try_count > 0 and is_ready == 0:
            if self.read_device_status() == 0:
                is_ready = 1
            else:
                self.init_board()
                time.sleep(1)

            try_count = try_count - 1
            if try_count == 5 or try_count == 6:
                logger.error(f"{self.id} init device failed 5 times,try to reprogram fpga")
                self.DA_reprog()

        if is_ready == 0:
            logger.error("init device failed")
            return 3

        self.set_trig_interval_l1(self.trig_interval_l1_info)
        self.set_loop(1, 1, 1, 1)
        self.set_da_output_delay(self.output_delay_info)
        self.set_trig_delay(200e-9)
        self.set_trig_count_l2(1)
        self.set_trig_interval_l2(0.001)
        self.stop_output_wave(0)
        self.clear_trig_count()
        self.set_multi_board(0)  ## 多板工作模式
        self.set_trig_select(self.trig_source)

        for k in range(0, self.channel_amount):
            self.set_gain(k + 1, self.channel_gain_info[k])  # channel start from 1
            self.set_default_volt(k + 1, self.channel_default_voltage_info[k])
        if self.batch_mode:
            self.commit_para()
            self.wait_response()
        self.set_monitor()  ## 使能触发，并设置状态包发送的目的ip为本机ip
        self.check_status()
        return 0

    def read_device_status(self):
        '''
        读取设备状态，状态参数定义参见AWG设备状态定义表
        :return:
        '''
        ref = self.read_da_hardware_status()
        offset = [100, 121, 202, 203, 204, 205, 300, 321, 402, 403, 404, 405, 722]  # , 732]
        mask = [255, 0b11000000, 255, 255, 255, 255, 255, 0b11000000, 255, 255, 255, 255, 0b00000000]
        expection = [4, 0b11000000, 255, 255, 255, 255, 4, 0b11000000, 255, 255, 255, 255, 0b00000000]
        if isinstance(ref, int):
            return 1
        for (a, b, c) in zip(offset, mask, expection):
            if ref[a] & b != c:
                return 1
        return 0

    def clear_trig_count(self):
        ret = self.write_command(0x00001F05, 0, 0)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_count failed!", self.id)
        return ret

    def init_board(self):
        ret = self.write_command(0x00001A05, 11, 1 << 16)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s init board failed!", self.id)
        return ret

    def power_on_dac(self, chip, on_off):
        ret = self.write_command(0x00001E05, chip, on_off)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s power on failed!", self.id)
        return ret

    def sync_ctrl(self, id, val):
        '''
            id: 触发模块寄存器标识（定义见《DA服务器软件说明》）
            val: 该寄存器定义的值
        '''
        self.set_para(0, 0x40, id | val)
        if id == 2:  ## 设置DA板波形输出延时
            self.set_para(0, 0x40, val | 2)  ## 脉冲变高计数
            self.set_para(0, 0x40, (val + (4 << 16)) | 3)  ## 脉冲变低计数
        if id == 4:  ## 设置DA板输出到AD的触发输出延时
            self.set_para(0, 0x40, val | 4)  ## 脉冲变高计数
            self.set_para(0, 0x40, (val + (4 << 16)) | 5)  ## 脉冲变低计数
        if id == 9:  ## 设置一级触发间隔
            if (val >> 12) > 65535:  # 如果触发间隔大于 65535， FPGA逻辑内部总的计数器设置为65535
                self.set_para(0, 0x40, (65535 << 16) | 1)
            elif (val >> 12) <= 0:  # 如果触发间隔设为0， FPGA逻辑内部总的计数器设置为1000
                self.set_para(0, 0x40, ((4 * 250) << 16) | 1)
            else:  # 其他时候FPGA逻辑内部总的计数器与触发间隔计数相等
                self.set_para(0, 0x40, (val << 4) | 1)

    def start(self, index):
        if self.batch_mode:
            self.set_para(0, 0x20, 0)
            self.set_para(0, 0x20, index)
            return 0
        ret = self.write_command(0x00000405, index, 0)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s start failed!", self.id)
        return ret

    def stop(self, index):
        ret = self.write_command(0x00000405, index, 0)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s stop failed!", self.id)
        return ret

    def set_loop(self, arg1, arg2, arg3, arg4):
        '''
        设置AWG各通道序列执行的总循环次数
        :param arg1: 通道1循环次数 范围：(1，65535)
        :param arg2: 通道1循环次数 范围：(1，65535)
        :param arg3: 通道1循环次数 范围：(1，65535)
        :param arg4: 通道1循环次数 范围：(1，65535)
        :return:
        '''
        if arg1 not in range(1, 65535) or arg2 not in range(1, 65535) or arg3 not in range(1,
                                                                                           65535) or arg4 not in range(
                1, 65535):
            logger.error('DAC %s set_loop param out of range 0~65535', self.id)
            return 3

        if self.batch_mode:
            self.set_para(0, 0x21, (arg1 << 16) | arg2)
            self.set_para(0, 0x23, (arg3 << 16) | arg4)
            return 0
        para1 = arg1 * 2 ** 16 + arg2
        para2 = arg3 * 2 ** 16 + arg4
        ret = self.write_command(0x00000905, para1, para2)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_loop failed!", self.id)
        return ret

    def set_dac_start(self, count):
        '''
        设置AWG波形输出延时计数,每个计数代表4ns
        :param count: (0,65535)
        :return:
        '''
        if count < 0 or count > 65536:
            logger.error("DAC %s set_dac_start count %s param out of range 0~65535", self.id, count)
            return 1

        count_trans = round(count) << 16

        if count_trans > 2 ** 32 - 1:
            logger.error("DAC %s set_dac_start count param error!", self.id)
            ret = 1
            return ret
        if count != round(count):
            real = round(count) * 4
            logger.warn(
                "Da_output_delay should be a multiple of 4ns,otherwise we'll round it up.In this case,the real value of da_output_delay is {}ns".format(
                    real))
        ret = self.write_command(0x00001805, 2, count_trans)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_dac_start failed!", self.id)
        return ret

    def set_trig_start(self, count):
        '''
        设置AWG输出到AD的触发延时计数，每个计数代表4ns
        :param count: (0,65535)
        :return:
        '''
        if count < 0 or count > 65536:
            logger.error("DAC %s set_dac_start count %s param out of range 0~65535", self.id, count)
            return 1

        count_trans = round(count) << 16
        if count_trans > 2 ** 32 - 1:
            logger.error("set_trig_start count param out of range,trig_delay should be less than 262.13e-6!")
            ret = 1
            return ret
        if abs(count - round(count)) > 0.1:
            real = round(count) * 4
            logger.warn(
                "Trig_delay should be a multiple of 4ns,otherwise we'll round it up.In this case,the real value of trig_delay is {}ns".format(
                    real))
        ret = self.write_command(0x00001805, 4, count_trans)

        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_start failed!", self.id)
        return ret

    def set_multi_board(self, mode=0):
        # mode为1设置单板触发，mode为0设置多板触发
        # 1:single board mode 0: multi board mode
        if mode not in [0, 1]:
            logger.error("DAC %s set_multi_board mode %s not in [0, 1]", self.id, mode)
            return 1

        if self.batch_mode:
            self.sync_ctrl(19, mode << 16)
            return 0

        ret = self.write_command(0x00001805, 19, mode << 16)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_multi_board failed!", self.id)
        return ret

    def set_trig_select(self, ch=0):
        '''
        设置输出到AD的触发信号来源
        0，主板发出的触发
        1，2，3，4分别为AWG1，2，3，4通道输出的触发标识
        :param ch: [0,1,2,3,4]
        :return:
        '''
        if ch not in [0, 1, 2, 3, 4]:
            logger.error("DAC %s set_trig_select ch %s not in [0, 1, 2, 3, 4]", self.id, ch)
            return 1

        if self.batch_mode:
            self.sync_ctrl(20, ch << 16)
            self.trig_source = ch
            return 0

        ret = self.write_command(0x00001805, 20, ch << 16)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_select failed!", self.id)
        else:
            self.trig_source = ch
        return ret

    def set_trig_stop(self, count):
        '''
        设置AWG输出到AD的触发延时停止计数，每个计数代表4ns
        :param count: (0,65535), 大于 set_trig_start中设置的值
        :return:
        '''
        if count < 0 or count > 65536:
            logger.error("DAC %s set_trig_stop count %s param out of range 0~65535", self.id, count)
            return 1

        count_trans = round(count) << 16
        if count_trans > 2 ** 32 - 1:
            logger.error("set_trig_stop count param out of range,width+trig_delay should be less than 262.14e-6!")
            ret = 1
            return ret
        if abs(count - round(count)) > 0.1:
            real = round(count) * 4
            logger.warn(
                "Width+trig_delay should be a multiple of 4ns,otherwise we'll round it up.In this case,the real value of width+trig_delay is {}ns".format(
                    real))
        ret = self.write_command(0x00001805, 5, count_trans)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_stop failed!", self.id)
        return ret

    def send_int_trig(self):
        '''触发使能, 这条指令应该直接执行，执行时，先重置触发，防止有未运行完的触发'''
        # self.clear_trig_count()
        ret = self.write_command(0x00001805, 8, 1 << 16)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s send_int_trig failed!", self.id)
        return ret

    def set_trig_interval_l1(self, trig_interval):
        '''
        设置AWG触发模块的一级触发间隔
        :param trig_interval: 单位ns，范围，100ns~5ms
        :return:
        '''
        if trig_interval == self.trig_interval_l1:
            return 0
        if trig_interval < 1e-7 or trig_interval > 5e-3:
            logger.error("DAC %s set_trig_interval_l1 %s out of range 100ns~5ms", self.id, trig_interval)
            return 1
        count = trig_interval / 4e-9
        count_trans = round(count) << 12
        if count_trans > 2 ** 32 - 1:
            logger.error("Interval_l1 count param out of range,interval_l1 should be less than 4.19e-3!")
            ret = 1
            return ret
        if abs(count - round(count)) > 0.1:
            real = round(count) * 4
            logger.warn(
                "Interval_l1 should be a multiple of 4ns,otherwise we'll round it up.In this case,the real value of interval_l1 is {}ns".format(
                    real))
        if self.batch_mode:
            self.sync_ctrl(9, count_trans)
            self.trig_interval_l1 = trig_interval
            return 0
        ret = self.write_command(0x00001805, 9, count_trans)

        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_interval failed!", self.id)
        else:
            self.trig_interval_l1 = trig_interval
        return ret

    def set_trig_interval_l2(self, trig_interval):
        '''
        设置AWG触发模块的二级触发间隔
        :param trig_interval: 单位ns，范围，100ns~5ms
        :return:
        '''
        if trig_interval == self.trig_interval_l2:
            return 0
        if trig_interval < 1e-7 or trig_interval > 5e-3:
            logger.error("DAC %s set_trig_interval_l2 %s out of range 100ns~5ms", self.id, trig_interval)
            return 1
        count = trig_interval / 4e-9
        count_trans = round(count) << 12
        if count_trans > 2 ** 32 - 1:
            logger.error("Interval_l2 count param out of range,interval_l2 should be less than 4.19e-3!")
            ret = 1
            return ret
        if abs(count - round(count)) > 1e-9:
            real = round(count) * 4
            logger.warn(
                "Interval_l2 should be a multiple of 4ns,otherwise we'll round it up.In this case,the real value of interval_l2 is {}ns".format(
                    real))
        if self.batch_mode:
            self.sync_ctrl(15, count_trans)
            self.trig_interval_l2 = trig_interval
            return 0
        ret = self.write_command(0x00001805, 15, count_trans)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_interval failed!", self.id)
        else:
            self.trig_interval_l2 = trig_interval
        return ret

    def set_trig_count_l1(self, count):
        '''
        设置AWG出发模块一级触发个数
        :param count: (1，100000)
        :return:
        '''
        if count < 1 or count > 100000:
            logger.error("DAC %s set_trig_count_l1 count %s param out of range 1~65535", self.id, count)
            return 1

        if count == self.trig_count_l1:
            return 0
        if self.batch_mode:
            self.sync_ctrl(10, count << 12)
            self.trig_count_l1 = count
            return 0

        ret = self.write_command(0x00001805, 10, count << 12)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_count failed!", self.id)
        else:
            self.trig_count_l1 = count
        return ret

    def set_trig_count_l2(self, count):
        '''
        设置AWG出发模块二级触发个数
        :param count: (1，100000)
        :return:
        '''
        if count < 1 or count > 100000:
            logger.error("DAC %s set_trig_count_l2 count %s param out of range 1~65535", self.id, count)
            return 1

        if count == self.trig_count_l2:
            return 0

        if self.batch_mode:
            self.sync_ctrl(16, count << 12)
            self.trig_count_l2 = count
            return 0
        ret = self.write_command(0x00001805, 16, count << 12)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_count failed!", self.id)
        else:
            self.trig_count_l2 = count
        return ret

    def set_monitor(self, ip=None):
        '''
        实时修改AWG状态包发送的目的IP地址, 如果没有输入IP地址，使用本机IP
        调用者负责IP地址的合法性
        ip like: '10.0.1.101'
        :return:
        '''
        _ip_para = 0
        ip = self.host_ip if ip is None else ip
        logger.info(f"DAC {self.id} set monitor ip to: {ip}")
        for idx, _d in enumerate(ip.split('.')):
            _ip_para = _ip_para | (int(_d) << (24 - idx * 8))
        self.write_command(0x00001305, 1, _ip_para)
        return 0

    def clear_trig_count(self):
        '''
        重置AWG触发，该函数能强制停止AWG正在输出的触发
        :return:
        '''
        ret = self.write_command(0x00001F05, 0, 0)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_trig_count failed!", self.id)
        return ret

    def set_trig_delay(self, point, width=10 * 4e-9):
        '''
        设置AWG输出到AD的触发的延时
        :param point: 单位ns，范围 0-256us
        :param width: 宽度默认为40ns，point+width 转换后的计数<65536
        :return:
        '''
        if point < 0 or point > 2.56e-4:
            logger.error("DAC %s set_trig_delay ponit %s param out of range 0-256us", self.id, point)
            return 1
        start = round((self.da_trig_delay_offset + point) / 4e-9 + 1)
        stop = round((self.da_trig_delay_offset + point) / 4e-9 + width / 4e-9)
        if stop > 65536:
            logger.error("DAC %s set_trig_delay stop %s param out of range 65535", self.id, stop)
            return 1
        if self.trig_delay == start and self.trig_delay_width == width:
            return 0
        self.trig_delay = start
        self.trig_delay_width = width

        if self.batch_mode:
            self.sync_ctrl(4, start << 16)
            self.sync_ctrl(5, stop << 16)
            return 0

        ret1 = self.set_trig_start(start)
        ret2 = self.set_trig_stop(stop)
        return ret1 | ret2

    def set_da_output_delay(self, delay):
        '''
        设置AWG波形触发输出的延时，输出宽度40ns
        :param delay: 单位ns，范围 0-256us, delay转换后的计数+10<65536
        :return:
        '''
        if delay < 0 or delay > 2.56e-4:
            logger.error("DAC %s set_da_output_delay delay %s param out of range 0-256us", self.id, delay)
            return 1
        count = round((delay) / 4e-9 + 1)
        if count + 10 > 65536:
            logger.error("DAC %s set_da_output_delay count+10 %s param out of range 65536", self.id, count + 10)
            return 1
        if delay == self.output_delay:
            return 0
        if self.batch_mode:
            self.sync_ctrl(2, count << 16)
            self.sync_ctrl(3, (count + 10) << 16)
            return 0
        else:
            ret = self.set_dac_start(delay / 4e-9 + 1)
            self.output_delay = delay
            return ret

    def set_gain(self, channel, gain):
        '''
        设置通道增益，对应bank值为7
        :param channel: [1,2,3,4]
        :param gain: 0-1023
        :return:
        '''
        if channel < 1 or channel > self.channel_amount:
            logger.error(f"[{self.id}] wrong channel: {channel}")
            return 3
        if gain < 0:
            gain += 1024
        if gain == self.channel_gain[channel - 1]:
            return 0

        channel_map = [2, 3, 0, 1]
        channel_ad = channel_map[channel - 1]
        if self.batch_mode:
            chip_sel = (channel_ad >> 1) + 1
            addr = 0x040 + ((channel_ad & 0x01) << 2)
            self.set_para(chip_sel, addr, (gain >> 8) & 0x03)
            self.set_para(chip_sel, addr + 1, gain & 0xFF)
            return 0
        ret = self.write_command(0x00000702, channel_ad, gain)
        if not ret == 0:
            self.disp_error(ret)
            logger.error("DAC %s set_gain failed!", self.id)
        self.channel_gain[channel - 1] = gain
        return ret

    def set_default_volt(self, channel, volt):
        '''
        设置AWG各通道的默认电压输出码值
        如果volt值为-1，表示对应AWG通道的波形输出在停止后，
        电压会保持为波形输出的最后一个电压值，该功能特性目前主要用于AWG的INL DNL校准
        :param channel: [1,2,3,4]
        :param volt: -1 或 volt+对应通道的offset < 65536
        :return:
        '''
        if channel < 1 or channel > self.channel_amount:
            logger.error(f"[{self.id}] wrong channel: {channel}")
            return 3
        hold = False
        offset = self.data_offset[channel - 1]
        if volt != -1:
            volt = 65535 - volt
            if volt > 65535:
                volt = 65534
            if volt < 0:
                volt = 0
        else:  # hold模式 1 to 3 2 to 4 3to 5
            hold = True
            channel = channel + 3
            volt = 32768

        if volt == self.channel_default_voltage[channel - 1]:
            return 0
        if round(volt - offset) < 0 or round(volt - offset) > 65535:
            logger.critical('set volt out of range')
            return -1
        if self.batch_mode:
            _code = round(volt - offset)
            _code1 = ((_code & 0xFF) << 24) | ((_code & 0xFF00) << 8)
            self.set_para(0, 0x41, (_code1 | (channel - 1)))
            self.channel_default_voltage[channel - 1] = volt
            ret = 0
        else:
            if hold:
                ret = self.write_command(0x00001B05, channel, round(volt - offset))
            else:
                ret = self.write_command(0x00001B05, channel - 1, round(volt - offset))
                self.channel_default_voltage[channel - 1] = volt
                if not ret == 0:
                    self.disp_error(ret)
                    logger.error("DAC %s set_default_volt failed!", self.id)
        return ret

    def start_output_wave(self, channel):
        '''
        使能波形输出，打开某一个通道；channel为0时，打开所有通道
        :param channel: [0,1,2,3,4]
        :return:
        '''
        ret = 0
        if channel > 0 and channel < self.channel_amount + 1:
            index = 1 << (channel - 1)
            ret = self.start(index)
            if not ret == 0:
                self.disp_error(ret)
                logger.error("DAC %s start_output_wave failed!", self.id)
        elif channel == 0:
            ret = 0
            for i in range(1, self.channel_amount + 1):
                index = 1 << (i - 1)
                ret0 = self.start(index)
                if not ret0 == 0:
                    self.disp_error(ret)
                    logger.error("DAC %s start_output_wave failed!", self.id)
                    ret = ret0
        return ret

    def stop_output_wave(self, channel):
        '''
        停止波形输出，关闭某一个通道；channel为0时，关闭所有通道
        :param channel: [0,1,2,3,4]
        :return:
        '''
        if channel > 0:
            index = 1 << (channel - 1 + self.channel_amount)
            ret = self.stop(index)
            if not ret == 0:
                self.disp_error(ret)
                logger.error("DAC {} channel {} stop_output_wave failed!".format(self.id, channel))
        elif channel == 0:
            ret = 0
            for i in range(1, self.channel_amount + 1):  # 遍历所有通道
                index = 1 << (i - 1 + self.channel_amount)
                ret0 = self.stop(index)
                if not ret0 == 0:
                    self.disp_error(ret)
                    logger.error("DAC {} channel {} stop_output_wave failed!".format(self.id, i))
                    ret = ret0
        return ret

    #   获取当前调用位置函数调用信息
    def get_func_type(self, offset):
        return 0

    #   获取返回值
    def get_return(self, offset):
        return 0

    #   根据错误码获取错误信息
    def disp_error(self, error_code):
        return 0

    def calc_temp(self, code):
        '''
        计算温度值
        :param code: (0,65535)
        :return:
        '''
        if code < 0 or code > 65535:
            logger.error("DAC %s calc_temp code %s param out of range 0~65535", self.id, code)
            return 3
        volt = code / 65536
        R = 10000 * volt / (1.8 - volt)
        B = 3435
        T2 = 273.15 + 25
        t = 1 / ((math.log(R / 10000) / B) + (1 / T2)) - 273.15
        return round(t, 2)

    def get_temperature(self):
        '''
        读取AWG设备温度监测值，AWG设备温度均通过状态数据读出，参见AWG状态数据定义表
        :return:
        '''
        sta = self.read_da_hardware_status()
        code = (sta[612] << 0) | (sta[613] << 8)
        dac1_temp = self.calc_temp(code)
        code = (sta[616] << 0) | (sta[617] << 8)
        dac2_temp = self.calc_temp(code)
        code = (sta[624] << 0) | (sta[625] << 8)
        amp1_temp = self.calc_temp(code)
        code = (sta[628] << 0) | (sta[629] << 8)
        amp2_temp = self.calc_temp(code)
        code = (sta[632] << 0) | (sta[633] << 8)
        amp3_temp = self.calc_temp(code)
        code = (sta[636] << 0) | (sta[637] << 8)
        amp4_temp = self.calc_temp(code)

        code = (sta[120] << 0) | (sta[119] << 8)
        chip1_temp = round(30 + 7.3 * (code - 39200) / 1000.0, 2)
        code = (sta[320] << 0) | (sta[319] << 8)
        chip2_temp = round(30 + 7.3 * (code - 39200) / 1000.0, 2)
        return chip1_temp, chip2_temp, dac1_temp, dac2_temp, amp1_temp, amp2_temp, amp3_temp, amp4_temp

    def check_status(self):
        return (0, 1, 0)

    # 主动读取DA板硬件信息，大小为1k
    def read_da_hardware_status(self):
        '''读取AWG状态数据'''
        return self.read_memory(0x80000000, 1024)

    # 设置数据偏置
    def set_data_offset(self, channel, offset):
        '''
        设置AWG偏置值, 该值会结合default volt值影响AWG默认电压输出
        :param channel: [1,2,3,4]
        :param offset: (-10000,10000)
        :return:
        '''
        if channel < 1 or channel > self.channel_amount:
            logger.error('DAC %s Wrong Channel', self.id)
            return 1

        if offset < -10000 or offset > 10000:
            logger.error("DAC %s set_data_offset offset %s param out of range -10000~10000", self.id, offset)
            return 1
        self.data_offset[channel - 1] = offset
        return 0

    def wait_response(self):
        # pdb.set_trace()
        if not self.batch_mode:
            return 0
        # 如果是提交参数，但是参数区无数据直接返回成功
        if self.commiting == operation_dic['para']:
            if len(self.para_addr_list) == 0:
                return 0
        else:
            # 否则是提交波形，如果无波形。返回成功
            if self.waves == [None] * 4:
                return 0

        # 有提交数据，等待硬件返回状态
        stat, data = self.receive_data()

        # 返回状态正常，清空指令区 或波形区
        if stat == 0:
            if self.commiting == operation_dic['para']:
                # 清空指令区
                self.para_addr_list.clear()
                self.para_data_list.clear()
            else:
                # 清空波形区
                self.waves = [None] * 4
                self.seqs = [None] * 4
            self.commiting = operation_dic['none']
            # if stat != 0:
            #     print(f'{self.id} receive data retrassminit faild')
            return stat
        # 此处 返回状态异常了 需要重传
        try_cnt = 5

        # 如果是提交指令，执行 提交，等待硬件返回，尝试5次
        if self.commiting == operation_dic['para']:
            while try_cnt > 0:
                self.commit_para()
                stat, data = self.receive_data()
                try_cnt -= 1
                if stat == 0:
                    break
            self.para_addr_list.clear()
            self.para_data_list.clear()
            self.commiting = operation_dic['none']
            if stat != 0:
                logger.error(f'{self.id} commit para retrassminit faild')
            return stat
        # 如果是提交波形，执行 提交，等待硬件返回，尝试5次
        if self.commiting == operation_dic['data']:
            while try_cnt > 0:
                self.commit_mem()
                stat, data = self.receive_data()
                try_cnt -= 1
                if stat == 0:
                    break

            self.waves = [None] * 4
            self.seqs = [None] * 4
            self.commiting = operation_dic['none']
            if stat != 0:
                logger.error(f'{self.id} commit data retrassminit faild')
            return stat
        # 如果是快速提交波形，执行 提交，等待硬件返回，尝试5次
        if self.commiting == operation_dic['data fast']:
            while try_cnt > 0:
                self.commit_mem_fast()
                stat, data = self.receive_data()
                try_cnt -= 1
                if stat == 0:
                    break
            self.waves = [None] * 4
            self.seqs = [None] * 4
            self.commiting = operation_dic['none']
            if stat != 0:
                logger.error(f'{self.id} commit data fast retrassminit faild')
            return stat
        return -1

    def write_parameter(self, addr, data):
        '''
        写入AWG配置参数
        :param addr: 参数起始地址, [0x1F80000,0x1F90000,0x1FA0000]
        :param data: 参数数据,数据字节长度上限为65536字节，256字节对齐
        :return:
        '''
        # 1. 擦除块
        # 2. 写入数据
        # 3. 回读检查
        valid_addr = [0x1F80000, 0x1F90000, 0x1FA0000]
        assert addr in valid_addr
        assert len(data) <= 65536
        pad_data = [0] * (256 - (len(data) & 0xFF))
        data += struct.pack(f'{len(pad_data)}B', *pad_data)
        self.flash_erase_sector(addr, 1)
        time.sleep(0.1)
        self.write_flash(addr, data)
        rd_data = self.read_flash(addr, len(data))
        if rd_data != data:
            print(f'flash 写入错误')
        else:
            print(f'flash 写入成功')

    def write_flash(self, addr, data):
        """ Write to FLASH command.
            data 待写入数据, 字节长度小于0xF50000
            addr 写入起始地址, 256字节对齐
            注意：如果写入数据过大，TCP通信的timeout时间要增加
            11MB数据时插JTAG时，写入时间160秒左右，不插JTAG时，写入时间30秒左右
        """
        # 地址最高位为1表示 写入FLASH操作,
        # 地址低两位为1 表示常规写入
        logger.info(f'{self.id} write flash data')
        valid_addr = [0x0000000, 0x0F50000, 0x1F80000, 0x1F90000, 0x1FA0000]
        assert addr in valid_addr
        assert len(data) <= 0xF50000
        assert addr + len(data) <= (32 << 20)
        start_addr = 0x80000000 | (addr & 0x01FFFF00) | (1)
        pad_cnt = 256 - (len(data) & 0xFF)
        pad_data = struct.pack(f'{pad_cnt}B', *([0] * pad_cnt))
        cmd = 0x04
        pad = 0xFFFFFF
        # I need to pack bank into 4 bytes and then only use the 3
        packedPad = struct.pack("L", pad)
        unpackedPad = struct.unpack('4b', packedPad)
        length = len(data)
        packet = struct.pack("4bLL", cmd, unpackedPad[0], unpackedPad[1], unpackedPad[2], start_addr, length)
        # Next I need to send the command
        self.send_data(packet)
        # next read from the socket
        recv_stat, _ = self.receive_data()
        if recv_stat != 0x0:
            logger.info(f'{self.id} write_memory send cmd Error stat={recv_stat}!!!')
            return recv_stat
        packet = data
        # 每1MB数据超时时间多等待15秒
        self.sockfd.settimeout(((length >> 20) + 1) * 15)
        self.send_data(packet)
        recv_stat, _ = self.receive_data()
        self.sockfd.settimeout(self.timeout)
        if recv_stat != 0x0:
            logger.info(f'{self.id} write_memory send data Error stat={recv_stat}!!!')
            return recv_stat
        return 0

        r = ['#' * i for i in range(1, 11)]
        for i in range(200):
            chunk = self.sockfd.recv(8)
            if len(chunk) == 8:
                return 0
            print("\r", self.id, '写flash', r[i % len(r)], end='', flush=True)
        print(f'{self.id} FLASH写入失败')
        return 1

    def read_flash(self, addr, length):
        '''
        地址+长度不能超过FLASH存储空间
        :param addr: 读起始地址，256字节对齐
        :param length: 读长度
        :return:
        '''
        logger.info(f'{self.id} read flash data')
        assert addr & 0xFF == 0
        assert addr + length <= (32 << 20)
        data = self.read_memory(addr, length)
        return data

    def flash_erase_sector(self, addr, sectors):
        '''
        起始地址+擦除大小应该小于FLASH存储空间大小（32MB）
        :param addr: FLASH擦除起始地址, 64kB对齐
        :param sectors: FLASH擦除块数，每一块是65536字节
        :return:
        '''
        logger.info(f'{self.id} erase flash sectors')
        assert addr + sectors * 65536 <= (32 << 20)
        assert addr & 0xFFFF == 0
        self.set_watchdog_timeout(45000, 40000)
        self.write_command(0x00000705, addr, sectors)
        self.wait_erase()

    def wait_erase(self):
        r = ['#' * i for i in range(1, 11)]
        for i in range(150):
            logger.debug(f'wait erase: {i}')
            print("\r", r[i % len(r)], end='', flush=True)
            time.sleep(0.4)
            prog_status = self.get_erase_status()
            if prog_status:
                break
            if i > 140:
                print('擦除失败')

    def flash_erase_all(self):
        '''
        擦除整个FLASH，FLASH擦除时间在100秒左右，擦除后FPGA软件会自动复位，此时上位机需要重连设备
        擦除后设备的默认ip地址如果有拨码开关，且拨码开关的值不是全0或全F，IP地址为拨码开关值
        否则擦除自动复位后的IP为10.0.1.101
        :return:
        '''
        r = ['*' * i for i in range(1, 11)]
        logger.info(f'{self.id} erase flash all')
        self.set_watchdog_timeout(65000, 60000)
        try:
            self.write_command(0x00000605, 0, 0)
        finally:
            pass
        self.disconnect()
        #  wait 120 second
        for i in range(1200):
            print("\r", r[i % len(r)], end='', flush=True)
            time.sleep(0.1)
        self.connect()
        return 0

    def get_flash_type(self):
        status = self.read_memory(0x80000000, 1024)
        return status[937]

    def get_version(self):
        status = self.read_memory(0x80000000, 1024)
        ver = struct.unpack('4B', status[716:720])
        return ver[::-1]

    def get_erase_status(self):
        status = self.read_memory(0x80000000, 1024)
        return status[916] == 0xFF

    def set_watchdog_timeout(self, reprog_timeout, reset_timeout):
        '''
        设置DA板底层逻辑复位和重配置的超时时间，
        reprog_timeout 重配置超时计数，单位10ms每计数
        reset_timeout 重复位超时计数，单位10ms每计数
        该命令目前有以下作用
        1. 禁止喂狗
        2. 禁止底层计数第10位为1时的自动复位
        3. 超时时间到达时一定会发生复位或重配置（取决于谁的的计数小）
        小心使用，目前只打算使用在配置过程中，实现可靠重配置
        超时最大值65535
        '''
        assert reprog_timeout < 65535
        assert reset_timeout < 65535
        self.write_command(0x00000805, reprog_timeout, reset_timeout)