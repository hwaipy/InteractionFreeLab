# coding: utf-8
import time
import socket
import numpy as np
import os
from struct import unpack, pack
import re

from .status import AWGStatus
from .logger import get_logger
from .protocol import SQCProtocol
from .pipeline import PipelineInstruction
from .utils import format_hex_data, ProgressBar
from .register import _REGISTER_MAP
from .error import *
from .utils import ip_to_int


class UstcAWG:
    """Driver class for USTC arbitrary waveform generator(awg).

    Attributes:
        logger (TimedRotatingFileHandler): Logger instance for logging.
        awg_count (int): Number of awg instances created.
        RESPONSE_TIMEOUT (float): Max time for waiting for awg response.
    """

    awg_count = 0
    RESPONSE_TIMEOUT = 1
    channel_amount = 4
    logger = None

    def __init__(
        self, ip, port=10000, name='', console_log=False, connect_status=0, slot=0, wave_type='u2',
        trig_interval_l1=200e-6, trig_count_l1=10, da_output_delay=0, channel_sampling_ratio=None, channel_gain=None,
        channel_default_voltage=None, data_offset=None, batch_mode=True, log_isolate=False, dev_mode=False
    ):
        """Initialize an awg instance.

        Args:
            ip ([type]): Ip address of awg.
            port (int, optional): Port number of awg. Defaults to 10000. Defaults to 10000.
            name (str, optional): Name of awg. Defaults to ''.
            console_log (bool, optional): Whether to print log in console. Defaults to False.
            trig_interval_l1 (float, optional): Trig interval of awg. Defaults to 200e-6.
            trig_count_l1 (int, optional): Trig count of awg. Defaults to 10.
            da_output_delay (int, optional): Output dealy of awg. Defaults to 0.
            channel_gain (list, optional): Channel gain. Defaults to None.
            channel_default_voltage (int, optional): Default voltage of channel. Defaults to None.
            data_offset ([type], optional): Channel data offset. Defaults to None.
            batch_mode (bool, optional): Whether data are sent in batch mode. Defaults to True.
        """
        # init awg basic information
        self.ip = ip
        self.port = port
        self.name = name if name else f'UnnamedAWG-{UstcAWG.awg_count}'
        if log_isolate:
            self.logger = get_logger(f'driver_{self.name}', console_log=console_log)
        else:
            if UstcAWG.logger is None:
                UstcAWG.logger = get_logger('driver', console_log=console_log)
        # init awg udp communication setting
        self.sock = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setblocking(1)  # set socket to non-blocking mode
        # small buffer may cause error 10035 in non-blocking mode
        # if data size exceeds buffer size
        self.buffer_size = 1024 * 1024 * 32
        self.sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_SNDBUF, self.buffer_size)
        self.recv_buffer_size = 1024 * 1024 * 32
        self.sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_RCVBUF, self.recv_buffer_size)
        self.sock.settimeout(self.RESPONSE_TIMEOUT)
        self.clear_buffer()

        # init awg function objects
        self.protocol = SQCProtocol(console_log=console_log)
        self.pipline_inst = PipelineInstruction()
        self.reg_map = _REGISTER_MAP
        self.awg_status = AWGStatus(self)
        self.set_memory_mapper()
        self.set_reg_packet()
        self.set_write_mem_packet()
        self.set_read_mem_packet()

        # init parameters of awg
        if channel_gain is None:
            channel_gain = [511] * self.channel_amount
        if channel_default_voltage is None:
            channel_default_voltage = [32767] * self.channel_amount
        if data_offset is None:
            data_offset = [0] * self.channel_amount
        if channel_sampling_ratio is None:
            channel_sampling_ratio = [1] * self.channel_amount
        self.channel_gain = channel_gain    # set channel gain
        # DAC data is a signed integer
        if wave_type == 'i2':
            channel_default_voltage = [0] * 4
        self.channel_default_voltage = channel_default_voltage  # set channel default voltage
        self.trig_delay_offset = 0  # set trig delay offset
        self.trig_interval_l1 = trig_interval_l1    # set trig interval level 1
        self.trig_count_l1 = trig_count_l1  # set trig count level 1
        self.trig_delay = None  # set trig delay
        self.trig_source = 0
        self.batch_mode = batch_mode
        self.data_offset = data_offset
        self.da_output_delay = da_output_delay
        self.channel_gian = channel_gain
        self.channel_sampling_ratio = channel_sampling_ratio  # super sample ratio
        self.connect_status = connect_status
        self.slot = slot
        self.wave_type = wave_type
        self.min_data = 0
        self.max_data = 65535
        if wave_type != 'u2':
            # DAC code value range of 16 bit
            self.min_data = -32767
            self.max_data = 32767

        self.dev_mode = dev_mode
        UstcAWG.awg_count += 1
        self.logger.info(f'Init {self.name}')

    def slot_check(self, slot):
        if slot is None:
            return self.slot
        else:
            return slot

    def connect(self, slot=None):
        """Connect to awg

        Args:
            slot (int, optional): The slot of crate. Defaults to 0.

        Raises:
            DacConnectFail: Connect to awg fail

        Returns:
            int: 0
        """
        self.connect_status = 0
        try_count = 0
        max_tries = 5
        fix_date_reg = 'CPU.FIX_DATE'
        slot = self.slot_check(slot)
        while try_count < max_tries:
            try:
                compile_time = self[slot, fix_date_reg]
                self.init_device()
                self.connect_status = 1
                return 0
            except RecvTimeoutError:
                self.connect_status = 0
            try_count += 1
            self.logger.warn(f'Try to connect DAC {self.name} for {try_count} times')
        if not self.connect_status:
            self.logger.error(f'DAC {self.name} connect failed')
            raise DacConnectFail(self.name)
        return 0

    def re_connect(self):
        """Re-connect awg.

        Raises:
            DacReConnectFail: Fail to re-connect awg.

        Returns:
            int: 0
        """
        try_count = 0
        max_tries = 5
        time.sleep(15)
        while try_count < max_tries:
            try:
                self.connect(self.slot)
                return 0
            except DacConnectFail:
                time.sleep(15)
            try_count += 1
            self.logger.warn(f'Try to re-connect DAC {self.name} for {try_count} times')
        self.logger.error(f'DAC {self.name} re-connect failed')
        raise DacReConnectFail(self.name)

    def init_device(self):
        """Init device.

        Includes:
        1. Hardware initialization.
        2. Set defualt parameters.
        3. Set default channel gain and offset.

        Returns:
            int: 0
        """

        self.init_board(self.slot)

        _batch_mode = self.batch_mode
        self.batch_mode = False
        self.set_trig_count_l1(self.trig_count_l1)
        self.set_trig_interval_l1(self.trig_interval_l1)
        self.set_dac_output_delay(self.da_output_delay)
        self.set_trig_delay(200e-9)
        self.stop_output_wave(0)
        self.set_multi_board(0)
        self.clear_trig_count()
        self.set_trig_select(self.trig_source)

        for ch in range(0, self.channel_amount):
            self.set_gain(ch+1, self.channel_gain[ch])
            self.set_default_volt(ch+1, self.channel_default_voltage[ch])
        self.batch_mode = _batch_mode
        return 0

    def init_board(self, slot=None, max_times=5):
        """Init board.

        Args:
            slot (int, optional): The slot of crate. Defaults to 0.

        Raises:
            InitBoardFail: Init board fail.

        Returns:
            int: 0
        """
        perssion_reg = 'CPU.PERMISSION'
        init_reg = 'CPU.FLASH_FUN'
        slot = self.slot_check(slot)
        self[slot, perssion_reg] = 1  # enable register
        try_times = 0
        # start init board
        self[slot, init_reg] = 0x05
        time.sleep(5)
        while try_times < max_times:
            read_back = self[slot, perssion_reg]
            if read_back == 1:
                break
            else:
                time.sleep(1)
            try_times += 1
            self.logger.info(f'Init board {self.name} for {try_times} times')
            if try_times == max_times:
                self.reboot(slot)
                raise InitBoardTimeoutError(self.name, try_times)
        return 0

    def set_logger(self, log_name, console_log):
        """Set logger for awg.

        Args:
            log_name (str): Name of log file.
            console_log (bool): Whether print log in console.
        """
        self.logger = get_logger(f'{log_name}', console_log=console_log)

    def set_memory_mapper(self):
        """Create a memory object for current AWG.
        """
        self._byte_mapper = AWGMemoryMapper(self, 'byte')

    def set_reg_packet(self):
        """Create register packet.
        """
        self.reg_packet = self.packet('reg')

    def set_write_mem_packet(self):
        """Create write memory packet.
        """
        self.w_mem_packet = self.packet('mem')

    def set_read_mem_packet(self):
        """Create read memory packet.
        """
        self.r_mem_packet = self.packet('mem')

    def map_memory(self):
        """Return current AWG's memory object.

        Returns:
            AWGMemoryMapper: Current AWG's memory management object.
        """
        return self._byte_mapper

    def __str__(self):
        return f'({self.name}|{self.ip}:{self.port})'

    def get_status(self, name=None):
        """Get AWG status from the specified AWG module.

        Args:
            name (str, optional): Composed of AWG module and status attrribute.
              The attribute name and module name are separated by character '.'.
              Defaults to None.

        Returns:
            dict: Awg status information of the specified module.
        """
        if name is None:
            return self.awg_status.get_status(update=True)
        module_name, status_name = name.split('.')
        status = self.awg_status.get_status(update=False)
        return status[module_name][status_name]

    def send(self, data):
        """Send *data* to AWG.

        Args:
            data (byte): Data to be sent to AWG.
        """
        dst = (self.ip, self.port)
        self.sock.sendto(data, dst)
        # self.display_data('Send', data)

    def recv(self, count):
        """Receive data from AWG

        Args:
            count (int): The number of bytes that should be received from the AWG.

        Returns:
            byte: Data received from the AWG.
        """
        data, addr_info = self.sock.recvfrom(count)
        # self.display_data('Recv', data)
        return data

    def clear_buffer(self):
        """Clear buffer that may be cached in the socket.
        """
        try:
            data = self.sock.recv(8192)
            self.logger.debug(f'Clear {len(data)} bytes from buffer.')
        except OSError:
            return

    def display_data(self, tag, data):
        """Convert data to hex data and display it in the log.

        Args:
            tag (str): Tag out where *data* belongs.
            data (byte): Data need to be converted to hex data and display in the log.
        """
        head = f'{tag} data ({len(data)} bytes)'
        segment = 32
        offset = 0
        total = len(data)
        self.logger.debug(head)
        while offset < total:
            data_seg = data[offset:(offset + segment)]
            seg_hex = format_hex_data(data_seg)
            self.logger.debug(f'[{offset:08X}] {seg_hex}')
            offset += segment

    def write_mem(self, address, data, format_type='byte', slot=None, wait_response=True):
        """Write *data* to awg memory.

        Args:
            address (int|list): Start address of awg memory where data will be written,
              which should be multiples of 1024.
            data (int|list): Data to be written in awg memory.
            format_type (str|list, optional): How to pack *data* to binary data, supported types
              includes 'byte', 'wave' and 'seq'. Defaults to 'byte'.
            slot (int|list): The slot of the crate.
            wait_response (bool, optional): Whether to wait for awg's response. Defaults to True.

        Returns:
            int: Number of frames received by awg if *wait_response* is True, otherwise
              number of frames sent by driver.
        """
        if isinstance(address, int):
            address = [address]
            data = [data]
            format_type = [format_type]

        n = len(address)
        if isinstance(format_type, str):
            format_type = [format_type] * n
        slot = self.slot_check(slot)
        if isinstance(slot, int):
            slot = [slot] * n
        total_count = self.write_mem_iterate_send(address, data, format_type, slot, wait_response)
        return total_count

    def write_mem_iterate_send(self, address, data, format_type, slot, wait_response):
        """Send write memory frame every time finish packing a frame

        Args:
            address (list): Start address of awg memory where data will be written,
              which should be multiples of 1024.
            data (list): Data to be written in awg memory.
            format_type (str, optional): How to pack *data* to binary data, supported types
              includes 'byte', 'wave' and 'seq'. Defaults to 'byte'.
            slot (list): The slot of crate.
            wait_response (bool): Whether to wait for awg's response. Defaults to True.

        Raises:
            RetransmissionTimeout: Retransmit miss frame fail.

        Returns:
            int: The number of frames had been sent.
        """
        frames_generator = self.protocol.write_mem_frames_spd_ctrl(address, data, format_type, slot)
        total_count = 0
        sent_frame = []
        while True:
            try:
                frame, last = next(frames_generator)
                total_count += 1
                self.send(frame)
                # print('s f', len(frame))
                if wait_response:
                    sent_frame.append(frame)
                if last and wait_response:
                    count, miss_frame_num = self.wait_write_mem_response()
                    if miss_frame_num is not None:
                        max_times = 5
                        retransmit_times = 0
                        while retransmit_times < max_times:
                            sent_cnt = len(sent_frame)
                            if sent_cnt - count == 1:
                                miss_frame = sent_frame[miss_frame_num]
                                # set last tag
                                last_tag = b'\x01\xC0'
                                # set frame number equals to 0
                                frame_number = b'\x00\x00'
                                miss_frame = miss_frame[:4] + frame_number + last_tag + miss_frame[8:]
                                self.logger.warn(f'{self.name} received {count} frames of {sent_cnt}, miss NO.{miss_frame_num}. ')
                                self.logger.warn(f'{self.name} retransmit NO.{miss_frame_num} frame. ')
                                self.send(miss_frame)
                                count, miss_frame_num = self.wait_write_mem_response()
                            else:
                                self.logger.warn(f'{self.name} retransmit all frames. ')
                                for frame in sent_frame:
                                    self.send(frame)
                                count, miss_frame_num = self.wait_write_mem_response()
                            retransmit_times += 1
                            if miss_frame_num is None:
                                sent_frame = []
                                break
                            if retransmit_times == max_times:
                                raise RetransmissionTimeout(self.name, retransmit_times)
                    else:
                        sent_frame = []
            except StopIteration:
                break
        return total_count

    def wait_write_mem_response(self):
        """Wait response for writing memory.

        Returns:
            turple: Numberr of frames received by AWG, number of miss frame.
        """
        try:
            response = self.wait_response(response_size=8)
            count, miss_frame_num = self.protocol.parse_write_mem_response(response)
        except RecvTimeoutError:
            count = 0
            miss_frame_num = 0
        return count, miss_frame_num

    def read_mem(self, address, length, format_type='byte', slot=None, wait_response=True):
        """Read *data* from AWG memory.

        Args:
            address (int|list[int]): Start address of AWG memory where data will be read from,
              which should be multiples of 1024.
            length (int|list[int]): The length of the data to be read, which should be
              multiples of 1024.
            format_type (str|list[str], optional): How to pack *data* to binary data,
              supported types includes 'byte', 'para', 'wave' and 'seq'. Defaults to 'byte'.
            wait_response (bool, optional): Whether to wait for AWG's response. Defaults to True.

        Returns:
            int|list: Data list read from AWG memory if *wait_response* is True,
              otherwise number of frames sent by driver.
        """
        if isinstance(address, int):
            address = [address]
            length = [length]
            format_type = [format_type]

        n = len(address)
        if isinstance(format_type, str):
            format_type = [format_type] * n

        slot = self.slot_check(slot)
        if isinstance(slot, int):
            slot = [slot] * n

        frames_list = []
        response_sizes_list = []
        for i, addr in enumerate(address):
            frames, resp_sizes = self.protocol.read_mem_frame_spd_ctrl(addr, length[i], slot[i])
            frames_list.append(frames)
            response_sizes_list.append(resp_sizes)
        if wait_response:
            data = []
            for frames, response_sizes, ftype in zip(frames_list, response_sizes_list, format_type):
                response = b''
                for idx, frame in enumerate(frames):
                    self.send(frame)
                    response += self.wait_response(response_sizes[idx])
                mem_data = self.protocol.parse_read_mem_response(response, ftype)
                data.append(mem_data)
            return data if len(data) > 1 else data[0]
        else:
            response_size = []
            for frames, response_sizes in zip(frames_list, response_sizes_list):
                rsize = []
                for idx, frame in enumerate(frames):
                    self.send(frame)
                    rsize.append(response_sizes[idx])
                response_size.append(sum(rsize))
            return response_size

    def send_reg_cmd(self, register_entries, wait_response=True):
        """Send register command to AWG register.

        Args:
            register_entries (tuple): List of register command entry. Register command entry
              is composed of slot(int), base address id(int) and register address(int),
              if it is a write register command, add the data(int) written to AWG register to the tuple.
            wait_response (bool, optional): Whether to wait for AWG's response. Defaults to True.

        Returns:
            list|int: List of register command result received by AWG if *wait_response* is True,
              otherwise number of frames sent by driver.
        """
        frame, response_size = self.protocol.reg_frame(register_entries)
        max_times = 5
        try_times = 0
        while try_times < max_times:
            try:
                self.send(frame)
                if wait_response:
                    response = self.wait_response(response_size)
                    registers = self.protocol.parse_reg_response(response)
                    return registers
                else:
                    return response_size
            except RecvTimeoutError:
                try_times += 1
            if try_times == max_times:
                raise RegRetransmissionTimeout(self.name, try_times)

    def wait_response(self, response_size, timeout=None, interval=None):
        """Wait response from AWG.

        Args:
            response_size (int): Size of response received from AWG.
            timeout (float, optional): Maximum time for waiting AWG's response. Defaults to None.
            interval (float, optional): Interval time for waiting AWG's response. Defaults to None.

        Raises:
            RecvTimeoutError: Error of not receiving enough *response_size* data within the *timeout* time.

        Returns:
            byte: Data received from AWG.
        """
        if timeout is None:
            timeout = self.RESPONSE_TIMEOUT
        if interval is None:
            interval = 1e-3
        self.sock.settimeout(timeout)
        offset = 0
        response = b''
        while offset < response_size:
            try:
                response += self.recv(response_size)
            except socket.error:
                break
            if len(response) == response_size:
                break
        if self.connect_status and len(response) == 0:
            self.re_connect()
        else:
            if len(response) != response_size:
                self.logger.error(
                    f'Recv timeout ({timeout:g} s) for {self.name}, '
                    f'expecting {response_size} bytes, '
                    f'{len(response)} bytes received')
                raise RecvTimeoutError(self, len(response), response_size, timeout)
        return response

    def close(self):
        """Close AWG socket connection.
        """
        self.sock.close()

    def __getitem__(self, key):
        slot = self.slot
        if isinstance(key, int):
            base_addr = 0
            addr = key
        elif isinstance(key, tuple):
            if len(key) == 3:
                slot, base_addr, addr = key
            else:
                prev, last = key
                if isinstance(last, str):
                    base_addr, addr = self.reg_map.get_addr_by_name(last)
                    slot = prev
                else:
                    base_addr, addr = prev, last
        elif isinstance(key, str):
            base_addr, addr = self.reg_map.get_addr_by_name(key)
        else:
            raise KeyError(f'index should be int, tuple or str, got {key}')
        if not self.dev_mode and not self.reg_map.readable(base_addr, addr):
            name = self.reg_map.get_name_by_addr(base_addr, addr)
            raise ReadRegisterPermissionError(name)
        entry = (slot, base_addr, addr)
        reg_info = self.send_reg_cmd([entry])
        # TODO: check read back infomation
        return reg_info[0]['data']

    def __setitem__(self, key, value):
        slot = self.slot
        if isinstance(key, int):
            base_addr = 0
            addr = key
        elif isinstance(key, tuple):
            if len(key) == 3:
                slot, base_addr, addr = key
            else:
                prev, last = key
                if isinstance(last, str):
                    base_addr, addr = self.reg_map.get_addr_by_name(last)
                    slot = prev
                else:
                    base_addr, addr = prev, last
        elif isinstance(key, str):
            base_addr, addr = self.reg_map.get_addr_by_name(key)
        if not self.dev_mode and not self.reg_map.writable(base_addr, addr):
            name = self.reg_map.get_name_by_addr(base_addr, addr)
            raise WriteRegisterPermissionError(name)
        entry = (slot, base_addr, addr, value)
        reg_info = self.send_reg_cmd([entry])
        return reg_info

    def packet(self, pkt_type='reg'):
        """Return awg packet class.

        Args:
            pkt_type (str, optional): Packet type. Defaults to 'reg'.

        Returns:
            RegisterPacket|MemoryPacket: Packet class.
        """
        pkt_map = dict(reg=RegisterPacket, mem=MemoryPacket)
        PacketClass = pkt_map[pkt_type]
        return PacketClass(self)

    def commit_mem(self):
        """Commit write data to ddr operation to awg.

        Returns:
            dict: Write memory data to data result.
        """
        result = self.w_mem_packet.send()
        self.w_mem_packet.clear()
        return result

    def commit_reg(self):
        """Commit register parameters settings to awg.

        Returns:
            dict: register setting result
        """
        result = self.reg_packet.send()
        self.reg_packet.clear()
        return result

    def clear_trig_count(self, slot=None):
        """Clear trig count.

        Raises:
            ClearTrigCountFail: Clear trig count fail.

        Returns:
            int: 0
        """
        clear_reg = 'TRIG.C_TRIG_COUNT_CLEAR'
        trig_cnt_reg = 'TRIG.C_TRIG_CNT'
        try_cnt = 10
        slot = self.slot_check(slot)
        while try_cnt > 0:
            if self.check_trig():
                break
            try_cnt -= 1
            time.sleep(0.1)
        clear = 1
        self[slot, clear_reg] = clear
        if self[slot, trig_cnt_reg] != 0:
            raise ClearTrigCountFail(self.name)
        return 0

    def check_trig(self, slot=None):
        """Check whether trigger is completed.

        Returns:
            bool: trigger already done return True,otherwise False.
        """
        reg = "TRIG.C_TRIG_CNT"
        slot = self.slot_check(slot)
        return self.trig_count_l1 == self[slot, reg]
    
    def write_lut_ram_TF(self,channel,addr,data,slot=None):
        """    
        Write a 32-bit numbers to the TF_reg.

        channel is 1，2，3，4 (the corresponding parameters are 5(8'b00101)，21(8'b10101)，7(8'b00111)，23(8'b10111));
        addr is 0 ~ 31;
        data is a 16bit number.

        Returns:
            int: 0
        """
        register = 'AWG.TF_REG'

        if channel == 1:
            channel = 5
        elif channel == 2:
            channel = 21
        elif channel == 3:
            channel = 7
        elif channel == 4:
            channel = 23

        TF_reg =  (channel << 24)  + (addr << 16) + data

        slot = self.slot_check(slot)       

        if self.batch_mode:
            self.reg_packet[slot, register] = TF_reg
        else:
            self[slot, register] = TF_reg
            if TF_reg != self[slot, register]:
                raise SetTrigCountL1Fail(self.name)

        return 0

    def set_trig_count_l1(self, count, slot=None):
        """Set awg trig count l1.

        Args:
            count (int): Trig count. Range 1-100000.

        Raises:
            TrigCountOufofRange: Trig count out of range.
            SetTrigCountL1Fail: Set trig count fail.

        Returns:
            int: 0
        """
        register = 'TRIG.C_TRIG_COUNT_L1'

        min_count = 1
        max_count = 100000
        if count < min_count or count > max_count:
            raise TrigCountOufOfRange(self.name, min_count, max_count, count)

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = count
        else:
            self[slot, register] = count
            print(self[slot, register])
            if count != self[slot, register]:
                raise SetTrigCountL1Fail(self.name)
        self.trig_count_l1 = count
        return 0

    def set_trig_interval_l1(self, trig_interval=1e-6, slot=None):
        """Set awg trig interval l1

        Args:
            trig_interval (float): Trig interval.Unit ns.

        Raises:
            TrigIntervalOutofRange: Trig interval out of range. Range 100ns-4.19ms.
            SetTrigIntervalL1Fail: Set trig interval fail.

        Returns:
            int: 0
        """
        register = 'TRIG.C_TRIG_INTERVAL_L1'

        min_trig_interval = 1e-7
        # trig interval register bit width equals to 20
        max_trig_interval = (2 ** 20 - 1) * 4e-9
        if trig_interval < min_trig_interval or trig_interval > max_trig_interval:
            raise TrigIntervalOutOfRange(self, min_trig_interval, max_trig_interval, trig_interval)
        count = trig_interval / 4e-9
        if abs(count - round(count)) > 0.1:
            real = round(count) * 4
            self.logger.warn(f'Trig interval l1 must be a multiple of 4ns, otherwise interval will be rounded up.'
                             f'In this case, the real value of interval l1 is {real}ns')
        count = round(count)
        self.trig_interval_l1 = count * 4e-9

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = count
        else:
            self[slot, register] = count
            if count != self[slot, register]:
                raise SetTrigIntervalL1Fail(self.name)
        return 0

    def set_trig_delay(self, point, width=5*4e-9, slot=None):
        """Set the delay for awg output to dac.

        Args:
            point (float): delay point for awg output to dac.
            width (float, optional): trig width. Defaults to 5*4e-9.

        Raises:
            TrigDelayOutOfRange: Trig delay out of range.

        Returns:
            int: 0
        """
        min_point = 0
        max_point = 2.56e-4
        if point < min_point or point > max_point:
            raise TrigDelayOutOfRange(self.name, min_point, max_point, point)
        if point > self.trig_interval_l1:
            raise TrigDelayWrongError(self.name, point, self.trig_interval_l1)
        start = round((self.trig_delay_offset + point) / 4e-9 + 1)
        stop = round((self.trig_delay_offset + point) / 4e-9 + width/4e-9)

        slot = self.slot_check(slot)
        self.set_trig_start(start, slot)
        self.set_trig_stop(stop, slot)
        return 0

    def set_trig_start(self, count, slot=None):
        """Set the trigger delay count of awg output to dac.

        Args:
            count (int): Trig start external count. One count represents 4ns.

        Raises:
            TrigStartOutOfRange: Set trig start external out of range.
            SetTrigStartFail: Set trig start external fail.

        Returns:
            int: 0
        """
        register = 'TRIG.C_START_EXTERNAL'

        min_count = 0
        # trig start external register bit width equals to 16
        max_count = 2 ** 16 - 1
        if count < min_count or count > max_count:
            raise TrigStartOutOfRange(self.name, min_count, max_count, count)

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = count
        else:
            self[slot, register] = count
            if count != self[slot, register]:
                raise SetTrigStartFail(self.name)
        return 0

    def set_trig_stop(self, count, slot=None):
        """Set the trigger delay stop count for awg output to dac.

        Args:
            count (int): Trig stop start external count. One count represents 4ns.

        Raises:
            TrigStopOutOfRange: Set trig stop external out of range.
            SetTrigStopFail: Set trig stop external fail.

        Returns:
            int: 0
        """
        register = 'TRIG.C_STOP_START_EXTERNAL'

        min_count = 0
        # trig stop external register bit width equals to 16
        max_count = 2 ** 16 - 1
        if count < min_count or count > max_count:
            raise TrigStopOutOfRange(self.name, min_count, max_count, count)

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = count
        else:
            self[slot, register] = count
            if count != self[slot, register]:
                raise SetTrigStopFail(self.name)
        return 0

    def set_multi_board(self, mode=0, slot=None):
        """Set awg work mode.

        Args:
            mode (int, optional): Awg word mode. 0 indicates multi board master trig mode,
            1 indicates single board trig mode. Defaults to 0.

        Raises:
            MultiBoardModeError: Multi board mode error.
            SetMultiBoardModeFail: Set multi board mode fail.

        Returns:
            int: 0
        """
        register = 'TRIG.C_MULTI_BOARD_MODE'

        if mode not in [0, 1]:
            raise MultiBoardModeError(self.name, mode)

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = mode
        else:
            self[slot, register] = mode
            if mode != self[slot, register]:
                raise SetMultiBoardModeFail(self.name)
        return 0

    def set_trig_select(self, ch=0, slot=None):
        """Set the source of awg trigger output to dac.

        Args:
            ch (int, optional): Trig source channel. 0 indicates master board trig.
              Defaults to 0.

        Raises:
            TrigSelectChannelError: Select the channel which is not exists.

        Returns:
            int: 0
        """
        register = 'TRIG.C_TRIG_AD_SOURCE_SEL'
        if ch not in [0, 1, 2, 3, 4]:
            raise TrigSelectChannelError(self.name, ch)

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = ch
        else:
            self[slot, register] = ch
        return 0

    def send_int_trig(self, slot=None):
        """Enable awg trigger.

        Raises:
            TrigEnableFail: Enable trigger fail.

        Returns:
            int: 0
        """
        trig_en_reg = 'TRIG.C_TRIG_EN'
        slot = self.slot_check(slot)
        enable = 1
        self[slot, trig_en_reg] = enable
        return 0

    def set_dac_output_delay(self, delay, slot=None):
        """Set the delay of awg wave output acrroding to
        set the delay of trigger for awg output.

        Args:
            delay (flaot): Delay of awg wave output.

        Raises:
            DacDelayOutOfRange: Delay out of range.
        """
        min_delay = 0
        max_delay = 2.56e-4
        if delay < min_delay or delay > max_delay:
            raise DacDelayOutOfRange(self.name, min_delay, max_delay, delay)
        start_count = round(delay / 4e-9 + 1)
        step = 10
        stop_count = start_count + step
        slot = self.slot_check(slot)
        self.set_dac_start(start_count, slot)
        self.set_dac_stop(stop_count, slot)

    def set_dac_start(self, count, slot=None):
        """Set the trigger delay count of awg output.

        Args:
            count (int): Dac start count.

        Raises:
            DacStartOutOfRange: Dac start count out of range.
            SetDacStartFail: set Dac start count fail.

        Returns:
            int: 0
        """
        register = "TRIG.C_START_DAC"

        min_count = 0
        # start dac register bit width equals to 16
        max_count = 2 ** 16 - 1
        if count < min_count or count > max_count:
            raise DacStartOutOfRange(self.name, min_count, max_count, count)
        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = count
        else:
            self[slot, register] = count
            if count != self[slot, register]:
                raise SetDacStartFail(self.name)
        return 0

    def set_dac_stop(self, count, slot=None):
        """Set the trigger delay count of awg output.

        Args:
            count (int): Dac stop count.

        Raises:
            DacStartOutOfRange: Dac stop count out of range.
            SetDacStartFail: Set dac stop count fail.

        Returns:
            int: 0
        """
        register = "TRIG.C_STOP_START_DAC"

        min_count = 0
        #  stop start dac register bit width equals to 16
        max_count = 2 ** 16 - 1
        if count < min_count or count > max_count:
            raise DacStopOutOfRange(self.name, min_count, max_count, count)
        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, register] = count
        else:
            self[slot, register] = count
            if count != self[slot, register]:
                raise SetDacStopFail(self.name)

    def start_output_wave(self, channel, slot=None):
        """Start awg channel output wave.

        Args:
            channel (int): Channel number.

        Raises:
            ChannelWrongError: Input the wrong channel.
            StartOutputWaveFail: Start output wave fail.

        Returns:
            int: 0
        """
        register = 'AWG.CTRL_REG'

        if channel < 0 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        if channel == 0:
            for ch in range(1, self.channel_amount+1):
                cmd = 1 << (ch - 1)
                self[slot, register] = cmd
        else:
            cmd = 1 << (channel - 1)
            self[slot, register] = cmd
        return 0


    def stop_output_wave(self, channel, slot=None):
        """Stop awg channel output wave.

        Args:
            channel (int): Channel number.

        Raises:
            StopOutputWaveFail: Stop output wave fail.

        Returns:
            int: 0
        """
        register = 'AWG.CTRL_REG'

        if channel < 0 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        if channel == 0:
            for ch in range(1, self.channel_amount+1):
                cmd = 1 << (ch - 1 + self.channel_amount)
                self[slot, register] = cmd
        else:
            cmd = 1 << (channel - 1 + self.channel_amount)
            self[slot, register] = cmd
        return 0

    def set_default_volt(self, channel, volt, hold=False, slot=None):
        """Set awg channel default voltage.

        Args:
            channel (int): Channel number.
            volt (int): Default coltage code value
            hold (bool, optional): output hold mode.if hold is true, awg will hold the output of
              last sampling point while wating for counter or trigger. Defaults to False.

        Raises:
            ChannelWrongError: Input the wrong channel.
            DefaultVoltOutOfRange: Default voltage out of range.
            SetDefaultVoltFail: Set default voltage fail.

        Returns:
            int: 0
        """
        volt_regs = {
            1: "AWG.DEFAULT_CODE1",
            2: "AWG.DEFAULT_CODE2",
            3: "AWG.DEFAULT_CODE3",
            4: "AWG.DEFAULT_CODE4"
        }
        hold_regs = {
            1: "AWG.CNFG_REG1",
            2: "AWG.CNFG_REG2",
            3: "AWG.CNFG_REG3",
            4: "AWG.CNFG_REG4"
        }

        min_volt = 0
        max_volt = 65535
        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        offset = self.data_offset[channel-1]
        if hold:
            volt = 32767
            hold_value = 1
            self.channel_default_voltage[channel-1] = 0
        else:
            if volt > max_volt:
                volt = max_volt - 1
            if volt < min_volt:
                volt = min_volt
            hold_value = 0
            self.channel_default_voltage[channel-1] = volt
        cali_volt = round(volt + offset)
        if cali_volt < min_volt or cali_volt > max_volt:
            raise DefaultVoltOutOfRange(self.name, min_volt, max_volt, cali_volt)
        volt_reg = volt_regs[channel]
        hold_reg = hold_regs[channel]

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, volt_reg] = cali_volt
            self.reg_packet[slot, hold_reg] = hold_value
        else:
            self[slot, volt_reg] = cali_volt
            self[slot, hold_reg] = hold_value
            if self[slot, volt_reg] != cali_volt or self[slot, hold_reg] != hold_value:
                raise SetDefaultVoltFail(self.name, channel)
        return 0

    def set_data_offset(self, channel, offset):
        """Set channel data offset.

        Args:
            channel (int): Channel number.
            offset (int): Channel data offset.

        Raises:
            ChannelWrongError: Input the wrong channel.
            ChannelOffsetOutOfRange: Channel data offset is out of range.

        Returns:
            int: 0
        """
        min_offset = -32768
        max_offset = 32768

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)

        if offset < min_offset or offset > max_offset:
            raise ChannelOffsetOutOfRange(self.name, min_offset, max_offset, channel, offset)

        self.data_offset[channel-1] = offset
        return 0

    def set_gain(self, channel, gain, slot=None):
        """Set channel gain.

        Args:
            channel (int): Channel number.
            gain (int): Channel gain.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Raises:
            ChannelWrongError: Input the wrong channel.
            ChannelGainOutOfRange: Channel gain is out of range.

        Returns:
            int: 0
        """
        if self.wave_type == 'i2':
            # LTC2000 DAC chip config free
            return 0
        registers = {
            0: ['DAC1.CH1_GAIN_HIGH', 'DAC1.CH1_GAIN_LOW'],
            1: ['DAC1.CH2_GAIN_HIGH', 'DAC1.CH2_GAIN_LOW'],
            2: ['DAC2.CH3_GAIN_HIGH', 'DAC2.CH3_GAIN_LOW'],
            3: ['DAC2.CH4_GAIN_HIGH', 'DAC2.CH4_GAIN_LOW']
        }

        min_gain = 0
        max_gain = 1024
        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        if gain < 0:
            gain += 1024
        if gain < min_gain or gain > max_gain:
            raise ChannelGainOutOfRange(self.name, min_gain, max_gain, channel, gain)

        print(f'setting gain: {channel} {gain}')
        channel_map = [2, 3, 0, 1]
        channel_id = channel_map[channel - 1]
        G98 = gain >> 8  # gain 2 bits lower
        G70 = gain & 0xFF  # gain 8 bits higer
        gain = [G98, G70]
        reg = registers[channel_id]
        slot = self.slot_check(slot)
        for i, cmd in enumerate(reg):
            if self.batch_mode:
                self.reg_packet[slot, cmd] = gain[i]
            else:
                self[slot, cmd] = gain[i]
        return 0

    def write_wave(self, channel, wave, slot=None):
        """Write wave to ddr then to awg bram.

        Args:
            channel (int): Channel number.
            wave (array): Wave data numpy array.

        Raises:
            ChannelWrongError: Input the wrong channel number.
            WaveLengthOutOfRange: Wave length out of range.

        Returns:
            int: 0
        """
        ddr_wave_map = {
            1: 0x10000000,
            2: 0x20000000,
            3: 0x30000000,
            4: 0x40000000
        }


        ddr_addr_reg = 'CPU.DDR_ADDR'
        ddr_len_reg = 'CPU.DDR_LEN'
        tdest_reg = 'CPU.TDEST'
        bram_reg = 'CPU.FLASH_FUN'
        tdest_wave_list = [5, 7, 9, 11]

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        max_wave = 20e4
        if len(wave) > max_wave:
            raise WaveLengthOutOfRange(self.name, max_wave, len(wave))
        wave_data = self.wave_calibrate(channel, wave)
        start_addr = ddr_wave_map[channel]
        length = self.calc_data_len(wave_data, format_type='wave')

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.w_mem_packet.write_mem(start_addr, wave_data, 'wave', slot)
            self.reg_packet[slot, ddr_addr_reg] = start_addr
            self.reg_packet[slot, ddr_len_reg] = length
            self.reg_packet[slot, tdest_reg] = tdest_wave_list[channel-1]
            self.reg_packet[slot, bram_reg] = 0x04
        else:
            self.write_mem(start_addr, wave_data, 'wave', slot)
            self[slot, ddr_addr_reg] = start_addr
            self[slot, ddr_len_reg] = length
            self[slot, tdest_reg] = tdest_wave_list[channel-1]
            self[slot, bram_reg] = 0x04
        return 0

    def wave_calibrate(self, channel, wave):
        """Wave data making up. Fill the default voltage data of 20ns
        at the end of wave. Then fill in wave data with multiples of 64 bytes.

        Args:
            channel (int): Channel number.
            wave (arrary): Wave data numpy array.

        Raises:
            ChannelWrongError: Input the wrong number.
            WaveDataOutOfRange: Wave data out of range.

        Returns:
            array: Wave data after calibrate.
        """
        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        min_data = self.min_data
        max_data = self.max_data
        data_offset = self.channel_default_voltage[channel-1] + self.data_offset[channel-1]
        pad_cnt = 40 + (32 - ((len(wave) + 40) & 31))
        data = np.pad(wave, [0, pad_cnt], 'constant', constant_values=(0, 0))
        data = data + data_offset
        if np.max(data) > max_data or np.min(data) < min_data:
            self.logger.critical(f'data in wave is out of range max:{np.max(data)}, min:{np.min(data)}')
        data = (np.clip(data, min_data, max_data)).astype('<u2')
        return data

    def write_seq(self, channel, seq, slot=None):
        """"Write wave sequnece to ddr then to awg bram.

        Args:
            channel (int): Channel number.
            seq (list): Wave sequence list.

        Raises:
            ChannelWrongError: Input the wrong channel.
            WaveSequenceLengthWrongError: Wave sequence out of range.

        Returns:
            int: 0
        """
        ddr_addr_reg = 'CPU.DDR_ADDR'
        ddr_len_reg = 'CPU.DDR_LEN'
        tdest_reg = 'CPU.TDEST'
        bram_reg = 'CPU.FLASH_FUN'
        tdest_wave_list = [4, 6, 8, 10]
        ddr_seq_map = {
            1: 0x70000000,
            2: 0x72000000,
            3: 0x54000000,
            4: 0x56000000
        }

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        max_seq_len = 16384
        if len(seq) & 0x3 != 0 or len(seq) > max_seq_len:
            raise WaveSequenceLengthWrongError(self.name, max_seq_len, len(seq))
        pad_cnt = (32 - (len(seq) & 31)) & 31
        seq = np.pad(seq, [0, pad_cnt], 'constant', constant_values=(0, 0))
        start_addr = ddr_seq_map[channel]
        length = self.calc_data_len(seq, format_type='seq')

        slot = self.slot_check(slot)
        if self.batch_mode:
            self.w_mem_packet.write_mem(start_addr, seq, 'seq', slot)
            self.reg_packet[slot, ddr_addr_reg] = start_addr
            self.reg_packet[slot, ddr_len_reg] = length
            self.reg_packet[slot, tdest_reg] = tdest_wave_list[channel-1]
            self.reg_packet[slot, bram_reg] = 0x04
        else:
            self.write_mem(start_addr, seq, 'seq', slot)
            self[slot, ddr_addr_reg] = start_addr
            self[slot, ddr_len_reg] = length
            self[slot, tdest_reg] = tdest_wave_list[channel-1]
            self[slot, bram_reg] = 0x04
        return 0

    def calc_data_len(self, data, format_type='byte'):
        """Calculate data bytes length.

        Args:
            data (list): Wave data or wave sequence data.
            format_type (str, optional): Data format type.How to pack *data* to binary data,
              supported types includes'byte', 'wave' and 'seq'. Defaults to 'byte'.

        Returns:
            int: Data bytes length.
        """
        type_map = dict(wave='<'+self.wave_type, seq='<u2', byte='B')
        if isinstance(data, bytes):
            return len(data)
        else:
            dtype = type_map[format_type]
            data_u16 = np.array(data, dtype=dtype)
            data_bytes = data_u16.tobytes()
            return len(data_bytes)

    def gen_iq(self, amp=32767, freq=100e6, phase=0, length=10e-6):
        """Generate IQ signal.

        Args:
            amp (u32, optional): The amplitude of signal. Defaults to 32767.
              Unit code.
            freq (u32, optional): The frequency of signal. Defaults to 100e6.
              Unit Hz.
            phase (int, optional): The phase of signal. Defaults to 0.
              Unit radian.
            length (float, optional): The length of signal. Defaults to 10e-6 10us.
              Unit second.

        Returns:
            numpy.array: Return IQ array.
        """
        assert length < 100e-3,  '单通道波形长度需要小于20ms'
        sample_rate = 2e9
        lcm_freq = np.lcm(int(freq), int(sample_rate))
        super_sample_rate = int(lcm_freq / sample_rate)
        _len = int(length * lcm_freq)
        line = np.linspace(0, length * freq * 2 * np.pi, _len, endpoint=False)+phase
        line = line[::super_sample_rate]
        # DAC data is signed integer, the sine wave doesn't need to be offsed.
        offset = 0 if self.wave_type == 'i2' else 1
        i_line = (np.sin(line) + offset) * amp
        q_line = (np.cos(line) + offset) * amp
        i_line = i_line.astype(self.wave_type)
        q_line = q_line.astype(self.wave_type)
        return np.array([i_line,  q_line])

    def output_sin_wave(self, channel=0, amp=32767, freq=100e6, phase=0, length=10e-6, is_trig=False):
        """Ouput sine wave directly.

        Args:
            channel (int, optional): The number of channel. Defaults to 0.
            amp (int, optional): The amplitude of sine wave. Defaults to 32767.
              Unit code.
            freq (float, optional): The frequency of sine wave. Defaults to 100e6.
              Unit Hz.
            phase (int, optional): The phase of sine wave. Defaults to 0.
              Unit radian.
            length (int, optional): The length of sine wave. Defaults to 10e-6.
              Unit second.
        """
        ch = [1, 2, 3, 4] if channel == 0 else [channel]
        wave_data = self.gen_iq(amp, freq, phase, length)[0]
        if is_trig:
            seq = [0, len(wave_data) >> 3, 0, 0x4000] * 4096
        else:
            seq = [0, len(wave_data) >> 3, 0, 0] * 4096
        for _ch in ch:
            self.stop_output_wave(_ch, slot=self.slot)
            self.write_seq(_ch, seq=seq, slot=self.slot)
            self.write_wave(_ch, wave_data, slot=self.slot)
            self.start_output_wave(_ch, slot=self.slot)

    def gen_squr(self, amp=32767, freq=100e6):
        """Ouput square wave directly.

        Args:
            amp (u32, optional): The amplitude of square wave . Defaults to 32767.
              Unit code.
            freq (u32, optional): The frequency of square wave. Defaults to 100e6.
              Unit Hz.
            length (float, optional): The length of . Defaults to 10e-6 10us.
              Unit second.

        Returns:
            numpy.array: Return squre wave.
        """
        smp_cnt = int(2e9 / freq)
        h_cnt = smp_cnt >> 1
        l_cnt = smp_cnt-h_cnt

        offset = 0 if self.wave_type == 'i2' else 1
        wave = [-1.0]*l_cnt + [1.0]*h_cnt
        wave = wave * 8
        wave = (np.array(wave)+offset) * amp
        wave = wave.astype(self.wave_type)
        return wave

    def output_squr_wave(self, channel=0, amp=32767, freq=10e6, is_trig=False):
        """Ouput square wave directyly.

        Args:
            channel (int, optional): The number of output channel. Defaults to 0.
            amp (int, optional): The amplitude of square wave. Defaults to 32767.
              Unit code.
            freq (float, optional): The frequency of square wave. Defaults to 100e6.
              Unit Hz
            phase (int, optional): The phase of square wave. Defaults to 0.
              Unit radian.
            length (_type_, optional): The length of square wave. Defaults to 10e-6.
              Unit second.
        """
        ch = [1, 2, 3, 4] if channel == 0 else [channel]
        wave_data = self.gen_squr(amp, freq)

        if is_trig:
            seq = [0, len(wave_data) >> 3, 0, 0x4000] * 4096
        else:
            seq = [0, len(wave_data) >> 3, 0, 0] * 4096
        for _ch in ch:
            self.stop_output_wave(_ch, slot=self.slot)
            self.write_seq(_ch, seq=seq, slot=self.slot)
            self.write_wave(_ch, wave_data, slot=self.slot)
            self.start_output_wave(_ch, slot=self.slot)

    def display_channel_status(self, channel=0, slot=None):
        """Display channel status

        Args:
            channel (int, optional): Input the wrong channel. Defaults to 0.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Raises:
            ChannelWrongError: Input the wrong channel.
        """
        regs = {
            1: 'AWG.STATUS1',
            2: 'AWG.STATUS2',
            3: 'AWG.STATUS3',
            4: 'AWG.STATUS4',
        }
        if channel < 0 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        status = []
        slot = self.slot_check(slot)
        if channel == 0:
            for i in range(1, self.channel_amount+1):
                reg = regs[i]
                status.append(self[slot, reg])
        else:
            reg = regs[channel]
            status.append(self[slot, reg])
        st1_map = {
            1: 'Channel is outputting wave',
            0: 'Channel output idle'
        }
        st74_map = {
            0b0000: 'AWG is idle',
            0b0011: 'AWG is loading the sequence',
            0b0010: 'AWG is waiting for trigger',
            0b0111: 'AWG is loading the wave data',
            0b0100: 'AWG is loading the last one data',
        }
        for idx, st in enumerate(status):
            if not channel:
                ch = idx + 1
            else:
                ch = channel
            st1 = (st >> 0) & 0x1
            st74 = (st >> 4) & 0xF
            st1_msg = st1_map[st1]
            st74_msg = st74_map[st74]
            msg = (f'Channel [{ch}] status info | '
                   f'ST[7-4]: {st74_msg:>12s}({st74:04b}) | '
                   f'ST[1]: {st1_msg:>8s}({st1}) ')
            self.logger.info(msg)

    def get_config_addr_from_bin(self, bin_data, config_type, slot=None):
        """Get flash config address based on bin file type.

        Args:
            bin_data (bytes): Bin file data.
            config_type (str): Bin file type. Update or golden.
            slot ([type]): The slot of the crate.

        Raises:
            FlashTypeNotMatchError: Awg flash type is differen from
              the flash type of bin file.
            BinFileTypeNoTMatchError: The config type of bin file is
              different from set type.

        Returns:
            int: Flash config address.
        """
        # check bin flash type: Spansion or Micron
        type_reg = 'CPU.FLASH_TYPE'
        slot = self.slot_check(slot)
        flash_type = self[slot, type_reg]
        if flash_type == 0:
            flash_type = 'Micron'
        else:
            flash_type = 'Spansion'
        head_bytes = bin_data[88:92]
        mircron_bytes = b'\x30\x03\xe0\x01'
        if head_bytes == mircron_bytes:
            bin_type = 'Micron'
        else:
            bin_type = 'Spansion'
        if flash_type != bin_type:
            raise FlashTypeNotMatchError(bin_type, flash_type)

        # check bin file type: update or golden
        bin_config_type = None
        config_addr = None
        flash_map = {'Micron': 124, 'Spansion': 104}
        flash_address_pos = flash_map[flash_type]
        fallbacken = bin_data[flash_address_pos+11]
        bin_flash_nxt_bytes = bin_data[flash_address_pos:flash_address_pos+4]
        bin_flash_nxt_addr, = unpack('>l', bin_flash_nxt_bytes)
        if bin_flash_nxt_addr == 0x00F50000 and fallbacken == 15:
            bin_config_type = 'golden'
            config_addr = 0x00000000
        elif bin_flash_nxt_addr == 0 and fallbacken == 0:
            bin_config_type = 'update'
            config_addr = 0x00F50000
        if bin_config_type != config_type:
            raise BinFileTypeNotMatchError(bin_config_type, config_type)
        return config_addr

    def check_op_status(self, timeout, slot=None, console=False):
        """Check cpu op_status register.

        Args:
            slot (int): The slot of the crate.
            timeout (float): Timeout for check cpu op_status.

        Returns:
            int: Cpu op status register value.
        """
        op_status_reg = 'CPU.OP_STATUS'

        waited_time = 0
        time_interval = 1
        op_status = None
        slot = self.slot_check(slot)
        response_timeout = self.RESPONSE_TIMEOUT
        self.RESPONSE_TIMEOUT = 60
        if console:
            pbar = ProgressBar(max=timeout, hint=f'{self.name} CHECK OP STATUS')
            pbar.start()
        while waited_time < timeout:
            op_status = self[slot, op_status_reg]
            if op_status == 0:
                if console:
                    pbar.update(timeout-waited_time)
                self.RESPONSE_TIMEOUT = response_timeout
                break
            time.sleep(time_interval)
            waited_time += time_interval
            if console:
                pbar.update(time_interval)
        return op_status

    def write_flash(self, addr, data, slot=None, ddr_address=0x58000000, timeout=500):
        """Write flash accroding to 1. Write data to DDR 2. Move data from DDR to flash.

        Args:
            addr (hexadecimal): Flash address data written to.
            data (bytes): bytes data.
            slot (int): The slot of the crate.
            ddr_address (hexadecimal, optional): DDR address data written to.
              Defaults to 0x58000000.
            timeout (int, optional): Timeout for write flash. Defaults to 500.

        Raises:
            WriteDDRTimeoutError: Write data to DDR timeout.
            WriteFlashTimeoutError: Move DDR data to flash timeout.

        Returns:
            int: 0
        """
        print(f'{self.name} WRITE DATA TO FLASH BEGIN.')
        try_times = 0
        max_times = 5
        while try_times < max_times:
            try:
                self.write_mem(ddr_address, data)
                readback_data = bytes(self.read_mem(ddr_address, len(data)))[:len(data)]
                if readback_data == data:
                    break
            except RecvTimeoutError:
                print(f'{self.name} WRITE MEM TO DDR FAIL FOR {try_times+1} time.')
            try_times += 1
            if try_times == max_times:
                raise WriteDDRTimeoutError(self.name, max_times)
        ddr_addr_reg = 'CPU.DDR_ADDR'
        ddr_len_reg = 'CPU.DDR_LEN'
        flash_addr_reg = 'CPU.FLASH_ADDR'
        flash_func_reg = 'CPU.FLASH_FUN'

        slot = self.slot_check(slot)
        self[slot, ddr_addr_reg] = ddr_address
        self[slot, flash_addr_reg] = addr
        self[slot, ddr_len_reg] = len(data)
        self[slot, flash_func_reg] = 0x01
        op_status = self.check_op_status(timeout, slot=slot, console=True)
        if op_status:
            raise WriteFlashTimeoutError(self.name, timeout, op_status)
        print(f'\n{self.name} WRITE DATA TO FALSH END.')
        return 0

    def read_flash(self, addr, length, slot=None, ddr_address=0x58000000, timeout=500):
        """Read flash data accroding to 1. Move data from flash to DDR
        2. Read flash data from DDR.

        Args:
            addr (hexadecimal): Flash address data read from.
            length (int): The length of flash data.
            slot (int): The slot of the crate.
            ddr_address (hexadecimal, optional): The DDR address flash data in.
              Defaults to 0x58000000.
            timeout (int, optional): Timeout of read flash. Defaults to 1000.

        Raises:
            ReadFlashTimeoutError: Read flash timeout.

        Returns:
            bytes: Flash data.
        """
        print(f'{self.name} READ DATA FROM FLASH BEGIN.')
        flash_addr_reg = 'CPU.FLASH_ADDR'
        flash_len_reg = 'CPU.FLASH_LEN'
        ddr_addr_reg = 'CPU.DDR_ADDR'
        flash_func_reg = 'CPU.FLASH_FUN'

        slot = self.slot_check(slot)
        self[slot, flash_addr_reg] = addr
        self[slot, flash_len_reg] = length
        self[slot, ddr_addr_reg] = ddr_address
        self[slot, flash_func_reg] = 0x02
        op_status = self.check_op_status(timeout, slot=slot, console=True)
        if op_status:
            raise ReadFlashTimeoutError(self.name, timeout, op_status)
        data = bytes(self.read_mem(ddr_address, length, slot=slot))[:length]
        print(f'\n{self.name} READ DATA FROM FLASH END.')
        return data

    def remote_config(self, file_path, config_type='update', slot=None):
        """Remotely configure the Bin file of the AWG.

        Args:
            file_path (str): The path of bin file.
            config_type (str, optional): The config type of bin file, 'update' or 'golden'.
              Defaults to 'update'.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Raises:
            BinFileNotFoundError: Bin file has not found.
            FlashDataNotMatch: The flash data configured is different form the bin file.

        Returns:
            int: 0
        """
        print(f'{self.name} REMOTE CONFIG PROCESS BEGIN.')
        if not os.path.exists(file_path):
            raise BinFileNotFoundError(file_path)
        with open(file_path, 'rb') as f:
            bin_data = f.read()

        slot = self.slot_check(slot)
        config_addr = self.get_config_addr_from_bin(bin_data, config_type, slot)
        pad_cnt = (1024 - (len(bin_data) & 0x3FF)) & 0x3FF
        bin_data += b'0' * pad_cnt
        self.write_flash(config_addr, bin_data, slot)
        flash_data = self.read_flash(config_addr, len(bin_data), slot)
        if flash_data != bin_data:
            raise FlashDataNotMatch()
        print(f'{self.name} REMOTE CONFIG PROCESS END, SUCCESS!')
        return 0

    def config_device_info(self, mac_address, serial_num, ip_address, slot=None, flash_address=0x1F80000):
        """Config device information of AWG.

        Args:
            mac_address (str): The mac address of AWG.
            serial_num (str): The serial number of AWG.
            ip_address (str): The ip address of AWG.
            slot (int, slot): The slot of crate. Defaults to 0.
            flash_address (hexadecimal, optional): The flash address data written to.
              Defaults to 0x1F80000.

        Raises:
            IllegalMacAddressError: Mac address is illegal.
            IllegalIpAddressError: Ip address is illegal.

        Returns:
            int: 0
        """
        mac = [0, 0] + [int(addr, 16) for addr in mac_address.split('-')]
        if len(mac) != 8:
            raise IllegalMacAddressError(mac_address)
        ip = [int(i) for i in ip_address.split('.')]
        if len(ip) != 4:
            raise IllegalIpAddressError(ip_address)
        mac[6] = ip[2]
        mac[7] = ip[3]
        serial_num = bytes(serial_num.encode('utf-8'))
        mac_data = pack('8B', *mac)
        mac_data += pack(f'{len(serial_num)}s', serial_num)
        slot = self.slot_check(slot)
        self.write_flash(flash_address, mac_data, slot)
        return 0

    def config_network_info(
        self, ip, monitor_ip='10.0.1.1', netmask='255.255.0.0',
        gateway='10.0.1.1', slot=None, flash_adrress=0x1F90000
    ):
        """Config network information of AWG.

        Args:
            ip (str): The ip address of AWG.
            monitor_ip (str, optional): The monitor ip address of AWG. Defaults to '10.0.1.1'.
            netmask (str, optional): The netmask address of AWG. Defaults to '255.255.0.0'.
            gateway (str, optional): The gateway address of AWG. Defaults to '10.0.1.1'.
            slot (int, optional): The slot of crate. Defaults to 0.
            flash_adrress (hexadecimal, optional): The flash address data written to.
              Defaults to 0x1F90000.

        Returns:
            int: 0
        """
        ip = [int(i) for i in ip.split('.')]
        monitor_ip = [int(i) for i in monitor_ip.split('.')]
        netmask = [int(i) for i in netmask.split('.')]
        gateway = [int(i) for i in gateway.split('.')]
        ip_data = pack('4B', *ip)
        ip_data += pack('4B', *monitor_ip)
        ip_data += pack('4B', *netmask)
        ip_data += pack('4B', *gateway)

        slot = self.slot_check(slot)
        self.write_flash(flash_adrress, ip_data, slot)
        return 0

    def config_awg_para_info(
        self, gain, data_offset, cal_temperature,
        cal_ppm, slot=None, flash_address=0x1FA0000
    ):
        """Config awg parameters information of AWG.

        Args:
            gain (list): The gain of four channels.
            data_offset (list): The gain of four channels.
            cal_temperature (Decimal): The temperature after calibration of AWG.
            cal_ppm (Decimal): The ppm after calibration of AWG.
            slot (int, optional): The slot of crate. Defaults to 0.
            flash_address (hexadecimal, optional): The flash address data written to.
              Defaults to 0x1FA0000.

        Returns:
            int: 0
        """
        cal_temperature = [int(c * 65536) for c in cal_temperature]
        cal_ppm = [int(p * 65536) for p in cal_ppm]
        para_data = pack('4i4i4I4I', *gain, *data_offset, *cal_temperature, *cal_ppm)

        slot = self.slot_check(slot)
        self.write_flash(flash_address, para_data, slot)
        return 0

    def get_awg_info(
        self, slot=None, device_address=0x1F80000,
        network_address=0x1F90000, para_address=0x1FA0000
    ):
        """Get AWG information.

        Args:
            slot (int, optional): The slot of crate. Defaults to 0.
            device_address (hexadecimal, optional): Flash address device info wrriten to.
              Defaults to 0x1F80000.
            network_address (hexadecimal, optional): Flash address netwrok info wrriten to.
              Defaults to 0x1F90000.
            para_address (hexadecimal, optional): Flash address parameters info wrriten to.
              Defaults to 0x1FA0000.

        Returns:
            int: 0
        """
        serial_len = 11
        info_dic = {}

        slot = self.slot_check(slot)
        _dev_info = self.read_flash(device_address, 8 + serial_len, slot)
        _net_info = self.read_flash(network_address, 16, slot)
        _para_info = self.read_flash(para_address, 64, slot)
        mac = unpack('6B', _dev_info[2:8])
        serial = unpack(f'{serial_len}s', _dev_info[8:])[0].decode()
        ip = unpack('4B', _net_info[0:4])
        monitor_ip = unpack('4B', _net_info[4:8])
        netmask = unpack('4B', _net_info[8:12])
        gate_way = unpack('4B', _net_info[12:16])
        _d = unpack('4i4i4I4I', _para_info[0:64])
        info_dic['MAC ADDRESS'] = '-'.join(['{:0>2x}'.format(i) for i in mac])
        info_dic['SERIAL NUM'] = serial
        info_dic['IP ADDRESS'] = '.'.join([str(i) for i in ip])
        info_dic['Monitor IP'] = '.'.join([str(i) for i in monitor_ip])
        info_dic['NETMASK'] = '.'.join([str(i) for i in netmask])
        info_dic['GATEWAY'] = '.'.join([str(i) for i in gate_way])
        info_dic['GAIN'] = _d[0:4]
        info_dic['OFFSET'] = [hex(32768 - i) for i in _d[4:8]]
        info_dic['CAL TEMPERATURE(℃)'] = [round((i / 65536), 2) for i in _d[8:12]]
        info_dic['CAL PPM(ppm/℃)'] = [round((i / 65536), 2) for i in _d[12:16]]
        print(f'{self.name} INFOMATION READ BACK')
        for key in info_dic:
            print(f'{key}: {info_dic[key]}')
        return 0

    def reboot(self, slot=None):
        """Awg fpga logic reconfiguration.

        Args:
            slot (int, optional): The slot of crate. Defaults to 0.

        Returns:
            int: 0
        """
        reboot_reg = 'CPU.REBOOT'

        slot = self.slot_check(slot)
        self[slot, reboot_reg] = 1
        time.sleep(15)
        return 0

    def set_monitor_ip(self, monitor_ip, port, slot=None):
        """Set da monitor ip address

        Args:
            monitor_ip (str): Da monitor ip address.
            port (int): Da monitor port.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Raises:
            IllegalIpAddressError: Ip address is illegal.

        Returns:
            int: 0
        """
        compile_ip = re.compile(r'^(172|10)\.'
                                r'(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.'
                                r'(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)\.'
                                r'(1\d{2}|2[0-4]\d|25[0-5]|[1-9]\d|\d)$')
        if not compile_ip.match(monitor_ip):
            raise IllegalIpAddressError(monitor_ip)
        monitor_address_reg = 'CPU.IP_ADDRESS'
        port_reg = 'CPU.PORT'
        enable_reg = 'CPU.STATUS_EN'

        slot = self.slot_check(slot)
        self[slot, monitor_address_reg] = ip_to_int(monitor_ip)
        self[slot, port_reg] = port
        self[slot, enable_reg] = 1
        return 0

    def close_da_monitor(self, slot=None):
        """Disabled da monitor function.

        Args:
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: 0
        """
        enable_reg = 'CPU.STATUS_EN'

        enable = 0
        slot = self.slot_check(slot)
        self[slot, enable_reg] = enable
        return 0

    def pipeline_rest(self, slot=None):
        """Reset pipeline catch free circuit num, circuit start number,
        completed circuit number, circuit to be executed number.

        Args:
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: 0
        """
        reset_reg = 'PIPELINE.RESET'

        reset = 1
        slot = self.slot_check(slot)
        self[slot, reset_reg] = reset
        return 0

    def get_ch_avail_circuit_num(self, channel, slot=None):
        """Get the number of channel that circuits can be sent.

        Args:
            channel (int): Channel number.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: Number of circuits.
        """
        avail_ckt_num_reg = 'PIPELINE.AVAIL_CKT_NUM'

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet(slot, avail_ckt_num_reg)
            num = 0
        else:
            num = (self[slot, avail_ckt_num_reg] & (0xFF << 8 * (channel - 1))) >> 8 * (channel - 1)
        return num

    def get_ch_avail_start_num(self, channel, slot=None):
        """Get the start number of channel that circuit sent to.

        Args:
            channel ([type]): Channel number.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: Start number of circuit.
        """
        avail_ckt_start_num_reg = 'PIPELINE.AVAIL_START_NUN'

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet(slot, avail_ckt_start_num_reg)
        else:
            start_num = (self[slot, avail_ckt_start_num_reg] & (0xFF << 8 * (channel - 1))) >> 8 * (channel - 1)
        return start_num

    def set_download_circuit_amount(self, amount_list, slot=None):
        """Set the number of channel that circuits has been sent.

        Args:
            amount_list (int): Amount of circuits that every channel downloads.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: 0
        """
        dl_ckt_amount_reg = 'PIPELINE.DL_CKT_NUM'

        dl_amount = 0
        for ch, amount in enumerate(amount_list):
            dl_amount |= amount << 8 * ch
        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet[slot, dl_ckt_amount_reg] = dl_amount
        else:
            self[slot, dl_ckt_amount_reg] = dl_amount
        return 0

    def search_ch_circuit(self, channel, circuit_num, slot=None):
        srch_ckt_num_regs = {
            1: 'PIPELINE.SRCH_CKT_NUM_CH1',
            2: 'PIPELINE.SRCH_CKT_NUM_CH2',
            3: 'PIPELINE.SRCH_CKT_NUM_CH3',
            4: 'PIPELINE.SRCH_CKT_NUM_CH4'
        }

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        srch_reg = srch_ckt_num_regs[channel]
        if self.batch_mode:
            self.reg_packet[slot, srch_reg] = circuit_num
        else:
            self[slot, srch_reg] = circuit_num

    def get_ch_ckt_analysis_result(self, channel, slot=None):
        """Get result of channel circuit analysis.

        Args:
            channel (int): Channel number.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            dict: Circuit analysis result.
        """
        ckt_analysis_result_regs = {
            1: 'PIPELINE.CKT_ANALYSIS_RESULT_CH1_2',
            2: 'PIPELINE.CKT_ANALYSIS_RESULT_CH1_2',
            3: 'PIPELINE.CKT_ANALYSIS_RESULT_CH3_4',
            4: 'PIPELINE.CKT_ANALYSIS_RESULT_CH3_4'
        }

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)

        ckt_result_reg = ckt_analysis_result_regs[channel]
        result = {'status': None, 'storage_num': None}
        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet(slot, ckt_result_reg)
            results = 0
        else:
            results = self[slot, ckt_result_reg]
            for idx, key in enumerate(result.keys()):
                if channel in (2, 4):
                    idx += 2
                result[key] = (results & (0xFF << 8 * idx)) >> 8 * idx
        return result

    def enable_ch_circuit(self, channel, circuit_num, slot=None):
        """Enable circuit of channel.

        Args:
            channel (int): Channel number.
            circuit_num (int): Number of circuit.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: 0
        """
        exec_ckt_regs = {
            1: 'PIPELINE.EXEC_CKT_NUM_CH1',
            2: 'PIPELINE.EXEC_CKT_NUM_CH2',
            3: 'PIPELINE.EXEC_CKT_NUM_CH3',
            4: 'PIPELINE.EXEC_CKT_NUM_CH4'
        }

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        exec_ckt_reg = exec_ckt_regs[channel]
        self[slot, exec_ckt_reg] = circuit_num
        return 0

    def get_ch_abandon_state(self, channel, slot=None):

        """Get the abandon state of channel.

        Note:
            0x00: Circuit analysis is not finished.
            0x55: Got the wrong circuit number.
            0xFF: Circuit analysis has finished.

        Args:
            channel (int): Channel number.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: Abandon state.
        """
        abandon_state_reg = 'PIPELINE.ABANDON_ST'

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        if self.batch_mode:
            self.reg_packet(slot, abandon_state_reg)
            state = None
        else:
            states = self[slot, abandon_state_reg]
            ch = channel - 1
            state = (states & (0xFF << 8 * ch)) >> 8 * ch
        return state

    def abandon_ch_circuit(self, channel, exp_id, slot=None):
        """Abadon circuit of channel.

        Args:
            channel (int): Channel number.
            exp_id (int): Experiment number.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Returns:
            int: 0
        """
        abandon_exp_regs = {
            1: 'PIPELINE.ABANDON_EXP_CH1',
            2: 'PIPELINE.ABANDON_EXP_CH2',
            3: 'PIPELINE.ABANDON_EXP_CH3',
            4: 'PIPELINE.ABANDON_EXP_CH4'
        }

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)
        slot = self.slot_check(slot)
        abandon_exp_reg = abandon_exp_regs[channel]
        if self.batch_mode:
            self.reg_packet[slot, abandon_exp_reg] = exp_id
        else:
            self[slot, abandon_exp_reg] = exp_id
        return 0

    def download_circuit(
        self, channel, exp_id, circuit_num, loop_cnt,
        trig_delay, trig_count, wave, seq, slot=None
    ):
        """

        Args:
            channel (int): Channel number.
            exp_id (int): Experiment id.
            circuit_num (int): Circuit number.
            loop_cnt (int): Circuit loop count.
            trig_delay (float): AWG trig delay.
            trig_count (int): AWG trig count.
            wave (list): Wave data.
            seq (list): Sequence data.
            slot (int, optional): The slot of the crate. Defaults to 0.

        Raises:
            ChannelWrongError: Input the wrong channel.
            WaveLengthOutOfRange: Wave length is out of range.
            WaveSequenceLengthWrongError: Wave sequence is out of range.

        Returns:
            int: 0
        """
        base_ddr_map = {
            1: 0x00000000,
            2: 0x08000000,
            3: 0x10000000,
            4: 0x08000000
        }
        trig_count_name = 'TRIG.C_TRIG_COUNT_L1'
        trig_start_name = 'TRIG.C_START_EXTERNAL'
        trig_end_name = 'TRIG.C_STOP_START_EXTERNAL'

        if channel < 1 or channel > self.channel_amount:
            raise ChannelWrongError(self.name, channel)

        trig_count_addr = sum(self.reg_map.get_addr_by_name(trig_count_name))
        trig_start_addr = sum(self.reg_map.get_addr_by_name(trig_start_name))
        trig_end_addr = sum(self.reg_map.get_addr_by_name(trig_end_name))
        reg_addr_list = [trig_count_addr, trig_start_addr, trig_end_addr]
        reg_amount = 3
        reg_length = reg_amount * 4 * 2

        trig_start = round((self.trig_delay_offset + trig_delay) / 4e-9 + 1)
        trig_end = round((self.trig_delay_offset + trig_delay) / 4e-9 + 5)
        reg_data_list = [trig_count, trig_start, trig_end]
        max_wave = 20e4
        if len(wave) > max_wave:
            raise WaveLengthOutOfRange(self.name, max_wave, len(wave))
        wave_data = self.wave_calibrate(channel, wave)
        wave_length = self.calc_data_len(wave_data, format_type='wave')
        max_seq_len = 16384
        if len(seq) & 0x3 != 0 or len(seq) > max_seq_len:
            raise WaveSequenceLengthWrongError(self.name, max_seq_len, len(seq))
        pad_cnt = (32 - (len(seq) & 31)) & 31
        seq = np.pad(seq, [0, pad_cnt], 'constant', constant_values=(0, 0))
        seq_length = self.calc_data_len(seq, format_type='seq')

        circuit = [
            {
                'inst_name': 'START_CIRCUIT',
                'parameter': {
                    'exp_id': exp_id,
                    'circuit_num': circuit_num,
                    'loop_count': loop_cnt
                }
            },
            {
                'inst_name': 'PARAM_CIRCUIT',
                'parameter': {
                    'length': reg_length,
                    'reg_amount': reg_amount,
                    'reg_addr_list': reg_addr_list,
                    'reg_data_list': reg_data_list
                }
            },
            {
                'inst_name': 'DIRECT_WAVE',
                'parameter': {
                    'length': wave_length,
                    'wave_data': wave_data
                }
            },
            {
                'inst_name': 'DIRECT_SEQ',
                'parameter': {
                    'length': seq_length,
                    'seq_data': seq
                }
            },
            {
                'inst_name': 'STOP_CIRCUIT',
                'parameter': {}
            },
        ]
        slot = self.slot_check(slot)
        circuit_packet = self.pipline_inst.pack_instructions(circuit)
        self.display_data('Instruction Bytes', circuit_packet)
        ddr_address = base_ddr_map[channel] + circuit_num * 0x7FFFF
        if self.batch_mode:
            self.w_mem_packet.write_mem(ddr_address, circuit_packet, format_type='byte', slot=slot)
        else:
            self.write_mem(ddr_address, circuit_packet, format_type='byte', slot=slot)
        return 0


