import time
from urllib.request import urlopen
from pytimetag import DataBlock
import datetime
from interactionfreepy import IFWorker
from TFQKDQBERAnalyser import TFQKDQBERAnalyser, DataBlockParseResult
import tick
from DopplerUtil import DopplerUtil

class TFQKDDataParser:
    def __init__(self, storage, dataBlockFetcher, frequencyFrame=0, phaseFrame=0.2e-3, intensityFrame=1e-3, savepath=''):
        self.storage = storage
        self.dataBlockFetcher = dataBlockFetcher
        self.frequencyFrame = frequencyFrame
        self.phaseFrame = phaseFrame
        self.intensityFrame = intensityFrame
        self.savepath = savepath
        self.analyser = TFQKDQBERAnalyser(16)
        self.dopplerUtil = DopplerUtil()

    def parse(self, beginTime, endTime):
        metas = self.__fetchMetas(beginTime, endTime)
        print(f'{len(metas)} seconds of data fetched...')
        tick.turnOff()

        for meta in metas:
            tick.tick('begin a DataBlock')
            fetchTime = meta['FetchTime']
            configs = meta['Data']['QKDQBER']['Configuration']
            dataBlock = self.dataBlockFetcher(fetchTime)
            dataBlock = self.dopplerUtil.rescale(dataBlock)
            tick.tick('DataBlock fetched')
            result = self.__parse(dataBlock, configs)
            tick.tick('end a DataBlock')
            print(DataBlockParseResult.toString(result))
            print(f'DONE: {fetchTime}')

        if True:
            print('Benchmarking individual DataBlock parsing...')
            meta = metas[-1]
            tick.turnOn()
            tick.tick('begin a DataBlock')
            fetchTime = meta['FetchTime']
            configs = meta['Data']['QKDQBER']['Configuration']
            dataBlock = self.dataBlockFetcher(fetchTime)
            dataBlock = self.dopplerUtil.rescale(dataBlock)
            tick.tick('DataBlock fetched')
            t1 = time.time()
            result = self.__parse(dataBlock, configs)
            t2 = time.time()
            tick.tick('end a DataBlock')
            print(f'Elapsed time for single DataBlock parsing: {t2 - t1:.3} seconds')

    def __fetchMetas(self, beginTime, endTime):
        if not isinstance(beginTime, list): beginTime = [beginTime]
        if not isinstance(endTime, list): endTime = [endTime]
        assert len(beginTime) == len(endTime)
        metas = []
        for i in range(len(beginTime)):
            ranges = self.storage.range('TFQKD_TDC', beginTime[i], endTime[i], filter={'_id': 1}, limit=1000000)
            for dataMeta in ranges:
                metas.append(self.storage.get('TFQKD_TDC', dataMeta['_id'], filter={'_id': 1, 'Data': 1, 'FetchTime': 1}))
        return metas
    
    def __parse(self, dataBlock, configs):
        ############## ⬇️ DEBUG ONLY  ##############
        configs['TimeEachBlock'] = int(1e12)
        configs['FrequencyFrame'] = int(self.frequencyFrame * 1e12)
        configs['PhaseFrame'] = int(self.phaseFrame * 1e12)
        configs['IntensityFrame'] = int(self.intensityFrame * 1e12)
        ############## ⬆️ DEBUG ONLY  ##############

        ############## ⬇️ DEBUG For LCL ONLY  ##############
        configs['SyncChannelAlice'] = 2
        configs['SyncChannelBob'] = 3
        configs['GateRef'] = 2000
        configs['Period'] = 10000
        configs['FrequencyFrame'] = int(500e6)
        configs['PhaseFrame'] = int(25e6)
        # self.rnsBob = np.array(configs['AliceRandomNumbers'])
        # self.rnsAlice = np.array(configs['BobRandomNumbers'])
        # self.matchedRandomNumbers, self.randomNumberBasisStat = self.generateMatchedRandomNumbers()
        ############## ⬆️ DEBUG For LCL ONLY  ##############

        self.analyser.configure(configs)
        return self.analyser.analysis(dataBlock)
        # dbp = DataBlockParser(dataBlock, configs, frequencyFrame=int(self.frequencyFrame * 1e12), phaseFrame=int(self.phaseFrame * 1e12), intensityFrame=int(self.intensityFrame * 1e12))
        # return dbp.parse()

def fetchDataBlockByHTTP(fetchTime):
    tick.tick('fetching DataBlock')
    fetchTime = datetime.datetime.fromisoformat(fetchTime).strftime('%Y-%m-%dT%H:%M:%S.%f+08:00')
    res = urlopen(f'http://172.20.8.32:1002/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock')
    data = res.read()
    res.close()
    tick.tick(f'readed from HTTP. {len(data)} bytes')
    dataBlock = DataBlock.deserialize(data)
    tick.tick('deserialized')
    return dataBlock

if __name__ == '__main__':
    # 10 M 频差，同源光
    begintime = ['2025-11-04T20:55:10+08:00']
    endtime = ['2025-11-04T20:55:11+08:00']
    
    # 独立光源
    begintime = ['2025-11-05T19:28:00+08:00']
    endtime = ['2025-11-05T19:28:01+08:00']

    worker = IFWorker('tcp://172.20.9.23:51061')
    def fetchDataBlock(fetchTime):
        print('fetching DataBlock', fetchTime)
        tick.tick('fetching DataBlock')
        date = fetchTime[:10]
        hour = fetchTime[11:13]
        dateTime = fetchTime.replace(':', '-').replace('T', ' ')[:23]
        path = '/'.join([date, hour, dateTime + '.datablock'])
        data = worker.TF_FileStorage.readFile("TFQKD_RAW", path)
        tick.tick(f'readed from server. {len(data)} bytes')
        dataBlock = DataBlock.deserialize(data)
        tick.tick('deserialized')
        return dataBlock
    parser = TFQKDDataParser(storage=worker.Storage, dataBlockFetcher=fetchDataBlock, frequencyFrame=1, phaseFrame=0.2e-3, intensityFrame=1e-3, savepath='/home/freespace/code/TFQKD_DataParse_AllInOne/DataParse/datalcl/200us/')

    import time
    t1 = time.time()
    for i in range(len(begintime)):
        parser.parse(begintime[i], endtime[i])
    t2 = time.time()
    print(f'Elapsed time: {t2 - t1} seconds')
