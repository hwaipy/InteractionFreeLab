import numpy as np
import os
import pickle

def read_out(filename):
    f = open(f'{filename}.pkl', 'rb')
    r = pickle.load(f)
    f.close()
    return r

class RNManager:
    instance = None

    def __init__(self) -> None:
        folder = f'{os.path.join(os.path.dirname(os.path.dirname(__file__)), "TFQKD/RNSfile")}'
        self.aliceRN = np.array(read_out(folder + '/rnsAlice'))
        self.bobRN = np.array(read_out(folder + '/rnsBob'))
        self.matchedRandomNumbersLab = None

    @classmethod
    def getInstance(cls):
        if RNManager.instance == None: RNManager.instance = RNManager()
        return RNManager.instance


