__author__ = 'Hwaipy'

import unittest
import os
from functional import seq
from random import Random
from Instrument.tdc.universaltdc.DataBlock import DataBlock, DataBlockSerializer

class DataBlockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        pass

    def testDataBlockGeneration(self):
        testDataBlock = DataBlock.generate(
            {"CreationTime": 100, "DataTimeBegin": 10, "DataTimeEnd": 1000000000010},
            {
                0: ("Period", 10000),
                1: ("Random", 230000),
                5: ("Random", 105888),
                10: ("Period", 10)
            }
        )
        self.assertTrue(testDataBlock.content is not None)
        self.assertFalse(testDataBlock.isReleased())
        self.assertEqual(len(testDataBlock.content[0]), 10000)
        self.assertEqual(len(testDataBlock.content[1]), 230000)
        self.assertEqual(len(testDataBlock.content[5]), 105888)
        self.assertEqual(len(testDataBlock.content[10]), 10)
        self.assertEqual(testDataBlock.content[10][5] - testDataBlock.content[10][4], 100000000000)
        testDataBlock.release()
        self.assertEqual(testDataBlock.content, None)
        self.assertTrue(testDataBlock.isReleased())
        self.assertEqual(testDataBlock.sizes[0], 10000)
        self.assertEqual(testDataBlock.sizes[1], 230000)
        self.assertEqual(testDataBlock.sizes[5], 105888)
        self.assertEqual(testDataBlock.sizes[10], 10)
        self.assertEqual(testDataBlock.sizes[11], 0)

    def testDataBlockSerializerProtocolDataBlock_V1(self):
        self.assertEqual(len(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize([])), 0)
        self.assertEqual(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize([823784993]), bytes([0, 0, 0, 0, 49, 25, 246, 33]))
        self.assertEqual(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize([823784993, 823784993 + 200, 823784993 + 2000, 823784993 + 2000, 823784993 + 2201]), bytes([0, 0, 0, 0, 49, 25, 246, 33, 48, 200, 55, 8, 16, 48, 201]))
        self.assertEqual(DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize([0, -1, -8, -17, -145, -274]), bytes([0, 0, 0, 0, 0, 0, 0, 0, 31, 25, 47, 114, 128, 63, 127]))
        list1 = seq([0,1]).map(lambda i: [1000 + i, 0]).flatten().to_list()
        binary1 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize(list1)
        desList1 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).deserialize(binary1)
        self.assertEqual(list1, desList1)
        rnd = Random()
        list2 = [int((rnd.gauss(0, 1) - 0.5) * 1e14) for i in range(0, 10000)]
        binary2 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).serialize(list2)
        desList2 = DataBlockSerializer.instance(DataBlock.PROTOCOL_V1).deserialize(binary2)
        self.assertEqual(list2, desList2)

    def testDataBlockSerializationAndDeserialization(self):
        testDataBlock = DataBlock.generate(
            {"CreationTime": 100, "DataTimeBegin": 10, "DataTimeEnd": 1000000000010},
            {
                0 : ("Period", 10000),
                1 : ("Random", 230000),
                5 : ("Random", 105888),
                10 : ("Period", 10),
                12 : ("Random", 1)
            })
        binary = testDataBlock.serialize()
        recoveredDataBlock = DataBlock.deserialize(binary)
        self.assertEqual(testDataBlock.creationTime, recoveredDataBlock.creationTime)
        self.assertEqual(testDataBlock.dataTimeBegin, recoveredDataBlock.dataTimeBegin)
        self.assertEqual(testDataBlock.dataTimeEnd, recoveredDataBlock.dataTimeEnd)
        self.assertEqual(testDataBlock.sizes, recoveredDataBlock.sizes)
        for ch in range(len(testDataBlock.sizes)):
            testDataBlockChannel = testDataBlock.content[ch]
            recoveredDataBlockChannel = recoveredDataBlock.content[ch]
            self.assertEqual(testDataBlock.sizes[ch], len(recoveredDataBlockChannel))
            self.assertEqual(testDataBlockChannel, recoveredDataBlockChannel)

    def testDataBlockSerializationAndDeserializationWithRandomizedData(self):
        rnd = Random()
        testDataBlock = DataBlock.create([seq(range(10000)).map(lambda s: rnd.randint(0, 1000000000000)).to_list()], 100001, 0, 1000000000000)
        binary = testDataBlock.serialize()
        recoveredDataBlock = DataBlock.deserialize(binary)
        self.assertEqual(testDataBlock.creationTime, recoveredDataBlock.creationTime)
        self.assertEqual(testDataBlock.dataTimeBegin, recoveredDataBlock.dataTimeBegin)
        self.assertEqual(testDataBlock.dataTimeEnd, recoveredDataBlock.dataTimeEnd)
        self.assertEqual(testDataBlock.sizes, recoveredDataBlock.sizes)
        for ch in range(len(testDataBlock.sizes)):
            testDataBlockChannel = testDataBlock.content[ch]
            recoveredDataBlockChannel = recoveredDataBlock.content[ch]
            self.assertEqual(testDataBlock.sizes[ch], len(recoveredDataBlockChannel))
            self.assertEqual(testDataBlockChannel, recoveredDataBlockChannel)

    def testDataBlockSerializationAndDeserializationWithTotallyReversedData(self):
        rnd = Random()
        data = seq(range(10000)).map(lambda i: i * 100000000).to_list()
        data.reverse()
        testDataBlock = DataBlock.create([data], 100001, 0, 1000000000000)
        binary = testDataBlock.serialize()
        recoveredDataBlock = DataBlock.deserialize(binary)
        self.assertEqual(testDataBlock.creationTime, recoveredDataBlock.creationTime)
        self.assertEqual(testDataBlock.dataTimeBegin, recoveredDataBlock.dataTimeBegin)
        self.assertEqual(testDataBlock.dataTimeEnd, recoveredDataBlock.dataTimeEnd)
        self.assertEqual(testDataBlock.sizes, recoveredDataBlock.sizes)
        for ch in range(len(testDataBlock.sizes)):
            testDataBlockChannel = testDataBlock.content[ch]
            recoveredDataBlockChannel = recoveredDataBlock.content[ch]
            self.assertEqual(testDataBlock.sizes[ch], len(recoveredDataBlockChannel))
            self.assertEqual(testDataBlockChannel, recoveredDataBlockChannel)

    def testDataBlockSerializationAndDeserializationWithReleasedDataBlock(self):
        testDataBlock = DataBlock.generate(
            {"CreationTime": 100, "DataTimeBegin": 10, "DataTimeEnd": 1000000000010},
            {
                0: ("Period", 10000),
                1: ("Random", 230000),
                5: ("Random", 105888),
                10: ("Period", 10),
                12: ("Random", 1)
            }
        )
        testDataBlock.release()
        binary = testDataBlock.serialize()
        recoveredDataBlock = DataBlock.deserialize(binary)
        self.assertEqual(testDataBlock.creationTime, recoveredDataBlock.creationTime)
        self.assertEqual(testDataBlock.dataTimeBegin, recoveredDataBlock.dataTimeBegin)
        self.assertEqual(testDataBlock.dataTimeEnd, recoveredDataBlock.dataTimeEnd)
        self.assertEqual(testDataBlock.sizes, recoveredDataBlock.sizes)
        self.assertIsNone(testDataBlock.content)
        self.assertIsNone(recoveredDataBlock.content)

    def testDataBlockConvertResolution(self):
        fineDataBlock = DataBlock.generate(
            {"CreationTime": 100, "DataTimeBegin": 10, "DataTimeEnd": 1000000000010},
            {
                0: ("Period", 10000),
                1: ("Random", 230000),
                5: ("Random", 105888),
                10: ("Period", 10),
                12: ("Random", 1)
            }
        )
        coarseDataBlock1 = fineDataBlock.convertResolution(12e-12)
        self.assertEqual(fineDataBlock.creationTime, coarseDataBlock1.creationTime)
        self.assertEqual(int(fineDataBlock.dataTimeBegin / 12), coarseDataBlock1.dataTimeBegin)
        self.assertEqual(int(fineDataBlock.dataTimeEnd / 12), coarseDataBlock1.dataTimeEnd)
        self.assertEqual(fineDataBlock.sizes, coarseDataBlock1.sizes)
        self.assertEqual(fineDataBlock.resolution, 1e-12)
        self.assertEqual(coarseDataBlock1.resolution, 12e-12)
        self.assertEqual(len(fineDataBlock.content), len(coarseDataBlock1.content))
        for ch in range(len(fineDataBlock.content)):
            chFine = fineDataBlock.content[ch]
            chCoarse = coarseDataBlock1.content[ch]
            self.assertEqual([int(d/12) for d in chFine], chCoarse)
        fineDataBlock.release()
        coarseDataBlock2 = fineDataBlock.convertResolution(24e-12)
        self.assertEqual(fineDataBlock.creationTime, coarseDataBlock2.creationTime)
        self.assertEqual(int(fineDataBlock.dataTimeBegin / 24), coarseDataBlock2.dataTimeBegin)
        self.assertEqual(int(fineDataBlock.dataTimeEnd / 24), coarseDataBlock2.dataTimeEnd)
        self.assertEqual(fineDataBlock.sizes, coarseDataBlock2.sizes)
        self.assertEqual(coarseDataBlock2.resolution, 24e-12)
        self.assertIsNone(coarseDataBlock2.content)

    def tearDown(self):
        pass

    @classmethod
    def tearDownClass(cls):
        pass


if __name__ == '__main__':
    unittest.main()
