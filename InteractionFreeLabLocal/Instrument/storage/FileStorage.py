import sys
import os
from datetime import datetime
import random

class FileStorage:
    def __init__(self, rootMap):
        self.rootMap = rootMap

    def listFiles(self, entry, path):
        return os.listdir(self.__getPath(entry, path))

    def readFile(self, entry, path):
        filePath = self.__getPath(entry, path)
        if not os.path.exists(filePath):
            raise ValueError(f'File {path} does not exist at Entry {entry}.')
        if not os.path.isfile(filePath):
            raise ValueError(f'{path} is not a valid file.')
        fileSize = os.path.getsize(filePath)
        if fileSize > 32 * 1024 * 1024:
            raise ValueError(f'{path}: file size {fileSize} exceed the limit of 32MB.')
        file = open(filePath, 'rb')
        data = file.read(fileSize)
        return data

    def writeFile(self, entry, path, data, force=False):
        print('writing', entry, path, len(data))
        filePath = self.__getPath(entry, path)
        print(filePath)
        if not force and os.path.exists(filePath):
            raise ValueError(f'File {path} already exist.')
        dir = '/'.join(filePath.split('/')[:-1])
        print(dir)
        if os.path.isfile(dir):
            raise ValueError(f'The parent path of File {path} is a File.')
        if not os.path.exists(dir):
            os.makedirs(dir)
        print('ready to write')
        file = open(filePath, 'wb')
        file.write(data)
        file.close()
        print('write done')

    def writeMassive(self, data):
        id = str(datetime.now()).replace(':', '-') + ' R' + str(random.Random().randint(100000, 999999))
        filePath = self.__getPath('MASSIVE', id)
        print(filePath)
        if os.path.exists(filePath):
            raise ValueError(f'File {path} already exist.')
        dir = '/'.join(filePath.split('/')[:-1])
        print(dir)
        if os.path.isfile(dir):
            raise ValueError(f'The parent path of File {path} is a File.')
        if not os.path.exists(dir):
            os.makedirs(dir)
        print('ready to write')
        file = open(filePath, 'wb')
        file.write(data)
        file.close()
        print('write done')
        return id

    def readMassive(self, id):
        return self.readFile('MASSIVE', id)

    def __getEntryRootPath(self, entry):
        if not self.rootMap.__contains__(entry):
            raise ValueError(f'Entry {entry} not defined.')
        return self.rootMap[entry]

    def __getPath(self, entry, path):
        return f'{self.__getEntryRootPath(entry)}/{path}'

if __name__ == '__main__':
    argv = sys.argv
    if len(argv) == 1:
        testPath = '/home/coder/test_store'
        argv.append(f'TFQKD_RAW:{testPath}')
        if not os.path.exists(testPath):
            os.mkdir(testPath)

    rootMap = dict([s.split(':') for s in argv[1:]])
    print(rootMap)
    fs = FileStorage(rootMap)
    print('fs created')

    # fs.listFiles('TFQKD_RAW', '.')
    # fs.readFile('TFQKD_RAW', '3')
    # fs.writeFile('TFQKD_RAW', '/d/f/g/ff.txt', b'fwfaewfawefafasdfasfwefawrwar23')

    from interactionfreepy import IFWorker, IFLoop
    addr = os.getenv('IFBROKER')
    addr = addr if addr else '172.16.60.200:224'
    serviceName = os.getenv('IFServiceName')
    serviceName = serviceName if serviceName else 'FileStorage'
    worker = IFWorker(endpoint=addr, serviceName=serviceName, serviceObject=fs, force=True)

    IFLoop().join()