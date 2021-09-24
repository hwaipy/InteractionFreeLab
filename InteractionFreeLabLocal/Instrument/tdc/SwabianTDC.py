import TimeTagger
import time
import msgpack_numpy
from interactionfreepy import IFWorker, IFException
import msgpack
import sys

if __name__ == '__main__':
    print(TimeTagger.scanTimeTagger())

    if len(sys.argv) < 4:
        raise RuntimeError('ARGV not correct')

    sn = sys.argv[1]
    # triggerLevelsStr = '0.08,0.08,0.08,0.08,0.08,0.1,0.1,0.1'
    triggerLevelsStr = sys.argv[2]
    deadtime = int(sys.argv[3])
    server = sys.argv[4]

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

    worker = IFWorker('tcp://127.0.0.1:224')
    adapter = worker.blockingInvoker(server, 1)
    totalDataSize = 0
    currentSectionStart = time.time()
    currentSectionDataSize = 0

    while stream.isRunning():
        data = stream.getData()
        if data.size:
            channels = data.getChannels()  # The channel numbers
            timestamps = data.getTimestamps()  # The timestamps in ps
            data = timestamps.astype('int64') * 16 + channels.astype('int8') - 1
            binary = msgpack.unpackb(msgpack_numpy.packb(data))[b'data']
            try:
                adapter.dataIncome(binary)
            except IFException as e:
                pass

            currentSectionDataSize += timestamps.shape[0]
            deltaTime = time.time() - currentSectionStart
            if deltaTime > 1:
                totalDataSize += currentSectionDataSize
                print('Event rate = {:.3f} M/s ({:.3f} M events in total).'.format(currentSectionDataSize / deltaTime / 1e6, totalDataSize / 1e6))
                currentSectionDataSize = 0
                currentSectionStart = time.time()
            if timestamps.shape[0] < bufferSize / 10:
                time.sleep(0.1)
