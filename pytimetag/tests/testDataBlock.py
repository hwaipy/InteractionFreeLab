__author__ = 'Hwaipy'

import unittest
from pytimetag import DataBlock, DataBlockSerializer, Parallels
import numpy as np
from random import Random


class DataBlockTest(unittest.TestCase):
  rnd = Random()

  @classmethod
  def setUpClass(cls):
    pass

  def setUp(self):
    pass

  def testDataBlockGeneration(self):
    testDataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
        {0: ['Period', 10000], 1: ['Random', 230000], 5: ['Random', 105888], 10: ['Period', 10]}
    )
    self.assertTrue(testDataBlock.content is not None)
    self.assertFalse(testDataBlock.isReleased())
    self.assertEqual(len(testDataBlock.content[0]), 10000)
    self.assertEqual(len(testDataBlock.content[1]), 230000)
    self.assertEqual(len(testDataBlock.content[5]), 105888)
    self.assertEqual(len(testDataBlock.content[10]), 10)
    self.assertEqual(testDataBlock.content[10][5] - testDataBlock.content[10][4], 100000000000)
    testDataBlock.release()
    self.assertIsNone(testDataBlock.content)
    self.assertTrue(testDataBlock.isReleased())
    self.assertEqual(testDataBlock.sizes[0], 10000)
    self.assertEqual(testDataBlock.sizes[1], 230000)
    self.assertEqual(testDataBlock.sizes[5], 105888)
    self.assertEqual(testDataBlock.sizes[10], 10)
    self.assertEqual(testDataBlock.sizes[11], 0)

  # def testDataBlockSerializerProtocolDataBlockV1(self):
  #   self.assertEqual(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize(np.array([])), ([], []))
  #   self.assertEqual(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize(np.array([[823784993]])), ([[bytes(bytearray([0, 0, 0, 0, 49, 25, 246, 33]))]], [[1]]))
  #   self.assertEqual(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize(np.array([[823784993, 823784993 + 200, 823784993 + 2000, 823784993 + 2000, 823784993 + 2201]])), ([[bytes(bytearray([0, 0, 0, 0, 49, 25, 246, 33, 48, 200, 55, 8, 16, 48, 201]))]], [[5]]))
  #   self.assertEqual(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize(np.array([[0, -1, -8, -17, -145, -274]])), ([[bytes(bytearray([0, 0, 0, 0, 0, 0, 0, 0, 31, 25, 47, 114, 128, 63, 127]))]], [[6]]))
  #   list1 = list(np.array([[1000 + i, 0] for i in range(2)]).flatten())
  #   binary1 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize([np.array(list1)])
  #   desList1 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).deserialize(binary1[0][0])
  #   self.assertEqual(list1, [i for i in desList1])
  #   list2 = [int((DataBlockTest.rnd.random() - 0.5) * 1e14) for i in range(10)]
  #   binary2 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize([np.array(list2)])
  #   desList2 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).deserialize(binary2[0][0])
  #   self.assertEqual(list2, [i for i in desList2])

  def testDataBlockSerializationAndDeserialization(self):
    testDataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
        {0: ['Period', 10000], 1: ['Random', 230000], 5: ['Random', 105888], 10: ['Period', 10], 12: ['Random', 1]}
    )
    binary = testDataBlock.serialize()
    recoveredDataBlock = DataBlock.deserialize(binary)
    self.assertDataBlockEqual(testDataBlock, recoveredDataBlock)

  def testDataBlockSerializationAndDeserializationWithRandomizedData(self):
    testDataBlock = DataBlock.create([[DataBlockTest.rnd.randint(0, 1000000000000) for i in range(10000)]], 100001, 0, 1000000000000)
    binary = testDataBlock.serialize()
    recoveredDataBlock = DataBlock.deserialize(binary)
    self.assertDataBlockEqual(testDataBlock, recoveredDataBlock)

  def testDataBlockSerializationAndDeserializationWithTotallyReversedData(self):
    ch1 = [i * 100000000 for i in range(10000)]
    ch1.reverse()
    testDataBlock = DataBlock.create([ch1], 100001, 0, 1000000000000)
    binary = testDataBlock.serialize()
    recoveredDataBlock = DataBlock.deserialize(binary)
    self.assertDataBlockEqual(testDataBlock, recoveredDataBlock)

  def testDataBlockSerializationAndDeserializationWithReleasedDataBlock(self):
    testDataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
        {0: ['Period', 10000], 1: ['Random', 230000], 5: ['Random', 105888], 10: ['Period', 10], 12: ['Random', 1]}
    )
    testDataBlock.release()
    binary = testDataBlock.serialize()
    recoveredDataBlock = DataBlock.deserialize(binary)
    self.assertDataBlockEqual(testDataBlock, recoveredDataBlock, compareContent=False)
    self.assertIsNone(testDataBlock.content)
    self.assertIsNone(recoveredDataBlock.content)

  def testDataBlockConvertResolution(self):
    fineDataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
        {0: ['Period', 10000], 1: ['Random', 230000], 5: ['Random', 105888], 10: ['Period', 10], 12: ['Random', 1]}
    )
    coarseDataBlock1 = fineDataBlock.convertResolution(12e-12)
    self.assertEqual(fineDataBlock.creationTime, coarseDataBlock1.creationTime)
    self.assertEqual(int(fineDataBlock.dataTimeBegin / 12), coarseDataBlock1.dataTimeBegin)
    self.assertEqual(int(fineDataBlock.dataTimeEnd / 12), coarseDataBlock1.dataTimeEnd)
    self.assertEqual(fineDataBlock.sizes, coarseDataBlock1.sizes)
    self.assertEqual(fineDataBlock.resolution, 1e-12)
    self.assertEqual(coarseDataBlock1.resolution, 12e-12)
    self.assertEqual(len(fineDataBlock.content), len(coarseDataBlock1.content))
    for ch in range(len(fineDataBlock.sizes)):
      ch1 = fineDataBlock.content[ch]
      ch2 = coarseDataBlock1.content[ch]
      self.assertEqual(fineDataBlock.sizes[ch], len(ch1))
      for i in range(len(ch1)):
        self.assertEqual(int(ch1[i] / 12), ch2[i])
    fineDataBlock.release()
    coarseDataBlock2 = fineDataBlock.convertResolution(24e-12)
    self.assertEqual(fineDataBlock.creationTime, coarseDataBlock2.creationTime)
    self.assertEqual(int(fineDataBlock.dataTimeBegin / 24), coarseDataBlock2.dataTimeBegin)
    self.assertEqual(int(fineDataBlock.dataTimeEnd / 24), coarseDataBlock2.dataTimeEnd)
    self.assertEqual(fineDataBlock.sizes, coarseDataBlock2.sizes)
    self.assertEqual(coarseDataBlock2.resolution, 24e-12)
    self.assertIsNone(coarseDataBlock2.content)

  def testDataBlockLazyDeserializeAndUnpack(self):
    testDataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
        {0: ['Period', 10000], 1: ['Random', 230000], 5: ['Random', 105888], 10: ['Period', 10], 12: ['Random', 1]}
    )
    binary = testDataBlock.serialize()
    recoveredDataBlock = DataBlock.deserialize(binary, True)
    self.assertDataBlockEqual(testDataBlock, recoveredDataBlock, compareContent=False)
    self.assertIsNone(recoveredDataBlock.content)
    self.assertFalse(recoveredDataBlock.isReleased())
    recoveredDataBlock.unpack()
    recoveredDataBlock.unpack()
    self.assertEqual([len(c) for c in recoveredDataBlock.content], recoveredDataBlock.sizes)
    self.assertFalse(recoveredDataBlock.isReleased())
    recoveredDataBlock2 = DataBlock.deserialize(binary, True)
    recoveredDataBlock2.release()
    recoveredDataBlock2.unpack()
    self.assertIsNone(recoveredDataBlock2.content)

  def testSyncedDataBlock(self):
    testDataBlock = DataBlock.generate(
        {'CreationTime': 100, 'DataTimeBegin': 20, 'DataTimeEnd': 1000000000020},
        {0: ['Period', 10000], 1: ['Random', 230000], 5: ['Random', 105888], 10: ['Period', 10], 12: ['Random', 1]}
    )
    delays = np.random.randint(-1000000, 1000000, size=16)
    syncedDataBlock = testDataBlock.synced(delays)
    for i in range(len(testDataBlock.content)):
      ch1 = testDataBlock.content[i]
      ch2 = syncedDataBlock.content[i]
      self.assertEqual(len(ch1), len(ch2))
      if len(ch1) > 0:
        delta = ch1 - ch2
        self.assertEqual(np.min(delta), -delays[i])
        self.assertEqual(np.max(delta), -delays[i])
    binary = syncedDataBlock.serialize()
    recoveredDataBlock = DataBlock.deserialize(binary)
    self.assertDataBlockEqual(syncedDataBlock, recoveredDataBlock)

  # def testDataBlockSerializationAndDeserializationParallels(self):
  #   testDataBlock = DataBlock.generate(
  #       {'CreationTime': 100, 'DataTimeBegin': 10, 'DataTimeEnd': 1000000000010},
  #       {0: ['Period', 10000], 1: ['Random', 2300000], 5: ['Random', 1058888], 10: ['Period', 10], 12: ['Random', 1]}
  #   )
  #   Parallels.enable()
  #   binary = testDataBlock.serialize()
  #   print('-----------------------')
  #   binary = testDataBlock.serialize()
  #   recoveredDataBlock = DataBlock.deserialize(binary)
  #   self.assertDataBlockEqual(testDataBlock, recoveredDataBlock)

  #   #.测两种情况：     给 普通的  和  直接给sharedmemory的 （后者，应该不会release才对）


  #   Parallels.disable()

  # def testSharedMemory(self):
  #   testDataBlock = DataBlock.generate(
  #       {'CreationTime': 100, 'DataTimeBegin': 20, 'DataTimeEnd': 1000000000020},
  #       {0: ['Period', 10000], 1: ['Random', 2300000], 5: ['Random', 1058888], 10: ['Period', 10000000], 12: ['Random', 20000000]}
  #   )
  #   dbSharedMemory = testDataBlock.sharedMemory()
  #   dbSharedMemory.content


  # def testDataBlockRanged(self):
    # testDataBlock = DataBlock.generate(
    #     {'CreationTime': 100, 'DataTimeBegin': 1000000000010, 'DataTimeEnd': 2000000000010},
    #     {0: ['Period', 10000], 10: ['Period', 10], 12: ['Random', 2000000]}
    # )
    # rangedDataBlock1 = testDataBlock.ranged()
    #     assert(testDataBlock.sizes.toList == rangedDataBlock1.sizes.toList)
    #     assert(testDataBlock.creationTime == rangedDataBlock1.creationTime)
    #     assert(testDataBlock.dataTimeBegin == rangedDataBlock1.dataTimeBegin)
    #     assert(testDataBlock.dataTimeEnd == rangedDataBlock1.dataTimeEnd)
    #     assert(testDataBlock.sizes.toList == rangedDataBlock1.sizes.toList)
    #     Range(0, testDataBlock.sizes.length).map(ch => {
    #       val rangedDataBlockChannel = rangedDataBlock1.getContent(ch).toList
    #       assert(testDataBlock.sizes(ch) == rangedDataBlockChannel.size)
    #       (testDataBlock.getContent(ch) zip rangedDataBlockChannel).foreach(z => assert(z._1 == z._2))
    #     })

    #     val rangedDataBlock2 = testDataBlock.ranged(1200000000010L, 1700000000009L)
    #     assert(testDataBlock.sizes.toList.map(_ / 2) == rangedDataBlock2.sizes.toList)
    #     assert(testDataBlock.creationTime == rangedDataBlock2.creationTime)
    #     assert(1200000000010L == rangedDataBlock2.dataTimeBegin)
    #     assert(1700000000009L == rangedDataBlock2.dataTimeEnd)
    #     Range(0, testDataBlock.sizes.length).map(ch => rangedDataBlock2.getContent(ch).foreach(t => assert(t >= rangedDataBlock2.dataTimeBegin && t <= rangedDataBlock2.dataTimeEnd)))
    #   }

