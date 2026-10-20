BEGIN_TIME = '2024-02-06T05:00:03+08:00'
END_TIME = '2024-02-06T05:00:04+08:00'



from interactionfreepy import IFWorker
from urllib.request import urlopen
from pytimetag import DataBlock

worker = IFWorker('tcp://code.qpqi.group:1061')
metas = worker.Storage.range("TFQKD_TDC", BEGIN_TIME, END_TIME, by='FetchTime', filter={'FetchTime': 1})

for meta in metas:
    fetchTime = meta['FetchTime']
    meta = worker.Storage.get("TFQKD_TDC", meta['_id'], filter={'_id': 1, 'Data': 1})
    res = urlopen(f'http://code.qpqi.group:1010/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock')
    data = res.read()
    res.close()
    dataBlock = DataBlock.deserialize(data)



print(len(metas))
print(meta.keys())
print(dataBlock.sizes)