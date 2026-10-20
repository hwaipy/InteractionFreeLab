# coding: utf-8
import os
import logging
from logging.handlers import TimedRotatingFileHandler


LOG_FORMAT = "[%(asctime)s][%(name)s][%(levelname)s] %(message)s"


def get_log_file_path(namespace):
    cwd = os.getcwd()
    log_dir = os.path.join(cwd, 'ustc_awg_log')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # filename = f'{namespace}_{datetime.now():%Y-%m-%d-%H-%M-%S}.log'
    filename = f'{namespace}.log'
    full_path = os.path.join(log_dir, filename)
    info = f'{namespace} log file path: {full_path}'
    seg = '=' * len(info)
    if not os.path.exists(full_path):
        print(f'{info}\n{seg}')
    return full_path


def get_logger(namespace, console_log=True):
    logger = logging.getLogger(namespace)
    logger.setLevel(logging.DEBUG)  # root logger

    # default setting for console log
    if console_log:
        level = logging.INFO
        formatter = logging.Formatter(LOG_FORMAT)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    set_logger_file_handler(logger, namespace)
    return logger


def set_logger_file_handler(logger, namespace):
    logger.name = namespace
    level = logging.DEBUG  # default level
    formatter = logging.Formatter(LOG_FORMAT)
    file_path = get_log_file_path(logger.name)
    file_handler = TimedRotatingFileHandler(
        filename=file_path, interval=1, when='d')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
