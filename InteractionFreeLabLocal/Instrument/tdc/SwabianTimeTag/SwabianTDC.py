import TimeTagger
import time
import msgpack_numpy
from interactionfreepy import IFWorker, IFException
import msgpack
import sys

class DataWriter:
    def __init__(self, filename):
        self.file = open(filename, 'wb')
        self.size = 0

    def dataIncome(self, binary):
        self.file.write(binary)
        self.size += len(binary)
        print(self.size / 1e9)
        if self.size > 2e9:
            self.file.close()
            sys.exit()

if __name__ == '__main__':
    print(TimeTagger.scanTimeTagger())

    if len(sys.argv) < 5:
        raise RuntimeError('ARGV not correct')

    ifserver = sys.argv[1]
    sn = sys.argv[2]
    # triggerLevelsStr = '0.08,0.08,0.08,0.08,0.08,0.1,0.1,0.1'
    triggerLevelsStr = sys.argv[3]
    deadtime = int(sys.argv[4])
    server = sys.argv[5]
    localFileName = None if len(sys.argv) < 7 else sys.argv[6]

    triggerLevels = [float(s) for s in triggerLevelsStr.split(',')]
    enabledChannels = [i + 1 for i in range(len(triggerLevels))]
    forever = True
    bufferSize = 10000000

    tagger = TimeTagger.createTimeTagger(sn)
    for i in range(len(enabledChannels)):
        tagger.setTriggerLevel(enabledChannels[i], triggerLevels[i])
        tagger.setDeadtime(enabledChannels[i], deadtime)

    stream = TimeTagger.TimeTagStream(tagger=tagger, n_max_events=bufferSize, channels=enabledChannels)
    if forever:
        stream.start()
    else:
        stream.startFor(int(5e12))

    worker = IFWorker(ifserver)
    adapterLocalFile = None if not localFileName else DataWriter(localFileName)
    adapter = worker.blockingInvoker(server, 1)
    totalDataSize = 0
    currentSectionStart = time.time()
    currentSectionDataSize = 0
    dealTime = 0

    while stream.isRunning():
        data = stream.getData()
        if data.size:
            t1 = time.time()
            channels = data.getChannels()  # The channel numbers
            timestamps = data.getTimestamps()  # The timestamps in ps
            data = timestamps.astype('int64') * 16 + channels.astype('int8') - 1
            binary = msgpack.unpackb(msgpack_numpy.packb(data))[b'data']
            t2 = time.time()
            dealTime += t2 - t1
            try:
                adapter.dataIncome(binary)
                if adapterLocalFile: adapterLocalFile.dataIncome(binary)
            except IFException as e:
                print(e)
                pass

            currentSectionDataSize += timestamps.shape[0]
            deltaTime = time.time() - currentSectionStart
            if deltaTime > 1:
                totalDataSize += currentSectionDataSize
                print(f'Event rate = {currentSectionDataSize / deltaTime / 1e6:.3f} M/s ({totalDataSize / 1e6:.3f} M events in total). Cost {dealTime:.3f} s in parsing data.')
                currentSectionDataSize = 0
                currentSectionStart = time.time()
                dealTime = 0
            # if timestamps.shape[0] < bufferSize / 10:
            #     time.sleep(0.1)
