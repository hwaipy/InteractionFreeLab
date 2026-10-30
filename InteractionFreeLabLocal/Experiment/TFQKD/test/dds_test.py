from interactionfreepy import IFWorker

worker = IFWorker('tcp://tf.qpqi.group:1161')

print(worker.listServiceNames())


dds = worker.blockingInvoker('DDSClock', timeout=None)

print(dds.correctDelay(1000))  # 补偿 +1000 ps（1 ns），阻塞到完成

# dds.setFrequency(1e7)