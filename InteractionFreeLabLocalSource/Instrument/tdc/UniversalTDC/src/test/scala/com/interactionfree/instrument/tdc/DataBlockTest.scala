package com.interactionfree.instrument.tdc

import org.scalatest.BeforeAndAfter
import org.scalatest.funsuite.AnyFunSuite

import scala.language.postfixOps
import scala.util.Random

class DataBlockTest extends AnyFunSuite with BeforeAndAfter {

  test("Test DataBlock generation.") {
    val testDataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Random", 230000),
        5 -> List("Random", 105888),
        10 -> List("Period", 10)
      )
    )
    assert(testDataBlock.content.isDefined)
    assert(!testDataBlock.isReleased)
    assert(testDataBlock.getContent(0).length == 10000)
    assert(testDataBlock.getContent(1).length == 230000)
    assert(testDataBlock.getContent(5).length == 105888)
    assert(testDataBlock.getContent(10).length == 10)
    assert(testDataBlock.getContent(10)(5) - testDataBlock.getContent(10)(4) == 100000000000L)
    testDataBlock.release()
    assert(testDataBlock.content.isEmpty)
    assert(testDataBlock.isReleased)
    assert(testDataBlock.sizes(0) == 10000)
    assert(testDataBlock.sizes(1) == 230000)
    assert(testDataBlock.sizes(5) == 105888)
    assert(testDataBlock.sizes(10) == 10)
    assert(testDataBlock.sizes(11) == 0)
  }

  test("Test DataBlockSerializer protocol DataBlock_V1.") {
    assert(DataBlockSerializers(DataBlock.PROTOCOL_V1).serialize(Array[Long]()).length == 0)
    assert(DataBlockSerializers(DataBlock.PROTOCOL_V1).serialize(Array[Long](823784993L)).toList == List(0, 0, 0, 0, 49, 25, -10, 33))
    assert(DataBlockSerializers(DataBlock.PROTOCOL_V1).serialize(Array[Long](823784993L, 823784993L + 200, 823784993L + 2000, 823784993L + 2000, 823784993L + 2201)).toList == List(0, 0, 0, 0, 49, 25, -10, 33, 48, -56, 55, 8, 16, 48, -55))
    assert(DataBlockSerializers(DataBlock.PROTOCOL_V1).serialize(Array[Long](0, -1, -8, -17, -145, -274)).toList == List(0, 0, 0, 0, 0, 0, 0, 0, 31, 25, 47, 114, -128, 63, 127))

    val list1 = Range(0, 1).map(i => List(1000L + i, 0L)).flatten.toList
    val binary1 = DataBlockSerializers(DataBlock.PROTOCOL_V1).serialize(list1.toArray)
    val desList1 = DataBlockSerializers(DataBlock.PROTOCOL_V1).deserialize(binary1).toList
    assert(list1 == desList1)
    val random = new Random()
    val list2 = Range(0, 10000).map(i => ((random.nextDouble() - 0.5) * 1e14).toLong).toList
    val binary2 = DataBlockSerializers(DataBlock.PROTOCOL_V1).serialize(list2.toArray)
    val desList2 = DataBlockSerializers(DataBlock.PROTOCOL_V1).deserialize(binary2).toList
    assert(list2 == desList2)
  }

  test("Test DataBlock serialization and deserialization.") {
    val testDataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Random", 230000),
        5 -> List("Random", 105888),
        10 -> List("Period", 10),
        12 -> List("Random", 1)
      )
    )
    val binary = testDataBlock.serialize()
    val recoveredDataBlock = DataBlock.deserialize(binary)
    assert(testDataBlock.creationTime == recoveredDataBlock.creationTime)
    assert(testDataBlock.dataTimeBegin == recoveredDataBlock.dataTimeBegin)
    assert(testDataBlock.dataTimeEnd == recoveredDataBlock.dataTimeEnd)
    assert(testDataBlock.sizes.toList == recoveredDataBlock.sizes.toList)
    Range(0, testDataBlock.sizes.length).map(ch => {
      val testDataBlockChannel = testDataBlock.getContent(ch).toList
      val recoveredDataBlockChannel = recoveredDataBlock.getContent(ch).toList
      assert(testDataBlock.sizes(ch) == recoveredDataBlockChannel.size)
      (testDataBlockChannel zip recoveredDataBlockChannel).foreach(z => assert(z._1 == z._2))
    })
  }

  test("Test DataBlock serialization and deserialization with randomized data.") {
    val testDataBlock = DataBlock.create(
      {
        val r = new Random()
        Array(Range(0, 10000).map(_ => r.nextLong(1000000000000L)).toArray)
      },
      100001,
      0,
      1000000000000L
    )
    val binary = testDataBlock.serialize()
    val recoveredDataBlock = DataBlock.deserialize(binary)
    assert(testDataBlock.creationTime == recoveredDataBlock.creationTime)
    assert(testDataBlock.dataTimeBegin == recoveredDataBlock.dataTimeBegin)
    assert(testDataBlock.dataTimeEnd == recoveredDataBlock.dataTimeEnd)
    assert(testDataBlock.sizes.toList == recoveredDataBlock.sizes.toList)
    Range(0, testDataBlock.sizes.length).map(ch => {
      val testDataBlockChannel = testDataBlock.getContent(ch).toList
      val recoveredDataBlockChannel = recoveredDataBlock.getContent(ch).toList
      assert(testDataBlock.sizes(ch) == recoveredDataBlockChannel.size)
      (testDataBlockChannel zip recoveredDataBlockChannel).foreach(z => assert(z._1 == z._2))
    })
  }

  test("Test DataBlock serialization and deserialization with totally reversed data.") {
    val testDataBlock = DataBlock.create(
      {
        val r = new Random()
        Array(Range(0, 10000).map(i => i * 100000000L).toArray.reverse)
      },
      100001,
      0,
      1000000000000L
    )
    val binary = testDataBlock.serialize()
    val recoveredDataBlock = DataBlock.deserialize(binary)
    assert(testDataBlock.creationTime == recoveredDataBlock.creationTime)
    assert(testDataBlock.dataTimeBegin == recoveredDataBlock.dataTimeBegin)
    assert(testDataBlock.dataTimeEnd == recoveredDataBlock.dataTimeEnd)
    assert(testDataBlock.sizes.toList == recoveredDataBlock.sizes.toList)
    Range(0, testDataBlock.sizes.length).map(ch => {
      val testDataBlockChannel = testDataBlock.getContent(ch).toList
      val recoveredDataBlockChannel = recoveredDataBlock.getContent(ch).toList
      assert(testDataBlock.sizes(ch) == recoveredDataBlockChannel.size)
      (testDataBlockChannel zip recoveredDataBlockChannel).foreach(z => assert(z._1 == z._2))
    })
  }

  test("Test DataBlock serialization and deserialization with released DataBlock.") {
    val testDataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Random", 230000),
        5 -> List("Random", 105888),
        10 -> List("Period", 10),
        12 -> List("Random", 1)
      )
    )
    testDataBlock.release()
    val binary = testDataBlock.serialize()
    val recoveredDataBlock = DataBlock.deserialize(binary)
    assert(testDataBlock.creationTime == recoveredDataBlock.creationTime)
    assert(testDataBlock.dataTimeBegin == recoveredDataBlock.dataTimeBegin)
    assert(testDataBlock.dataTimeEnd == recoveredDataBlock.dataTimeEnd)
    assert(testDataBlock.sizes.toList == recoveredDataBlock.sizes.toList)
    assert(testDataBlock.getContent == null)
    assert(recoveredDataBlock.getContent == null)
  }

  test("Test DataBlock convert resolution.") {
    val fineDataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Random", 230000),
        5 -> List("Random", 105888),
        10 -> List("Period", 10),
        12 -> List("Random", 1)
      )
    )
    val coarseDataBlock1 = fineDataBlock.convertResolution(12e-12)
    assert(fineDataBlock.creationTime == coarseDataBlock1.creationTime)
    assert(fineDataBlock.dataTimeBegin / 12 == coarseDataBlock1.dataTimeBegin)
    assert(fineDataBlock.dataTimeEnd / 12 == coarseDataBlock1.dataTimeEnd)
    assert(fineDataBlock.sizes.toList == coarseDataBlock1.sizes.toList)
    assert(fineDataBlock.resolution == 1e-12)
    assert(coarseDataBlock1.resolution == 12e-12)
    assert(fineDataBlock.getContent.size == coarseDataBlock1.getContent.size)
    (fineDataBlock.getContent zip coarseDataBlock1.getContent).foreach(zip => assert(zip._1.toList.map(n => n / 12) == zip._2.toList))

    fineDataBlock.release()
    val coarseDataBlock2 = fineDataBlock.convertResolution(24e-12)
    assert(fineDataBlock.creationTime == coarseDataBlock2.creationTime)
    assert(fineDataBlock.dataTimeBegin / 24 == coarseDataBlock2.dataTimeBegin)
    assert(fineDataBlock.dataTimeEnd / 24 == coarseDataBlock2.dataTimeEnd)
    assert(fineDataBlock.sizes.toList == coarseDataBlock2.sizes.toList)
    assert(coarseDataBlock2.resolution == 24e-12)
    assert(coarseDataBlock2.getContent == null)
  }

  test("Test DataBlock lazy deserialize and unpack.") {
    val testDataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Random", 230000),
        5 -> List("Random", 105888),
        10 -> List("Period", 10),
        12 -> List("Random", 1)
      )
    )
    val binary = testDataBlock.serialize()
    val recoveredDataBlock = DataBlock.deserialize(binary, true)
    assert(testDataBlock.creationTime == recoveredDataBlock.creationTime)
    assert(testDataBlock.dataTimeBegin == recoveredDataBlock.dataTimeBegin)
    assert(testDataBlock.dataTimeEnd == recoveredDataBlock.dataTimeEnd)
    assert(testDataBlock.sizes.toList == recoveredDataBlock.sizes.toList)
    assert(testDataBlock.getContent != null)
    assert(recoveredDataBlock.getContent == null)
    assert(!recoveredDataBlock.isReleased)
    recoveredDataBlock.unpack()
    recoveredDataBlock.unpack()
    assert(!recoveredDataBlock.isReleased)

    val recoveredDataBlock2 = DataBlock.deserialize(binary, true)
    recoveredDataBlock2.release()
    recoveredDataBlock2.unpack()
    assert(recoveredDataBlock2.getContent == null)
  }

  // test("Test SyncedDataBlock.") {
  //   val testDataBlock = DataBlock.generate(
  //     Map("CreationTime" -> 100, "DataTimeBegin" -> 20, "DataTimeEnd" -> 10000000000020L),
  //     Map(
  //       0 -> List("Period", 10000),
  //       1 -> List("Period", 230000),
  //       5 -> List("Random", 105888),
  //       10 -> List("Period", 10),
  //       12 -> List("Random", 1)
  //     )
  //   )
  //   testDataBlock.content.foreach(content => content.zipWithIndex.foreach(z => content(z._2) = z._1.sorted))
  //   val testDataBlockRef = DataBlock.deserialize(testDataBlock.serialize())
  //   assertThrows[IllegalArgumentException](testDataBlock.synced(List(0, 1, 2, 4)))
  //   val delays = List(10000000, 10L, 0, 0, 0, -10000, 0, 0, 0, 0, 10, 0, -10, 0, 0, 0)
  //   val testDelayedDataBlock = testDataBlock.synced(delays)
  //   (testDelayedDataBlock.content.get zip testDataBlock.content.get zip testDelayedDataBlock.delays).foreach(z => (z._1._1 zip z._1._2).foreach(zz => assert(zz._1 - zz._2 == z._2)))
  //   assertThrows[IllegalArgumentException](testDataBlock.synced(delays, Map("Method" -> "N")))
  //   val testSyncedDataBlock = testDataBlock.synced(delays, Map("Method" -> "PeriodSignal", "SyncChannel" -> "0", "Period" -> "2e8"))
  //   (testSyncedDataBlock.content.get zip testSyncedDataBlock.sizes).foreach(z => assert(z._1.size == z._2))
  //   (testSyncedDataBlock.content.get zip testDataBlock.content.get).zipWithIndex.foreach(z => {
  //     val size1 = z._1._1.size
  //     val list2 = z._1._2.filter(t => t + delays(z._2) >= testDataBlock.content.get(0)(0) + delays(0) && t + delays(z._2) <= testDataBlock.content.get(0).last + delays(0))
  //     val size2 = list2.size
  //     assert(size1 == size2)
  //     val mappedList2 = list2.map(v => (v + delays(z._2) - delays(0)) * 2)
  //     (mappedList2 zip z._1._1).foreach(zz => assert(math.abs(zz._1 - zz._2) < 2))
  //   })
  //   (testDataBlockRef.content.get zip testDataBlock.content.get).foreach(z => {
  //     assert(z._1.size == z._2.size)
  //     (z._1 zip z._2).foreach(zz => assert(zz._1 == zz._2))
  //   })
  // }

  test("Test DataBlock ranged.") {
    val testDataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 1000000000010L, "DataTimeEnd" -> 2000000000010L),
      Map(
        0 -> List("Period", 10000),
        10 -> List("Period", 10),
        12 -> List("Period", 2000000)
      )
    )
    val rangedDataBlock1 = testDataBlock.ranged()
    assert(testDataBlock.sizes.toList == rangedDataBlock1.sizes.toList)
    assert(testDataBlock.creationTime == rangedDataBlock1.creationTime)
    assert(testDataBlock.dataTimeBegin == rangedDataBlock1.dataTimeBegin)
    assert(testDataBlock.dataTimeEnd == rangedDataBlock1.dataTimeEnd)
    assert(testDataBlock.sizes.toList == rangedDataBlock1.sizes.toList)
    Range(0, testDataBlock.sizes.length).map(ch => {
      val rangedDataBlockChannel = rangedDataBlock1.getContent(ch).toList
      assert(testDataBlock.sizes(ch) == rangedDataBlockChannel.size)
      (testDataBlock.getContent(ch) zip rangedDataBlockChannel).foreach(z => assert(z._1 == z._2))
    })

    val rangedDataBlock2 = testDataBlock.ranged(1200000000010L, 1700000000009L)
    assert(testDataBlock.sizes.toList.map(_ / 2) == rangedDataBlock2.sizes.toList)
    assert(testDataBlock.creationTime == rangedDataBlock2.creationTime)
    assert(1200000000010L == rangedDataBlock2.dataTimeBegin)
    assert(1700000000009L == rangedDataBlock2.dataTimeEnd)
    Range(0, testDataBlock.sizes.length).map(ch => rangedDataBlock2.getContent(ch).foreach(t => assert(t >= rangedDataBlock2.dataTimeBegin && t <= rangedDataBlock2.dataTimeEnd)))
  }

  test("Test DataBlock merge.") {
    val testDataBlock1 = DataBlock
      .generate(
        Map("CreationTime" -> 100, "DataTimeBegin" -> 1000000000010L, "DataTimeEnd" -> 2000000000010L),
        Map(
          0 -> List("Period", 10000),
          10 -> List("Period", 10),
          12 -> List("Period", 2000000)
        )
      )
      .ranged(after = 1500000000010L)
    val testDataBlock2 = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 2000000000010L, "DataTimeEnd" -> 3000000000010L),
      Map(
        0 -> List("Period", 10000),
        10 -> List("Period", 10),
        12 -> List("Period", 2000000)
      )
    )
    val testDataBlock3 = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 3000000000010L, "DataTimeEnd" -> 4000000000010L),
      Map(
        0 -> List("Period", 10000),
        10 -> List("Period", 10),
        12 -> List("Period", 2000000)
      )
    )
    try { DataBlock.merge(testDataBlock3 :: testDataBlock1 :: Nil) }
    catch { case e: IllegalArgumentException => }
    try { DataBlock.merge(testDataBlock1 :: testDataBlock3 :: Nil) }
    catch { case e: IllegalArgumentException => }
    DataBlock.merge(testDataBlock1 :: testDataBlock3 :: Nil, true)
    val mergedDataBlock = DataBlock.merge(testDataBlock1 :: testDataBlock2 :: testDataBlock3 :: Nil)
    Range(0, testDataBlock1.sizes.size).foreach(ch => assert(testDataBlock1.getContent(ch).size + testDataBlock2.getContent(ch).size + testDataBlock3.getContent(ch).size == mergedDataBlock.getContent(ch).size))
    assert(mergedDataBlock.getContent(0).size == 25000)
    Range(0, testDataBlock1.sizes.size).foreach(ch => assert((testDataBlock1.getContent(ch).headOption == mergedDataBlock.getContent(ch).headOption)))
    Range(0, testDataBlock1.sizes.size).foreach(ch => assert((testDataBlock3.getContent(ch).lastOption == mergedDataBlock.getContent(ch).lastOption)))
    assert(testDataBlock1.creationTime == mergedDataBlock.creationTime)
    assert(testDataBlock1.dataTimeBegin == mergedDataBlock.dataTimeBegin)
    assert(testDataBlock3.dataTimeEnd == mergedDataBlock.dataTimeEnd)
  }
}