#   test("Test DataBlock merge.") {
#     val testDataBlock1 = DataBlock
#       .generate(
#         Map("CreationTime" -> 100, "DataTimeBegin" -> 1000000000010L, "DataTimeEnd" -> 2000000000010L),
#         Map(
#           0 -> List("Period", 10000),
#           10 -> List("Period", 10),
#           12 -> List("Period", 2000000)
#         )
#       )
#       .ranged(after = 1500000000010L)
#     val testDataBlock2 = DataBlock.generate(
#       Map("CreationTime" -> 100, "DataTimeBegin" -> 2000000000010L, "DataTimeEnd" -> 3000000000010L),
#       Map(
#         0 -> List("Period", 10000),
#         10 -> List("Period", 10),
#         12 -> List("Period", 2000000)
#       )
#     )
#     val testDataBlock3 = DataBlock.generate(
#       Map("CreationTime" -> 100, "DataTimeBegin" -> 3000000000010L, "DataTimeEnd" -> 4000000000010L),
#       Map(
#         0 -> List("Period", 10000),
#         10 -> List("Period", 10),
#         12 -> List("Period", 2000000)
#       )
#     )
#     try { DataBlock.merge(testDataBlock3 :: testDataBlock1 :: Nil) }
#     catch { case e: IllegalArgumentException => }
#     try { DataBlock.merge(testDataBlock1 :: testDataBlock3 :: Nil) }
#     catch { case e: IllegalArgumentException => }
#     DataBlock.merge(testDataBlock1 :: testDataBlock3 :: Nil, true)
#     val mergedDataBlock = DataBlock.merge(testDataBlock1 :: testDataBlock2 :: testDataBlock3 :: Nil)
#     Range(0, testDataBlock1.sizes.size).foreach(ch => assert(testDataBlock1.getContent(ch).size + testDataBlock2.getContent(ch).size + testDataBlock3.getContent(ch).size == mergedDataBlock.getContent(ch).size))
#     assert(mergedDataBlock.getContent(0).size == 25000)
#     Range(0, testDataBlock1.sizes.size).foreach(ch => assert((testDataBlock1.getContent(ch).headOption == mergedDataBlock.getContent(ch).headOption)))
#     Range(0, testDataBlock1.sizes.size).foreach(ch => assert((testDataBlock3.getContent(ch).lastOption == mergedDataBlock.getContent(ch).lastOption)))
#     assert(testDataBlock1.creationTime == mergedDataBlock.creationTime)
#     assert(testDataBlock1.dataTimeBegin == mergedDataBlock.dataTimeBegin)
#     assert(testDataBlock3.dataTimeEnd == mergedDataBlock.dataTimeEnd)
#   }
# }

  def assertDataBlockEqual(self, db1, db2, compareContent=True):
    self.assertEqual(db1.creationTime, db2.creationTime)
    self.assertEqual(db1.dataTimeBegin, db2.dataTimeBegin)
    self.assertEqual(db1.dataTimeEnd, db2.dataTimeEnd)
    self.assertEqual(db1.sizes, db2.sizes)
    if compareContent:
      for ch in range(len(db1.sizes)):
        ch1 = db1.content[ch]
        ch2 = db2.content[ch]
        self.assertEqual(db1.sizes[ch], len(ch1))
        for i in range(len(ch1)):
          self.assertEqual(ch1[i], ch2[i])

  def tearDown(self):
    pass

  @classmethod
  def tearDownClass(cls):
    pass


if __name__ == '__main__':
  unittest.main()
