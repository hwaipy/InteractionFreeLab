from multiprocessing.shared_memory import SharedMemory
from multiprocessing.managers import SharedMemoryManager
import numpy as np
from multiprocessing import Pool



def testFunc(smn):
  try:
    print('p2: in')
    import time
    print(smn)
    print('======      ', smn[1001])
    print('p2: out')
  except BaseException as e:
    import traceback
    print(e)
    traceback.format_exc(e)


if __name__ == '__main__':
  dataOriginal = np.random.randint(0, 1000000000000, 100000000, dtype='<i8')
  print('------      ', dataOriginal[1001])

  # smm = SharedMemoryManager()
  # smm.start()

  # sm = smm.SharedMemory(dataOriginal.nbytes)

  sm = SharedMemory(create=True, size=dataOriginal.nbytes)
  # print(sm)

  pool = Pool(8)
  print('to be applied')
  r = pool.apply_async(func=testFunc, args=(sm,))
  print('applied')
  r.wait()
  print('waited')
  # print(r.get())

  sm.close()
  sm.unlink()
