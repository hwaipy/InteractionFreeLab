from interactionfreepy import IFWorker
import time

worker = IFWorker('tcp://172.20.8.33:1161')
print(worker.listServiceNames())

    #   while True:
    #     time.sleep(0.05)
    #     if time.time() < self.beginTime - 0.5:
    #       continue
worker.TF_TriggerBoard_Alice.start()
worker.TF_TriggerBoard_Alice.stop()
worker.TF_TriggerBoard_Bob.start()
worker.TF_TriggerBoard_Bob.stop()
print('ok')
