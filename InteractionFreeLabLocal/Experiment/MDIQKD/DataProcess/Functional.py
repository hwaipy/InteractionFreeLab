from IFWorker import IFWorker
import time
import numpy as np


def fetchRecentDelay():
    worker = IFWorker('tcp://127.0.0.1:224')
    last = None
    while True:
        latest = worker.Storage.latest('MDIQKD_GroundTDC', after=last, filter={
            'FetchTime': 1,
            'Data.MDIQKDEncoding.Configuration.Period': 1,
            'Data.MDIQKDEncoding.Histogram Alice Time': 1,
            'Data.MDIQKDEncoding.Histogram Bob Time': 1,
        })
        if latest == None: yield None
        last = latest['FetchTime']
        period = latest['Data']['MDIQKDEncoding']['Configuration']['Period']
        aliceYs = latest['Data']['MDIQKDEncoding']['Histogram Alice Time']
        bobYs = latest['Data']['MDIQKDEncoding']['Histogram Bob Time']
        xs = [i for i in np.linspace(0, period / 1000, len(aliceYs))]
        aliceRise = worker.Algorithm_Fitting.riseTimeFit(xs, aliceYs)
        bobRise = worker.Algorithm_Fitting.riseTimeFit(xs, bobYs)
        yield aliceRise, bobRise


if __name__ == '__main__':
    print('functional test')

    gen = fetchRecentDelay()
    print(gen.__next__())
    # print(gen.__next__())
