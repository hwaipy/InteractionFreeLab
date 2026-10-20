import msgpack
import time
import random
from worker_config import worker
r = random.Random()


def testRandomNumberSetting(analyser, key, rns):
  value = rns if len(rns) < 100000 else worker.TF_FileStorage.writeMassive(msgpack.packb(rns))
  worker.TFTDCServer.configureAnalyser(analyser, {key: value})

  time.sleep(5)

  latest = worker.Storage.latest('TFQKD_TDC', filter={'_id': 1, 'FetchTime': 1, 'Data': 1})
  fetchedRNs = latest['Data'][analyser]['Configuration'][key]
  if (isinstance(fetchedRNs, str)):
    fetchedRNs = msgpack.unpackb(worker.TF_FileStorage.readMassive(fetchedRNs))
  assert(fetchedRNs == rns)
  print(f'{analyser} - {key} - with RN size {len(rns)} varified.')


rnsLong = [i for i in range(100)] * 10 * 1000 * 20
rnsShort = [i for i in range(100)] * 10 * 20
testRandomNumberSetting('TFQKDEncoding', 'RandomNumbers', rnsLong)  # 网页Encoding
testRandomNumberSetting('TFQKDEncoding', 'RandomNumbers', rnsShort)
testRandomNumberSetting('TFQKDSyncAlice', 'RandomNumbers', rnsLong)  # 给Alice同步路的随机数
testRandomNumberSetting('TFQKDSyncAlice', 'RandomNumbers', rnsShort)
testRandomNumberSetting('TFQKDSyncBob', 'RandomNumbers', rnsLong)    # 给Bob同步路的随机数
testRandomNumberSetting('TFQKDSyncBob', 'RandomNumbers', rnsShort)
testRandomNumberSetting('QKDQBER', 'AliceRandomNumbers', rnsLong)  # 给后处理
testRandomNumberSetting('QKDQBER', 'AliceRandomNumbers', rnsShort)
testRandomNumberSetting('QKDQBER', 'BobRandomNumbers', rnsLong)  # 给后处理
testRandomNumberSetting('QKDQBER', 'BobRandomNumbers', rnsShort)


