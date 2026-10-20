import os
import sys
import importlib


def installIfNotExist(module, pipName=None):
    try:
        mod = importlib.import_module(module)
    except BaseException as e:
        name = pipName if pipName else module
        os.system(
            f'{sys.executable} -m pip install {name} -i https://pypi.mirrors.ustc.edu.cn/simple/')


installIfNotExist('interactionfreepy')
installIfNotExist('yaml', 'pyaml')
installIfNotExist('numpy')
installIfNotExist('pyvisa')
installIfNotExist('serial', 'pyserial')
installIfNotExist('msgpack_numpy')
installIfNotExist('numba')
installIfNotExist('rich')
installIfNotExist('websockets')
installIfNotExist('h5py')
installIfNotExist('scipy')
