import os
import subprocess
from interactionfreepy import IFWorker, IFLoop
import time


class KeyRate:
    def __init__(self, exe):
        self.root = ''
        self.exe = exe

    def keyRate(self, data, inf=False):
        C = 1 if not inf else 1e10
        repeRate = data['RepetitionRate']
        dataFile = open('{}DATA_FILE.csv'.format(self.root), 'w')
        dataFile.write('{}\n'.format(', '.join([str(i) for i in (data['aliceMius'] + data['alicePs'])])))
        dataFile.write('{}\n'.format(', '.join([str(i) for i in (data['bobMius'] + data['bobPs'])])))
        dataFile.write('{}\n'.format(', '.join([str(i) for i in [
            0, int(data['ValidTime'] * repeRate) * C,
               int(data['XX Correct']) * C, int(data['XX Wrong']) * C,
               int(data['YY Count']) * C,
               int(data['XO Count']) * C,
               int(data['OX Count']) * C,
               int(data['YO Count']) * C,
               int(data['OY Count']) * C,
               int(data['OO Count']) * C,
               int(data['ZZ Correct']) * C, int(data['ZZ Wrong']) * C,
        ]])))
        dataFile.close()

        p = subprocess.Popen('{}{}'.format(self.root, self.exe), shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        # os.remove('{}DATA_FILE.csv'.format(self.root))
        result = str(stdout, 'GB2312')
        retults = result.split('\n')
        for r in retults:
            if r.startswith('Line 0'):
                print(r)
                try:
                    return float(r.split(',')[1][3:]) * repeRate
                except BaseException as e:
                    return 0
        return 0


IFWorker('tcp://172.16.60.200:224', 'MDI-QKD KeyRate', KeyRate('MDI-freespace-data_process_failure_1e-7.exe'))
IFWorker('tcp://172.16.60.200:224', 'MDI-QKD KeyRate 20201016', KeyRate('MDI-freespace-data_process_failure_1e-7_20201016.exe'))
IFLoop.join()

