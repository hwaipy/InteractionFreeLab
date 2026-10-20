from interactionfreepy import IFWorker
import msgpack
from urllib.request import urlopen
from pytimetag import DataBlock
from pytimetag.analysers.HistogramAnalyser import HistogramAnalyser
from pytimetag.analysers.EncodingAnalyser import EncodingAnalyser
import numpy as np

worker = IFWorker('tcp://10.1.1.1:1061')
# print(worker.listServiceNames())
# worker.TF_AtomicClock_Alice.delay1PPS(4100)
# print(worker.listServiceNames())

# LongWaveformGenerator.waveformID()['Delay']['step1']
step1 = '2023-04-06 19-04-10.851159 R820892'
msv = msgpack.unpackb(worker.TF_FileStorage.readMassive(id=step1))

# print(len(msv))
# print(msv[:1000])
# print(msv[-1000:])

ha = HistogramAnalyser(8)
ha.configure({
    "Sync": 1,
    "Signals": [2],
    "ViewStart": 0,
    "ViewStop": 1000000000000,
    "BinCount": 1000,
    "Divide": 1250
})
ha.turnOn()

# ranges = worker.Storage.range('TFQKD_TDC', '2023-04-07T19:45:00+08:00', '2023-04-07T19:46:00+08:00', filter={'_id': 1})
# result = 0

# for item in ranges[:1]:
#     fetchTime = item["FetchTime"]
#     res = urlopen(f'http://10.1.1.1:1001/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock')
#     data = res.read()
#     res.close()

#     dataBlock = DataBlock.deserialize(data)
#     dataBlock.unpack()
#     print(dataBlock.sizes)
#     r = ha.dataIncome(dataBlock)
#     h = np.array(r['Histograms'])
#     # print(r)
#     result += h

# print(result)

# start = 393418179817421120 / 1000000.0
# ch0 = np.array([393418179849539999, 393418179889540014, 393418179929540069, 393418179969540145, 393418180009540119, 393418180049540159, 393418180089540234, 393418180129540253, 393418180169540269, 393418180209540265]) / 1000000 - start
# ch2 = np.array([393418179818326930, 393418179819946009, 393418191618244558, 393418213457372653, 393418235964524404, 393418246521265577, 393418264535001700, 393418298593119218, 393418301216978339, 393418318861161643, 393418319914418415, 393418379818288627, 393418379821057707, 393418398284027899, 393418403797701604, 393418409320636949, 393418413076519173, 393418418597658411, 393418431065635222, 393418434053258741, 393418450865698344, 393418494867412435, 393418519185896159, 393418522065939074, 393418529674188757, 393418529696162536, 393418552003213342, 393418579819849340, 393418579820026956, 393418579820662508, 393418579821152083, 393418593420343311, 393418611840470730, 393418617051005898, 393418623436054175, 393418637146789698, 393418665256874171, 393418665685340351, 393418717821933606, 393418738818841322, 393418740429566841, 393418753344230596, 393418768137955838, 393418771927723744, 393418779821459917, 393418782872930988, 393418801140770956, 393418818432473311, 393418900335146389, 393418917198824249, 393418950661626881, 393418955866829450, 393418959901613470, 393418979820510062, 393418983500686988, 393418995164579734, 393418998637840018, 393419001915486380, 393419005469784484, 393419022436311119, 393419024466052451, 393419029582316672, 393419040977176943, 393419047354284139, 393419050220659085, 393419050537192198, 393419068067280148, 393419102116821392, 393419102841874178, 393419107743931767, 393419128784466555, 393419164441570827, 393419173889983989]) / 1000000 - start

# print(ch0)
# print(ch2)

# h = np.histogram(ch2, bins=100)
# print(h)



ea = EncodingAnalyser(16, 256)
ea.turnOn({
    'Period': 10000,
    'TriggerChannel': 0,
    'SignalChannel': 2,
    'RandomNumbers': [64, 65] * 500 + [0 for i in range(79000)],
    'Histograms': { 
        'All Pulses': [i for i in range(128)],
        'All Signals': [i for i in range(64)],
        'All Ref': [64, 128],
        'Vacuum': [i for i in range(64) if i % 4 == 0],
        'X': [i for i in range(64) if i % 4 == 1],
        'Y': [i for i in range(64) if i % 4 == 2],
        'Z': [i for i in range(64) if i % 4 == 3],
    }})


ranges = worker.Storage.range('TFQKD_TDC', '2023-04-07T21:15:00+08:00', '2023-04-07T21:16:00+08:00', filter={'_id': 1})
result = 0

for item in ranges[:1]:
    fetchTime = item["FetchTime"]
    res = urlopen(f'http://10.1.1.1:1001/{fetchTime.split("T")[0]}/{fetchTime.split("T")[1][:2]}/{fetchTime[:23].replace("T", "%20").replace(":", "-")}.datablock')
    data = res.read()
    res.close()

    dataBlock = DataBlock.deserialize(data)
    dataBlock.unpack()
    print(dataBlock.sizes)
    r = ea.dataIncome(dataBlock)
    print(r.keys())
    print(r['Histogram[Vacuum]'])
#     h = np.array(r['Histograms'])
#     # print(r)
#     result += h

    dataBlock.content[0] = [dataBlock.content[0][0]]
    r = ha.dataIncome(dataBlock)
    h = np.array(r['Histograms'])
    print(r)

# print(result)

