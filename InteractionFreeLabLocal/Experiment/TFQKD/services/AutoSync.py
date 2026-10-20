from interactionfreepy import IFWorker
from datetime import datetime, timedelta, timezone
import numpy as np
from tornado.ioloop import IOLoop
import time
from threading import Thread, Event, Lock
from rich.live import Live
from rich.table import Table
from rich.console import Group
from rich.text import Text
import readchar

class AutoSync:
    def __init__(self, worker):
        self.worker = worker
        self.aliceOn = False
        self.bobOn = False
        self.aliceParameter = 0.0
        self.bobParameter = 0.0

        self._lock = Lock()
        self._stop = Event()
        self._thread = Thread(target=self._run, daemon=False)
        self._thread.start()

    def _run(self):
        while not self._stop.wait(1):
            # 在这里添加同步逻辑，可以正常 print()
            pass

    def toggle(self, target):
        with self._lock:
            if target == "alice":
                self.aliceOn = not self.aliceOn
                enabled = self.aliceOn
            else:
                self.bobOn = not self.bobOn
                enabled = self.bobOn

        print(f"{target.capitalize()} Sync -> {'ON' if enabled else 'OFF'}")

    def setParameters(self, alice=None, bob=None):
        with self._lock:
            if alice is not None:
                self.aliceParameter = alice
            if bob is not None:
                self.bobParameter = bob

    def render(self):
        with self._lock:
            states = [
                ("Alice Sync", self.aliceOn, self.aliceParameter),
                ("Bob Sync", self.bobOn, self.bobParameter),
            ]

        table = Table()
        table.add_column("Sync")
        table.add_column("Status")
        table.add_column("Parameter", justify="right")

        for name, enabled, value in states:
            status = Text(
                "ON" if enabled else "OFF",
                style="green" if enabled else "red",
            )
            table.add_row(name, status, f"{value:.3f}")

        alice_action = "Stop" if states[0][1] else "Start"
        bob_action = "Stop" if states[1][1] else "Start"

        return Group(
            table,
            Text(
                f"[A] {alice_action} Alice   "
                f"[B] {bob_action} Bob   "
                "[Q] Quit"
            ),
        )

    def close(self):
        self._stop.set()
        self._thread.join()


    # def __syncOnce(self):
    #     data = self.__fetchLatest(7)
    #     centerTimeAlice = self.__estimateCenterTime([d['Data']['TFQKDSyncAlice'] for d in data], 'Sync Alice')
    #     centerTimeBob = self.__estimateCenterTime([d['Data']['TFQKDSyncBob'] for d in data], 'Sync Bob')

    #     target = 5
    #     deltaAlice = 0 if np.isnan(centerTimeAlice) or not self.aliceOn else (target - centerTimeAlice / 1000)
    #     deltaBob = 0 if np.isnan(centerTimeBob) or not self.bobOn else (target - centerTimeBob / 1000)

    #     self.clockManager.delay(alice=deltaAlice, bob=deltaBob)
    #     print('AutoSynced: {:.3f} ns for Alice, {:.3f} ns for Bob.'.format(deltaAlice, deltaBob)) 
        
    # def __fetchLatest(self, limit):
    #     # data = self.storage.latest(self.collection, by='FetchTime', after=(datetime.now(tz=pytz.timezone('Asia/Shanghai')) - timedelta(seconds=limit)).isoformat(), filter={'_id': 1}, length=limit + 5)
    #     data = self.storage.latest(self.collection, by='FetchTime', after=(datetime.now(tz=timezone.utc) - timedelta(seconds=limit)).isoformat(), filter={'_id': 1}, length=limit + 5)
    #     return [self.storage.get(self.collection, d['_id'], key='_id', filter={'Data.TFQKDSyncAlice': 1, 'Data.TFQKDSyncBob': 1}) for d in data]

    # def __estimateCenterTime(self, dataSet, key):
    #     if len(dataSet) == 0: return np.nan
    #     config = dataSet[0]['Configuration'] 
    #     period = config['Period']
    #     binCount = config['BinCount']
    #     xs = np.linspace(0, period, binCount + 1)[:-1] 
    #     xs += (xs[1] - xs[0]) / 2

    #     histograms = np.array([d['Histogram[{}]'.format(key)] for d in dataSet])
    #     histogram = np.sum(histograms, axis=0)

    #     if np.max(histogram) / np.min(histogram) < 10 or (np.sum(histogram) / len(dataSet)) < 500:
    #         return np.nan

    #     return self.__fitCenterTime(xs, histogram)

    # def __fitCenterTime(self, xs, ys):
    #     maxValue = np.max(ys)
    #     maxIndex = np.where(ys == maxValue)[0][0]
    #     inPulseIndices = np.where(ys > maxValue * 0.2)[0]

    #     maxIndexInPulse = np.where(inPulseIndices == maxIndex)[0][0]

    #     inPulseIndices = inPulseIndices[np.where(inPulseIndices == [i + maxIndex - maxIndexInPulse for i in range(len(inPulseIndices))])]
    #     return sum([xs[i] * ys[i] for i in inPulseIndices]) / sum(ys[inPulseIndices])



if __name__ == '__main__':
    worker = IFWorker('tcp://192.168.0.5:1061')
    syncer = AutoSync(worker)

    try:
        with Live(
            get_renderable=syncer.render,
            refresh_per_second=24,
        ):
            while True:
                key = readchar.readkey().lower()

                if key == "a":
                    syncer.toggle("alice")
                elif key == "b":
                    syncer.toggle("bob")
                elif key in ("q", "\x03"):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        syncer.close()