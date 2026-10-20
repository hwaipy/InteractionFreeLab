import os
import msgpack
from IFWorker import IFWorker


def loadMsgpackEntries(path):
    file = open(path, 'rb')
    data = file.read(os.path.getsize(path))
    file.close()
    unpacker = msgpack.Unpacker(raw=False)
    unpacker.feed(data)
    entries = []
    for packed in unpacker:
        entries.append(packed)
    return entries


def searchForRises(data, threshold):
    riseIndices = []
    for i in range(0, len(data) - 1):
        triggerLevelPre = data[i]
        triggerLevelPost = data[i + 1]
        if (triggerLevelPre < threshold and triggerLevelPost > threshold):
            riseIndices.append(i)
    return riseIndices


def doDataOfASecond(worker, channelEntry):
    result = {}
    data = channelEntry['Monitor']
    dataTrigger = [m[0] for m in data]
    data1 = [m[1] for m in data]
    data2 = [m[2] for m in data]
    dataTimes = [m[3] for m in data]
    result['Triggers'] = [dataTimes[i] for i in searchForRises(dataTrigger, 1)]
    result['TimeFirstSample'] = dataTimes[0]
    result['TimeLastSample'] = dataTimes[-1]
    result['Channel1'] = data1
    result['Channel2'] = data2
    worker.Storage.append('MDIChannelMonitor', result, fetchTime=dataTimes[0] / 1000.0)  # fetchTime=None, key=None


if __name__ == '__main__':
    worker = IFWorker('tcp://172.16.60.199:224')
    # worker = IFWorker('tcp://127.0.0.1:224')
    # root = '/Users/hwaipy/Downloads/20200501DavidAliceHOMTDC数据-排查筛选问题/dumps20200501'
    root = 'E:/MDIQKD_Parse/ReviewForCode/ChannelMonitorDump'
    files = [f for f in os.listdir(root) if f.endswith('Channel.dump')]
    files.sort()
    print(len(files))

    for file in files:
        channelEntries = loadMsgpackEntries('{}/{}'.format(root, file))
        for channelEntry in channelEntries[:-1]:
            doDataOfASecond(worker, channelEntry)
