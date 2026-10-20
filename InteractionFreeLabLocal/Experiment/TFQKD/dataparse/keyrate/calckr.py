from keyrate_server import calKeyRate
import json
data = '''{
    "all": {
        "ref": {
            "count": 7000000,
            "ratio": 0.35,
            "detector_count": 3839905113
        },
        "signal": {
            "count": 12750000,
            "ratio": 0.6375,
            "detector_count": 105205678
        }
    },
    "signal": {
        "signal": {
            "count": 45900000000,
            "ratio": 1.0,
            "detector_count": 105205678
        },
        "signal0": {
            "count": 28137600,
            "ratio": 0.0006130196078431373,
            "detector_count": 33849
        },
        "signalX": {
            "count": 1983567600,
            "ratio": 0.04321498039215686,
            "detector_count": 4073520
        },
        "signalY": {
            "count": 160282800,
            "ratio": 0.003492,
            "detector_count": 466608
        },
        "signalZ": {
            "count": 43728012000,
            "ratio": 0.95268,
            "detector_count": 100631701
        },
        "signalZ1": {
            "count": 12212978400,
            "ratio": 0.2660779607843137,
            "detector_count": 63105432
        },
        "signalZ0": {
            "count": 31515033600,
            "ratio": 0.6866020392156863,
            "detector_count": 37526269
        }
    },
    "signal0": {
        "signal": {
            "count": 28137600,
            "ratio": 0.0006130196078431373,
            "detector_count": 31593
        },
        "signal0": {
            "count": 25200,
            "ratio": 5.490196078431373e-07,
            "detector_count": 0
        },
        "signalX": {
            "count": 1339200,
            "ratio": 2.9176470588235294e-05,
            "detector_count": 1203
        },
        "signalY": {
            "count": 86400,
            "ratio": 1.8823529411764707e-06,
            "detector_count": 149
        },
        "signalZ": {
            "count": 26686800,
            "ratio": 0.0005814117647058824,
            "detector_count": 30241
        },
        "signalZ1": {
            "count": 7538400,
            "ratio": 0.00016423529411764706,
            "detector_count": 30022
        },
        "signalZ0": {
            "count": 19148400,
            "ratio": 0.00041717647058823527,
            "detector_count": 219
        }
    },
    "signalX": {
        "signal": {
            "count": 1983567600,
            "ratio": 0.04321498039215686,
            "detector_count": 4092018
        },
        "signal0": {
            "count": 1288800,
            "ratio": 2.807843137254902e-05,
            "detector_count": 1249
        },
        "signalX": {
            "count": 84945600,
            "ratio": 0.0018506666666666667,
            "detector_count": 154625
        },
        "signalY": {
            "count": 7063200,
            "ratio": 0.00015388235294117646,
            "detector_count": 18619
        },
        "signalZ": {
            "count": 1890270000,
            "ratio": 0.04118235294117647,
            "detector_count": 3917525
        },
        "signalZ1": {
            "count": 528570000,
            "ratio": 0.011515686274509804,
            "detector_count": 2610094
        },
        "signalZ0": {
            "count": 1361700000,
            "ratio": 0.029666666666666668,
            "detector_count": 1307431
        }
    },
    "signalY": {
        "signal": {
            "count": 160282800,
            "ratio": 0.003492,
            "detector_count": 598904
        },
        "signal0": {
            "count": 104400,
            "ratio": 2.2745098039215685e-06,
            "detector_count": 288
        },
        "signalX": {
            "count": 7027200,
            "ratio": 0.00015309803921568628,
            "detector_count": 24653
        },
        "signalY": {
            "count": 543600,
            "ratio": 1.1843137254901961e-05,
            "detector_count": 2420
        },
        "signalZ": {
            "count": 152607600,
            "ratio": 0.0033247843137254904,
            "detector_count": 571543
        },
        "signalZ1": {
            "count": 42249600,
            "ratio": 0.0009204705882352941,
            "detector_count": 279642
        },
        "signalZ0": {
            "count": 110358000,
            "ratio": 0.002404313725490196,
            "detector_count": 291901
        }
    },
    "signalZ": {
        "signal": {
            "count": 43728012000,
            "ratio": 0.95268,
            "detector_count": 100483163
        },
        "signal0": {
            "count": 26719200,
            "ratio": 0.0005821176470588236,
            "detector_count": 32312
        },
        "signalX": {
            "count": 1890255600,
            "ratio": 0.04118203921568627,
            "detector_count": 3893039
        },
        "signalY": {
            "count": 152589600,
            "ratio": 0.0033243921568627452,
            "detector_count": 445420
        },
        "signalZ": {
            "count": 41658447600,
            "ratio": 0.9075914509803922,
            "detector_count": 96112392
        },
        "signalZ1": {
            "count": 11634620400,
            "ratio": 0.25347756862745097,
            "detector_count": 60185674
        },
        "signalZ0": {
            "count": 30023827200,
            "ratio": 0.6541138823529412,
            "detector_count": 35926718
        }
    },
    "signalZ1": {
        "signal": {
            "count": 12213572400,
            "ratio": 0.26609090196078433,
            "detector_count": 65390814
        },
        "signal0": {
            "count": 7466400,
            "ratio": 0.00016266666666666667,
            "detector_count": 32116
        },
        "signalX": {
            "count": 530715600,
            "ratio": 0.01156243137254902,
            "detector_count": 2712350
        },
        "signalY": {
            "count": 42508800,
            "ratio": 0.0009261176470588236,
            "detector_count": 253619
        },
        "signalZ": {
            "count": 11632881600,
            "ratio": 0.2534396862745098,
            "detector_count": 62392729
        },
        "signalZ1": {
            "count": 3245072400,
            "ratio": 0.07069874509803921,
            "detector_count": 26707344
        },
        "signalZ0": {
            "count": 8387809200,
            "ratio": 0.18274094117647058,
            "detector_count": 35685385
        }
    },
    "signalZ0": {
        "signal": {
            "count": 31514439600,
            "ratio": 0.6865890980392156,
            "detector_count": 35092349
        },
        "signal0": {
            "count": 19252800,
            "ratio": 0.00041945098039215687,
            "detector_count": 196
        },
        "signalX": {
            "count": 1359540000,
            "ratio": 0.029619607843137254,
            "detector_count": 1180689
        },
        "signalY": {
            "count": 110080800,
            "ratio": 0.0023982745098039215,
            "detector_count": 191801
        },
        "signalZ": {
            "count": 30025566000,
            "ratio": 0.6541517647058823,
            "detector_count": 33719663
        },
        "signalZ1": {
            "count": 8389548000,
            "ratio": 0.18277882352941177,
            "detector_count": 33478330
        },
        "signalZ0": {
            "count": 21636018000,
            "ratio": 0.4713729411764706,
            "detector_count": 241333
        }
    },
    "Sifted Key": {
        "XX": {
            "correct": 18918,
            "incorrect": 554,
            "count": 19472
        },
        "YY": {
            "correct": 297,
            "incorrect": 12,
            "count": 309
        },
        "Z1Z1": {
            "correct": 3252943,
            "incorrect": 84412,
            "count": 3337355
        }
    }
}'''

counts = json.loads(data)
for keyA in counts:
    if keyA.startswith('signal'):
        map = counts[keyA]
        for keyB in map:
            print(map[keyB].keys())
            map[keyB]['count'] *= 5


# print(counts)

kr = calKeyRate(counts, num_photons=[0.1, 0.264779, 0.499962], phaseSeletcedRatio=1 / 8, strict=False, scale=1e10)
print(kr)
kr = calKeyRate(counts, num_photons=[0.1, 0.264779, 0.499962], phaseSeletcedRatio=1 / 8, strict=False, scale=1)
print(kr)
kr = calKeyRate(counts, num_photons=[0.1, 0.264779, 0.499962], phaseSeletcedRatio=1 / 8, strict=True, scale=1)
print(kr)
