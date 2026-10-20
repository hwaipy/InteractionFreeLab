class Registry:
    def __init__(self, storage, collection):
        self.storage = storage
        self.collection = collection
        self.__inited = False

    async def __prepare(self):
        if not self.__inited:
            self.latest = await self.__getLatestEntry()
            if self.latest == None:
                await self.storage.append(self.collection, {})
            self.__inited = True

    async def set(self, key, value):
        await self.__prepare()
        keySeq = key.split('.')
        data = (await self.__getLatestEntry())['Data']
        entry = data
        while len(keySeq) > 1:
            if not entry.__contains__(keySeq[0]):
                entry[keySeq[0]] = {}
            entry = entry[keySeq[0]]
            keySeq.pop(0)
        entry[keySeq[0]] = value
        await self.__updateEntry(data)

    async def get(self, key, default=None):
        await self.__prepare()
        data = (await self.__getLatestEntry())['Data']
        keySeq = key.split('.')
        while len(keySeq) > 0:
            if not data.__contains__(keySeq[0]):
                return default
            data = data[keySeq[0]]
            keySeq.pop(0)
        return data

    async def __getLatestEntry(self):
        return await self.storage.latest(self.collection, by='FetchTime', filter={'_id': 1, 'Data': 1})

    async def __updateEntry(self, data):
        await self.storage.append(self.collection, data)

if __name__ == '__main__':
    from interactionfreepy import IFWorker, IFLoop

    worker = IFWorker('tcp://192.168.25.5:224')
    worker.bindService("TF_Registry", Registry(worker.asyncInvoker('Storage'), 'TFQKD_Reg'))
    IFLoop.join()