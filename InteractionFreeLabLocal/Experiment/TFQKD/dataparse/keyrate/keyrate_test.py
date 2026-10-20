from ctypes import *
import sys
import platform

lib7 = cdll.LoadLibrary(f"{sys.path[0]}/keyrate_1e-7.{'so' if platform.system() == 'Linux' else 'dll'}")
lib7.keyrate.restype = c_double
lib10 = cdll.LoadLibrary(f"{sys.path[0]}/keyrate_1e-10.{'so' if platform.system() == 'Linux' else 'dll'}")
lib10.keyrate.restype = c_double
libInf = cdll.LoadLibrary(f"{sys.path[0]}/keyrate_inf.{'so' if platform.system() == 'Linux' else 'dll'}")
libInf.keyrate.restype = c_double


class KeyRate:
#   def calculate(self, counts, pulseNumber, intensities, errorX):
#     basis = ['signalZ0', 'signalZ1', 'signal0', 'signalX', 'signalY']

#     # 0 - 4 X基真空光源、X基弱源、X基强光、Z基发射、Z基真空概率
#     results = [sum([counts[f'{b1}-{b2}']['ratio'] for b2 in basis]) for b1 in ['signal0', 'signalX', 'signalY', 'signalZ1', 'signalZ0']]

#     # 5 - 7   X基弱源强度、X基强光强度、Z基相关态光源强度
#     results += intensities

#     # 8    # 发送总脉冲数
#     results += [pulseNumber]

#     # 9 - 33 实际发送组合比例
#     # 34 - 58 实际引起有效响应个数
#     for key in ['ratio', 'detector_count']:
#       for b1 in basis:
#         for b2 in basis:
#           results.append(counts[f'{b1}-{b2}'][key])

#     results += [
#         # 59 - 60
#         0.1291,  # 筛选比例
#         0,  # X基1错误计数
#     ]

#     kr = lib.keyrate((c_double * len(results))(*results))
#     return kr

  def calculate(self, results, strict=False, scale=1):
    lib = lib10 if strict else lib7
    multiI = [8] + [i for i in range(34, 59)] + [60]
    for i in multiI:
        results[i] *= scale
    kr = lib.keyrate((c_double * len(results))(*results))
    return kr


if __name__ == '__main__2':
    kr = KeyRate()
    from interactionfreepy import IFWorker, IFLoop
    worker = IFWorker('tcp://10.1.1.1:224', 'TF_KeyRate', kr, force=True)
    IFLoop().join()



