# coding: utf-8
import struct
from socket import inet_aton
import time


def format_hex_data(data):
    hex_str = [f'{d:02X}' for d in data]
    return ' '.join(hex_str)


def get_bit(data, pos):
    mask = (1 << pos)
    bit = (data & mask) >> pos
    return bit


def int_to_bytes(x):
    return struct.pack('>I', x)


def int_to_ip(x):
    local_ip = int_to_bytes(x)
    ip = '.'.join([str(d) for d in local_ip])
    return ip


def ip_to_int(ip):
    ib = inet_aton(ip)
    ip_int, = struct.unpack('>I', ib)
    return ip_int


class ProgressBar():
    """Progress bar util.
    """
    def __init__(self, max, symbol='*', hint='Progress'):
        """Init progress bar.

        Args:
            max (int): Max process.
            symbol (str, optional): Progress bar symbol. Defaults to '*'.
            hint (str, optional): Progress bar hint. Defaults to 'Progress'.
        """
        self.hint = hint
        self.max = max
        self.symbol = symbol
        self.progress = 0

    def set_hint(self, hint):
        """Set progress hint.

        Args:
            hint (str): Progress hint.
        """
        self.hint = hint

    def set_symbol(self, symbol):
        """Set progress bar sysmbol.

        Args:
            symbol (str): Progress bar symbol.
        """
        self.symbol = symbol

    def start(self):
        """Record process start time.
        """
        self.start = time.perf_counter()

    def update(self, increment, info=''):
        """Update process by *increment*

        Args:
            increment (int): The increment of process.
            info (str, optional): Process infomation. Defaults to ''.
        """
        self.progress += increment
        progress = self.progress
        all_work = self.max
        if self.progress > self.max:
            progress = self.max
        scale = 50
        i = int(progress / all_work * scale)
        completed = self.symbol * i
        remain = "." * (scale - i)
        completed_percent = (i / scale) * 100
        try:
            dur = time.perf_counter() - self.start
            print(f'\r{self.hint} {info} {completed_percent:^3.0f}%'
                  f'[{completed}->{remain}]{dur:.2f}s', end='')
        except AttributeError:
            print("start() is not implemented.")

    def next(self, info=''):
        """Update process every time.

        Args:
            info (str, optional): Process infomation. Defaults to ''.
        """
        self.progress += 1
        progress = self.progress
        all_work = self.max
        if self.progress > self.max:
            progress = self.max
        scale = 50
        i = int(progress / all_work * scale)
        completed = self.symbol * i
        remain = "." * (scale - i)
        completed_percent = (i / scale) * 100
        try:
            dur = time.perf_counter() - self.start
            print(f'\r{self.hint} {info} {completed_percent:^3.0f}%'
                  f'[{completed}->{remain}]{dur:.2f}s', end='')
        except AttributeError:
            print("start() is not implemented.")
