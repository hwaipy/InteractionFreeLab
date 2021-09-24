from ctypes import (
    c_int,
    c_char_p,
)
from time import sleep
from Instrument.lab.thorlabs_kinesis import polarizer as mpc
from threading import Thread
from queue import Queue
import numpy as np

class MPC320:
    def __init__(self, SN):
        self.SN = c_char_p(bytes(SN, "utf-8"))
        self.delay = c_int(40)
        self.positions = [0, 0, 0]
        mpc.TLI_BuildDeviceList()
        err = mpc.MPC_Open(self.SN)
        if err != 0:
            mpc.MPC_Close(self.SN)
            raise NameError(f"Can't open kinesis polarizer, make sure the Serial Number is OK and the device connection. You can check both on the kinesis program. Error number: {err}")
        mpc.MPC_StartPolling(self.SN, self.delay)
        mpc.MPC_ClearMessageQueue(self.SN)
        self.actionQueue = Queue()
        def loop():
            while True:
                sleep(0.05)
                if self.actionQueue.qsize() > 0:
                    action = self.actionQueue.get()
                    print(action)
                self.positions = [mpc.MPC_GetPosition(self.SN, i) for i in range(1, 4)]
                # print(self.positions)

        Thread(target=loop, daemon=True).start()

    def getCurrentPositions(self):
        return self.positions

    def setPositions(self, positions):
        assert len(positions) == 3
        for position in positions:
            assert position > 0 and position < 170
        for i in range(3):
            mpc.MPC_MoveToPosition(self.SN, i + 1, positions[i])
        previousPositions = np.array(self.positions)
        targetPositions = np.array(positions)
        unmovedStep = 0
        while True:
            sleep(0.1)
            currentPositions = np.array(self.positions)
            moveDeltas = currentPositions - previousPositions
            targetDeltas = currentPositions - targetPositions
            moveDelta = np.max(np.abs(moveDeltas))
            targetDelta = np.max(np.abs(targetDeltas))
            previousPositions = currentPositions
            if targetDelta < 0.1: break
            if moveDelta < 0.01: unmovedStep += 1
            if unmovedStep == 10:
                raise ValueError('Move Status Error.')

    def setPosition(self, paddle, position):
        positions = [p for p in self.positions]
        positions[paddle] = position
        self.setPositions(positions)

if __name__ == '__main__':
    import sys

    sn = sys.argv[1]
    serviceName = sys.argv[2]

    mpc320 = MPC320(sn) # 38161274
    sleep(1)

    from interactionfreepy import IFWorker, IFLoop
    IFWorker('tcp://192.168.25.5:224', serviceName, mpc320)
    print('Polarizer Started!')
    IFLoop.join()
