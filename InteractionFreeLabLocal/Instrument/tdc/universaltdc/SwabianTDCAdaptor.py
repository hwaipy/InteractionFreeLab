# import TimeTagger
# import time
# import msgpack_numpy
# from interactionfreepy import IFBroker, IFWorker, IFException, IFLoop
# import msgpack
#
# if __name__ == '__main__':
#     enabledChannels = [1, 2, 3, 4, 5, 6, 7, 8]
#     triggerLevels = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
#     forever = True
#     bufferSize = 10000000
#
#     IFBroker('tcp://*:2048')
#
#     tagger = TimeTagger.createTimeTagger()
#     for i in range(len(enabledChannels)):
#         tagger.setTriggerLevel(enabledChannels[i], triggerLevels[i])
#
#     stream = TimeTagger.TimeTagStream(tagger=tagger, n_max_events=bufferSize, channels=enabledChannels)
#     if forever:
#         stream.start()
#     else:
#         stream.startFor(int(5e12))
#
#     worker = IFWorker('tcp://127.0.0.1:2048')
#     adapter = worker.blockingInvoker('SwabianTDCAdapter', 1)
#     totalDataSize = 0
#     currentSectionStart = time.time()
#     currentSectionDataSize = 0
#
#     while stream.isRunning():
#         data = stream.getData()
#         if data.size:
#             channels = data.getChannels()            # The channel numbers
#             timestamps = data.getTimestamps()       # The timestamps in ps
#             data = timestamps.astype('int64') * 16 + channels.astype('int8') - 1
#             binary = msgpack.unpackb(msgpack_numpy.packb(data))[b'data']
#             try:
#                 adapter.dataIncome(binary)
#             except IFException as e:
#                 pass
#
#             currentSectionDataSize += timestamps.shape[0]
#             deltaTime = time.time() - currentSectionStart
#             if deltaTime > 1:
#                 totalDataSize += currentSectionDataSize
#                 print('Event rate = {:.3f} M/s ({:.3f} M events in total).'.format(currentSectionDataSize / deltaTime / 1e6, totalDataSize / 1e6))
#                 currentSectionDataSize = 0
#                 currentSectionStart = time.time()
#             if timestamps.shape[0] < bufferSize / 10:
#                 time.sleep(0.1)
