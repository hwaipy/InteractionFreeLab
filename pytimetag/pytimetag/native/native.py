# from ctypes import cdll, c_longlong, c_int32
# import platform
# import os
# import numpy as np

# lib = cdll.LoadLibrary(f"{os.path.realpath(__file__)[:-9]}timetag.{'so' if platform.system() == 'Linux' or platform.system() == 'Darwin' else 'dll'}")


# def convertNativeList(data):
#   nl = (c_longlong * len(data))()
#   for i in range(len(data)):
#     nl[i] = data[i]
#   return nl  

# def convertNativeContent(content):
#   if content is None: return None
#   nativeContent = []
#   for c in content:
#     nativeContent.append(convertNativeList(c))
#   return nativeContent

# def convertContent(contentNative):
#   if contentNative is None: return None
#   return [list(ch) for ch in contentNative]

# def convertNumpyContent(timestamps, channels):
#   assert isinstance(timestamps, np.ndarray)
#   assert timestamps.dtype == 'int64'
#   assert isinstance(channels, np.ndarray)
#   assert channels.dtype == 'int32'

#   print(timestamps[0], timestamps[100], timestamps[9999999])
#   print(channels[0], channels[100], channels[9999999])

#   lib.convertNumpyContent(
#     (c_longlong * timestamps.shape[0]).from_address(addressof(timestamps)), timestamps.shape[0], 
#     (c_longlong * channels.shape[0]).from_address(addressof(channels)), channels.shape[0]
#   )

# def serializeNative(data, begin, end):
#   buffer = bytes((end - begin) * 8)
#   size = lib.serializeDataBlock(addressof(data), begin, end, buffer)
#   return buffer[:size]


# def deserializeNative(data):
#   if isinstance(data, bytes):
#     data = [data]
#   resultSet = []
#   for section in data:
#     buffer = (c_longlong * int(len(section) / 2))()
#     resultSize = lib.deserializeDataBlock(section, len(section), buffer)
#     resultSet.append([buffer, resultSize])
#   result = (c_longlong * sum(r[1] for r in resultSet))()
#   totalDataSize = 0
#   for r in resultSet:
#     lib.mergeDataSection(result, totalDataSize, r[0], 0, r[1] * 8)
#     totalDataSize += r[1]
#   return result

# def histogram(triggerList, signalList, binCount, divide, viewFrom, viewTo):
#   result = (c_int32 * binCount)()
#   lib.histogram(addressof(triggerList), len(triggerList), addressof(signalList), len(signalList), binCount, divide, c_longlong(viewFrom), c_longlong(viewTo), result)
#   return list(result)

# def addressof(array):
#   return array.__array_interface__['data'][0]