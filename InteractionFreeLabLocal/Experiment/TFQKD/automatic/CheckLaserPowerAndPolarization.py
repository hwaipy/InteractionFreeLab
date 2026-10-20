from worker_config import worker, ip
import LongRandomWaveform as LRW

def checkLaserPowerAndPolarization():
  powersAlice = worker.TF_PowerMeter_Alice.readPower()
  powersBob = worker.TF_PowerMeter_Bob.readPower()

  print(powersAlice)
  print(powersBob)
  print('Need to set a threshold to check whether the power is valid.')

  # rnsAliceForAWG, rnsAliceForTDC, rnsAliceForSync, rnsBobForAWG, rnsBobForTDC, rnsBobForSync = LRW.getRNS()
  # globalDelayA = worker.TF_Registry.get('Runtime.Alice.Time.GlobalDelay')
  # globalDelayB = worker.TF_Registry.get('Runtime.Bob.Time.GlobalDelay')
  # print("Preparing Alice's waveform")
  # LRW.control_Alice(rnsForAWG=rnsAliceForAWG, rnsForTDC=rnsAliceForTDC, globalDelay=globalDelayA, onoff=[1, 0, 1, 0], V=0.69, rnsForSync=rnsAliceForSync)

    # process.turnOnAnalyser("TFQKDSyncAlice", Map("Period" -> 10000, "TriggerChannel" -> 0, "SignalChannel" -> 4, "RandomNumbers" -> Range(0, 129).toList, "Histograms" -> Map("Sync Alice" -> Range(0, 64).toList)))

  # print("Preparing Bob's waveform")
  # LRW.control_Bob(rnsForAWG=rnsBobForAWG, rnsForTDC=rnsBobForTDC, globalDelay=globalDelayB, onoff=[1, 0, 1, 0], V=0.7, rnsForSync=rnsBobForSync)

  # worker.TFTDCServer.configureAnalyser('TFQKDSyncAlice', {'SignalChannel': 4, 'Period': 10000, 'RandomNumbers': [100] * 160 + [1] * 240})
  # worker.TFTDCServer.configureAnalyser('TFQKDSyncBob', {'SignalChannel': 5, 'Period': 10000, 'RandomNumbers': [1] * 160 + [128] * 240})

  return True
