import numpy as np
from worker_config import worker


def ATT_set(target: str, V):
    if target == 'Alice':
        dc = worker.TF_PowerSupply_Alice_3
        dc.setVoltage(2, V)
    elif target == 'Bob':
        dc = worker.TF_PowerSupply_Bob_4
        dc.setVoltage(2, V)


def ATT_get(target: str):
    if target == 'Alice':
        dc = worker.TF_PowerSupply_Alice_3
        return dc.getVoltageSetPoint(2)
    elif target == 'Bob':
        dc = worker.TF_PowerSupply_Bob_4
        return dc.getVoltageSetPoint(2)
    return np.nan


def AM_DCget(target: str, AM: int):
    dc = eval(f'worker.TF_PowerSupply_{target}_{2 if target == "Alice" else 3}')
    return dc.getVoltageSetPoint(AM)


def AM_DCset(target: str, AM: int, Voltage):
    Voltage = Voltage % 15.0001
    dc = eval(f'worker.TF_PowerSupply_{target}_{2 if target == "Alice" else 3}')
    dc.setVoltage(AM, Voltage)


if __name__ == '__main__':
    pass
