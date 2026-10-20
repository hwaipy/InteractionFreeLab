from interactionfreepy import IFWorker, IFLoop
from datetime import datetime, timedelta, timezone
import numpy as np
from tornado.ioloop import IOLoop
from threading import Thread 
import time
import pytz
from pytimetag import DataBlock
from urllib.request import urlopen


if __name__ == '__main__':
    worker = IFWorker('10.1.1.1:224')
    
    def fetchLatest(limit):
        collection = 'TDCServerTestCollection'
        return worker.Storage.latest(collection, by='FetchTime', filter={'_id': 0, 'FetchTime': 1}, length=limit)

    data = fetchLatest(1)
    fetchTime = data['FetchTime']
    print('fetching DataBlock', fetchTime)

    fetchTime = datetime.fromisoformat(fetchTime).strftime('%Y-%m-%dT%H:%M:%S.%f+08:00')
    url = f'http://192.168.25.7:8002/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock'
    print(url)
    res = urlopen(url)
    data = res.read()
    res.close()
    dataBlock = DataBlock.deserialize(data)
    print(dataBlock.sizes)