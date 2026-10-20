import time
import numpy as np
from TF_PowerSupply_Control import ATT_set, ATT_get, AM_DCget, AM_DCset
from getLatestPulseRatio import getLatestPulseRatio
import matplotlib.pyplot as plt
from PIL import Image
import threading
import math
from AutoSyncExra_wmy import MoMethod
from AutoSync_wmy_version3 import AutoSync


def to_dB(ratio):
    return 10 * math.log10(ratio)


def openPicture(*args):
        path = args[0]
        im = Image.open(path)
        im.show()


def plot(V_Ratio_list, target=np.nan, AM=np.nan, pltshow=False):
    # 增加线程 绘制数据图
    V_Ratio_list.sort(key=lambda x: x[1], reverse=True)
    maxlist = V_Ratio_list[0]
    V_Ratio_list.sort(key=lambda x: x[0], reverse=False)
    V = [i[0] for i in V_Ratio_list]
    Ratio = [to_dB(i[1]) for i in V_Ratio_list]
    plt.figure(dpi=1000)
    plt.plot(V, Ratio)
    plt.title(f'{target} AM={AM} Ratio—V({round(to_dB(maxlist[1]), 3)} dB—{round(maxlist[0], 3)})')
    plt.xlabel('DC Voltage')
    plt.ylabel('Ratio(dB)')
    if pltshow:
        plt.show()
        plt.close()
    else:
        import os
        if not os.path.exists('./AM_DC-Picture'):
            os.mkdir('./AM_DC-Picture')
        path = f'./AM_DC-Picture/{target}_AM{AM}.png'
        plt.savefig(path)
        plt.close()
        thread = threading.Thread(target=openPicture, args=(path,))
        thread.start()


def alignPulse(target):
    print('Aligning pulses……')
    autosync = AutoSync(target=target, searchMOfirst=False, Nroundlimit=3)
    autosync.loop()
    MoMethod.setMO(target=target, MO=MoMethod.latest_MOsync(target=target))
    print('Aligning pulses……Done!')


def AM_DCserch(target: str, AM: int, plotYN=True, changeAnotherAM=True):
    # 指令下达的延时
    control_delay = 0.5
    # 使另一个AM处于不消光状态
    if changeAnotherAM:
        AM_another = (AM + 1) % 2
        DC_another = AM_DCget(target, AM_another)
        AM_DCset(target, AM_another, int(DC_another + 7) % 15.0001)
    # 衰减另一个发射端的光
    target_another = [i for i in ['Alice', 'Bob'] if i != target][0]
    att = ATT_get(target=target_another)
    ATT_set(target=target_another, V=5.9)

    def search(Vlist, n=1):
        # 使脉冲中心对齐
        alignPulse(target=target)
        V_Ratio_list = []
        for V in Vlist:
            V = V % 15.0001
            AM_DCset(target=target, AM=AM, Voltage=V)
            time.sleep(n+control_delay)
            result = getLatestPulseRatio(nset=n)
            Ratio = result['SignalVacuumRatio']  # 多取几秒数据取平均值
            print(f'{target}, AM={AM}, V = {V}, SignalVacuumRatio = {result["SignalVacuumRatio(dB)"]} dB')
            V_Ratio_list.append([V, Ratio])
        V_Ratio_list.sort(key=lambda x: x[1], reverse=True)
        Vm0 = V_Ratio_list[0][0]
        Vm1 = V_Ratio_list[1][0]
        AM_DCset(target, AM, Vm0)
        time.sleep(control_delay+1)
        return Vm0, Vm1, V_Ratio_list

    Vm0, Vm1, V_Ratio_list = search(np.linspace(0, 15, 16))
    searchrange = np.unique(np.hstack((np.linspace(Vm1 - 1, Vm1 + 1, 21), np.linspace(Vm0-1, Vm0+1, 21))))
    Vm00, Vm01, V_Ratio_list0 = search(searchrange, 2)
    searchrange = np.unique(np.hstack((np.linspace(Vm01 - 0.1, Vm01 + 0.1, 21), np.linspace(Vm00-0.1, Vm00+0.1, 21))))
    Vm10, Vm11, V_Ratio_list1 = search(searchrange, 2)
    VRL = V_Ratio_list0 + V_Ratio_list1
    VRL.sort(key=lambda x: x[1], reverse=True)
    # 最优值
    Vm = VRL[0][0]
    # 输出最优值
    print('*' * 30)
    print(f'{target}, AM={AM}, V = {Vm}, SignalVacuumRatio = {to_dB(VRL[0][1])} dB')
    print('*' * 30)

    # 恢复另一个发射端的光
    ATT_set(target=target_another, V=att)
    # 将另一个AM恢复
    if changeAnotherAM: AM_DCset(target, AM_another, DC_another)
    # 将此AM调节至最佳消光比位置
    AM_DCset(target=target, AM=AM, Voltage=round(Vm, 3))

    if plotYN:
        plot(V_Ratio_list+V_Ratio_list0+V_Ratio_list1, target, AM)
    return