class AWGPacket:
    def __init__(self, awg, pkt_type):
        self.awg = awg
        self.result = None
        self.response = None
        self.pkt_type = pkt_type

    def update_result(self, data):
        result = self.parse_response(data)
        self.result = result
        self.check_result()

    def get_result(self):
        return self.result

    @property
    def sock(self):
        return self.awg.sock

    @property
    def awg_name(self):
        return self.awg.name

    @property
    def protocol(self):
        return self.awg.protocol

    def send(self):
        raise NotImplementedError('send is not implemented')

    def parse_response(self, data):
        raise NotImplementedError('parse_response is not implemented')

    def check_result(self):
        # raise NotImplementedError('check_result is not implemented')
        pass


class RegisterPacket(AWGPacket):
    """Class for batch register operations.
    """

    def __init__(self, awg):
        self.queue = []
        AWGPacket.__init__(self, awg, 'reg')

    def get_addr(self, name):
        return self.awg.reg_map.get_addr_by_name(name)

    def __setitem__(self, key, value):
        slot = 0
        if isinstance(key, tuple):
            if len(key) == 3:
                slot, base_addr, addr = key
            else:
                prev, last = key
                if isinstance(last, str):
                    base_addr, addr = self.awg.reg_map.get_addr_by_name(last)
                    slot = prev
                else:
                    base_addr, addr = prev, last
        elif isinstance(key, str):
            base_addr, addr = self.get_addr(key)
        if not self.awg.dev_mode and not self.awg.reg_map.writable(base_addr, addr):
            name = self.awg.reg_map.get_name_by_addr(base_addr, addr)
            raise WriteRegisterPermissionError(name)
        entry = (slot, base_addr, addr, value)
        self.queue.append(entry)

    def __call__(self, *key):
        slot = 0
        if len(key) == 3:
            slot, base_addr, addr = key
        elif len(key) == 2:
            prev, last = key
            if isinstance(last, str):
                base_addr, addr = self.awg.reg_map.get_addr_by_name(last)
                slot = prev
            else:
                base_addr, addr = prev, last
        elif len(key) == 1:
            base_addr, addr = self.get_addr(key[0])
        if not self.awg.dev_mode and not self.awg.reg_map.readable(base_addr, addr):
            name = self.awg.reg_map.get_name_by_addr(base_addr, addr)
            raise ReadRegisterPermissionError(name)
        entry = (slot, base_addr, addr)
        self.queue.append(entry)

    def send(self, wait_response=True):
        registers = self.queue
        if self.queue:
            ret = self.awg.send_reg_cmd(registers, wait_response=wait_response)
        else:
            ret = 0
        return ret

    def parse_response(self, data):
        self.response = data
        return self.awg.protocol.parse_reg_response(data)

    def check_result(self):
        # TODO: check write register result if there are write operations in self.queue
        pass

    def clear(self):
        self.queue = []


