class MassiveStore:
    def __init__(self, storage, collection):
        self.storage = storage
        self.collection = collection

    async def put(self, value):
        return await self.storage.append(self.collection, value)

    async def get(self, id, filter={'_id': 1, 'Data': 1}):
        return await self.storage.get(self.collection, id, key='_id', filter=filter)

if __name__ == '__main__':
    from interactionfreepy import IFWorker, IFLoop

    worker = IFWorker('tcp://192.168.25.5:224')
    worker.bindService("TF_MassiveStore", MassiveStore(worker.asyncInvoker('Storage'), 'TFQKD_MassiveStore'))
    IFLoop.join()