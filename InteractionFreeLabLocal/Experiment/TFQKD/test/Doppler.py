from interactionfreepy import IFWorker, IFLoop
from datetime import datetime, timedelta, timezone
import numpy as np
from tornado.ioloop import IOLoop
from threading import Thread 
import time



from interactionfreepy import IFWorker, IFLoop



# worker = IFWorker('192.168.25.5:1061', 'name', obj, force=True)
# IFLoop().join()

worker = IFWorker('192.168.25.5:1061')
print(worker.listServiceNames())
# worker.TFTDCServer.startDopplerShift(int(datetime.now().timestamp()) + 20)


# worker.TFTDCServer.startDopplerShift(datetime.now().timestamp()) + 20


# beginDateTime = datetime.fromisoformat('2024-08-28 12:14:00')
# worker.TFTDCServer.startDopplerShift(int(beginDateTime.timestamp()))

# worker.TFTDCServer.startDopplerShift(0)

print(worker.Freq_DDS_Alice.getTimeSeq())

time.sleep(1)