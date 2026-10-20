from datetime import datetime
import time
import sys
from scipy import signal
import numpy as np

class ReadTimeTDC:
    def __init__(self):
        self.dataBuffer = []
    
    def offer(self, data):
        print(f'offerred at {datetime.now()}')
        self.dataBuffer.append(data)
        if len(self.dataBuffer) > 360000:
            self.dataBuffer.pop(0)
    
    def getRecent(self, count, reversed=False):
        print(f'getting recent at {datetime.now()}')
        result = [d for d in self.dataBuffer]
        result = result if (len(result) <= count) else result[-count:]
        if (reversed): result.reverse()
        print(f'get recent at {datetime.now()}')
        return result

    def getRanged(self, begin, end, reversed=False):
        print(f'getting ranged at {datetime.now()}')
        begin = datetime.fromisoformat(begin).timestamp() * 1000
        end = datetime.fromisoformat(end).timestamp() * 1000
        result = [d for d in self.dataBuffer if d['FetchTime'] >= begin and d['FetchTime'] <= end]
        if (reversed): result.reverse()
        print(f'get ranged at {datetime.now()}')
        return result

    def getRecentDipCenter(self, count, target):
        data = self.getRecent(count, reversed=True)

        def estimateCenter(target):
            dataAs = np.array([d[f'TFQKDSync{target}'][f'Histogram[Sync {target}]'] for d in data])
            dataA = np.sum(dataAs, axis=0)
            if target == 'Alice':
                dataA = np.hstack((dataA[-int(len(dataA) / 4):], dataA[:int(len(dataA) / 4)]))
            else:
                dataA = dataA[int(len(dataA) / 4):int(len(dataA) / 4 * 3)]

            b, a = signal.butter(8, 5 / len(dataA), 'highpass')
            filteredDataA = signal.filtfilt(b, a, dataA)

            peakValue = min(filteredDataA)
            center = np.where(filteredDataA == peakValue)[0][0]
            for right in range(center, len(filteredDataA)):
                if filteredDataA[right] > peakValue / 2: break
            for left in range(center, 0, -1):
                if filteredDataA[left] > peakValue / 2: break
            weight = 0
            count = 0
            for i in range(left, right + 1):
                weight += i * filteredDataA[i]
                count += filteredDataA[i]
            valid = min(filteredDataA[:left]) > peakValue * 0.7 and max(filteredDataA[right:]) > peakValue * 0.7
            center = weight / count / len(dataA) * 10
            return center if valid else np.nan

        return np.average([d['FetchTime'] / 1000.0 for d in data]), estimateCenter(target)


if __name__ == '__main__':
    from interactionfreepy import IFWorker, IFLoop
    import sys
    
    ifserver = sys.argv[1] if len(sys.argv) >= 2 else 'tcp://192.168.25.5:1061'

    worker = IFWorker(ifserver, 'RealTimeTDC', ReadTimeTDC(), force=True)
    print('RealTime TDC started.')

    if len(sys.argv) >= 3:
        outputDir = sys.argv[2]
        sys.stdout = open(f"{outputDir}/RealTimeTDC_Log_{str(datetime.now()).replace(':', '-')}.txt", "w")

    IFLoop().join()