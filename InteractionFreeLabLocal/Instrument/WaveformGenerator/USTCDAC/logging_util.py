# -- coding: utf-8 --
import logging
from logging import handlers

logger = logging.getLogger('da')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s]-%(name)s-%(levelname)s# %(message)s')

# 终端日志设置
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
# console.setFormatter(formatter)
logger.addHandler(console)


def init_error_msg_dict():
    illegal_para = 'Fail to create wave object, parameter is illegal.'
    wave_not_exist = 'Wave object does not exist.'
    illegal_channel = 'Channel should be 0 or 1.'
    illegal_delta_y = 'Delta y should not be 0.'
    memory_error = 'Fail to sample, too many samples.'
    buffer_not_exist = 'Wave data buffer does not exists.'
    tcp_not_connect = 'Fail to establish data channel.'
    socket_not_exist = 'Tcp connection is not established.'
    frame_recv_timeout = 'Receive wave control frame timeout.'
    pool_not_exist = 'Process pool does not exist.'
    dac_not_found = 'DAC not found!'
    dac_disconnected = "DAC disconnected!"
    err_msg = {
        -10201: illegal_para,
        -10401: illegal_para,
        -10701: illegal_para,
        -10801: illegal_para,
        -10901: illegal_para,
        -11101: illegal_para,
        -11201: illegal_para,
        -20101: wave_not_exist,
        -20201: wave_not_exist,
        -20301: wave_not_exist,
        -20401: wave_not_exist,
        -20402: illegal_channel,
        -20501: wave_not_exist,
        -20502: illegal_channel,
        -20601: wave_not_exist,
        -30101: wave_not_exist,
        -30102: illegal_delta_y,
        -30103: memory_error,
        -40101: buffer_not_exist,
        -40201: buffer_not_exist,
        -40301: buffer_not_exist,
        -40401: buffer_not_exist,
        -40701: buffer_not_exist,
        -120001: tcp_not_connect,
        -120201: socket_not_exist,
        -120202: frame_recv_timeout,
        -120203: pool_not_exist,
        -1: dac_not_found,
        -469762047: dac_disconnected
    }
    return err_msg


def log_by_code(logger, code, err_msg):
    if code:
        msg = err_msg.get(code, 'Unknown error.')
        logger.error('%s [ErrorCode: %d]', msg, code)
    return code


def set_logfile(log_dict):

    # 终端日志设置
    console = logging.StreamHandler()
    console.setLevel(log_dict['stream_log_level'])
    # console.setFormatter(formatter)
    logger.addHandler(console)

    # 文件日志设置
    file_time_rotating = handlers.TimedRotatingFileHandler(
        log_dict['file_log_path'] + log_dict['file_log_name'] + ".log", when='d',
        interval=int(log_dict['file_log_interval']), backupCount=5)
    file_time_rotating.setFormatter(formatter)
    file_time_rotating.setLevel(log_dict['file_log_level'])

    logger.addHandler(file_time_rotating)