import numpy as np

class RandomNumberSource:
    def generateRandomNumberPairs(self, pAs, pBs, length, seed):
        pAs = np.array(pAs)
        pBs = np.array(pBs)
        assert pAs.size == pBs.size
        pAs = pAs / np.sum(pAs)
        pBs = pBs / np.sum(pBs)

        meshP = np.meshgrid(pAs, pBs)
        pPairs = (meshP[0] * meshP[1]).flatten()
        nPairs = pPairs * length

        l = [i for i in nPairs]
        l.sort()
        print(l)

        f = lambda x: np.sum((nPairs + x).astype(int)) - length
        lower, upper, x = 0, 1, 0.5
        while True:
            v = f(x)
            # print(lower, upper, x, v)
            if v == 0: break
            if v > 0:
                upper = x
            else:
                lower = x
            previousX = x
            x = (lower + upper) / 2
            if previousX == x:
                raise RuntimeError('Searching Failed!')
        niPairs = (nPairs + x).astype(int)

        # meshRNK = np.meshgrid(np.linspace(0, pAs.size - 1, pAs.size), np.linspace(0, pBs.size - 1, pBs.size))
        # RNKs = np.vstack((meshRNK[0].flatten(), meshRNK[1].flatten(), niPairs)).transpose()
        #
        # rns = np.vstack([np.repeat(np.array([rnk[:2]]), rnk[2], axis=0) for rnk in RNKs])
        # rns = rns[:, 0] * pAs.size + rns[:, 1]
        # from random import Random
        # rand = Random(seed)
        # rand.shuffle(rns)
        # rnsA = (rns / pAs.size).astype(int)
        # rnsB = (rns % pAs.size).astype(int)
        #
        # return rnsA, rnsB

    def check(self, rndA, rndB):
        rndA = np.array(rndA)
        rndB = np.array(rndB)
        display = ''

        maxA = np.max(rndA)
        maxB = np.max(rndB)
        if np.min(rndA) != 0: raise RuntimeError('Random Number Range does not start at 0 for Alice: {}'.format(np.min(rndA)))
        if np.min(rndB) != 0: raise RuntimeError('Random Number Range does not start at 0 for Bob: {}'.format(np.min(rndB)))
        if maxA == maxB:
            display += ('Random Number Range: {}\n'.format(maxA + 1))
        else:
            raise RuntimeError('Random Number Range not matched: {} != {}'.format(maxA, maxB))

        histA = np.histogram(rndA, maxA + 1)
        histB = np.histogram(rndB, maxB + 1)
        display += ('Probabilities for Alice: {}\n'.format(histA[0] / np.sum(rndA)))
        display += ('Probabilities for Bob:   {}\n'.format(histB[0] / np.sum(rndB)))

        distribution = [[0] * (maxA + 1) for i in range(maxA + 1)]
        for i in range(len(rndA)):
            distribution[rndA[i]][rndB[i]] += 1
        unitWidth = 2 + len(str(max(np.max(np.array(distribution)), maxA + 1, 3)))
        tableWidth = (unitWidth + 1) * (maxA + 2) + 1
        title = 'DISTRIBUTION'
        hline = '+' + '-' * (tableWidth - 2) + '+\n'
        display += hline
        display += '|' + (' ' * int((tableWidth - 2 - len(title)) / 2) + title + ' ' * tableWidth)[:tableWidth - 2] + '|\n' + hline

        def unit(content):
            return ' ' * (unitWidth - 1 - len(str(content))) + str(content) + ' '

        def row(contents):
            return '|' + ' '.join([unit(c) for c in contents]) + '|\n'

        display += row(['A\B'] + [i for i in range(maxA + 1)])
        for i in range(maxA + 1):
            display += row([i] + distribution[i])
        display += hline
        return display

    def generateTFPattern(self, pA, pB, signalLength, totalLength, seed):
        rpsA = self._generateSignalProbs(pA)
        rpsB = self._generateSignalProbs(pB)
        self.generateRandomNumberPairs(rpsA, rpsB, signalLength, seed)

    def _generateSignalProbs(self, p):
        pX, pY, pZ, pZemit = p['X'], p['Y'], p['Z'], p['Zemit']
        pO = 1 - sum([pX, pY, pZ])
        assert pO >= 0
        rps = []
        for rnd in range(1 << 6):
            rDecoy = rnd & 0b11
            rPhaseLow = (rnd & 0b100) >> 2
            pDecoy = [pO, pX, pY, pZ][rDecoy]
            if rDecoy == 3:
                pPhase = pZemit if rPhaseLow == 1 else (1 - pZemit)
            else:
                pPhase = 0.5
            pPhase /= 8
            rps.append(pDecoy * pPhase)
        return rps

if __name__ == '__main__':
    rnSource = RandomNumberSource()
    rnSource.generateTFPattern({'X': 0.1102, 'Y': 0.2331, 'Z': 0.51, 'Zemit': 0.1}, {'X': 0.164, 'Y': 0.211, 'Z': 0.55, 'Zemit': 0.1233}, signalLength=9000, totalLength=10000, seed=101)
