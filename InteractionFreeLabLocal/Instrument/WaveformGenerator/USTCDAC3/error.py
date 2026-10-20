# coding: utf-8


class UstcAWGError(Exception):
    """USTC AWG base error class
    """

    msg = ''

    def __init__(self, msg=None, code=0):
        self.msg = msg
        self.code = int(code)

    def __str__(self):
        return f'[{self.code}] {self.msg}'


class IllegalMemoryAddressError(UstcAWGError):
    code = 1000001

    def __init__(self, address, segment):
        self.msg = (
            f'AWG memory address should be '
            f'divided by {segment}, got {address}')


class IllegalResponseError(UstcAWGError):
    code = 1000002

    def __init__(self, tag):
        self.msg = (
            f'Tag in memory writing command '
            f'response should be USTC, got {tag}')


class IllegalMemoryFrameLengthError(UstcAWGError):
    code = 1000003

    def __init__(self, count, expected):
        self.msg = (
            f'Length of memory frames should be '
            f'divided by {expected}, got {count}')


class TooManyRegisterEnriesError(UstcAWGError):
    code = 1000004

    def __init__(self, count, expected):
        self.msg = (
            f'Too many register entries in one frame, '
            f'should not be more than {expected}, '
            f'got {count}')


class RecvTimeoutError(UstcAWGError):
    code = 1000005

    def __init__(self, awg, recv=None, expect=None, waited_time=None):
        if isinstance(awg, list):
            awg = ', '.join([str(a) for a in awg])

        if None in {recv, expect, waited_time}:
            self.msg = f'Recv timeout for {awg}'
        else:
            self.msg = (
                f'Recv timeout ({waited_time:g} s) for {awg}, '
                f'expecting {expect} bytes, '
                f'{recv} bytes received')


class SendNotMatchRecvError(UstcAWGError):
    code = 1000006

    def __init__(self, awg, sent, recv):
        self.msg = f'Sent {sent} frames to {awg}, only {recv} received by awg'


class ReadRegisterPermissionError(UstcAWGError):
    code = 1000007

    def __init__(self, name):
        self.msg = f'Read Permission Denied for register module {name}'


class WriteRegisterPermissionError(UstcAWGError):
    code = 1000008

    def __init__(self, name):
        self.msg = f'Write Permission Denied for register module {name}'


class RegisterMapKeyError(UstcAWGError):
    code = 1000009

    def __init__(self, reg):
        self.msg = f'Key {reg} is not in register map'


class RetransmissionTimeout(UstcAWGError):
    code = 1000010

    def __init__(self, awg, times):
        self.msg = f'DAC {awg} write memory {times} times retransmission timeout'


class RegRetransmissionTimeout(UstcAWGError):
    code = 1000011

    def __init__(self, awg, times):
        self.msg = f'DAC {awg} send registers commads {times} times retransmission timeout'


class TrigCountOufOfRange(UstcAWGError):
    code = 2000000

    def __init__(self, awg, mini, maxi, count):
        self.msg = (f'Set {awg} trig count l1 out of range, '
                    f'which should be between {mini} and {maxi}, got {count}')


class SetTrigCountL1Fail(UstcAWGError):
    code = 2000001

    def __init__(self, awg):
        self.msg = f'Set {awg} trig count l1 fail'


class TrigIntervalOutOfRange(UstcAWGError):
    code = 2000002

    def __init__(self, awg, mini, maxi, trig_interval):
        self.msg = (f'Set {awg} trig interval out of range, '
                    f'which should be between {mini*1e9}ns and {maxi*1e3:.3}ms, got {trig_interval}')


class SetTrigIntervalL1Fail(UstcAWGError):
    code = 2000003

    def __init__(self, awg):
        self.msg = f'Set {awg} trig interval l1 fail'


class TrigStartOutOfRange(UstcAWGError):
    code = 2000004

    def __init__(self, awg, mini, maxi, count):
        self.msg = (f'Set {awg} trig start external out of range, '
                    f'which should be between {mini} and {maxi}, got {count}')


class SetTrigStartFail(UstcAWGError):
    code = 2000005

    def __init__(self, awg):
        self.msg = f'Set {awg} trig start external fail'


class TrigStopOutOfRange(UstcAWGError):
    code = 2000006

    def __init__(self, awg, mini, maxi, count):
        self.msg = (f'Set {awg} trig stop external out of range, '
                    f'which should be between {mini} and {maxi}, got {count}')


class SetTrigStopFail(UstcAWGError):
    code = 2000007

    def __init__(self, awg):
        self.msg = f'Set {awg} trig stop external fail'


