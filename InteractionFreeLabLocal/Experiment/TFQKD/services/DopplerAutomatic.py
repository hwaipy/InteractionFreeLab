from interactionfreepy import IFWorker, IFLoop
import time
from queue import Queue
from threading import Thread

class DopplerAutomatic:
  def __init__(self, worker, workerRemote):
    self.worker = worker
    self.status = 'Not Started'  # 'Not Started' (changable), 'Starting', 'Waiting' (changable), 'In Progress' (changable), 'Stopping', 'Stopped' (changable), 'Finished' (changable)
    self.beginTime = None
    self.actions = Queue()   # BeginAt, Stop
    self.beginTime = 0
    self.progress = 0
    self.totalDuration = 700
    self.tdc = workerRemote.TFTDCServer
    Thread(target=self._loop).start()

  def beginDopplerAt(self, beginTime):
    self.actions.put(['BeginAt', beginTime])

  def stopDoppler(self):
    self.actions.put(['Stop'])

  def getStatus(self):
    if self.status == 'Waiting': return [self.status, self.beginTime - time.time()]
    if self.status == 'In Progress': return [self.status, self.progress, self.totalDuration]
    return [self.status]

  def _loop(self):
    while True:
      if self.actions.qsize():
        action = self.actions.get()
        if action[0] == 'BeginAt':
          if self.status in ['Waiting', 'In Progress']:
            self._do_stop()
          if self.status in ['Not Started', 'Stopped', 'Finished']:
            self._do_begin_at(action[1])
          else: print('Not a valid status at action begin: ' + self.status)
        if action[0] == 'Stop':
          if self.status in ['Waiting', 'In Progress']:
            self._do_stop()

      if self.status == 'Not Started' or self.status == 'Stopped' or self.status == 'Finished' :
        time.sleep(0.1)
      elif self.status == 'Waiting':
        time.sleep(0.05)
        if time.time() < self.beginTime - 7:
          continue
        suc = self._beginAllDevicesImmediately()
        if suc:
          self.status = 'In Progress'
          self.progress = 0
        else:
          self.status = 'Stopped'
      elif self.status == 'In Progress':
        time.sleep(0.1)
        self.progress += 0.1
        if self.progress >= self.totalDuration:
          self.status = 'Finished'
      else:
        print('Invalid status: ' + self.status)
        time.sleep(0.1)

  def _do_begin_at(self, beginTime):
    print('begin! ', beginTime)
    # check if the begin time is in future
    self.status = 'Starting'
    self.beginTime = beginTime / 1000
    ava = self._checkAvaibilityBeforeStart()
    self.worker.AliceLocalService.stopTimeDoppler()
    self.worker.BobLocalService.stopTimeDoppler()
    if ava:
      if time.time() < self.beginTime - 4:
        self.status = 'Waiting'
      else:
        self.status = 'Stopped'
    else:
      self.status = 'Stopped'

  def _do_stop(self):
    print('stop')
    self.status = 'Stopping'
    cont = True
    def func():
      self.worker.AliceLocalService.stopTimeDoppler()
      self.worker.BobLocalService.stopTimeDoppler()
      self.worker.TF_TriggerBoard_Alice.stop()
      self.worker.TF_TriggerBoard_Bob.stop()
      self.tdc.startDopplerShift(0)
      print('Done stopping.')
    t = Thread(target=func)
    t.start()
    t.join(timeout=10)
    cont = False
    self.status = 'Stopped'

  def _checkAvaibilityBeforeStart(self):
    cont = True
    finished = False
    def func():
      nonlocal finished
      if cont: pass
      finished = True
    t = Thread(target=func)
    t.start()
    t.join(timeout=10)
    cont = False
    return finished

  def _beginAllDevicesImmediately(self):
    finished = False
    def func():
      nonlocal finished
      self.worker.AliceLocalService.startTimeDoppler()
      self.worker.BobLocalService.startTimeDoppler()
      print('Time Doppler starting.')
      self.worker.AliceLocalService.startFreqDoppler()
      self.worker.BobLocalService.startFreqDoppler()
      print('Freq Doppler starting.')
      print(self.beginTime)
      self.tdc.startDopplerShift(int(self.beginTime))
      print('TDC prepared.')
      while True:
        time.sleep(0.05)
        if time.time() < self.beginTime - 0.5:
          continue
        self.worker.TF_TriggerBoard_Alice.start()
        self.worker.TF_TriggerBoard_Bob.start()
        print('Trigger Board starting.')
        break
      finished = True
    t = Thread(target=func)
    t.start()
    t.join(timeout=10)
    return finished

if __name__ == '__main__':
  from interactionfreepy import IFWorker, IFLoop
  
  da = DopplerAutomatic(IFWorker('tcp://172.20.8.102:1161', blocking=False), IFWorker('tcp://tf.qpqi.group:1161', blocking=False))
  worker = IFWorker('tcp://172.20.8.102:1161', serviceName='DopplerAutomatic', serviceObject=da, force=True)
  print('Doppler Automatic Started...')
  IFLoop().join()