class MemoryPacket(AWGPacket):
    def __init__(self, awg):
        self.address = []
        self.data = []
        self.length = []
        self.format_type = []
        self.slot = []
        self.operation = None
        AWGPacket.__init__(self, awg, 'mem')

    def write_mem(self, address, data, format_type='byte', slot=None):
        self.address.append(address)
        self.data.append(data)
        self.format_type.append(format_type)
        slot = self.awg.slot_check(slot)
        self.slot.append(slot)
        self.operation = 'write'

    def read_mem(self, address, length, format_type='byte', slot=None):
        self.address.append(address)
        self.format_type.append(format_type)
        self.length.append(length)
        slot = self.awg.slot_check(slot)
        self.slot.append(slot)
        self.operation = 'read'

    def send(self, wait_response=True):
        if self.operation == 'write':
            self.sent_frame_cnt = self.awg.write_mem(
                self.address, self.data,
                self.format_type, self.slot, wait_response=wait_response)
            if wait_response:
                self.result = self.sent_frame_cnt
                ret = self.sent_frame_cnt
            else:
                cnt = int(np.ceil(self.sent_frame_cnt / self.protocol.MAX_MEM_SEND_FRAMES))
                ret = 8 * cnt  # response size in bytes
        elif self.operation == 'read':
            ret = self.awg.read_mem(
                self.address, self.length,
                self.format_type, self.slot, wait_response=wait_response)
            self.read_mem_ret = ret
        else:
            ret = 0
        return ret

    def parse_response(self, data):
        ret = 0
        # self.awg.display_data(f'{self.awg.name} Recv Response', data)
        self.response = data
        if self.operation == 'write':
            offset = 0
            segment = 8
            while offset < len(self.response):
                cnt, _ = self.protocol.parse_write_mem_response(self.response[offset:offset+segment])
                ret += cnt
                offset += segment
        else:
            response_sizes = self.read_mem_ret
            offset = 0
            ret = []
            for ftype, rsize in zip(self.format_type, response_sizes):
                segment = data[offset:(offset + rsize)]
                mem_data = self.protocol.parse_read_mem_response(segment, ftype)
                ret.append(mem_data)
                offset += rsize
            if len(ret) == 1:
                ret = ret[0]
        return ret

    def check_result(self):
        if self.operation == 'write':
            recv_cnt_by_awg = self.result
            if recv_cnt_by_awg != self.sent_frame_cnt:
                raise SendNotMatchRecvError(
                    self.awg_name, self.sent_frame_cnt, recv_cnt_by_awg)
        else:
            # TODO: check read back data length
            pass

    def clear(self):
        self.address = []
        self.data = []
        self.length = []
        self.format_type = []
        self.slot = []
        self.operation = None


class AWGMemoryMapper:
    """Class for mapping awg memory like a Python list.
    """

    def __init__(self, awg, memory_type):
        self.awg = awg
        self.memory_type = memory_type

    def get_range(self, key):
        if isinstance(key, slice):
            start = key.start
            stop = key.stop
            if start is None:
                start = 0
            if stop is None:
                stop = start + 1
        elif isinstance(key, int):
            start = key
            stop = start + 1
        return start, stop

    def index_to_memory_addr(self, start, stop):
        start_KB = start // 1024 * 1024
        end_KB = (stop - 1) // 1024 * 1024
        length = end_KB - start_KB + 1024
        return start_KB, length

    def __getitem__(self, key):
        start, stop = self.get_range(key)
        start_address, length = self.index_to_memory_addr(start, stop)
        data = self.awg.read_mem(start_address, length)
        values = data[(start - start_address):(stop - start_address)]
        if len(values) == 1:
            values = values[0]
        return values

    def __setitem__(self, key, value):
        start, stop = self.get_range(key)
        start_address, length = self.index_to_memory_addr(start, stop)
        data = self.awg.read_mem(start_address, length)
        data[(start - start_address):(stop - start_address)] = value
        self.awg.write_mem(start_address, data)
