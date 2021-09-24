from Algorithm.fitting.GaussianFit import singlePeakGaussianFit
from Algorithm.fitting.RiseTimeFit import riseTimeFit
from Algorithm.fitting.SinFit import sinFit

class FittingService:
    def __init__(self):
        pass

    def singlePeakGaussianFit(self, xs, ys):
        return singlePeakGaussianFit(xs, ys)

    def riseTimeFit(self, xs, ys):
        try:
            return riseTimeFit(xs, ys)
        except Exception as e:
            # import traceback
            # msg = traceback.format_exc()  # 方式1
            # print(msg)
            return 0.0

    def sinFit(self, xs, ys, paraW=None):
        return sinFit(xs, ys, paraW)


if __name__ == '__main__':
    from IFWorker import IFWorker
    from IFCore import IFLoop

    endpoint = 'tcp://127.0.0.1:224'
    serviceName = 'Algorithm_Fitting'

    worker = IFWorker(endpoint, serviceName, FittingService())
    IFLoop.join()
