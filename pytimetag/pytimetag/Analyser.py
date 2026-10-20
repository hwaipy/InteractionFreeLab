__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

class Analyser:
    def __init__(self):
        self.on = False
        self.configuration = {}

    def turnOn(self, paras={}):
        self.on = True
        self.configure(paras)

    def turnOff(self):
        self.on = False

    def isTurnedOn(self):
        return self.on

    def dataIncome(self, dataBlock):
        if self.on:
            result = self.analysis(dataBlock)
            result['Configuration'] = self.getConfigurations()
            return result
        else:
            return None

    def analysis(self, dataBlock):
        return {}

    def configure(self, paras):
        for key in paras.keys():
            newValue = paras[key]
            if self.configuration.__contains__(key):
                oldValue, validator = self.configuration[key]
                if validator(newValue):
                    self.configuration[key] = [newValue, validator]
                else: 
                    raise ValueError(f"Configuration {oldValue} -> {newValue} is not valid.")
            else:
                raise ValueError(f'[{key}] is not a valid configuration key.')

    def setConfiguration(self, key, defaultValue, validator):
        self.configuration[key] = [defaultValue, validator]

    def getConfigurations(self):
        configurations = {}        
        for key in self.configuration:
            configurations[key] = self.configuration[key][0]
        return configurations

    def getConfiguration(self, key):
        if self.configuration.__contains__(key):
            return self.configuration[key][0]
        else:
            raise ValueError(f'[{key}] is not a valid configuration key.')


class Validator:
    @classmethod
    def bool(clz):
        def func(value):
            return isinstance(value, bool)
        return func

    @classmethod
    def int(clz, min=None, max=None):
        def func(value):
            try:
                if int(value) != value:
                    return False
                if min and min > value: return False
                if max and max < value: return False
                return True
            except BaseException:
                return False
        return func

    @classmethod
    def float(clz, min=None, max=None):
        def func(value):
            try:
                if min and min > value: return False
                if max and max < value: return False
                return True
            except BaseException:
                return False
        return func

    @classmethod
    def intList(clz, min=None, max=None):
        def func(value):
            try:
                for v in value:
                    if int(v) != v:
                        return False
                    if min and min > v: 
                        return False
                    if max and max < v: 
                        return False
                return True
            except BaseException:
                return False
        return func
