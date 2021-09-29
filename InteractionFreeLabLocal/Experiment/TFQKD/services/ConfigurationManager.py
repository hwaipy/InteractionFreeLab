from interactionfreepy import IFWorker, IFLoop


class ConfigurationManager:
    def __init__(self, worker):
        self.worker = worker

    async def test(self):
        print('hahaha')
        self.worker.TFTDCServer.


if __name__ == '__main__':
    worker1 = IFWorker('tcp://172.16.60.200:224')
    cm = ConfigurationManager(worker1)
    worker2 = IFWorker('tcp://172.16.60.200:224', 'TF_ConfigurationManager', cm, force=True)
    worker2.TF_ConfigurationManager.test()
    # IFLoop.join()
    # worker1.TF_ClockManager.delay(alice=0.1)
