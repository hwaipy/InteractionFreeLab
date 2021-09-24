from interactionfreepy import IFWorker
from random import Random
import time
import numpy as np
import matplotlib.pyplot as plt

if __name__ == '__main__':
    print('Net Speed Test')
    t = time.time()

    lengths = []
    times = []

    class NST:
        def __init__(self):
            pass

        def test(self, data):
            return time.time() - t

    worker1 = IFWorker('tcp://172.16.60.200:224', '__NetSpeedTest', NST(), force=True)
    worker2 = IFWorker('tcp://172.16.60.200:224')

    rnd = Random()

    for l in np.logspace(3, 7, 10):
        print(l)
        l = int(l)
        bs = ''.join(['0' for i in range(l)])
        bs = bytearray(bs, 'UTF-8')
        t = time.time()
        lengths.append(l)
        times.append(worker2.__NetSpeedTest.test(bs))

    plt.plot(lengths, times)
    plt.show()