if __name__ == '__main__':
  resultA = '''
{
    "all": {
        "ref": {
            "count": 1400,
            "ratio": 0.35,
            "detector_count": 5483654
        },
        "signal": {
            "count": 2500,
            "ratio": 0.625,
            "detector_count": 238177
        }
    },
    "signal0": {
        "signal0": {
            "count": 175,
            "ratio": 0.07,
            "detector_count": 33
        },
        "signalX": {
            "count": 152,
            "ratio": 0.0608,
            "detector_count": 8498
        },
        "signalY": {
            "count": 153,
            "ratio": 0.0612,
            "detector_count": 20256
        },
        "signalZ": {
            "count": 156,
            "ratio": 0.0624,
            "detector_count": 744
        },
        "signalZ1": {
            "count": 3,
            "ratio": 0.0012,
            "detector_count": 710
        },
        "signalZ0": {
            "count": 153,
            "ratio": 0.0612,
            "detector_count": 34
        }
    },
    "signalX": {
        "signal0": {
            "count": 175,
            "ratio": 0.07,
            "detector_count": 8849
        },
        "signalX": {
            "count": 169,
            "ratio": 0.0676,
            "detector_count": 17748
        },
        "signalY": {
            "count": 145,
            "ratio": 0.058,
            "detector_count": 26652
        },
        "signalZ": {
            "count": 154,
            "ratio": 0.0616,
            "detector_count": 9473
        },
        "signalZ1": {
            "count": 7,
            "ratio": 0.0028,
            "detector_count": 2083
        },
        "signalZ0": {
            "count": 147,
            "ratio": 0.0588,
            "detector_count": 7390
        }
    },
    "signalY": {
        "signal0": {
            "count": 161,
            "ratio": 0.0644,
            "detector_count": 20060
        },
        "signalX": {
            "count": 151,
            "ratio": 0.0604,
            "detector_count": 26910
        },
        "signalY": {
            "count": 160,
            "ratio": 0.064,
            "detector_count": 41418
        },
        "signalZ": {
            "count": 144,
            "ratio": 0.0576,
            "detector_count": 19505
        },
        "signalZ1": {
            "count": 7,
            "ratio": 0.0028,
            "detector_count": 2602
        },
        "signalZ0": {
            "count": 137,
            "ratio": 0.0548,
            "detector_count": 16903
        }
    },
    "signalZ": {
        "signal0": {
            "count": 143,
            "ratio": 0.0572,
            "detector_count": 1798
        },
        "signalX": {
            "count": 147,
            "ratio": 0.0588,
            "detector_count": 9963
        },
        "signalY": {
            "count": 161,
            "ratio": 0.0644,
            "detector_count": 22392
        },
        "signalZ": {
            "count": 154,
            "ratio": 0.0616,
            "detector_count": 3878
        },
        "signalZ1": {
            "count": 7,
            "ratio": 0.0028,
            "detector_count": 1851
        },
        "signalZ0": {
            "count": 147,
            "ratio": 0.0588,
            "detector_count": 2027
        }
    },
    "signalZ1": {
        "signal0": {
            "count": 7,
            "ratio": 0.0028,
            "detector_count": 1756
        },
        "signalX": {
            "count": 6,
            "ratio": 0.0024,
            "detector_count": 1881
        },
        "signalY": {
            "count": 5,
            "ratio": 0.002,
            "detector_count": 1874
        },
        "signalZ": {
            "count": 9,
            "ratio": 0.0036,
            "detector_count": 2457
        },
        "signalZ1": {
            "count": 1,
            "ratio": 0.0004,
            "detector_count": 458
        },
        "signalZ0": {
            "count": 8,
            "ratio": 0.0032,
            "detector_count": 1999
        }
    },
    "signalZ0": {
        "signal0": {
            "count": 136,
            "ratio": 0.0544,
            "detector_count": 42
        },
        "signalX": {
            "count": 141,
            "ratio": 0.0564,
            "detector_count": 8082
        },
        "signalY": {
            "count": 156,
            "ratio": 0.0624,
            "detector_count": 20518
        },
        "signalZ": {
            "count": 145,
            "ratio": 0.058,
            "detector_count": 1421
        },
        "signalZ1": {
            "count": 6,
            "ratio": 0.0024,
            "detector_count": 1393
        },
        "signalZ0": {
            "count": 139,
            "ratio": 0.0556,
            "detector_count": 28
        }
    }
}
   '''
  result = '''
    {
    "all": {
        "ref": {
            "count": 7000000,
            "ratio": 0.35,
            "detector_count": 585240
        },
        "signal": {
            "count": 12500000,
            "ratio": 0.625,
            "detector_count": 16532
        }
    },
    "signal0": {
        "signal0": {
            "count": 7,
            "ratio": 5.6e-07,
            "detector_count": 0
        },
        "signalX": {
            "count": 331,
            "ratio": 2.648e-05,
            "detector_count": 451
        },
        "signalY": {
            "count": 34,
            "ratio": 2.72e-06,
            "detector_count": 105
        },
        "signalZ": {
            "count": 7291,
            "ratio": 0.00058328,
            "detector_count": 10961
        },
        "signalZ1": {
            "count": 2083,
            "ratio": 0.00016664,
            "detector_count": 10925
        },
        "signalZ0": {
            "count": 5208,
            "ratio": 0.00041664,
            "detector_count": 36
        }
    },
    "signalX": {
        "signal0": {
            "count": 363,
            "ratio": 2.904e-05,
            "detector_count": 209
        },
        "signalX": {
            "count": 23422,
            "ratio": 0.00187376,
            "detector_count": 45753
        },
        "signalY": {
            "count": 1914,
            "ratio": 0.00015312,
            "detector_count": 6155
        },
        "signalZ": {
            "count": 514488,
            "ratio": 0.04115904,
            "detector_count": 1102784
        },
        "signalZ1": {
            "count": 143757,
            "ratio": 0.01150056,
            "detector_count": 857204
        },
        "signalZ0": {
            "count": 370731,
            "ratio": 0.02965848,
            "detector_count": 245580
        }
    },
    "signalY": {
        "signal0": {
            "count": 25,
            "ratio": 2e-06,
            "detector_count": 56
        },
        "signalX": {
            "count": 1860,
            "ratio": 0.0001488,
            "detector_count": 6227
        },
        "signalY": {
            "count": 166,
            "ratio": 1.328e-05,
            "detector_count": 780
        },
        "signalZ": {
            "count": 41599,
            "ratio": 0.00332792,
            "detector_count": 147837
        },
        "signalZ1": {
            "count": 11609,
            "ratio": 0.00092872,
            "detector_count": 85800
        },
        "signalZ0": {
            "count": 29990,
            "ratio": 0.0023992,
            "detector_count": 62037
        }
    },
    "signalZ": {
        "signal0": {
            "count": 7268,
            "ratio": 0.00058144,
            "detector_count": 7088
        },
        "signalX": {
            "count": 514574,
            "ratio": 0.04116592,
            "detector_count": 1149383
        },
        "signalY": {
            "count": 41536,
            "ratio": 0.00332288,
            "detector_count": 148184
        },
        "signalZ": {
            "count": 11345122,
            "ratio": 0.90760976,
            "detector_count": 27564486
        },
        "signalZ1": {
            "count": 3169848,
            "ratio": 0.25358784,
            "detector_count": 19791169
        },
        "signalZ0": {
            "count": 8175274,
            "ratio": 0.65402192,
            "detector_count": 7773317
        }
    },
    "signalZ1": {
        "signal0": {
            "count": 2046,
            "ratio": 0.00016368,
            "detector_count": 7042
        },
        "signalX": {
            "count": 143926,
            "ratio": 0.01151408,
            "detector_count": 670848
        },
        "signalY": {
            "count": 11852,
            "ratio": 0.00094816,
            "detector_count": 70768
        },
        "signalZ": {
            "count": 3166644,
            "ratio": 0.25333152,
            "detector_count": 15404109
        },
        "signalZ1": {
            "count": 884709,
            "ratio": 0.07077672,
            "detector_count": 7673386
        },
        "signalZ0": {
            "count": 2281935,
            "ratio": 0.1825548,
            "detector_count": 7730723
        }
    },
    "signalZ0": {
        "signal0": {
            "count": 5222,
            "ratio": 0.00041776,
            "detector_count": 46
        },
        "signalX": {
            "count": 370648,
            "ratio": 0.02965184,
            "detector_count": 478535
        },
        "signalY": {
            "count": 29684,
            "ratio": 0.00237472,
            "detector_count": 77416
        },
        "signalZ": {
            "count": 8178478,
            "ratio": 0.65427824,
            "detector_count": 12160377
        },
        "signalZ1": {
            "count": 2285139,
            "ratio": 0.18281112,
            "detector_count": 12117783
        },
        "signalZ0": {
            "count": 5893339,
            "ratio": 0.47146712,
            "detector_count": 42594
        }
    }
}
    '''

  import json

  counts = json.loads(result)

  basis = ['signalZ0', 'signalZ1', 'signal0', 'signalX', 'signalY']

  # 0 - 4 X基真空光源、X基弱源、X基强光、Z基发射、Z基真空概率
  results = [sum([counts[b1][b2]['ratio'] for b2 in basis]) for b1 in ['signal0', 'signalX', 'signalY', 'signalZ1', 'signalZ0']]

  results += [
      # 5 - 7
      0.1055,  # X基弱源强度
      0.2630,  # X基强光强度
      0.5000,  # Z基相关态光源强度

      # 8
      1.125e11,  # 发送总脉冲数
  ]

  # 9 - 33 实际发送组合比例
  # 34 - 58 实际引起有效响应个数
  for key in ['ratio', 'detector_count']:
    for b1 in basis:
      for b2 in basis:
        results.append(counts[b1][b2][key])

  results += [
      # 59 - 60
      0.1291,  # 筛选比例
      58,  # X基1错误计数
  ]

  kr = libInf.keyrate((c_double * len(results))(*results))
#   import math
#   print(kr, math.fabs(kr - 4.5329513128066943e-07) < 1e-8)

  k = KeyRate()
  k.calculate(results, strict=False)
  k.calculate(results, strict=True)

  k.calculate(results, strict=False, scale=1e10)
  k.calculate(results, strict=True, scale=1e10)