def AM_DCserch_Control(target):
    AM_DCserch(target=target, AM=0, plotYN=True, changeAnotherAM=True)
    AM_DCserch(target=target, AM=1, plotYN=True, changeAnotherAM=True)


def AM_DCserch_alittle(target: str, AM: int, plotYN=True, changeAnotherAM=True):
    # 指令下达的延时
    control_delay = 0.5
    # 使另一个AM处于不消光状态
    if changeAnotherAM:
        AM_another = (AM + 1) % 2
        DC_another = AM_DCget(target, AM_another)
        AM_DCset(target, AM_another, int(DC_another + 7) % 15.0001)
    # 衰减另一个发射端的光
    target_another = [i for i in ['Alice', 'Bob'] if i != target][0]
    att = ATT_get(target=target_another)
    ATT_set(target=target_another, V=5.9)

    def search(Vlist, n=1):
        # 使脉冲中心对齐
        alignPulse(target=target)
        V_Ratio_list = []
        for V in Vlist:
            V = V % 15.0001
            AM_DCset(target=target, AM=AM, Voltage=V)
            time.sleep(n+control_delay)
            result = getLatestPulseRatio(nset=n)
            Ratio = result['SignalVacuumRatio']  # 多取几秒数据取平均值
            print(f'{target}, AM={AM}, V = {V}, SignalVacuumRatio = {result["SignalVacuumRatio(dB)"]} dB')
            V_Ratio_list.append([V, Ratio])
        V_Ratio_list.sort(key=lambda x: x[1], reverse=True)
        Vm0 = V_Ratio_list[0][0]
        Vm1 = V_Ratio_list[1][0]
        AM_DCset(target=target, AM=AM, Voltage=round(Vm0, 3))
        time.sleep(control_delay+1)
        return Vm0, Vm1, V_Ratio_list

    DC = AM_DCget(target, AM)
    searchrange = np.linspace(DC - 0.3, DC, 31)
    _, _, V_Ratio_list = search(searchrange, 2)
    searchrange = np.linspace(DC, DC + 0.3, 31)
    _, _, V_Ratio_list1 = search(searchrange, 2)
    VRL = V_Ratio_list + V_Ratio_list1
    VRL.sort(key=lambda x: x[1], reverse=True)
    # 最优值
    Vm = VRL[0][0]
    # 输出最优值
    print('*' * 30)
    print(f'{target}, AM={AM}, V = {Vm}, SignalVacuumRatio = {to_dB(VRL[0][1])} dB')
    print('*' * 30)

    # 恢复另一个发射端的光
    ATT_set(target=target_another, V=att)
    # 将另一个AM恢复
    if changeAnotherAM: AM_DCset(target, AM_another, DC_another)
    # 将此AM调节至最佳消光比位置
    AM_DCset(target=target, AM=AM, Voltage=round(Vm, 3))

    if plotYN:
        plot(V_Ratio_list+V_Ratio_list1, target, AM)
    return


def AM_DCserch_Control_alittle(target):
    AM_DCserch_alittle(target=target, AM=0, plotYN=True, changeAnotherAM=False)
    AM_DCserch_alittle(target=target, AM=1, plotYN=True, changeAnotherAM=False)


if __name__ == '__main__':
    AM_DCserch_Control('Alice')
    # AM_DCserch_Control('Bob')

    # AM_DCserch_Control_alittle('Alice')
    # AM_DCserch_Control_alittle('Bob')
