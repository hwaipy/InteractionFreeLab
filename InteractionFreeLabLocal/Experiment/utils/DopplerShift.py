import pickle
import numpy as np

timeUnit = 0.01

with open('Doppler_Timing.pkl', 'rb') as file:
    dopplerTimings = pickle.load(file)

def calc_int(dopplerTimings, baseFrequency):
    wavenumber = 0
    for f in dopplerTimings['f']:
        wavenumber += (f - baseFrequency) * timeUnit
    return wavenumber

print('原始波形累积相位(/2pi)', calc_int(dopplerTimings, 10e6))

for i in range(9364):
    dopplerTimings['f'].append(dopplerTimings['f'][-1])
dopplerTimings['f'].append(10e6 - 80.07734867077092)
for i in range(635):
    dopplerTimings['f'].append(10e6)

print(len(dopplerTimings['f']))

print('增加采样点后累积相位(/2pi)', calc_int(dopplerTimings, 10e6))

for i in range(10000):
    dopplerTimings['T'].append(dopplerTimings['T'][-1] + timeUnit)

# import matplotlib.pyplot as plt
# plt.plot(dopplerTimings['T'], dopplerTimings['f'])
# plt.show()

# for i in range(len(dopplerTimings['f'])):
#     dopplerTimings['f'][i] = 10e6 + 238.1234 # dopplerTimings['f'][-1]

with open('Doppler_Timing_e.pkl', 'wb') as file:
    pickle.dump(dopplerTimings, file)

# with open('../Launchers/Doppler_Timing.pkl', 'rb') as file:
#     dopplerTimings = pickle.load(file)
#     print(dopplerTimings['T'][:100])
#     print(dopplerTimings['f'][:100])
