__author__ = 'Hwaipy'

import unittest
from pytimetag import DataBlock, DataBlockSerializer, Validator, CounterAnalyser, HistogramAnalyser, EncodingAnalyser, FastCounterAnalyser
from random import Random
import numpy as np
import msgpack


class DataBlockTest(unittest.TestCase):
  rnd = Random()

  @classmethod
  def setUpClass(cls):
    pass

  def setUp(self):
    pass

  def testValidators(self):
    self.assertTrue(Validator.int(0, 10)(9))
    self.assertTrue(Validator.int(0, 10)(0))
    self.assertTrue(Validator.int(0, 10)(10))
    self.assertFalse(Validator.int(0, 10)(11))
    self.assertTrue(Validator.int(-100, 100)(11))
    self.assertFalse(Validator.int(-100, 100)(-111))
    self.assertFalse(Validator.int(-100, 100)(-1.11))
    self.assertFalse(Validator.int(-100, 100)({}))
    self.assertFalse(Validator.float(0, 10.0)({}))
    self.assertTrue(Validator.float(0, 10.0)(1))
    self.assertFalse(Validator.float(0, 10.0)(11))
    self.assertFalse(Validator.float(0, 10.0)(11.1))
    self.assertTrue(Validator.float(0, 10.0)(1.1))
    self.assertFalse(Validator.float(-90, 10.0)(-91))
    self.assertTrue(Validator.float(-90, 10.0)(-90))

  def testCounterAnalyser(self):
    offset = 50400000000010
    dataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': offset, 'DataTimeEnd': (offset + 1000000000000)},
        {0: ['Period', 10000], 5: ['Pulse', 100000000, 200000, 1000]}
    )
    mha = CounterAnalyser()
    mha.turnOn()
    result = mha.dataIncome(dataBlock)
    self.assertEqual(result['Configuration'], {})
    self.assertEqual(result['0'], 10000)
    self.assertEqual(result['1'], 0)
    self.assertEqual(result['2'], 0)
    self.assertEqual(result['3'], 0)
    self.assertEqual(result['4'], 0)
    self.assertEqual(result['5'], 200000)
    self.assertEqual(result['6'], 0)
    self.assertEqual(result['7'], 0)
    self.assertEqual(result['8'], 0)
    self.assertEqual(result['9'], 0)
    self.assertEqual(result['10'], 0)
    mha.turnOff()
    result2 = mha.dataIncome(dataBlock)
    self.assertIsNone(result2)

  def testHistogramAnalyser(self):
    offset = 50400000000010
    dataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': offset, 'DataTimeEnd': (offset + 1000000000000)},
        {0: ['Period', 10000], 1: ['Pulse', 100000000, 200000, 1000], 2: ['Period', 10000000]}
    )
    mha = HistogramAnalyser(16)
    mha.turnOn({"Sync": 0, "Signals": [1, 2], "ViewStart": -1000000, "ViewStop": 1000000, "BinCount": 100, "Divide": 100})
    result = mha.dataIncome(dataBlock)
    self.assertEqual(result.get("Configuration")["Sync"], 0)
    self.assertEqual(result.get("Configuration")["Signals"], [1, 2])
    self.assertEqual(result.get("Configuration")["ViewStart"], -1000000)
    self.assertEqual(result.get("Configuration")["ViewStop"], 1000000)
    self.assertEqual(result.get("Configuration")["BinCount"], 100)
    self.assertEqual(result.get("Configuration")["Divide"], 100)
    histos = result['Histograms']
    self.assertEqual(len(histos), 2)
    histo1 = histos[0]
    self.assertEqual(len(histo1), 100)
    self.assertTrue(histo1[0] > 0.5 * max(histo1) and histo1[0] < 1.5 * max(histo1))
    self.assertTrue(histo1[-1] > 0.5 * max(histo1) and histo1[-1] < 1.5 * max(histo1))
    self.assertTrue(histo1[int(len(histo1) / 2)] > 0.6 * max(histo1) and histo1[int(len(histo1) / 2)] < 1.5 * max(histo1))
    self.assertTrue(histo1[int(len(histo1) / 4)] < 0.05 * max(histo1) and histo1[int(len(histo1) / 4 * 3)] < 0.05 * max(histo1))

    mha.turnOn({"Sync": 0, "Signals": [1, 2], "ViewStart": -1000000, "ViewStop": 1000000, "BinCount": 100, "Divide": 1})
    result = mha.dataIncome(dataBlock)
    histos = result['Histograms']
    self.assertEqual(list(histos[1]), [9999, 0, 0, 0, 0] * 10 + [10000, 0, 0, 0, 0] * 9 + [10000, 0, 0, 0, 10000])

    mha.turnOn({"ViewStart": 0, "ViewStop": 1000000000000})
    result = mha.dataIncome(dataBlock)
    histos = result['Histograms']
    self.assertTrue(np.all(np.array(histos[0]) == -1))
    self.assertTrue(np.all(np.array(histos[1]) == -1))
    self.assertTrue(np.all(np.array(msgpack.unpackb(msgpack.packb(histos))) == np.array(histos)))

    mha.turnOff()
    result2 = mha.dataIncome(dataBlock)
    self.assertIsNone(result2)

  def testEncodingAnalyser(self):
    offset = 50400000000010
    dataBlock1 = DataBlock.generate(
      {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
      {0: ['Period', 10000], 1: ['Pulse', 100000000, 2300000, 10]}
    ).synced([0, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    mha = EncodingAnalyser(16, 128)
    configHistograms = {'G1': [1, 3, 5], 'G2': [10, 12, 14], 'G1+G2': [1, 3, 5, 10, 12, 14], "G1'": [3, 4, 5], "G1+G1'": [1, 3, 4, 5]}
    mha.turnOn({
      "Period": 10000,
      "TriggerChannel": 0,
      "SignalChannel": 1,
      "RandomNumbers": [i for i in range(128)],
      "Histograms": configHistograms
    })

    result1 = mha.dataIncome(dataBlock1)
    for key in configHistograms:
      self.assertEqual(result1[f'PulseCount[{key}]'], len(configHistograms[key]))
      histogram = np.array(result1.get(f'Histogram[{key}]'))
      self.assertTrue(np.abs(np.where(histogram == np.max(histogram))[0][0] - 50) < 5)
      self.assertTrue(np.where(histogram > 0)[0].shape[0] < 15)
      self.assertTrue(np.all(histogram[:42] == 0))
      self.assertTrue(np.all(histogram[57:] == 0))

    histogram1G1 = np.array(result1['Histogram[G1]'])
    histogram1G2 = np.array(result1['Histogram[G2]'])
    histogram1G1G2 = np.array(result1['Histogram[G1+G2]'])
    histogram1G1G2Exp = histogram1G1 + histogram1G2
    self.assertTrue(np.all(histogram1G1G2Exp == histogram1G1G2))

    dataBlock2 = DataBlock.generate(
      {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
      {0: ['Period', 10000], 1: ['Pulse', 50000000, 2300000, 100]}
    ).synced([0, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    result2 = mha.dataIncome(dataBlock2)
    for key in configHistograms:
      self.assertEqual(result2[f'PulseCount[{key}]'], len(configHistograms[key]))
    histogram2G1 = result2['Histogram[G1]']
    self.assertEqual(np.max(histogram2G1), 0)
    histogram2G2 = np.array(result2['Histogram[G2]'])
    self.assertTrue(np.abs(np.where(histogram2G2 == np.max(histogram2G2))[0][0] - 50) < 5)
    self.assertTrue(np.where(histogram2G2 > 0)[0].shape[0] < 15)
    self.assertTrue(np.all(histogram2G2[:42] == 0))
    self.assertTrue(np.all(histogram2G2[57:] == 0))
    histogram2G1G2 = result2['Histogram[G1+G2]']
    histogram2G1G2Exp = histogram2G1 + histogram2G2
    self.assertTrue(np.all(histogram2G1G2Exp == histogram2G1G2))

    dataBlock3 = DataBlock.generate(
      {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
      {0: ['Period', 1], 1: ['Pulse', 50000000, 2300000, 100]}
    ).synced([0, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    result3 = mha.dataIncome(dataBlock3)
    for key in configHistograms:
      self.assertTrue(np.all(np.array(result3[f'Histogram[{key}]']) == 0))

  def testFastCounterAnalyser(self):
    offset = 50400000000010
    dataBlock = DataBlock.generate(
      {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
      {0: ['Period', 10000], 1: ['Period', 200000], 5: ['Random', 105888], 10: ['Period', 10], 12: ['Random', 2]}
    )
    mha = FastCounterAnalyser()
    mha.turnOn({'Channels': [0, 1, 5, 10], 'Frequency': 1000})
    result = mha.dataIncome(dataBlock)
    countSections = result['CountSections']
    self.assertTrue(np.all(np.array(countSections['0']) == 10))
    self.assertTrue(np.all(np.array(countSections['1']) == 200))
    self.assertTrue(np.all(np.array(countSections['10']) == np.array(([1] + [0] * 99) * 10)))


  def tearDown(self):
    pass

  @classmethod
  def tearDownClass(cls):
    pass


if __name__ == '__main__':
  unittest.main()

#   test("Test ExceptionMonitorAnalyser.") {
#     val offset = 50400000000010L
#     val dataBlock = DataBlock.generate(
#       Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
#       Map(
#         0 -> List("Period", 10000),
#         1 -> List("Period", 230000),
#         5 -> List("Random", 105888),
#         10 -> List("Period", 10),
#         12 -> List("Random", 1)
#       )
#     )
#     dataBlock.content.foreach(content => content.zipWithIndex.foreach(z => content(z._2) = z._1.sorted))
#     val mha = new ExceptionMonitorAnalyser(16)
#     mha.turnOn(Map("SyncChannels" -> List(0, 1, 5, 10)))
#     val result = mha.dataIncome(dataBlock)
#     assert(result.isDefined)
#     assert(result.get("ReverseCounts").asInstanceOf[Array[Int]].toList == List(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
#     val syncMonitor = result.get("SyncMonitor").asInstanceOf[Map[String, Map[String, Any]]]
#     assert(syncMonitor("0")("Average") == 1e8)
#     assert(syncMonitor("0")("Max") == 1e8)
#     assert(syncMonitor("0")("Min") == 1e8)
#     assert(syncMonitor("1")("Average") == 4347826.086952552)
#     assert(syncMonitor("1")("Max") == 4347827)
#     assert(syncMonitor("1")("Min") == 4347826)
#     assert(syncMonitor("10")("Average") == 1e11)
#     assert(syncMonitor("10")("Max") == 1e11)
#     assert(syncMonitor("10")("Min") == 1e11)
#     List(5, 10, 100, 1100, 1101, 20230, 33323).foreach(i => dataBlock.content.get(1)(i) = 10)
#     val result2 = mha.dataIncome(dataBlock)
#     assert(result2.get("ReverseCounts").asInstanceOf[Array[Int]].toList == List(0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
#   }

#   test("Test EncodingAnalyser.") {
#     val offset = 50400000000010L
#     val dataBlock1 = DataBlock
#       .generate(
#         Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
#         Map(
#           0 -> List("Period", 10000),
#           1 -> List("Pulse", 100000000, 2300000, 100)
#         )
#       )
#       .synced(List(0, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
#     val mha = new EncodingAnalyser(16, 128)
#     val configHistograms = Map("G1" -> List[Int](1, 3, 5), "G2" -> List[Int](10, 12, 14), "G1+G2" -> List[Int](1, 3, 5, 10, 12, 14), "G1'" -> List[Int](3, 4, 5), "G1+G1'" -> List[Int](1, 3, 4, 5))
#     mha.turnOn(
#       Map(
#         "Period" -> 10000,
#         "TriggerChannel" -> 0,
#         "SignalChannel" -> 1,
#         "RandomNumbers" -> Range(0, 128).toList,
#         "Histograms" -> configHistograms
#       )
#     )
#     val result1 = mha.dataIncome(dataBlock1)
#     assert(result1.isDefined)
#     configHistograms.foreach(entry => {
#       assert(result1.get(s"PulseCount[${entry._1}]") == entry._2.size)
#       val histogram = result1.get(s"Histogram[${entry._1}]").asInstanceOf[List[Int]]
#       assert(Math.abs(histogram.indexOf(histogram.max) - 50) < 5)
#       assert(histogram.filter(_ > 0).size < 15)
#       assert(histogram.slice(0, 42).max == 0)
#       assert(histogram.slice(57, 100).max == 0)
#     })
#     val histogram1G1 = result1.get(s"Histogram[G1]").asInstanceOf[List[Int]]
#     val histogram1G2 = result1.get(s"Histogram[G2]").asInstanceOf[List[Int]]
#     val histogram1G1G2 = result1.get(s"Histogram[G1+G2]").asInstanceOf[List[Int]]
#     val histogram1G1G2Exp = (histogram1G1 zip histogram1G2).map(z => z._1 + z._2)
#     (histogram1G1G2Exp zip histogram1G1G2).foreach(z => assert(z._1 == z._2))

#     val dataBlock2 = DataBlock
#       .generate(
#         Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
#         Map(
#           0 -> List("Period", 10000),
#           1 -> List("Pulse", 50000000, 2300000, 100)
#         )
#       )
#       .synced(List(0, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
#     val result2 = mha.dataIncome(dataBlock2)
#     assert(result2.isDefined)
#     configHistograms.foreach(entry => assert(result2.get(s"PulseCount[${entry._1}]") == entry._2.size))
#     val histogram2G1 = result2.get(s"Histogram[G1]").asInstanceOf[List[Int]]
#     assert(histogram2G1.max == 0)
#     val histogram2G2 = result2.get(s"Histogram[G2]").asInstanceOf[List[Int]]
#     assert(Math.abs(histogram2G2.indexOf(histogram2G2.max) - 50) < 5)
#     assert(histogram2G2.filter(_ > 0).size < 15)
#     assert(histogram2G2.slice(0, 42).max == 0)
#     assert(histogram2G2.slice(57, 100).max == 0)
#     val histogram2G1G2 = result2.get(s"Histogram[G1+G2]").asInstanceOf[List[Int]]
#     val histogram2G1G2Exp = (histogram2G1 zip histogram2G2).map(z => z._1 + z._2)
#     (histogram2G1G2Exp zip histogram2G1G2).foreach(z => assert(z._1 == z._2))
#   }

#   test("Test ChannelMonitorAnalyser.") {
#     val offset = 50400000000010L
#     val dataBlock = DataBlock.generate(
#       Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
#       Map(
#         0 -> List("Period", 10000),
#         1 -> List("Period", 200000),
#         5 -> List("Random", 105888),
#         10 -> List("Period", 10),
#         12 -> List("Random", 2)
#       )
#     )
#     val mha = new ChannelMonitorAnalyser(16)
#     mha.turnOn(Map("SyncChannel" -> 12, "Channels" -> List(0, 1, 5, 10), "SectionCount" -> 1000))
#     val result = mha.dataIncome(dataBlock)
#     assert(result.isDefined)
#     assert(result.get("DataBlockBegin") == 10L)
#     assert(result.get("DataBlockEnd") == 1000000000010L)
#     assert(result.get("Sync").asInstanceOf[Array[Long]].toList == dataBlock.getContent(12).toList)
#     val countSections = result.get("CountSections").asInstanceOf[Map[String, Array[Int]]]
#     assert(countSections("0").toList == Range(0, 1000).toList.map(_ => 10))
#     assert(countSections("1").toList == Range(0, 1000).toList.map(_ => 200))
#   }

#   test("Test PhaseComparingAnalyser.") {
#     val offset = 50400000000010L
#     val dataBlock = DataBlock.generate(
#       Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
#       Map(
#         0 -> List("Period", 10000),
#         2 -> List("Period", 200000),
#         3 -> List("Random", 105888),
#         10 -> List("Period", 10),
#         12 -> List("Random", 2)
#       )
#     )
#     val pca = new PhaseComparingAnalyser(16, 128, 16)
#     pca.turnOn(Map("ReferenceGateWidth" -> 5000, "SignalGateWidth" -> 1000, "SectionPulseCount" -> 10000, "AliceRandomNumbers" -> List(67, 99, 3, 23), "BobRandomNumbers" -> List(67, 67, 3, 23)))
#     val result = pca.dataIncome(dataBlock)
#   }
# }
