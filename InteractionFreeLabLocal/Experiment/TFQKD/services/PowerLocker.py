from interactionfreepy import IFWorker, IFLoop
import time
from queue import Queue
import math
from threading import Thread

class PowerLocker:
  def __init__(self, powerMeter, powerSupply, powerSupplyChannel):
    self.locked = False
    self.powerMeter = powerMeter
    self.powerSupply = powerSupply
    self.powerSupplyChannel = powerSupplyChannel
    self.targetPower = -70
    Thread(target=self._loop).start()

  def setLockValue(self, value):
    self.targetPower = float(value)

  def getLockValue(self):
    return self.targetPower

  def setLockStatus(self, locked):
    self.locked = locked

  def getLockStatus(self):
    return self.locked

  def _loop(self):
    while True:
      if self.locked:
        currentPower = self.powerMeter.readPower()[1]
        curerentVoltage = self.powerSupply.measureVoltages()[self.powerSupplyChannel]
        step = 0.01 if currentPower > self.targetPower else -0.01
        if math.fabs(currentPower - self.targetPower) < 0.3: step /= 5
        self.powerSupply.setVoltage(self.powerSupplyChannel, curerentVoltage + step)
        print(f'Current power is {currentPower}, change voltage from {curerentVoltage} to {curerentVoltage + step}')
        time.sleep(0.9)
      time.sleep(0.1)

if __name__ == '__main__':
  from interactionfreepy import IFWorker, IFLoop
  
  worker = IFWorker('tcp://172.20.8.33:1161', blocking=True)
  plA = PowerLocker(worker.TF_PowerMeter_Alice, worker.TF_PowerSupply_Alice_3, 2)
  plB = PowerLocker(worker.TF_PowerMeter_Bob, worker.TF_PowerSupply_Bob_4, 2)
  # worker = IFWorker('tcp://172.20.8.33:1161', serviceName='PowerLocker_Alice', serviceObject=plA, force=True)
  worker = IFWorker('tcp://172.20.8.33:1161', serviceName='PowerLocker_Bob', serviceObject=plB, force=True)
  print('Power Locker Started...')
  IFLoop().join()
