__author__ = 'Hwaipy'

import unittest
import os

from random import Random


class DataBlockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        pass

    def testDBFunctions(self):
        # self.assertTrue(await StorageTest.storage.latest(StorageTest.collection, 'FetchTime', '2020-07-01T00:01:00+08:00', {'FetchTime': 1, '_id': 0}) == {'FetchTime': '2020-07-01T00:01:39+08:00'})
        pass

    def tearDown(self):
        pass

    @classmethod
    def tearDownClass(cls):
        pass


if __name__ == '__main__':
    unittest.main()

# package com.interactionfree.instrument.tdc

# import org.scalatest.BeforeAndAfter
# import org.scalatest.funsuite.AnyFunSuite
# import scala.language.postfixOps

# class AnalyserTest extends AnyFunSuite with BeforeAndAfter {

#   test("Test Validators.") {
#     assert(Validator.int(0, 10)(9))
#     assert(Validator.int(0, 10)(0))
#     assert(Validator.int(0, 10)(10))
#     assert(!Validator.int(0, 10)(11))
#     assert(Validator.int(-100, 100)(11))
#     assert(!Validator.int(-100, 100)(-111))
#     assert(!Validator.int(-100, 100)(-1.11))
#     assert(!Validator.int(-100, 100)(new Object))
#     assert(!Validator.double(0, 10.0)(new Object))
#     assert(Validator.double(0, 10.0)(1))
#     assert(!Validator.double(0, 10.0)(11))
#     assert(!Validator.double(0, 10.0)(11.1))
#     assert(Validator.double(0, 10.0)(1.1))
#     assert(!Validator.double(-90, 10.0)(-91))
#     assert(Validator.double(-90, 10.0)(-90))
#   }

#   test("Test MultiHistogramAnalyser.") {
#     val offset = 50400000000010L
#     val dataBlock = DataBlock.generate(
#       Map("CreationTime" -> 100, "DataTimeBegin" -> offset, "DataTimeEnd" -> (offset + 1000000000000L)),
#       Map(
#         0 -> List("Period", 10000),
#         1 -> List("Pulse", 100000000, 200000, 1000),
#       )
#     )
#     val mha = new MultiHistogramAnalyser(16)
#     mha.turnOn(Map("Sync" -> 0, "Signals" -> List(1), "ViewStart" -> -1000000, "ViewStop" -> 1000000, "BinCount" -> 100, "Divide" -> 100))
#     val result = mha.dataIncome(dataBlock)
#     assert(result.isDefined)
#     assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("Sync") == 0)
#     assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("Signals") == List(1))
#     assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("ViewStart") == -1000000)
#     assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("ViewStop") == 1000000)
#     assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("BinCount") == 100)
#     assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("Divide") == 100)
#     val histos = result.get("Histograms").asInstanceOf[List[List[Int]]]
#     assert(histos.size == 1)
#     val histo1 = histos(0)
#     assert(histo1.size == 100)
#     assert(histo1.head > 0.5 * histo1.max && histo1.head < 1.5 * histo1.max)
#     assert(histo1.last > 0.5 * histo1.max && histo1.last < 1.5 * histo1.max)
#     assert(histo1(histo1.length / 2) > 0.6 * histo1.max && histo1(histo1.length / 2) < 1.5 * histo1.max)
#     assert(histo1(histo1.length / 4) < 0.05 * histo1.max && histo1(histo1.length / 4 * 3) < 0.05 * histo1.max)
#     mha.turnOff()
#     val result2 = mha.dataIncome(dataBlock)
#     assert(result2.isEmpty)
#   }
# }
