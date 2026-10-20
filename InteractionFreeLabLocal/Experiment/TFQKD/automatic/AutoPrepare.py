from interactionfreepy import IFWorker
from rich.console import Console
import sys
sys.path.append('/home/coder/project/interactionfreelab/InteractionFreeLabLocal/Experiment/TFQKD/automatic/p20221101')
from worker_config import worker, ip
from CheckLaserPowerAndPolarization import checkLaserPowerAndPolarization
from CheckServices import checkServices
from SearchGlobalDelay import searchGlobalDelay

def checkServices():
  serviceNames = worker.listServiceNames()
  expectedServices = ['TF_PowerSupply_Alice_1', 'TF_PowerSupply_Alice_2', 'TF_PowerSupply_Alice_3', 'TF_PowerSupply_Alice_4',
                      'TF_PowerSupply_Bob_1', 'TF_PowerSupply_Bob_3', 'TF_PowerSupply_Bob_4',
                      'TF_PowerMeter_Alice', 'TF_PowerMeter_Bob', 'TF_Polarizer_Alice', 'TF_Polarizer_Bob',
                      'TF_AtomicClock_Alice', 'TF_AtomicClock_Bob', 'TF_AtomicClock_Charlie',
                      'HMC7044EvalAlice', 'HMC7044EvalBob', 'HMC7044EvalCharlie', 'TF_ClockManager',
                      'TF_AWGEncoder_Alice', 'TF_AWGEncoder_Bob',
                      'TFTDCServer', 'TF_SwabianTDCAdapter', 'TFTDCAdapter', 'RealTimeTDC',
                      'Storage', 'TF_Registry', 'TF_FileStorage',
                      ]
  missingServices = []
  for expectedService in expectedServices:
    if not serviceNames.__contains__(expectedService):
      missingServices.append(expectedService)

  if len(missingServices) == 0:
    return True
  else:
    raise BaseException(f'Missing Services: {missingServices}')

def checkLaserPowerAndPolarization():
  powersAlice = worker.TF_PowerMeter_Alice.readPower()
  powersBob = worker.TF_PowerMeter_Bob.readPower()

  print(powersAlice)
  print(powersBob)
  print('Need to set a threshold to check whether the power is valid.')

def setExperimentalWaveform(target):
  import LongRandomWaveform
  rnsAliceForAWG, rnsAliceForTDC, rnsAliceForSync, rnsBobForAWG, rnsBobForTDC, rnsBobForSync = LongRandomWaveform.getRNS()
  globalDelayA = worker.TF_Registry.get('Runtime.Alice.Time.GlobalDelay')
  globalDelayB = worker.TF_Registry.get('Runtime.Bob.Time.GlobalDelay')
  if target == 'Alice':
    LongRandomWaveform.control_Alice(rnsForAWG=rnsAliceForAWG, rnsForTDC=rnsAliceForTDC, globalDelay=globalDelayA, onoff=[1, 0, 1, 0], V=0.69, rnsForSync=rnsAliceForSync)
  if target == 'Bob':
    LongRandomWaveform.control_Bob(rnsForAWG=rnsBobForAWG, rnsForTDC=rnsBobForTDC, globalDelay=globalDelayB, onoff=[1, 0, 1, 0], V=0.7, rnsForSync=rnsBobForSync)
  # worker.TFTDCServer.configureAnalyser(f'TFQKDSync{target}', {'SignalChannel': 3, 'Period': 20000, 'RandomNumbers': [1] * 80 + [100] * 120, 'BinCount': 200})
  # worker.TFTDCAdapter.configureAnalyser(f'TFQKDSync{target}', {'SignalChannel': 3, 'Period': 20000, 'RandomNumbers': [1] * 80 + [100] * 120, 'BinCount': 200})
  channel = 4 if target == 'Alice' else 5
  rnsForSync = rnsAliceForSync if target == 'Alice' else rnsBobForSync
  worker.TFTDCServer.configureAnalyser(f'TFQKDSync{target}', {'SignalChannel': channel, 'Period': 10000, 'RandomNumbers': rnsForSync, 'BinCount': 100})
  worker.TFTDCAdapter.configureAnalyser(f'TFQKDSync{target}', {'SignalChannel': channel, 'Period': 10000, 'RandomNumbers': rnsForSync, 'BinCount': 100})

# def configEncoderViewer(target):


def searchGlobalDelay(target):
  import Delay as DL
  Delay = DL.getDelay(AliceChannel=4, BobChannel=5, triggerChannel=0, ip=ip)
  Delay.Control2(target=target)


if __name__ == '__RUN__INT__':
  checkServices()
  checkLaserPowerAndPolarization()
  searchGlobalDelay('Alice')
  searchGlobalDelay('Bob')

  setExperimentalWaveform('Alice')
  setExperimentalWaveform('Bob')


  import LongRandomWaveform
  rnsAliceForAWG, rnsAliceForTDC, rnsAliceForSync, rnsBobForAWG, rnsBobForTDC, rnsBobForSync = LongRandomWaveform.getRNS()
  worker.TFTDCServer.configureAnalyser('TFQKDEncoding', {'SignalChannel': 3, 'Period': 10000, 'RandomNumbers': rnsAliceForTDC})
  worker.TFTDCServer.configureAnalyser('TFQKDEncoding', {'SignalChannel': 5, 'Period': 10000, 'RandomNumbers': rnsBobForAWG})


# localStoreOpened = worker.TFTDCServer
#   actions = [
#       # Action('CheckLaserPowerAndPolarization', checkLaserPowerAndPolarization),
#       Action('SearchGlobalDelay', searchGlobalDelay),
#   ]
#   for action in actions:
#     console.log(f'Performing Action [{action.name}]')
#     success = action.perform()
#     console.log(f'Action [{action.name}] done.')
#     if not success:
#       console.log(f'Action [{action.name}] failed, exiting...')
#   # actions[0].perform()
