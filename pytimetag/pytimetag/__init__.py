__license__ = "GNU General Public License v3"
__author__ = 'Hwaipy'
__email__ = 'hwaipy@gmail.com'

from pytimetag.datablock import DataBlock, DataBlockSerializer
from pytimetag.Analyser import Analyser, Validator
from pytimetag.analysers.CounterAnalyser import CounterAnalyser, FastCounterAnalyser
from pytimetag.analysers.HistogramAnalyser import HistogramAnalyser
from pytimetag.analysers.EncodingAnalyser import EncodingAnalyser
# from pytimetag.Parallels import Parallels

# import platform, asyncio
# if (platform.platform().startswith('Windows')):
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
