from interactionfreepy import IFWorker, IFLoop


class ClockManager:
    def __init__(self, aliceAsyncInvoker, bobAsyncInvoker, charlieAsyncInvoker, aliceChannel=0, bobChannel=0, charlieChannel=0):
        self.alice = aliceAsyncInvoker
        self.bob = bobAsyncInvoker
        self.charlie = charlieAsyncInvoker
        self.aliceChannel = aliceChannel
        self.bobChannel = bobChannel
        self.charlieChannel = charlieChannel
        if charlieAsyncInvoker == None: raise RuntimeError('Charlie Invoker can not be None.')

    async def delay(self, alice=0, bob=0, charlie=0):
        minDelay = min(alice, bob, charlie)
        if minDelay < 0:
            alice -= minDelay
            bob -= minDelay
            charlie -= minDelay
        futures = []
        if self.alice != None: futures.append(self.alice.delay(self.aliceChannel, alice))
        if self.bob != None: futures.append(self.bob.delay(self.bobChannel, bob))
        futures.append(self.charlie.delay(self.charlieChannel, charlie))
        for future in futures:
            await future


if __name__ == '__main__':
    worker1 = IFWorker('tcp://192.168.25.5:224')
    cm = ClockManager(worker1.asyncInvoker('HMC7044EvalAlice'), worker1.asyncInvoker('HMC7044EvalBob'), worker1.asyncInvoker('HMC7044EvalCharlie'), aliceChannel=1, bobChannel=1, charlieChannel=1)
    worker2 = IFWorker('tcp://192.168.25.5:224', 'TF_ClockManager', cm, force=True)
    IFLoop.join()
   # worker.TF_ClockManager.delay(alice=5)
