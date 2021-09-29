if __name__ == '__main__':
    from IFWorker import IFWorker
    from IFCore import IFLoop
    import time
    import numpy as np

    worker = IFWorker('tcp://172.16.60.199:224')

    dmm = worker.EO_DMM
    dc = worker.EO_DC
    dmm.setDCCurrentMeasurement(2e-3, autoRange=False, aperture=0.1)


    def readPower():
        return dmm.directMeasure(count=1)[0]


    def setVoltage(v):
        if v < 0: v = 0
        if v > 7: v = 7
        dc.setVoltage(0, v)


    # voltages = np.linspace(0, 5, 20)
    # currents = []
    # for v in voltages:
    #     setVoltage(v)
    #     time.sleep(0.5)
    #     power = readPower()
    #     print(v, power)
    #     currents.append(power)
    #
    # import matplotlib.pyplot as plt
    # plt.plot(voltages, currents)
    # plt.show()
    # print(worker.EO_LaserDrive.test())

    target = 0.5e-3
    voltage = dc.getVoltageSetpoints()[0]
    voltage = 2.1
    step = -0.001
    while True:
        power = readPower()
        if power > target:
            voltage += step
        else:
            voltage -= step
        setVoltage(voltage)
        print(power, voltage)
        time.sleep(0.2)