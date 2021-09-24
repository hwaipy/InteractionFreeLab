package com.interactionfree.instrument.tdc

import org.scalatest.BeforeAndAfter
import org.scalatest.funsuite.AnyFunSuite
import scala.language.postfixOps
import java.nio.channels.Channel

class AnalyserTest extends AnyFunSuite with BeforeAndAfter {

  test("Test Validators.") {
    assert(Validator.int(0, 10)(9))
    assert(Validator.int(0, 10)(0))
    assert(Validator.int(0, 10)(10))
    assert(!Validator.int(0, 10)(11))
    assert(Validator.int(-100, 100)(11))
    assert(!Validator.int(-100, 100)(-111))
    assert(!Validator.int(-100, 100)(-1.11))
    assert(!Validator.int(-100, 100)(new Object))
    assert(!Validator.double(0, 10.0)(new Object))
    assert(Validator.double(0, 10.0)(1))
    assert(!Validator.double(0, 10.0)(11))
    assert(!Validator.double(0, 10.0)(11.1))
    assert(Validator.double(0, 10.0)(1.1))
    assert(!Validator.double(-90, 10.0)(-91))
    assert(Validator.double(-90, 10.0)(-90))
  }

  test("Test MultiHistogramAnalyser.") {
    val offset = 50400000000010L
    val dataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> offset, "DataTimeEnd" -> (offset + 1000000000000L)),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Pulse", 100000000, 200000, 1000)
      )
    )
    val mha = new MultiHistogramAnalyser(16)
    mha.turnOn(Map("Sync" -> 0, "Signals" -> List(1), "ViewStart" -> -1000000, "ViewStop" -> 1000000, "BinCount" -> 100, "Divide" -> 100))
    val result = mha.dataIncome(dataBlock)
    assert(result.isDefined)
    assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("Sync") == 0)
    assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("Signals") == List(1))
    assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("ViewStart") == -1000000)
    assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("ViewStop") == 1000000)
    assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("BinCount") == 100)
    assert(result.get("Configuration").asInstanceOf[Map[String, Any]]("Divide") == 100)
    val histos = result.get("Histograms").asInstanceOf[List[List[Int]]]
    assert(histos.size == 1)
    val histo1 = histos(0)
    assert(histo1.size == 100)
    assert(histo1.head > 0.5 * histo1.max && histo1.head < 1.5 * histo1.max)
    assert(histo1.last > 0.5 * histo1.max && histo1.last < 1.5 * histo1.max)
    assert(histo1(histo1.length / 2) > 0.6 * histo1.max && histo1(histo1.length / 2) < 1.5 * histo1.max)
    assert(histo1(histo1.length / 4) < 0.05 * histo1.max && histo1(histo1.length / 4 * 3) < 0.05 * histo1.max)
    mha.turnOff()
    val result2 = mha.dataIncome(dataBlock)
    assert(result2.isEmpty)
  }

  test("Test CounterAnalyser.") {
    val offset = 50400000000010L
    val dataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> offset, "DataTimeEnd" -> (offset + 1000000000000L)),
      Map(
        0 -> List("Period", 10000),
        5 -> List("Pulse", 100000000, 200000, 1000)
      )
    )
    val mha = new CounterAnalyser()
    mha.turnOn()
    val result = mha.dataIncome(dataBlock)
    assert(result.isDefined)
    assert(result.get("Configuration").asInstanceOf[Map[String, Any]] == Map())
    assert(result.get("0") == 10000)
    assert(result.get("1") == 0)
    assert(result.get("2") == 0)
    assert(result.get("3") == 0)
    assert(result.get("4") == 0)
    assert(result.get("5") == 200000)
    assert(result.get("6") == 0)
    assert(result.get("7") == 0)
    assert(result.get("8") == 0)
    assert(result.get("9") == 0)
    assert(result.get("10") == 0)
    mha.turnOff()
    val result2 = mha.dataIncome(dataBlock)
    assert(result2.isEmpty)
  }

  test("Test ExceptionMonitorAnalyser.") {
    val offset = 50400000000010L
    val dataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Period", 230000),
        5 -> List("Random", 105888),
        10 -> List("Period", 10),
        12 -> List("Random", 1)
      )
    )
    dataBlock.content.foreach(content => content.zipWithIndex.foreach(z => content(z._2) = z._1.sorted))
    val mha = new ExceptionMonitorAnalyser(16)
    mha.turnOn(Map("SyncChannels" -> List(0, 1, 5, 10)))
    val result = mha.dataIncome(dataBlock)
    assert(result.isDefined)
    assert(result.get("ReverseCounts").asInstanceOf[Array[Int]].toList == List(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    val syncMonitor = result.get("SyncMonitor").asInstanceOf[Map[String, Map[String, Any]]]
    assert(syncMonitor("0")("Average") == 1e8)
    assert(syncMonitor("0")("Max") == 1e8)
    assert(syncMonitor("0")("Min") == 1e8)
    assert(syncMonitor("1")("Average") == 4347826.086952552)
    assert(syncMonitor("1")("Max") == 4347827)
    assert(syncMonitor("1")("Min") == 4347826)
    assert(syncMonitor("10")("Average") == 1e11)
    assert(syncMonitor("10")("Max") == 1e11)
    assert(syncMonitor("10")("Min") == 1e11)
    List(5, 10, 100, 1100, 1101, 20230, 33323).foreach(i => dataBlock.content.get(1)(i) = 10)
    val result2 = mha.dataIncome(dataBlock)
    assert(result2.get("ReverseCounts").asInstanceOf[Array[Int]].toList == List(0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
  }

  test("Test EncodingAnalyser.") {
    val offset = 50400000000010L
    val dataBlock1 = DataBlock
      .generate(
        Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
        Map(
          0 -> List("Period", 10000),
          1 -> List("Pulse", 100000000, 2300000, 100)
        )
      )
      .synced(List(0, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    val mha = new EncodingAnalyser(16, 128)
    val configHistograms = Map("G1" -> List[Int](1, 3, 5), "G2" -> List[Int](10, 12, 14), "G1+G2" -> List[Int](1, 3, 5, 10, 12, 14), "G1'" -> List[Int](3, 4, 5), "G1+G1'" -> List[Int](1, 3, 4, 5))
    mha.turnOn(
      Map(
        "Period" -> 10000,
        "TriggerChannel" -> 0,
        "SignalChannel" -> 1,
        "RandomNumbers" -> Range(0, 128).toList,
        "Histograms" -> configHistograms
      )
    )
    val result1 = mha.dataIncome(dataBlock1)
    assert(result1.isDefined)
    configHistograms.foreach(entry => {
      assert(result1.get(s"PulseCount[${entry._1}]") == entry._2.size)
      val histogram = result1.get(s"Histogram[${entry._1}]").asInstanceOf[List[Int]]
      assert(Math.abs(histogram.indexOf(histogram.max) - 50) < 5)
      assert(histogram.filter(_ > 0).size < 15)
      assert(histogram.slice(0, 42).max == 0)
      assert(histogram.slice(57, 100).max == 0)
    })
    val histogram1G1 = result1.get(s"Histogram[G1]").asInstanceOf[List[Int]]
    val histogram1G2 = result1.get(s"Histogram[G2]").asInstanceOf[List[Int]]
    val histogram1G1G2 = result1.get(s"Histogram[G1+G2]").asInstanceOf[List[Int]]
    val histogram1G1G2Exp = (histogram1G1 zip histogram1G2).map(z => z._1 + z._2)
    (histogram1G1G2Exp zip histogram1G1G2).foreach(z => assert(z._1 == z._2))

    val dataBlock2 = DataBlock
      .generate(
        Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
        Map(
          0 -> List("Period", 10000),
          1 -> List("Pulse", 50000000, 2300000, 100)
        )
      )
      .synced(List(0, 5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    val result2 = mha.dataIncome(dataBlock2)
    assert(result2.isDefined)
    configHistograms.foreach(entry => assert(result2.get(s"PulseCount[${entry._1}]") == entry._2.size))
    val histogram2G1 = result2.get(s"Histogram[G1]").asInstanceOf[List[Int]]
    assert(histogram2G1.max == 0)
    val histogram2G2 = result2.get(s"Histogram[G2]").asInstanceOf[List[Int]]
    assert(Math.abs(histogram2G2.indexOf(histogram2G2.max) - 50) < 5)
    assert(histogram2G2.filter(_ > 0).size < 15)
    assert(histogram2G2.slice(0, 42).max == 0)
    assert(histogram2G2.slice(57, 100).max == 0)
    val histogram2G1G2 = result2.get(s"Histogram[G1+G2]").asInstanceOf[List[Int]]
    val histogram2G1G2Exp = (histogram2G1 zip histogram2G2).map(z => z._1 + z._2)
    (histogram2G1G2Exp zip histogram2G1G2).foreach(z => assert(z._1 == z._2))
  }

  test("Test ChannelMonitorAnalyser.") {
    val offset = 50400000000010L
    val dataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        1 -> List("Period", 200000),
        5 -> List("Random", 105888),
        10 -> List("Period", 10),
        12 -> List("Random", 2)
      )
    )
    val mha = new ChannelMonitorAnalyser(16)
    mha.turnOn(Map("SyncChannel" -> 12, "Channels" -> List(0, 1, 5, 10), "SectionCount" -> 1000))
    val result = mha.dataIncome(dataBlock)
    assert(result.isDefined)
    assert(result.get("DataBlockBegin") == 10L)
    assert(result.get("DataBlockEnd") == 1000000000010L)
    assert(result.get("Sync").asInstanceOf[Array[Long]].toList == dataBlock.getContent(12).toList)
    val countSections = result.get("CountSections").asInstanceOf[Map[String, Array[Int]]]
    assert(countSections("0").toList == Range(0, 1000).toList.map(_ => 10))
    assert(countSections("1").toList == Range(0, 1000).toList.map(_ => 200))
  }

  test("Test PhaseComparingAnalyser.") {
    val offset = 50400000000010L
    val dataBlock = DataBlock.generate(
      Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L),
      Map(
        0 -> List("Period", 10000),
        2 -> List("Period", 200000),
        3 -> List("Random", 105888),
        10 -> List("Period", 10),
        12 -> List("Random", 2)
      )
    )
    val pca = new PhaseComparingAnalyser(16, 128, 16)
    pca.turnOn(Map("ReferenceGateWidth" -> 5000, "SignalGateWidth" -> 1000, "SectionPulseCount" -> 10000, "AliceRandomNumbers" -> List(67, 99, 3, 23), "BobRandomNumbers" -> List(67, 67, 3, 23)))
    val result = pca.dataIncome(dataBlock)
  }
}
