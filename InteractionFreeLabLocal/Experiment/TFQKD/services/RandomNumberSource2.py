import numpy as np


class RandomNumberSource:
    def generateTFPatterns(self, pA, pB, signalLength, totalLength, seed):
        rpsA = self._generateSignalProbs(pA)
        rpsB = self._generateSignalProbs(pB)
        assert abs(sum(list(rpsA.values())) - 1) < 1e-012
        assert abs(sum(list(rpsB.values())) - 1) < 1e-012
        self.generateRandomNumberPairs(rpsA, rpsB, signalLength, seed)

    def generateRandomNumberPairs(self, pAs, pBs, length, seed):
        pARNs = list(pAs.keys())
        pBRNs = list(pBs.keys())

        print(pARNs)
        print(pBRNs)

        meshP = np.meshgrid(pARNs, pBRNs)
        rnPairs = np.vstack((meshP[0].flatten(), meshP[1].flatten())).transpose()
        pPairs = np.array([pAs[rnPair[0]] * pBs[rnPair[1]] for rnPair in rnPairs])
        nPairs = pPairs * length

        l = [i for i in nPairs]
        l.sort()
        print(l)

        # def __fSum(x, )
    #         f = lambda x: np.sum((nPairs + x).astype(int)) - length
    #         lower, upper, x = 0, 1, 0.5
    #         while True:
    #             v = f(x)
    #             # print(lower, upper, x, v)
    #             if v == 0: break
    #             if v > 0:
    #                 upper = x
    #             else:
    #                 lower = x
    #             previousX = x
    #             x = (lower + upper) / 2
    #             if previousX == x:
    #                 raise RuntimeError('Searching Failed!')
    #         niPairs = (nPairs + x).astype(int)
    #
    #         # meshRNK = np.meshgrid(np.linspace(0, pAs.size - 1, pAs.size), np.linspace(0, pBs.size - 1, pBs.size))
    #         # RNKs = np.vstack((meshRNK[0].flatten(), meshRNK[1].flatten(), niPairs)).transpose()
    #         #
    #         # rns = np.vstack([np.repeat(np.array([rnk[:2]]), rnk[2], axis=0) for rnk in RNKs])
    #         # rns = rns[:, 0] * pAs.size + rns[:, 1]
    #         # from random import Random
    #         # rand = Random(seed)
    #         # rand.shuffle(rns)
    #         # rnsA = (rns / pAs.size).astype(int)
    #         # rnsB = (rns % pAs.size).astype(int)
    #         #
    #         # return rnsA, rnsB
    #
    #     def check(self, rndA, rndB):
    #         rndA = np.array(rndA)
    #         rndB = np.array(rndB)
    #         display = ''
    #
    #         maxA = np.max(rndA)
    #         maxB = np.max(rndB)
    #         if np.min(rndA) != 0: raise RuntimeError('Random Number Range does not start at 0 for Alice: {}'.format(np.min(rndA)))
    #         if np.min(rndB) != 0: raise RuntimeError('Random Number Range does not start at 0 for Bob: {}'.format(np.min(rndB)))
    #         if maxA == maxB:
    #             display += ('Random Number Range: {}\n'.format(maxA + 1))
    #         else:
    #             raise RuntimeError('Random Number Range not matched: {} != {}'.format(maxA, maxB))
    #
    #         histA = np.histogram(rndA, maxA + 1)
    #         histB = np.histogram(rndB, maxB + 1)
    #         display += ('Probabilities for Alice: {}\n'.format(histA[0] / np.sum(rndA)))
    #         display += ('Probabilities for Bob:   {}\n'.format(histB[0] / np.sum(rndB)))
    #
    #         distribution = [[0] * (maxA + 1) for i in range(maxA + 1)]
    #         for i in range(len(rndA)):
    #             distribution[rndA[i]][rndB[i]] += 1
    #         unitWidth = 2 + len(str(max(np.max(np.array(distribution)), maxA + 1, 3)))
    #         tableWidth = (unitWidth + 1) * (maxA + 2) + 1
    #         title = 'DISTRIBUTION'
    #         hline = '+' + '-' * (tableWidth - 2) + '+\n'
    #         display += hline
    #         display += '|' + (' ' * int((tableWidth - 2 - len(title)) / 2) + title + ' ' * tableWidth)[:tableWidth - 2] + '|\n' + hline
    #
    #         def unit(content):
    #             return ' ' * (unitWidth - 1 - len(str(content))) + str(content) + ' '
    #
    #         def row(contents):
    #             return '|' + ' '.join([unit(c) for c in contents]) + '|\n'
    #
    #         display += row(['A\B'] + [i for i in range(maxA + 1)])
    #         for i in range(maxA + 1):
    #             display += row([i] + distribution[i])
    #         display += hline
    #         return display

    def _generateSignalProbs(self, p):
        p['O'] = 1 - sum([p['X'], p['Y'], p['Z']])
        assert p['O'] >= 0
        rps = {}
        for decoy in RandomNumber.AVAILABLE_DECOY:
            for phase in RandomNumber.AVAILABLE_PHASE:
                for zEmit in ([True, False] if decoy == 'Z' else [False]):
                    pDecoy = p[decoy]
                    # for decoyO or Z0, phase = 0, pi
                    if decoy == 'O' or (decoy == 'Z' and not zEmit):
                        pPhase = 1 / 2 if (phase == 0 or phase == int(len(RandomNumber.AVAILABLE_PHASE) / 2)) else 0
                    else:
                        pPhase = 1 / len(RandomNumber.AVAILABLE_PHASE)
                    # for decoyZ only
                    if decoy == 'Z':
                        pZEmit = p['ZEmit'] if zEmit else 1 - p['ZEmit']
                    else:
                        pZEmit = 1
                    prob = pDecoy * pPhase * pZEmit
                    if prob > 0: rps[RandomNumber(decoy, phase, zEmit, False, False)] = prob
        return rps


