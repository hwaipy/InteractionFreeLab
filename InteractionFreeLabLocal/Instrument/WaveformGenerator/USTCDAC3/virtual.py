# coding: utf-8
import socket
import select
from struct import pack
from .logger import get_logger
from .protocol import SQCProtocol
from .utils import format_hex_data
from collections import defaultdict


class VirtualAWGManager:
    """Class for imitating multiple awg devices according to SQC protocol.
    """

    def __init__(self, ip=None, console_log=True):
        if ip is None:
            ip = 'localhost'
        self.ip = ip
        self.console_log = True
        self.protocol = SQCProtocol()

    def listen(self, ports):
        tag = '_'.join([str(p) for p in ports])
        self.logger = get_logger(
            f'virtual_awg_{tag}', console_log=self.console_log)

        sockets = []
        for port in ports:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_socket.bind((self.ip, port))
            sockets.append(server_socket)
        self.logger.info(f'Listen ip: {self.ip}, ports: {ports}')

        empty = []
        mem_recv = defaultdict(int)
        while True:
            # readable, writable, exceptional sockects
            readable, _, _ = select.select(sockets, empty, empty, 1)
            for s in readable:
                (client_data, client_address) = s.recvfrom(32 * 1024)
                recv_data = format_hex_data(client_data)
                self.logger.debug(f'Recv: {recv_data}')
                frame_info = self.protocol.parse_cmd(client_data)
                cmd_type = frame_info['cmd_type']
                op_type = frame_info['op_type']
                is_last = frame_info['is_last']
                msg = (
                    f'Recv from {client_address}: '
                    f'cmd_type = {cmd_type}, is_last = {is_last}, '
                    f'op_type = {op_type}')
                self.logger.info(msg)
                if cmd_type == 'mem' and op_type == 'write':
                    mem_recv[s] += 1
                    if is_last == 1:
                        response = self.write_mem_response(mem_recv[s])
                        s.sendto(response, client_address)
                        mem_recv[s] = 0
                        hex_data = format_hex_data(response)
                        self.logger.info(
                            f'Send to {client_address}, data: {hex_data}')
                elif cmd_type == 'mem' and op_type == 'read':
                    addr = frame_info['addr']
                    length = frame_info['length']
                    cnt = length // SQCProtocol.MEM_FRAME_DATA_LEN
                    self.logger.info(
                        f'Read data from {addr:08x}, length {length}')
                    for i in range(cnt):
                        frame_num = pack('<I', i)
                        tag = b'USTC'
                        data = b'\x00' * SQCProtocol.MEM_FRAME_DATA_LEN
                        frame = frame_num + tag[::-1] + data
                        s.sendto(frame, client_address)
                        self.logger.info(f'Send frame {i}')
                elif cmd_type == 'reg':
                    tag = b'USTC'
                    length = frame_info['length']
                    len_bytes = pack('<I', length)
                    data = frame_info['data']
                    response = tag[::-1] + len_bytes + data
                    s.sendto(response, client_address)
                    self.logger.info(
                        f'Send register data to {client_address}: '
                        f'{format_hex_data(response)}')

    def write_mem_response(self, recv_cnt):
        cnt_bytes = pack('<I', recv_cnt)
        tag = b'USTC'
        response = cnt_bytes + tag[::-1]
        return response
