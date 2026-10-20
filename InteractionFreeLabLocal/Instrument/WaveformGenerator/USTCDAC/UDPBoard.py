# 	FileName:UDPBoard.py
# 	Author:LinJin
# 	E-mail:18685029093@163.com
# 	All right reserved @ LinJin.
# 	Modified: 2020.12.18
#   Description:The class of udp board

import socket
import time
import sys
import os

from types import coroutine
import struct
import math
try:
    from .logging_util import logger
except:
    from logging_util import logger
from itertools import repeat
from collections import Counter
import asyncio
import numpy as np
class UDPBoard(object):
    """
        硬件对象
        实现与硬件的连接，

        """

    def __init__(self, ip, port=10000, id=None, connect_status=0,trig_interval_l1=200e-6,trig_interval_l2=0.001,
                 trig_count_l1=10,trig_count_l2=1, output_delay=0, channel_gain=None, is_mock=0,
                channel_default_voltage=None, data_offset=None, trig_out_delay_step=None, 
                 output_delay_step=None, sample_rate=0.5e-9, sync_delay=None, channel_sampling_ratio=None):
        self.RSV_FLAG = 0x0A000000
        self.id     = id
        self.ip     = ip
        self.port   = port
        self.is_mock=is_mock
        self.bufsize    = 1024 * 1024 * 2
        # Create a UDP socket
        self.sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockfd.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.bufsize)
        self.sockfd.settimeout(0.5)
        self.soft_version = None
        self.da_trig_delay_offset = 0  # DA板触发延时偏置
        self.channel_amount = 4
        if channel_gain is None:
            channel_gain = [511 for x in range(0, self.channel_amount)]
        if channel_default_voltage is None:
            channel_default_voltage = [32768 for x in range(0, self.channel_amount)]
        if data_offset is None:
            data_offset = [0 for x in range(0, self.channel_amount)]
        
        # 记录配置到板子的信息
        self.channel_gain = channel_gain
        self.channel_default_voltage = channel_default_voltage
        self.trig_interval_l1 = trig_interval_l1  # DA板默认触发间隔
        self.trig_interval_l2 = trig_interval_l2  # DA板默认触发间隔
        self.trig_count_l1 = trig_count_l1
        self.trig_count_l2 = trig_count_l2
        self.trig_delay = None  # DA板触发延时
        self.trig_delay_width=None
        self.output_delay = output_delay  # DA板输出延时
        self.data_offset = data_offset

        self.max_read_size = 1<<19
        self.cmd_list = []
        self.tdest_map = {'CH1_SEQ':4, 'CH1_WAVE':5, 'CH2_SEQ':6, 'CH2_WAVE':7, 'CH3_SEQ':8, 'CH3_WAVE':9, 'CH4_SEQ':10, 'CH4_WAVE':11}
        self.mem_map = {'CH1_WAVE':0x10000000,
                        'CH2_WAVE':0x20000000,
                        'CH3_WAVE':0x30000000,
                        'CH4_WAVE':0x40000000,
                        'CH1_SEQ':0x7F800000,
                        'CH2_SEQ':0x7FA00000,
                        'CH3_SEQ':0x7FC00000,
                        'CH4_SEQ':0x7FE00000,
                    }
        self.vid_map = {'CPU': 32, 'TRIG':15, 'CPU_RAM':1, 'FEEDBACK':14, 'AWG':16, 'DAC1':5, 'DAC2':6, 'CLOCK':3}

    def connect(self):
        return
    def disconnect(self):
        return
    def virtual_id_check(self, virtual_id):
        assert virtual_id in self.vid_map.values(), f'virtual_id: {virtual_id}'
    def gen_read_reg(self, addr, virtual=1, virtual_id=0):
        if virtual==0:
            assert addr < 0x1000000
            self.cmd_list.extend([0xFFFFFFFF, 0x00000000 | addr])
        else:
            assert addr < 0x10000
            self.virtual_id_check(virtual_id)
            self.cmd_list.extend([0xFFFFFFFF, 0x40000000 | addr | (virtual_id << 16)])
        assert len(self.cmd_list) <= (1464 >> 2)

    def gen_write_reg(self, addr, data, virtual=1, virtual_id=0):
        # print(f'addr-{hex(addr)}, data-{data}, virtual_id-{virtual_id}')
        if virtual==0:
            assert addr < 0x1000000
            self.cmd_list.extend([data, 0x20000000 | addr])
        else:
            assert addr < 0x10000
            self.virtual_id_check(virtual_id)
            self.cmd_list.extend([data, 0x60000000 | addr | (virtual_id << 16)])
        assert len(self.cmd_list) <= (1464 >> 2)

    def read_write_regs(self, analyse=False):
        """[读写寄存器操作]
        Bits	    Name	    功能
        63  	    VARIABLE	是否为变长指令，变长指令该位为1
        62  	    RSV	        0
        61  	    RSV	        0
        60~56	    RSV	        5bit 01010
        55~32	    LENGTH	    用来定义附加定长指令字节数
        31~0	    RSV	        0
        REG_RW[…]	REG_RW	    要操作的寄存器读写指令，1条或多条，总字节长度不超过1464
                                单条定长指令最大支持183条寄存器访问指令
        Returns:
            [type]: [description]
        """  
        assert   len(self.cmd_list) > 0, '没有寄存器命令'
        msg = struct.pack(f'{len(self.cmd_list)}I', *self.cmd_list)
        cmd_bytes_num = len(msg)
        cmd_head = [0, cmd_bytes_num | self.RSV_FLAG]
        cmd_bytes = struct.pack('II', *cmd_head)+msg
        _len = len(cmd_bytes)
        assert _len <= 1472
        try_cnt = 5
        
        while try_cnt > 0:
            try:
                self.sockfd.sendto(cmd_bytes, (self.ip, self.port))
                data = self.sockfd.recvfrom(2048)
                self.cmd_list = []
                if analyse:
                    return struct.unpack(f'{len(data[0][8:])>>2}I', data[0][8:])
                return data[0][8:]
            except:
                try_cnt -= 1
                print(f'寄存器读写重传：{5-try_cnt}')
        return None
    # def read_write_regs(self, msg):
    #     """[读写寄存器操作]
    #     Bits	    Name	    功能
    #     63  	    VARIABLE	是否为变长指令，变长指令该位为1
    #     62  	    RSV	        0
    #     61  	    RSV	        0
    #     60~56	    RSV	        5bit 01010
    #     55~32	    LENGTH	    用来定义附加定长指令字节数
    #     31~0	    RSV	        0
    #     REG_RW[…]	REG_RW	    要操作的寄存器读写指令，1条或多条，总字节长度不超过1464
    #                             单条定长指令最大支持183条寄存器访问指令
    #     Returns:
    #         [type]: [description]
    #     """    
    #     cmd_bytes_num = len(msg)
    #     cmd_head = [0, cmd_bytes_num | self.RSV_FLAG]
    #     cmd_bytes = struct.pack('II', *cmd_head)+msg
    #     _len = len(cmd_bytes)
    #     assert _len <= 1472
    #     self.sockfd.sendto(cmd_bytes, (self.ip, self.port))
    #     data = self.sockfd.recvfrom(_len)
    #     return data[8:]
    
    def _gen_read_mem_cmd(self, addr, length):
        """[summary]
        Bits	Name	功能
        63	    MEM_REG	指令类型，存储指令该位为1
        62	    LAST	是否是最后1帧，1表示是最后一帧，读数据时用于清零发送数据帧计数，见返回数据格式定义。
        61	    R/W	    读写选择，0：读，1：写
        60~56	RSV	    5bit 01010
        55~32	LENGTH	用来定义附加数据的长度，单位是字节（要求数据长度是1kB的整数倍)
        31~0	ADDR	用来定义读写的位置，单位是字节（要求数据地址是1kB的整数倍)

        Args:
            addr (u32): [写存储器地址，单位字节]
            length ([u32]): [description]

        Returns:
            [list]: [指令]
        """        
        rw_seg = 6 << 29
        cmd_list = [addr & 0x7FFFFFFF, rw_seg|length|self.RSV_FLAG]
        cmd = struct.pack('2I', *cmd_list)
        return cmd

    def _gen_write_mem_cmd(self, idx, addr, is_last=False):
        """[summary]
        Bits	Name	功能
        63	    MEM_REG	指令类型，存储指令该位为1
        62	    LAST	是否是最后1帧，1表示是最后一帧，写数据时用于属于同一批数据的帧数判断。
                        逻辑收到该帧后，写入数据，同时主动返回1帧数据，表示已接收到多少帧数据，
                        清零已接收数据帧计数，见返回数据格式定义。
        61	    R/W	    读写选择，0：读，1：写
        60~56	RSV	    5'b01010
        55~32	LENGTH	用来定义附加数据的长度，单位是字节（固定1024)， 写存储的时候表示帧序号
        31~0	ADDR	用来定义读写的位置，单位是字节（要求数据地址是1024字节的整数倍)
        DATA[…]	DATA	要传输的数据，其字节数由LENGTH指示

        Args:
            addr (u32): [写存储器地址，单位字节]
            length ([u32]): [description]
            is_last (bool, optional): [description]. Defaults to False.

        Returns:
            [list]: [指令]
        """        
        rw_seg = 7 << 29 if is_last else 5 << 29 
        cmd_list = [addr & 0x7FFFFFFF, rw_seg|idx|self.RSV_FLAG]
        cmd = struct.pack('2I', *cmd_list)
        return cmd

    def _recv_memory(self, length):
        """Read received data from the socket after a read RAM command.
           在接收数据的过程中可能会超时，
           此时数据可能还是在正常传输的, 出错后可能需要清空UDP协议栈缓存
        """
        _length = (length >> 10)*1032
        resp = bytearray(_length)
        view = memoryview(resp)
        rlen = _length
        while rlen > 0:
            try:
                nbytes = self.sockfd.recv_into(view, rlen)
                if nbytes == 0:
                    raise 'err'
                view = view[nbytes:]
                rlen -= nbytes
            except:
                print(f'error, recved bytes: {hex(rlen)}')
                return None
        return resp

    def read_device_status(self):
        '''
        读取设备状态，状态参数定义参见AWG设备状态定义表
        :return:
        '''
        self.gen_read_reg(0x147, virtual_id = self.vid_map['DAC1'])
        self.gen_read_reg(0x147, virtual_id = self.vid_map['DAC2'])
        reg = self.read_write_regs(analyse=True)
        # print(reg)
        if reg[0] != 0xC0 or reg[2] != 0xC0:
            print('error')
            return 1
        return 0

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
        # if gain == self.channel_gain[channel-1]:
            # return 0

        channel_map = [2, 3, 0, 1]
        channel_id = channel_map[channel - 1]
        virtual_id = self.vid_map['DAC1'] if channel_id < 2 else self.vid_map['DAC2']
        addr = 0x040 + ((channel_id & 0x01) << 2)
        self.gen_write_reg(addr, (gain >> 8) & 0x03, virtual_id = virtual_id)
        self.gen_write_reg(addr+1, gain & 0xFF, virtual_id = virtual_id)
        print(f'gain, addr1:{hex(addr)}, d1:{(gain >> 8) & 0x03}, addr2:{hex(addr+1)}, d2:{gain & 0xFF}')
        reg = self.read_write_regs(analyse=True)
        print('reg is', reg)
        self.channel_gain[channel-1]=gain

    def init_board(self):
        self.sockfd.settimeout(5)
        self.gen_write_reg(40, 5, virtual_id = self.vid_map['CPU'])
        self.read_write_regs()
        self.sockfd.settimeout(0.1)

    def init_device(self):
        #   初始化设备
        #   1、硬件状态检测，读取状态寄存器，若状态异常，则进行硬件初始化（init_board），初始化后重新检测硬件状态；
        #   重复该步骤知道硬件状态正常或达到最大尝试次数，若最终状态为异常，则报错并推出初始化流程
        #   2、默认参数配置
        #   3、设置通道增益、通道默认电压值
        #   4、打开DA芯片
        self.stop_output_wave(0)
        self._check_awg_idle()
        is_ready = self.is_mock
        try_count = 10
        while try_count > 0 and is_ready == 0:
            if self.read_device_status()==0:
                is_ready=1
            else:
                self.init_board()
                time.sleep(1)

            try_count = try_count - 1
            if try_count == 5 or try_count == 6:
                logger.error(f"{self.id} init device failed 5 times,try to reprogram fpga")
                self.reboot()

        if is_ready == 0:
            logger.error("init device failed")
            return 3
        self.set_loop(1,1,1,1)
        return 0

    def clear_udp(self):
        while True:
            try:
                data, addr = self.sockfd.recvfrom(8192)
                print(data, addr)
            except:
                return

    def recover_data(self, data):
        _len = len(data)
        rd = np.frombuffer(data, dtype='uint32')
        rd1 = rd.reshape(int(_len/1032), 258)
        rd2 = rd1[:, 2:]
        rd3 = rd2.reshape(256*(int(_len/1032))*1,)
        # return rd3
        return rd3.tobytes()

    def _read_memory(self, addr, length, recover=True):
        """[读写存储器]

        Args:
            addr ([int]): [起始地址，单位：字节, 地址需要为1024字节整数倍]
            length ([int]): [读取长度，单位：字节, 长度需要为1024字节整数倍]
            recover ([bool]): [是否要恢复数据，默认恢复，返回字节数据]

        Returns:
            [bytes]: [返回的读取数据]
        """
        self._check_awg_idle()
        # print(f'memory read: addr {addr}, length {length}')
        pad_cnt = (1024 - (length & 0x3FF)) & 0x3FF
        _length = pad_cnt + length
        assert _length & (1024-1) == 0, '长度需要为1024字节整数倍'
        assert addr & (1024-1) == 0, '地址需要为1024字节整数倍'
        repeats =  int((_length+(self.max_read_size-1)) / self.max_read_size)
        data = b''
        try:
            for i in range(repeats-1):
                cmd = self._gen_read_mem_cmd(addr, self.max_read_size)
                self.sockfd.sendto(cmd, (self.ip, self.port))
                data += self._recv_memory(self.max_read_size)
                addr += self.max_read_size
            
            _len = _length - (repeats-1)*self.max_read_size
            # print(f'memory read: addr {addr}, length {_len}')
            ## 数据的接收和处理可以开成多线程的方式，流水发送和处理 能达到最高的带宽利用
            cmd = self._gen_read_mem_cmd(addr, _len)
            self.sockfd.sendto(cmd, (self.ip, self.port))
            data += self._recv_memory(_len)
        except:
            self.clear_udp()
            return False, None
        # print(hex(_length),hex(len(data)))
        return True, data[:length] if not recover else self.recover_data(data)[:length]
    
    def read_memory(self, addr, length, recover=True):
        test_cnt = 0
        while test_cnt < 5:
            data = self._read_memory(addr, length, recover)
            if self.check_ddr():
                return data
            print(f'存储读重传：{test_cnt}')
        assert test_cnt < 5, f'数传失败'
        return None
    
    def _check_awg_idle(self):
        self.gen_read_reg(0x80, virtual_id = self.vid_map['AWG'])
        self.gen_read_reg(0x84, virtual_id = self.vid_map['AWG'])
        self.gen_read_reg(0x88, virtual_id = self.vid_map['AWG'])
        self.gen_read_reg(0x8C, virtual_id = self.vid_map['AWG'])
        reg = self.read_write_regs(analyse=True)
        sta = (reg[0] | reg[2] | reg[4] | reg[6]) & 0x01
        if sta:
            self.stop_output_wave(0)
            time.sleep(0.5)

    def _write_memory(self, addr, data):
        """[读写存储器]

        Args:
            addr ([int]): [起始地址，单位：字节, 地址需要为1024字节整数倍]
            length ([int]): [读取长度，单位：字节, 长度需要为1024字节整数倍]

        Returns:
            [bytes]: [返回的读取数据]
        """
        length = len(data)
        pad_cnt = (1024 - (length & 0x3FF)) & 0x3FF
        if pad_cnt:
            p_data = [0]*pad_cnt
            pad_data = struct.pack(f'{pad_cnt}B', *p_data)
            data += pad_data
        length = len(data)
        assert (length & (1024-1)) == 0, '长度需要为1024字节整数倍'
        assert addr & (1024-1) == 0, '地址需要为1024字节整数倍'
        repeats =  length >> 10
        # print(f'write mem addr {addr}, len {length}')
        # cmd = self._gen_write_mem_cmd(addr, 1024)
        for i in range(repeats-1):
            cmd = self._gen_write_mem_cmd(i, addr)
            msg = cmd + data[i<<10:(i+1)<<10]
            self.sockfd.sendto(msg, (self.ip, self.port))
            addr += 1024
        cmd = self._gen_write_mem_cmd(repeats-1, addr, is_last=True)
        msg = cmd + data[(repeats-1)<<10:repeats<<10]
        self.sockfd.sendto(msg, (self.ip, self.port))
        try:
            data = self.sockfd.recvfrom(2048)[0]
            # print(data)
            ret = struct.unpack(f'{len(data)>>2}I', data)
            missed_frame = ret[1]
            hardware_received_frame = ret[0]
            if(hardware_received_frame != repeats):
                print(f'hardware recieved pacekt count is {hardware_received_frame} of {repeats}, missed {missed_frame}')
            # assert hardware_received_frame == repeats
            missed_frame_cnt = repeats - hardware_received_frame
            return missed_frame_cnt, missed_frame
        except:
            return 2, 0

    def write_memory(self, addr, data):
        self._check_awg_idle()
        ret = 0
        test_cnt = 0
        while test_cnt < 5:
            missed_frame_cnt, missed_frame = self._write_memory(addr, data)
            if missed_frame_cnt == 1:
                addr = addr + (missed_frame << 10)
                _cnt, _missed = self._write_memory(addr, data[missed_frame << 10:(missed_frame+1) << 10])
                if _cnt == 0:
                    if self.check_ddr():
                        ret = 1
                        break
            elif missed_frame_cnt == 0:
                if self.check_ddr():
                    break
            ret = 1
            test_cnt += 1 
            print(f'存储写重传整组：{test_cnt}')
        assert test_cnt < 5, f'数传失败'
        return ret

    def writeFlash(self,addr,msg,ddr_address=0x58000000):
        print(f'Flash write has started')
        while True:
            err = self.write_memory(ddr_address, msg)
            rd_data = self.read_memory(ddr_address, len(msg))[1]
            if rd_data==msg:
                print(f'Write Data to DDR. Done')
                break  
        self.ddr2flash(ddr_address, addr,len(msg))
        print(f'Flash write has completed')
        return err


    def readFlash(self,addr,_len, expect_data=None,ddr_address=0x58000000):
        self.flash2ddr(addr,ddr_address,_len)
        rd_data = self.read_memory(ddr_address, _len)[1]
        if expect_data is not None:
            s = 'ok' if rd_data == expect_data else 'no'
            print(f'data compare is {s}')
        return rd_data
    def clear_ddr_error(self):
        self.gen_write_reg(0x0022_0020, 1, virtual=0)
        self.read_write_regs(analyse=True)

    def check_ddr(self):
        """[检查DDR状态]

        Args:
            clear (bool, optional): [清除DDR状态]. Defaults to False.

        Returns:
            [type]: [description]
        """        
        self.gen_read_reg(0x0022_0024, virtual=0)
        reg = self.read_write_regs(analyse=True)[0]
        # print(hex(reg))
        if reg & 0x0F:
            print('DDR state is abnormal')
            self.clear_ddr_error()
            return False
        return True
    def compare_data(self, bf_data, rd_bf_data):
        """[比较文件]

        Args:
            bf_data ([bytes]): [配置文件]
            rd_bf_data ([list]): [回读的数据]
        """
        compare_sta = True

        if bf_data == rd_bf_data:
            compare_sta = True
        else:
            compare_sta = False
            print('data compare failed')
        return compare_sta

    def config_check(self, flash_data):
        '''
        获取带配置文件的信息， 文件长度， 配置类型， FLASH配置地址
        :param source_file_name: FPGA配置文件名字
        :return:
        '''
        board_flash_type = self.get_flash_type()
        head_bytes = flash_data[88:92]
        MICRON_FLAG = b'\x30\x03\xe0\x01'
        file_flash_type = 0 if(head_bytes == MICRON_FLAG) else 3
        if board_flash_type != file_flash_type:
            print(f'flash type not match, {board_flash_type}, {board_flash_type}')
            return False, 0
        
        flash_addr_pos = 124 if(head_bytes == MICRON_FLAG) else 104

        fallbacken = flash_data[flash_addr_pos+11]
        file_flash_nxt_addr = struct.unpack('>l',flash_data[flash_addr_pos:flash_addr_pos+4])[0]
        
        valid = 0
        if file_flash_nxt_addr == 0x00F50000 and fallbacken == 15:
            valid = 1
            config_addr = 0x00000000
        if file_flash_nxt_addr == 0 and fallbacken == 0:
            valid = 1
            config_addr = 0x00F50000

        if valid == 0:
            print('flash data check failed')
            return False, 0
        return True, config_addr

    def remote_config(self, filename):
        #     """[远程配置FPU/EPU]
        # 配置过程
        # 1. 读文件
        # 2. 检查输入参数，槽位及其对应的配置文件是否匹配
        # 4. 写入待配置EPU/FPU，DDR并检查
        # 5. 启动FLASH配置
        # 6. 回读FLASH数据并检查
        # 7. 配置成功，重启
        # Args:
        #     slots ([list]): [target slot list]
        #     filename ([str]): [待配置文件名]
        # """

        # 1. 读文件
        filesize = os.path.getsize(filename)
        bf_data = None
        with open(filename, 'rb') as bf:
            bf_data = bf.read(filesize)
        
        sta, flash_addr = self.config_check(bf_data)
        if not sta:
            return

        pad_cnt = (1024-(len(bf_data) & 0x3FF)) & 0x3FF
        bf_data += b'0'*pad_cnt
        # print(hex(len(bf_data)))
        # return
        # 2. TODO: 检查文件中的特定域
        # flash_addr = 0x0000000 if fileType=='golden' else 0xF50000
        self.writeFlash(flash_addr,bf_data)
        self.readFlash(flash_addr,len(bf_data),bf_data)
       
    def get_flash_type(self):
        self.gen_read_reg(72,virtual_id = self.vid_map['CPU'])
        return self.read_write_regs(analyse=True)[0]

    def reboot(self):
        self.gen_write_reg(0x80080,1,virtual= 0)
        try:
            self.read_write_regs()
        except:
            pass
        time.sleep(15)

    def memory_test(self, test_type=0, data_type=2, test_time=60):
        """[存储测试， 包含功能测试，压力测试，边界测试]
        data_type:累加数-2，全0数-0，全1数-1
        每种测试要覆盖：累加数，全0数，全1数
        test_type-0:功能测试指读写1MB数据
        test_type-1:边界测试1,1kB数据读写，
        test_type-2:边界测试2,64MB数据读写
        test_type-3:压力测试：1MB数据在2GB存储空间循环遍历读写，持续48小时以上，数据以累加数，全0数，全1数交替读写
        Args:
            test_type (int, optional): [description]. Defaults to 0.
            test_time (int, optional): [压力测试时的测试时间，单位：秒]
        """ 
        
        s_map = {0:'常规', 1:'边界-1kB', 2:'边界-64MB', 3:'压力'}
        def gen_test_data(data_type, test_type):
            len_map = {0:1<<20, 1:1<<10, 2: 1<<26, 3:1<<20} 
            length = len_map[test_type]>>2
            
            if test_type == 3:
                d0 = np.zeros((length,1), dtype='uint32')
                d1 = np.zeros((length,1), dtype='uint32')+0xFFFFFFFF
                d2 = np.linspace(0, length, length, dtype='uint32')
                return d0, d1, d2

            if data_type == 0:
                return np.zeros((length,1), dtype='int32')

            if data_type == 1:
                return np.zeros((length,1), dtype='int32')+0xFFFFFFFF

            if data_type == 2:
                return np.linspace(0, length, length, dtype='uint32')
        
        def test(hw, addr, msg):
            err = hw.write_memory(addr, msg)
            sta, rd_data = hw.read_memory(addr, len(msg))
            s = 'ok' if rd_data == msg else 'no'
            err = 1 if not sta else err
            return s, err
        addr = [0]
        if test_type == 0 or test_type == 1:
            addr = [0, 0x10000000]
        
        if test_type != 3:
            data = gen_test_data(data_type, test_type)
            ts = time.time()
            for a in addr:
                ret = test(self, a, data.tobytes())[0]
                print(f'memory test test type-{s_map[test_type]}, data type: {data_type}, addr: {hex(a)}, result: {ret}')
            te = time.time()
            print(f'测试时间：{round(te-ts, 3)}秒')
            return
        
        ts = time.time()
        test_cnt = 0
        retrans = 0
        d0, d1, d2 = gen_test_data(data_type, test_type)
        data = [d0.tobytes(), d1.tobytes(), d2.tobytes()]
        while True:
            tc = time.time()
            if tc-ts > test_time:
                print('test finish')
                break
            msg = data[test_cnt%3]
            addr = (test_cnt << 20) & 0x7FFFFFFF
            ret, err = test(self, addr, msg)
            retrans += err
            test_cnt += 1
            print(f'memory test test type-{s_map[test_type]}, test cnt: {test_cnt}, 重传：{retrans} addr: {hex(addr)}, result: {ret}')

    def memory_self_test(self,test_time=60):
        for test_type in [0, 1 , 2]:
            for data_type in [0, 1, 2]:
                self.memory_test(test_type, data_type)
        self.memory_test(3, test_time=test_time)


    def StatusNetSet(self,IP_Address=0x0A00FFFF,PORT=7000,EN=1):
        # IP set
        hw.gen_write_reg(0x3C, IP_Address,virtual_id=self.vid_map['CPU'])
        hw.gen_write_reg(0x40, PORT,virtual_id=self.vid_map['CPU'])
        hw.gen_write_reg(0x44, EN,virtual_id=self.vid_map['CPU'])#enable status share
        self.read_write_regs()
		
    def flash2ddr(self, flashAddr,ddrAddr,flashLen):
        self.gen_write_reg(44, flashAddr,virtual_id=self.vid_map['CPU'])#flash addr
        self.gen_write_reg(20, ddrAddr,virtual_id=self.vid_map['CPU'])#ddr addr        
        self.gen_write_reg(48, flashLen,virtual_id=self.vid_map['CPU'])#flash len  1024的整数倍
        self.gen_write_reg(40, 2,virtual_id=self.vid_map['CPU'])#1 flash2ddr
        self.read_write_regs()
        print(f'execute read data from flash')
        self.waitDone()
        

    def ddr2flash(self, ddrAddr,flashAddr,ddrLen):
        self.gen_write_reg(20, ddrAddr,virtual_id=self.vid_map['CPU'])#ddr addr
        self.gen_write_reg(44, flashAddr,virtual_id=self.vid_map['CPU'])#flash addr       
        self.gen_write_reg(24, ddrLen,virtual_id=self.vid_map['CPU'])#ddr len     256的整数倍   
        self.gen_write_reg(40, 1,virtual_id=self.vid_map['CPU'])#1 ddr2flash 
        self.read_write_regs()
        print(f'execute write data to flash')
        self.waitDone()

    def getCpuStatus(self):
        self.gen_read_reg(28,virtual_id=self.vid_map['CPU'])
        regdata=self.read_write_regs(analyse=True)
        # for d in regdata:
        # print(f'addr-{hex(regdata[1])}, data-{hex(regdata[0])}')
        return regdata[0]
        # print(regdata)

    def waitDone(self):
        self.sockfd.settimeout(60)
        for i in range(1000):
            if self.getCpuStatus() == 0:
                self.sockfd.settimeout(0.1)
                return True
            time.sleep(1)
            print(f'wait {i+1} seconds')
        print(f'wait cpu status timeout: status is: {self.getCpuStatus()}')
        self.sockfd.settimeout(0.1)
        return False
    
    def load_ddr2awg(self, ddrAddr, ddrLen, tdest):
        self.gen_write_reg(20, ddrAddr,virtual_id=self.vid_map['CPU'])#ddr addr
        self.gen_write_reg(32, tdest,virtual_id=self.vid_map['CPU'])#flash addr       
        self.gen_write_reg(24, ddrLen,virtual_id=self.vid_map['CPU'])#ddr len     256的整数倍   
        self.gen_write_reg(40, 4,virtual_id=self.vid_map['CPU'])#1 ddr2flash 
        self.read_write_regs()

    def start_stop(self, index):
        self.gen_write_reg(0x20, index,virtual_id=self.vid_map['AWG'])#awg ctrl
        self.read_write_regs()

    def stop_output_wave(self, channel):
        '''
        停止波形输出，关闭某一个通道；channel为0时，关闭所有通道
        :param channel: [0,1,2,3,4]
        :return:
        '''
        index = 1 << (channel - 1 + self.channel_amount) if channel > 0 else 0xF << self.channel_amount
        self.start_stop(index)
    
    def start_output_wave(self, channel):
        '''
        使能波形输出，打开某一个通道；channel为0时，打开所有通道
        :param channel: [0,1,2,3,4]
        :return:
        '''
        index = 1 << (channel - 1) if channel > 0 else 0xF << 0
        self.start_stop(index)

    def set_loop(self, arg1, arg2, arg3, arg4):
        '''
        设置AWG各通道序列执行的总循环次数
        :param arg1: 通道1循环次数 范围：(1，65535)
        :param arg2: 通道1循环次数 范围：(1，65535)
        :param arg3: 通道1循环次数 范围：(1，65535)
        :param arg4: 通道1循环次数 范围：(1，65535)
        :return:
        '''
        if arg1 not in range(1, 65535) or arg2 not in range(1, 65535) or arg3 not in range(1, 65535) or arg4 not in range(1, 65535):
            # logger.error('DAC %s set_loop param out of range 0~65535', self.id)
            return 3

        self.gen_write_reg(0x34, arg1, virtual_id=self.vid_map['AWG'])#awg loop1
        self.gen_write_reg(0x44, arg1, virtual_id=self.vid_map['AWG'])#awg loop2
        self.gen_write_reg(0x54, arg1, virtual_id=self.vid_map['AWG'])#awg loop3
        self.gen_write_reg(0x64, arg1, virtual_id=self.vid_map['AWG'])#awg loop4
        self.read_write_regs()

    def get_version(self):
        self.gen_read_reg(0x04, virtual_id=self.vid_map['CPU_RAM']) # cpu ram FIX_DATE
        ver = self.read_write_regs(analyse=True)
        return ver[0]

    def set_multi_board(self, mode = 0):
        # mode为1设置单板触发，mode为0设置多板触发
        # 1:single board mode 0: multi board mode
        self.gen_write_reg(0xB8, mode, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()

    def set_trig_count_l1(self, count):
        '''
        设置AWG出发模块一级触发个数
        :param count: (1，100000)
        :return:
        '''
        if count < 1 or count > 100000:
            logger.error("DAC %s set_trig_count_l1 count %s param out of range 1~65535", self.id, count)
            return 1

        self.gen_write_reg(0x94, count, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()
        return 0

    # def set_trig_count_l2(self, count):
    #     '''
    #     设置AWG出发模块二级触发个数
    #     :param count: (1，100000)
    #     :return:
    #     '''
    #     if count < 1 or count > 100000:
    #         logger.error("DAC %s set_trig_count_l2 count %s param out of range 1~65535", self.id, count)
    #         return 1

    #     # if count == self.trig_count_l2:
    #     #     return 0
    #     self.gen_write_reg(0x9C, count, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
    #     self.read_write_regs()
    #     return 0

    def set_trig_interval_l1(self, trig_interval):
        '''
        设置AWG触发模块的一级触发间隔
        :param trig_interval: 单位ns，范围，100ns~5ms
        :return:
        '''
        # if trig_interval == self.trig_interval_l1:
        #     return 0
        if trig_interval < 1e-7 or trig_interval > 5e-3:
            logger.error("DAC %s set_trig_interval_l1 %s out of range 100ns~5ms", self.id, trig_interval)
            return 1
        count = trig_interval / 4e-9
    
        if abs(count - round(count))>0.1:
            real=round(count)*4
            logger.warn("Interval_l1 should be a multiple of 4ns,otherwise we'll round it up.In this case,the real value of interval_l1 is {}ns".format(real))
        
        self.gen_write_reg(0x90, int(count), virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()
        self.trig_interval_l1=trig_interval
            
        return 0

    # def set_trig_interval_l2(self, trig_interval):
    #     '''
    #     设置AWG触发模块的二级触发间隔
    #     :param trig_interval: 单位ns，范围，100ns~5ms
    #     :return:
    #     '''
    #     # if trig_interval == self.trig_interval_l2:
    #     #     return 0
    #     if trig_interval < 1e-7 or trig_interval > 5e-3:
    #         logger.error("DAC %s set_trig_interval_l2 %s out of range 100ns~5ms", self.id, trig_interval)
    #         return 1
    #     count = trig_interval/ 4e-9

    #     if abs(count - round(count))>1e-9:
    #         real_cnt=round(count)*4
    #         logger.warn("Interval_l2 should be a multiple of 4ns,otherwise we'll round it up.In this case,the real value of interval_l2 is {}ns".format(real_cnt))
    #     self.gen_write_reg(0x98, int(count), virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
    #     self.read_write_regs()
    #     self.trig_interval_l2=trig_interval
    #     return 0

    def set_trig_delay(self, point, width=10*4e-9):
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
        stop = round((self.da_trig_delay_offset + point) / 4e-9 + width/4e-9)
        if stop > 65536:
            logger.error("DAC %s set_trig_delay stop %s param out of range 65535", self.id, stop)
            return 1
        # if self.trig_delay == start and self.trig_delay_width == width:
        #     return 0
        self.trig_delay = start
        self.trig_delay_width = width
        self.gen_write_reg(0x88, start, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.gen_write_reg(0x8C, stop, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()
        
        return 0

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
        if count+10 > 65536:
            logger.error("DAC %s set_da_output_delay count+10 %s param out of range 65536", self.id, count+10)
            return 1

        self.output_delay=delay
        self.gen_write_reg(0x80, int(count), virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.gen_write_reg(0x84, int(count+10), virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()
        
        return 0
    
    def set_trig_select(self, ch = 0):
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

        self.gen_write_reg(0xAC, ch, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()
        self.trig_source = ch
        return 0
    
    def clear_trig_count(self):
        self.gen_write_reg(0xC0, 1, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()

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
        print(len(seq.tobytes()))
        self.write_memory(self.mem_map[f'CH{channel}_SEQ'], seq.tobytes())
        self.load_ddr2awg(self.mem_map[f'CH{channel}_SEQ'], len(seq.tobytes()), self.tdest_map[f'CH{channel}_SEQ'])

    def wave_calc_fast(self, channel, wave=None):
        '''
        波形写入时，末尾先补20ns的默认电压数据，再按64字节对齐进行补齐
        :param channel: AWG 通道
        :param wave: 波形数据，波形数据要求为numpy数组类型，取值范围[0，65535]
        :return: uint16 类型 numpy array
        '''
        data_offset = self.channel_default_voltage[channel - 1] - self.data_offset[channel - 1]
        pad_cnt = 40 + (32 - ((len(wave)+40) & 31))
        data = np.pad(wave, [0, pad_cnt], 'constant', constant_values=(0,0))  # 补齐64字节0
        data = data + data_offset  # 校准后的偏置
        if np.max(data) > 65535 or np.min(data) < 0:
            logger.critical(f'data in wave is out of range max:{np.max(data)}, min:{np.min(data)}')
        data = (np.clip(data, 0, 65535)).astype('<u2')  # <u2底层按照四字节接收，先转为<u2在clip可能会导致波形数据不对，造成波形翻转
        return data

    def write_wave(self, channel, offset=0, wave=None):
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

        data = self.wave_calc_fast(channel, wave)
        self.stop_output_wave(channel)
        self.write_memory(self.mem_map[f'CH{channel}_WAVE'], data.tobytes())
        self.load_ddr2awg(self.mem_map[f'CH{channel}_WAVE'], len(data.tobytes()), self.tdest_map[f'CH{channel}_WAVE'])

    def send_int_trig(self):
        '''触发使能, 这条指令应该直接执行，执行时，先重置触发，防止有未运行完的触发'''
        # self.clear_trig_count()
        self.gen_write_reg(0xBC, 1, virtual_id=self.vid_map['TRIG']) # cpu ram FIX_DATE
        self.read_write_regs()

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

        offset = self.data_offset[channel - 1]
        if volt != -1:
            volt = 65535 - volt
            if volt > 65535:
                volt = 65534
            elif volt < 0:
                volt = 0
            self.gen_write_reg(0x30+((channel-1)<<4), 0, virtual_id=self.vid_map['AWG']) # cpu ram FIX_DATE
        else:  # hold模式 
            self.gen_write_reg(0x30+((channel-1)<<4), 2, virtual_id=self.vid_map['AWG']) # cpu ram FIX_DATE

        # if volt == self.channel_default_voltage[channel-1]:
        #     return 0
        if round(volt-offset) < 0 or round(volt-offset) > 65535:
            logger.critical('set volt out of range')
            return -1

        self.channel_default_voltage[channel-1] = volt
        _code = round(volt-offset)
        self.gen_write_reg(0x38+((channel-1)<<4), _code, virtual_id=self.vid_map['AWG']) # cpu ram FIX_DATE
        self.read_write_regs()

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

if __name__ == '__main__':
    ip = '10.0.5.132'
    hw = UDPBoard(ip)

    import numpy as np
    hw.init_device()
    # 存储测试
    hw.memory_self_test(test_time=10)
    # wr_data1 = np.array([i for i in range(256 * 4 * 1)], dtype='uint32')
    # msg = wr_data1.tobytes()
    # hw.load_ddr2awg(0, 1024, 4)
    # hw.writeFlash(0xF50000, msg)

    # # FLASH配置测试
    # filename='.\\CONFIG_FILES\\V_20210925_G.bin'
    # hw.remote_config(filename,'update')
    
    # filename='B:\\FPGA\\vivado_2018.3\\verilog_ethernet\\auto_prj\\CONFIG_FILES\\V_20210925_U.bin'
    # hw.remote_config(filename,'update')
