from yaml import load, dump
import os
import re
import hashlib
import datetime
import shutil

try:
  from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
  from yaml import Loader, Dumper

serverRoot = '/Users/hwaipy/github/hwaipy/InteractionFreeLab/publish'
mappings = [
  ['/Users/hwaipy/github/hwaipy/InteractionFreeLab/InteractionFreeLabLocal/', 'Lib/Python/'],
  # ['/home/coder/project/interactionfreelab/InteractionFreeLabLocalSource/Instrument/tdc/TDCServer/target/scala-2.13/', 'Lib/Java/TDCServer/', lambda file: file.lower().endswith('.jar')],
  # ['/home/coder/project/interactionfreelab/InteractionFreeLabLocalSource/Instrument/tdc/adaptors/SwabianTDCAdaptor/target/scala-2.13/', 'Lib/Java/SwabianTDCAdaptor/', lambda file: file.lower().endswith('.jar')],
  # Map the project root so the published pytimetag/ and tests/ levels stay unchanged.
  ['/Users/hwaipy/github/hwaipy/InteractionFreeLab/pytimetag/', 'Lib/extproject/PyTimeTag/'],
]
ignores = [
  '/.idea/',
  '/.metals/',
  '/.vscode/',
  '/__pycache__/',
  '/.git/',
  # Generated analysis results, intermediate caches, and acquisition logs.
  r'/(?:results|intermediate(?:_[^/]+)?|mems_compensation_scans|smoke_output)/',
  r'(?i)\.(?:npz|npy|datablock|jsonl|log)$',
  r'/Experiment/TFQKD/clockDrift/output\.csv$',
  r'/Experiment/MDIQKD/DataProcess/DATA_FILE\.csv$',
]
version = '0.1'


class FileMapping:
  ignorePatterns = [re.compile(i) for i in ignores]

  def __init__(self, sourceFile, targetFile):
    self.sourceFile = sourceFile
    self.targetFile = targetFile
    self.ignore = self.__checkIgnore()
    if not self.ignore: self.__prepare()

  def __checkIgnore(self):
    return self.isIgnored(self.sourceFile)

  @classmethod
  def isIgnored(cls, path):
    path = path.replace('\\', '/')
    return any(p.search(path) for p in cls.ignorePatterns)

  def __prepare(self):
    f = open(self.sourceFile, 'rb')
    bs = f.read()
    f.close()
    self.hash = hashlib.sha512(bs).hexdigest()
    self.fileLength = len(bs)

  def __repr__(self):
    return 'M: {}  {}'.format(self.sourceFile, self.targetFile)


def prepareFileMappings():
  fileMappings = []
  for mapping in mappings:
    source = mapping[0]
    target = mapping[1]
    filter = (lambda file: True) if len(mapping) <= 2 else mapping[2]

    for path, dir_list, file_list in os.walk(source):
      # Do not descend into excluded data/cache directories.
      dir_list[:] = [d for d in dir_list
                     if not FileMapping.isIgnored(os.path.join(path, d) + '/')]
      targetPath = os.path.join(target, os.path.relpath(path, source))
      for file in file_list:
        sourceFile = os.path.join(path, file).replace('\\.\\', '\\').replace('\\', '/')
        targetFile = os.path.join(targetPath, file).replace('\\.\\', '\\').replace('\\', '/')
        if filter(sourceFile): fileMappings.append(FileMapping(sourceFile, targetFile))

  fileMappings = [fm for fm in fileMappings if not fm.ignore]
  return fileMappings


def prepareSourceFileStructure(fileMappings):
  mappings = []
  for fm in fileMappings:
    mappings.append({
      'url': fm.targetFile,
      'size': fm.fileLength,
      'sha512': fm.hash
    })
  date = datetime.datetime.now()
  return {
    'files': mappings,
    'releaseDate': date.isoformat(),
    'version': '{}.{}'.format(version, f'{date:%Y%m%d%H%M%S}')
  }


def loadTargetFileStructure(file):
  if not os.path.exists(file):
    return {
      'files': []
    }
  f = open(file, 'r')
  yml = f.read()
  f.close()
  return load(yml, Loader=Loader)


def differential(fileMappings, sourceFileStructure, targetFileStructure):
  def fileMap(fs):
    fs = fs['files']  
    fm = {}
    for f in fs:
      fm[f['url']] = f
    return fm

  sourceFileMap = fileMap(sourceFileStructure)
  targetFileMap = fileMap(targetFileStructure)

  actions = []

  for fileMapping in fileMappings:
    url = fileMapping.targetFile
    if (targetFileMap.__contains__(url)):
      if not (sourceFileMap[url]['sha512'] == targetFileMap[url]['sha512']):
        actions.append(['upload', fileMapping])
    else:
      actions.append(['upload', fileMapping])

  for file in targetFileMap:
    if not sourceFileMap.__contains__(file):
      actions.append(['remove', file]) 

  return actions


def performFiles(actions):
  for action in actions:
    print(action)
    if action[0] == 'upload':
      targetPath = os.path.join(serverRoot, action[1].targetFile)
      os.makedirs(os.path.dirname(targetPath), exist_ok=True)
      shutil.copy(action[1].sourceFile, targetPath)
    if action[0] == 'remove':
      os.remove(os.path.join(serverRoot, action[1]))


def performSummary(summary):
  bytes = dump(summary)
  f = open(os.path.join(serverRoot, 'summary.yml'), 'w')
  f.write(bytes)
  f.close()


if __name__ == '__main__':
  fileMappings = prepareFileMappings()
  sourceFileStructure = prepareSourceFileStructure(fileMappings)
  targetFileStructure = loadTargetFileStructure(os.path.join(serverRoot, 'summary.yml'))
  actions = differential(fileMappings, sourceFileStructure, targetFileStructure)
  performFiles(actions)
  performSummary(sourceFileStructure)
