from interactionfreepy import IFWorker
import sys

workerSrc = IFWorker('tcp://172.20.8.102:1061', timeout=10)
workerDes = IFWorker('tcp://172.20.8.102:1061', timeout=10)

collectionSrc = 'TFQKD_TDC'
collectionDes = 'TFQKD_TDC_7km_old'

fileStorageEntrySrc = 'TFQKD_RAW'
fileStorageEntryDes = 'TFQKD_RAW_7km'

print(workerSrc.listServiceNames())
print(workerDes.listServiceNames())

def loop():
    print('Data Backup start a new loop.')
    latestInDes = workerDes.Storage.latest(collectionDes, by='FetchTime', filter={'FetchTime': 1}, length=1)
    latestDateInDes = None if latestInDes is None else latestInDes['FetchTime']
    print(f'Latest backuped data is at {latestDateInDes}.')

    nextData = workerSrc.Storage_7km_old.first(collectionSrc, by='FetchTime', after=latestDateInDes, filter={'FetchTime': 1}, length=1000)
    print('No new data.' if nextData == None else f'Next data to be backuped: {len(nextData)} in total.')

    for nextMeta in nextData:
        fetchTime = nextMeta['FetchTime']
        print(fetchTime)
        entry = workerSrc.Storage_7km_old.get(collectionSrc, nextMeta['_id'], filter={'_id': 1, 'FetchTime': 1, 'RecordTime': 1, 'Data': 1})

        date = fetchTime[:10]
        hour = fetchTime[11:13]
        dateTime = (fetchTime.replace(':', '-').replace('T', ' ')[:-6] + '.000000')[:23]
        path = '/'.join([date, hour, dateTime + '.datablock'])
        try:
            data = workerSrc.TF_FileStorage_7km_old.readFile(fileStorageEntrySrc, path)
            print(path)
            workerDes.TF_FileStorage.writeFile(fileStorageEntryDes, path, data)
            print(f'Raw Data stored ({len(data)/1e6:.6f} MB)')
        except BaseException as e:
            print(e)
        workerDes.Storage.append(collectionDes, entry['Data'], entry['FetchTime'])
        

while True:
    loop()