class RandomNumber:
    AVAILABLE_DECOY = ['O', 'X', 'Y', 'Z']
    AVAILABLE_PHASE = [i for i in range(16)]
    ALL_RANDOMNUMBERS = []

    def __init__(self, decoy, phase, zEmit, reference, extendedVacuum):
        assert RandomNumber.AVAILABLE_DECOY.__contains__(decoy)
        assert RandomNumber.AVAILABLE_PHASE.__contains__(phase)
        assert isinstance(zEmit, bool)
        assert isinstance(extendedVacuum, bool)
        assert isinstance(reference, bool)
        assert decoy == 'Z' or zEmit == False
        self.__decoy = decoy
        self.__extendedVacuum = extendedVacuum
        self.__zEmit = zEmit
        self.__phase = phase
        self.__reference = reference

    def getDecoy(self):
        return self.__decoy

    def getPhase(self):
        return self.__phase

    def isExtendedVacuum(self):
        return self.__extendedVacuum

    def isReference(self):
        return self.__reference

    def isSignal(self):
        return not self.__reference

    def isDecoyVacuum(self):
        return self.__decoy == 'O'

    def isDecoyX(self):
        return self.__decoy == 'X'

    def isDecoyY(self):
        return self.__decoy == 'Y'

    def isDecoyZ(self):
        return self.__decoy == 'Z'

    def isZEmit(self):
        return self.__zEmit

    def __str__(self):
        return 'RN_{}_P{}_{}'.format(self.__decoy if self.__decoy != 'Z' else ('Z1' if self.__zEmit else 'Z0'), self.__phase, 'Signal' if not self.__reference else ('Ref' if not self.__extendedVacuum else 'RefTail'))

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, RandomNumber): return False
        return self.__decoy == other.__decoy and self.__phase == other.__phase and self.__zEmit == other.__zEmit and self.__reference == other.__reference and self.__extendedVacuum == other.__extendedVacuum

    def __hash__(self):
        return hash(self.__str__())


for decoy in RandomNumber.AVAILABLE_DECOY:
    for phase in RandomNumber.AVAILABLE_PHASE:
        for reference in [True, False]:
            for extendedVacuum in [True, False]:
                for zEmit in [True, False]:
                    if decoy == 'Z' or zEmit == False:
                        RandomNumber.ALL_RANDOMNUMBERS.append(RandomNumber(decoy, phase, zEmit, reference, extendedVacuum))

if __name__ == '__main__':
    rnSource = RandomNumberSource()
    rnSource.generateTFPatterns({'X': 0.03857, 'Y': 0.003239, 'Z': 0.957827, 'ZEmit': 0.720367}, {'X': 0.03357, 'Y': 0.003039, 'Z': 0.962827, 'ZEmit': 0.750367}, signalLength=2000, totalLength=10000, seed=101)
    #
    # for i in range(len(RandomNumber.ALL_RANDOMNUMBERS)):
    #     print(i, RandomNumber.ALL_RANDOMNUMBERS[i])
