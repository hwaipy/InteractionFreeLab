from interactionfreepy import IFWorker, IFLoop
from datetime import datetime, timedelta, timezone
import numpy as np
from tornado.ioloop import IOLoop
from threading import Thread 
import time
from urllib.request import urlopen
from pytimetag import DataBlock, CounterAnalyser, FastCounterAnalyser

if __name__ == '__main__':
    worker = IFWorker('tcp://172.20.8.33:1161')
    l = worker.Storage.latest('TFQKD_TDC', filter={'FetchTime': 1})
    print(l)
    fetchTime = l['FetchTime']
    url = f'http://172.20.8.33:1001/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock'
    res = urlopen(url)
    data = res.read()
    res.close()
    print(len(data))

    dataBlock = DataBlock.deserialize(data)
    print(dataBlock.sizes)

    ana = FastCounterAnalyser()
    ana.turnOn({'Frequency': 1000, 'Channels': [2, 3]})

    r = ana.dataIncome(dataBlock)
    print(r)