class TrigDelayOutOfRange(UstcAWGError):
    code = 2000008

    def __init__(self, awg, mini, maxi, point):
        self.msg = (f'Set {awg} trig delay point out of range, '
                    f'which should be between {mini*1e6}us and {maxi*1e6}us, got {point}')


class MultiBoardModeError(UstcAWGError):
    code = 2000009

    def __init__(self, awg, mode):
        self.msg = (f'Set {awg} mulit board mode error, '
                    f'which should be 0 or 1, got {mode}')


class SetMultiBoardModeFail(UstcAWGError):
    code = 2000010

    def __init__(self, awg):
        self.msg = f'Set {awg} multi board mode fail'


class ClearTrigCountFail(UstcAWGError):
    code = 2000011

    def __init__(self, awg):
        self.msg = f'Clear {awg} trig count fail'


class TrigSelectChannelError(UstcAWGError):
    code = 2000012

    def __init__(self, awg, ch):
        self.msg = (f'Select {awg} trig channel error, '
                    f'which should be 1, 2, 3, 4 or 0, got {ch}')


class TrigEnableFail(UstcAWGError):
    code = 2000013

    def __init__(self, awg):
        self.msg = f'Enable {awg} trigger fail'


class DacStartOutOfRange(UstcAWGError):
    code = 20000014

    def __init__(self, awg, mini, maxi, count):
        self.msg = (f'Set {awg} dac start out of range, '
                    f'which should be between {mini} and {maxi}, got {count}')


class SetDacStartFail(UstcAWGError):
    code = 20000015

    def __init__(self, awg):
        self.msg = f'Set {awg} dac start fail'


class DacStopOutOfRange(UstcAWGError):
    code = 20000016

    def __init__(self, awg, mini, maxi, count):
        self.msg = (f'Set {awg} dac stop out of range, '
                    f'which should be between {mini} and {maxi}, got {count}')


class SetDacStopFail(UstcAWGError):
    code = 20000017

    def __init__(self, awg):
        self.msg = f'Set {awg} dac stop fail'


class DacDelayOutOfRange(UstcAWGError):
    code = 20000018

    def __init__(self, awg, mini, maxi, delay):
        self.msg = (f'Set {awg} dac delay out of range, '
                    f'which should be between {mini} and {maxi*1e6}us, got {delay}')


class TrigDelayWrongError(UstcAWGError):
    code = 20000019

    def __init__(self, awg, trig_delay, trig_interval):
        self.msg = (f'Set {awg} trig delay value {trig_delay} wrong, '
                    f'which should be less than trig interval value {trig_interval}')


class SetLoopOutOfRange(UstcAWGError):
    code = 30000000

    def __init__(self, awg):
        self.msg = (f'Set {awg} channel loop param out of range, '
                    f'which should be between 0 and 65535')


class SetLoopFail(UstcAWGError):
    code = 30000001

    def __init__(self, awg):
        self.msg = f'Set {awg} dac loop fail'


class StopOutputWaveFail(UstcAWGError):
    code = 30000002

    def __init__(self, awg,  channel):
        self.msg = f'Dac {awg} channel {channel} stop output wave fail'


class StartOutputWaveFail(UstcAWGError):
    code = 30000003

    def __init__(self, awg,  channel):
        self.msg = f'Dac {awg} channel {channel} start output wave fail'


class ChannelWrongError(UstcAWGError):
    code = 30000004

    def __init__(self, awg, channel):
        self.msg = f'Set the wrong channel {channel} for awg {awg}'


class SetDefaultVoltFail(UstcAWGError):
    code = 30000005

    def __init__(self, awg, channel):
        self.msg = f'Dac {awg} set channel {channel} default volt fail'


class DefaultVoltOutOfRange(UstcAWGError):
    code = 30000006

    def __init__(self, awg, mini, maxi, volt):
        self.msg = (f'Set {awg} dac default volt out of range, '
                    f'which should be between {mini} and {maxi}, got {volt}')


class WaveLengthOutOfRange(UstcAWGError):
    code = 30000007

    def __init__(self, awg, maxi, length):
        self.msg = (f'DAC {awg} write wave fail, wave length out of range, '
                    f'which should be less than {maxi}, got {length}')


class WaveDataOutOfRange(UstcAWGError):
    code = 30000008

    def __init__(self, awg, mini, maxi, min_data, max_data):
        self.msg = (f'Dac {awg} data in wave out of range, '
                    f'which should be between {mini} and {maxi},'
                    f'got min data {min_data}, got max data {max_data}')


