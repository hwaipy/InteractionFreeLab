from worker_config import worker, ip
import Delay as DL
import LongRandomWaveform as LRW

def searchGlobalDelay():
  Delay = DL.getDelay(AliceChannel=4, BobChannel=5, triggerChannel=0, ip=ip)
  # Delay.Control2(target='Alice')
  Delay.Control2(target='Bob')

  rnsAliceForAWG, rnsAliceForTDC, rnsAliceForSync, rnsBobForAWG, rnsBobForTDC, rnsBobForSync = LRW.getRNS()
  globalDelayA = worker.TF_Registry.get('Runtime.Alice.Time.GlobalDelay')
  globalDelayB = worker.TF_Registry.get('Runtime.Bob.Time.GlobalDelay')
  # print("Preparing Alice's waveform")
  # LRW.control_Alice(rnsForAWG=rnsAliceForAWG, rnsForTDC=rnsAliceForTDC, globalDelay=globalDelayA, onoff=[1, 0, 1, 0], V=0.69, rnsForSync=rnsAliceForSync)
  print("Preparing Bob's waveform")
  LRW.control_Bob(rnsForAWG=rnsBobForAWG, rnsForTDC=rnsBobForTDC, globalDelay=globalDelayB, onoff=[1, 0, 1, 0], V=0.7, rnsForSync=rnsBobForSync)


  return True


    # # target = sys.argv[1]
    # target = 'Bob'
    # # target = 'Alice'
    # # globalDelay = Delay.Control(target=target, keep_waveform=True)
    # st = time.time()
    # globalDelay = Delay.Control2(target=target)
    # et = time.time()
    # print('用时：', et-st)

    # # 检查
    # # globalDelay = worker.TF_Registry.get(f'Runtime.{target}.Time.GlobalDelay')
    # # print(f'globalDelay_{target}=', globalDelay)
    # # Delay.checkLongWaveform(globalDelay)


