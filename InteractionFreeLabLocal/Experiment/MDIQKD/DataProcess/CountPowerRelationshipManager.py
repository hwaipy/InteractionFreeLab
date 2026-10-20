from IFWorker import IFWorker
from IFCore import IFLoop
from functional import seq
import numpy as np
from datetime import datetime, timedelta
import time
from IFCore import debug_timerecord
from threading import Thread
import pytz
from queue import Queue
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from io import BytesIO
import struct
import base64


class CountPowerRelationshipManager:
    def __init__(self, worker):
        self.storage = worker.asyncInvoker('Storage')

    async def plotCountPowerRelationship(self, collection, id):
        result = await self.storage.get(collection, id, '_id', {'Data': 1})
        data = np.array(result['Data']['CountChannelRelations']['Data'])
        fig = plt.figure(figsize=(3.2, 2.5))
        ax = fig.add_subplot(1, 1, 1)
        ax.scatter(data[:, 2], data[:, 0], s=1)
        ax.scatter(data[:, 3], data[:, 1], s=1)
        figfile = BytesIO()
        plt.savefig(figfile, format='png')
        plt.close(fig)
        binaries = figfile.getvalue()
        return base64.b64encode(binaries).decode('utf-8')


if __name__ == '__main__':
    worker = IFWorker("tcp://127.0.0.1:224")
    cprm = CountPowerRelationshipManager(worker)
    worker.bindService('CountPowerRelationshipManager', cprm)
    IFLoop.join()