class WaveSequenceLengthWrongError(UstcAWGError):
    code = 30000009

    def __init__(self, awg, max_seq_len, length):
        self.msg = (f'Dac {awg} wave sequence length error, '
                    f'which should be multipule of 4 and less than {max_seq_len},'
                    f'got wave sequence length {length}')


class ChannelGainOutOfRange(UstcAWGError):
    code = 30000010

    def __init__(self, awg, mini, maxi, channel, gain):
        self.msg = (f'Set {awg} dac channel {channel} gain out of range, '
                    f'which should be between {mini} and {maxi}, got {gain}')


class ChannelOffsetOutOfRange(UstcAWGError):
    code = 30000011

    def __init__(self, awg, mini, maxi, channel, offset):
        self.msg = (f'Set {awg} dac channel {channel} offset out of range, '
                    f'which should be between {mini} and {maxi}, got {offset}')


class BinFileNotFoundError(UstcAWGError):
    code = 40000000

    def __init__(self, file_path):
        self.msg = f'Could not find the bin file on path : {file_path}'


class FlashTypeNotMatchError(UstcAWGError):
    code = 40000001

    def __init__(self, bytes_type, flash_type):
        self.msg = (f'Flash type read from bin file is different from AWG flash type,'
                    f'got flash type {bytes_type} from bin file, {flash_type} from AWG')


class BinFileTypeNotMatchError(UstcAWGError):
    code = 40000002

    def __init__(self, bin_config_type, config_type):
        self.msg = (f'Config type read from bin file is different from host setting, '
                    f'got config type {bin_config_type} from bin file, {config_type} from host')


class WriteDDRTimeoutError(UstcAWGError):
    code = 40000003

    def __init__(self, awg, max_times):
        self.msg = (f'DAC {awg} write ddr {max_times} times timeout, '
                    f'data written to ddr is different from read back data')


class WriteFlashTimeoutError(UstcAWGError):
    code = 40000004

    def __init__(self, awg, waited_time, status):
        self.msg = (f'Write data to flash from DDR timeout ({waited_time:g} s) for {awg}, '
                    f'op status equals to {status}')


class ReadFlashTimeoutError(UstcAWGError):
    code = 40000005

    def __init__(self, awg, waited_time, status):
        self.msg = (f'Read data from flash accroding to DDR timeout ({waited_time:g} s) for {awg}, '
                    f'op status equals to {status}')


class FlashDataNotMatch(UstcAWGError):
    code = 40000006

    def __init__(self):
        self.msg = f'Data read from bin file is different from data written to awg flash area'


class DacConnectFail(UstcAWGError):
    code = 50000000

    def __init__(self, awg):
        self.msg = f'Dac {awg} connect fail'


class InitBoardFail(UstcAWGError):
    code = 50000001

    def __init__(self, awg):
        self.msg = f'Dac {awg} init board fail'


class InitBoardTimeoutError(UstcAWGError):
    code = 50000002

    def __init__(self, awg, waited_time):
        self.msg = f'Init board timeout ({waited_time:g} times) for {awg}'


class DacReConnectFail(UstcAWGError):
    code = 50000003

    def __init__(self, awg):
        self.msg = f'Dac {awg} re-connect fail'


class IllegalIpAddressError(UstcAWGError):
    code = 60000000

    def __init__(self, ip_address):
        self.msg = (f'IP address {ip_address} is illegal, '
                    f'which should be suit IPV4 format, '
                    f'and start with 172 or 10')


class IllegalMacAddressError(UstcAWGError):
    code = 60000001

    def __init__(self, mac_address):
        self.msg = (
            f'AWG mac address length should be '
            f'equal to 64 bit, got {mac_address}')


class InstructionEmptyError(UstcAWGError):
    code = 700000

    def __init__(self):
        self.msg = f'Instruction is empty'


class InstructionParaNumError(UstcAWGError):
    code = 700001

    def __init__(self, inst_name, arg_num, given_num):
        self.msg = f'{inst_name}() takes exactly {arg_num} argument ({given_num} given)'


class InstructionNameError(UstcAWGError):
    code = 700002

    def __init__(self, inst_name):
        self.msg = f'Instruction {inst_name} is not in instruction map'


class InstructionParaError(UstcAWGError):
    code = 7000003

    def __init__(self, inst_name, inst_para):
        self.msg = f'Instruction {inst_name} got an unexpected keyword argument "{inst_para}"'


class RegAmountNotEqualError(UstcAWGError):
    code = 7000004

    def __init__(self, address_amount, data_amount):
        self.msg = f'Instruction reg address amount {address_amount} is not equal to reg data amount {data_amount}'
