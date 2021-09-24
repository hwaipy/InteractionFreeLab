from interactionfreepy import IFWorker
from random import Random
import time
import numpy as np
import matplotlib.pyplot as plt

if __name__ == '__main__':
    print('DB Speed Test')
    t = time.time()

    lengths = []
    times = []

    worker = IFWorker('tcp://172.16.60.200:224')

    rnd = Random()

    for l in np.logspace(3, 7, 10):
        print(l)
        l = int(l)
        bs = ''.join(['0' for i in range(l)])
        bs = bytearray(bs, 'UTF-8')
        lengths.append(l)
        t = time.time()
        worker.Storage.append('DBSpeedTest', bs)
        times.append(time.time() - t)

    plt.plot(lengths, times)
    plt.show()