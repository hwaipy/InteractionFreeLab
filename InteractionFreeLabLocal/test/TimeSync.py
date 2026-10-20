from lib2to3.pytree import Base
import os
import sys
import importlib
import time
import random
import platform
import threading
from queue import Queue
import urllib
import shutil
from datetime import datetime, timedelta

########## check for system ##########
platformString = platform.platform()
isWindows = platformString.lower().startswith('windows')
isLinux = platformString.lower().startswith('linux')
########## check for system ##########

########## check for modules ##########
def installIfNotExist(module, pipName=None):
    try:
        mod = importlib.import_module(module)
    except BaseException as e:
        name = pipName if pipName else module
        os.system(
            f'{sys.executable} -m pip install {name} -i https://pypi.mirrors.ustc.edu.cn/simple/')

installIfNotExist('rich')
if isWindows:
    installIfNotExist('win32api', 'pywin32')
installIfNotExist('interactionfreepy')

from interactionfreepy import IFWorker

########## check for modules ##########

timeServiceAddress = 'code.qpqi.group'
timeServicePort = 1161

class NTPSyncer:
    def __init__(self, address, port):
        self.worker = IFWorker(f'tcp://{timeServiceAddress}:{timeServicePort}')
        self.offset = 0
        self.hasError = False
        self.lastCheckTime = 0

    def getTimeOffset(self):
        # return ntplib.NTPClient().request(self.server, version=3).offset
        t1 = time.time()
        t2 = self.worker.time()
        t3 = time.time()

        # 本地时间基准 T_local
        # 服务器时间基准 T_server
        # t1 = T_local
        # t2 = T_server + T_trans
        # t3 = T_local + 2 * T_trans

        # 所以 T_trans = (t3 - t1) / 2
        # T_local - T_server = t1 - t2 + T_trans = (t3 + t1) / 2 - t2

        deltaT = (t3 + t1) / 2 - t2
        return -deltaT

    def calibrate(self):
        offset = self.getTimeOffset()
        if isWindows:
            import win32api
            correctTime = time.time() + offset
            tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst = time.gmtime(correctTime)
            win32api.SetSystemTime(tm_year, tm_mon, tm_wday, tm_mday, tm_hour, tm_min, tm_sec, int((correctTime - int(correctTime)) * 1000))
            offset = self.getTimeOffset()
        if isLinux:
            # print(str(datetime.now() + timedelta(seconds=offset)))
            os.system(f'timedatectl set-time "{str(datetime.now() + timedelta(seconds=offset))}"')
            offset = self.getTimeOffset()
        return offset

    def lock(self, checkMin, checkMax):
        while True:
            try:
                self.offset = self.calibrate()
                self.hasError = False
                self.lastCheckTime = time.time()
            except BaseException as e:
                print(e)
                self.hasError = True
            time.sleep(random.Random().randint(checkMin, checkMax))

    def getOffset(self):
        return self.offset

    def isHavingError(self):
        return self.hasError

if __name__ == '__main__':
    from rich.console import Console
    from rich.progress import Progress
    from yaml import load, dump
    try:
        from yaml import CLoader as Loader, CDumper as Dumper
    except ImportError:
        from yaml import Loader, Dumper
    import requests
    from interactionfreepy import IFBroker

    console = Console()

    broker = IFBroker()
    ntpSyncer = NTPSyncer(timeServiceAddress, timeServicePort)
    threading.Thread(target=lambda: ntpSyncer.lock(60, 120), daemon=True).start()
    outputFlag = True

    def loop():
        global outputFlag
        while True:
            try:
                offset = ntpSyncer.getOffset()
                checkedTime = time.time() - ntpSyncer.lastCheckTime
                offsetS = str(int(offset * 1000))
                checkedTimeS = str(int(checkedTime))
                inited = checkedTime < 1e4
                ntpSyncString = f'dT = {offsetS if inited else "??"} ms ({"[bold red]Error![/bold red] " if ntpSyncer.hasError else ""}{"synced" if isWindows else "checked"} {checkedTimeS if inited else "--"} s ago)'

                if outputFlag:
                    console.print(ntpSyncString)
                    outputFlag = False

            except BaseException as e:
                print(e)
            time.sleep(1)
    threading.Thread(target=loop, daemon=True).start()

    while True:
        l = sys.stdin.readline()
        if l.startswith('q'):
            sys.exit(0)
        if l == '\n':
            outputFlag = True
        if l.startswith('a'):
            updateLauncher()