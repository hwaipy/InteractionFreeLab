class Registry:
    def __init__(self, storage, collection):
        self.storage = storage
        self.collection = collection
        latest = self.__getLatestEntry()
        if latest == None:
            self.storage.append(collection, {})

    def set(self, key, value):
        keySeq = key.split('.')
        data = self.__getLatestEntry()['Data']
        entry = data
        while len(keySeq) > 1:
            if not entry.__contains__(keySeq[0]):
                entry[keySeq[0]] = {}
            entry = entry[keySeq[0]]
            keySeq.pop(0)
        entry[keySeq[0]] = value
        self.__updateEntry(data)

    def get(self, key, default=None):
        data = self.__getLatestEntry()['Data']
        keySeq = key.split('.')
        while len(keySeq) > 0:
            if not data.__contains__(keySeq[0]):
                return default
            data = data[keySeq[0]]
            keySeq.pop(0)
        return data

    def __getLatestEntry(self):
        return self.storage.latest(self.collection, by='FetchTime', filter={'_id': 1, 'Data': 1})

    def __updateEntry(self, data):
        self.storage.append(self.collection, data)

if __name__ == '__main__':
    from interactionfreepy import IFWorker, IFLoop

    worker = IFWorker('tcp://interactionfree.cn:224')
    worker.bindService("TF_Registry", Registry(worker.Storage, 'TFQKD_Reg'))
    IFLoop.join()