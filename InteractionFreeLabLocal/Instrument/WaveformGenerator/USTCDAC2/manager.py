# coding: utf-8
import time
import select
from .driver import UstcAWG
from .error import RecvTimeoutError
import socket
from multiprocessing import Pool
import functools
import traceback
import os
import platform


class AWGManager:
    """Class for awg management.
    """

    def __init__(self):
        self.pool = {}

    def connect(self, name, address):
        ip, port = address
        awg = UstcAWG(ip, port, name)
        self.pool[name] = awg

    def get_awg(self, name):
        return self.pool[name]

    def packet(self, awg_name, pkt_type):
        awg = self.get_awg(awg_name)
        packet = awg.packet(pkt_type)
        return packet

    def send(self, packets, timeout=10, multi_process=False, max_workers=4):
        if multi_process:
            result = self.send_multi_process(packets, max_workers)
        else:
            result = self.send_single_process(packets, timeout)
        return result

    def send_multi_process(self, packets, max_workers):
        result = {}
        try:
            pool = Pool(max_workers)
            for packet in packets:
                pool.apply_async(packet_process, (packet, ))
            pool.close()
            pool.join()
        except KeyboardInterrupt as e:
            sys = platform.system().lower()
            if sys == 'windows':
                pid = os.getpid()
                os.popen(f'taskkill.exe /f /pid:{pid}')  # this command resquired to force procees exit on windows
            else:
                raise e
        return result

    def send_single_process(self, packets, timeout):
        response_info = {}
        for pkt in packets:
            n = pkt.send(wait_response=False)
            response_info[pkt.sock] = n, pkt
        responded = 0
        total = len(packets)
        sockets = [pkt.sock for pkt in packets]
        waited_time = 0
        wait_interval = 2.5e-2
        while responded < total and waited_time < timeout:
            readable, _, _ = select.select(sockets, [], [], 1)
            for s in readable:
                expected_size, pkt = response_info[s]
                if isinstance(expected_size, list):
                    expected_size = sum(expected_size)
                response = b''
                rev_time = 0
                rev_interval = 1e-3
                while rev_time < timeout:
                    try:
                        data, addr_info = s.recvfrom(expected_size)
                        response += data
                    except socket.error:
                        time.sleep(rev_interval)
                        rev_time += rev_interval
                    if len(response) == expected_size:
                        break
                if len(response) != expected_size:
                    raise RecvTimeoutError(pkt.awg_name, len(response), expected_size, rev_time)
                pkt.update_result(response)
                responded += 1
            if responded < total:
                time.sleep(wait_interval)
            waited_time += wait_interval
        timeout_list = [pkt.awg_name for pkt in packets if pkt.result is None]
        if timeout_list:
            raise RecvTimeoutError(timeout_list)
        result = {pkt.awg_name: pkt.get_result() for pkt in packets}
        return result


def trace_subprocess_exception(func):
    @functools.wraps(func)
    def wrap_func(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception:
            traceback.print_exc()
    return wrap_func


@trace_subprocess_exception
def packet_process(pkt):
    log_name = f'manager_{pkt.awg_name}'
    console_log = False
    pkt.awg.set_logger(log_name, console_log)
    result = pkt.send(wait_response=True)
    return result
