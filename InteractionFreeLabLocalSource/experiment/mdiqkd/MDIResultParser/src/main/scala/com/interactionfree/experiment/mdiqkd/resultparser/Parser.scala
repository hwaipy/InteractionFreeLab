package com.interactionfree.experiment.mdiqkd.resultparser

import java.time.{LocalDateTime, ZoneOffset, ZonedDateTime}
import java.util.concurrent.atomic.{AtomicBoolean, AtomicInteger, AtomicReference}
import com.interactionfree.{BlockingIFWorker, IFWorker}
import com.interactionfree.NumberTypeConversions._
import scala.collection.mutable
import scala.collection.mutable.{ArrayBuffer, ListBuffer}
import scala.language.postfixOps

class Reviewer(worker: BlockingIFWorker, startTime: String, stopTime: String, ignoredChannel: Int) {
  def this(worker: BlockingIFWorker, startTime: LocalDateTime, stopTime: LocalDateTime, ignoredChannel: Int = -1) = {
    this(worker, startTime.toString, stopTime.toString, ignoredChannel)
  }

  def this(worker: BlockingIFWorker, startTime: String, stopTime: String) = {
    this(worker, startTime, stopTime, -1)
  }

  def prepareDataPairs: List[Tuple2[QBERs, Channels]] = {
    val qberSections = worker.Storage.range("TDCLocal", startTime, stopTime, by = "FetchTime",
      filter = Map("FetchTime" -> 1, "Data.MDIQKDQBER.ChannelMonitorSync" -> 1)
    ).asInstanceOf[List[Map[String, Any]]].map(meta => new QBERSection(meta))
    val qbersList = QBERs(qberSections)

    //        val channelSections = worker.Storage.range("MDIChannelMonitor", LocalDateTime.of(2020, 6, 9, 12, 22).toString, LocalDateTime.of(2020, 6, 9, 12, 40).toString,
    //          Map("Data.Triggers" -> 1, "Data.TimeFirstSample" -> 1, "Data.TimeLastSample" -> 1)).asInstanceOf[List[Map[String, Any]]].map(meta => new ChannelSection(meta))
    //        val channelsList = Channels(channelSections)
    //
    //        qbersList.map(qber => (qber, channelsList.filter(channel => Math.abs(qber.systemTime - channel.channelMonitorSyncs.head) < 3).headOption)).filter(_._2.isDefined).map(z => (z._1, z._2.get))
    qbersList.map(qber => (qber, null))
  }

  val dataPairBuffer = prepareDataPairs.toBuffer

  while (dataPairBuffer.nonEmpty) {
    val dataPair = dataPairBuffer.head
    try {
      val dpp = new DataPairParser(dataPair._1, dataPair._2)
      //      dpp.parse()
      dataPairBuffer.remove(0)
      println("parsed")
    } catch {
      case e: Throwable => println(e)
    }
  }

  object HOMandQBEREntry {
    private val bases = List("O", "X", "Y", "Z")
    val HEAD = s"Threshold, Ratio, ValidTime, " +
      (List("XX", "YY", "All").map(bb => List("Dip", "Act").map(position => bb + position)).flatten.mkString(", ")) + ", " +
      (bases.map(a => bases.map(b => List("Correct", "Wrong").map(cw => a + b + " " + cw))).flatten.flatten.mkString(", "))
  }

  class HOMandQBEREntry(val ratioLow: Double, val ratioHigh: Double, val powerOffsets: Tuple2[Double, Double] = (0, 0), val powerInvalidLimit: Double = 4.5) {
    private val homCounts = new Array[Double](6)
    private val qberCounts = new Array[Int](32)
    private val validSectionCount = new AtomicInteger(0)

    def ratioAcceptable(rawPower1: Double, rawPower2: Double) = {
      val power1 = rawPower1 - (if (ignoredChannel == 0) powerOffsets._1 else 0)
      val power2 = rawPower2 - (if (ignoredChannel == 1) powerOffsets._2 else 0)
      val actualRatio = if (power2 == 0) 0 else power1 / power2
      if (power1 > powerInvalidLimit || power2 > powerInvalidLimit) false
      else (actualRatio >= ratioLow) && (actualRatio < ratioHigh)
    }

    def append(qberEntry: QBEREntry) = {
      val homs = qberEntry.HOMs
      Range(0, 3).foreach(kk => {
        homCounts(kk * 2) += homs(kk * 2)
        homCounts(kk * 2 + 1) += homs(kk * 2 + 1)
      })
      val qbers = qberEntry.QBERs
      Range(0, qberCounts.size).foreach(kk => qberCounts(kk) += qbers(kk))
      validSectionCount.incrementAndGet
    }

    def toData(): Array[Double] = Array[Double](ratioLow, ratioHigh, validSectionCount.get) ++ homCounts ++ qberCounts.map(_.toDouble)
  }

  class DataPairParser(val qbers: QBERs, val channels: Channels) {
    private val hasExternalPowerMonitor = channels != null
    performTimeMatch
    performEntryMatch
//    val timeMatchedQBEREntries = if (hasExternalPowerMonitor) qbers.entries.filter(e => e.relatedPowerCount > 0) else qbers.entries
    //    val powerOffsets = (timeMatchedQBEREntries.map(p => p.relatedPowers._1).min, timeMatchedQBEREntries.map(p => p.relatedPowers._2).min)

    //    def parse() = {
    //      val result = new mutable.HashMap[String, Any]()
    //      result("CountChannelRelations") = countChannelRelations()
    //      val halfRatio = Range(0, 200).map(i => math.pow(1.02, i))
    //      val ratios = halfRatio.reverse.dropRight(1).map(a => 1 / a) ++ halfRatio
    //      result("HOMandQBERs") = HOMandQBERs(ratios.toList)
    //      worker.Storage.append("MDIQKD_DataReviewer", result)
    //    }

    private def performTimeMatch = {
      if (hasExternalPowerMonitor) {
        val qberSyncPair = qbers.channelMonitorSyncs
        val timeUnit = (qberSyncPair(1) - qberSyncPair(0)) / (channels.riseIndices(1) - channels.riseIndices(0))
        Range(channels.riseIndices(0), channels.riseIndices(1)).foreach(i => channels.entries(i).tdcTime set (i - channels.riseIndices(0)).toDouble * timeUnit + qberSyncPair(0))
      }
    }

    private def performEntryMatch = {
      if (hasExternalPowerMonitor) {
        val channelSearchIndexStart = new AtomicInteger(0)
        qbers.entries.foreach(qberEntry => {
          val channelSearchIndex = new AtomicInteger(channelSearchIndexStart get)
          val break = new AtomicBoolean(false)
          while (channelSearchIndex.get() < channels.entries.size && !break.get) {
            val channelEntry = channels.entries(channelSearchIndex.get)
            if (channelEntry.tdcTime.get < qberEntry.tdcStart) {
              channelSearchIndex.incrementAndGet
              channelSearchIndexStart.incrementAndGet
            } else if (channelEntry.tdcTime.get < qberEntry.tdcStop) {
              qberEntry.appendPowers(channelEntry.power1, channelEntry.power2)
              channelSearchIndex.incrementAndGet
            } else break set true
          }
        })
      } else qbers.entries.foreach(qberEntry => qberEntry.appendPowers(qberEntry.counts(0), qberEntry.counts(1)))
    }

    //    private def countChannelRelations(): Map[String, Any] = {
    //      val counts = timeMatchedQBEREntries.map(_.counts)
    //      val powers = timeMatchedQBEREntries.map(_.relatedPowers)
    //      Map("Counts 1" -> counts.map(_ (0)), "Counts 2" -> counts.map(_ (1)), "Powers 1" -> powers.map(_._1), "Powers 2" -> powers.map(_._2))
    //    }
    //
    //    private def HOMandQBERs(ratios: List[Double]) = {
    //      val ratioPairs = (List(0) ++ ratios).zip(ratios ++ List(Double.MaxValue))
    //      val homAndQberEntries = ratioPairs.map(ratioPair => new HOMandQBEREntry(ratioPair._1, ratioPair._2, powerOffsets)).toArray
    //      timeMatchedQBEREntries.foreach(entry => {
    //        val relatedPowers = entry.relatedPowers
    //        homAndQberEntries.filter(_.ratioAcceptable(relatedPowers._1, relatedPowers._2)).foreach(hqe => hqe.append(entry))
    //      })
    //      val totalEntryCount = timeMatchedQBEREntries.size
    //      val r = homAndQberEntries.map(e => e.toData()).toList
    //      Map("TotalEntryCount" -> totalEntryCount, "SortedEntries" -> r)
    //    }
  }

  object QBERs {
    def apply(entries: List[QBERSection]) = {
      val syncedEntryIndices = entries.zipWithIndex.filter(z => z._1.slowSync.isDefined).map(_._2)
      syncedEntryIndices.dropRight(1).zip(syncedEntryIndices.drop(1)).map(iz => new QBERs(entries.slice(iz._1, iz._2 + 1)))
    }
  }

  class QBERs(val sections: List[QBERSection]) {
    val systemTime = sections.head.pcTime
    val TDCTimeOfSectionStart = sections(0).tdcStart
    val channelMonitorSyncs = List(sections.head, sections.last).map(s => (s.slowSync.get - TDCTimeOfSectionStart) / 1e12)
    val valid = math.abs(channelMonitorSyncs(1) - channelMonitorSyncs(0) - 10) < 0.001

    lazy val entries = sections.map(section => {
      val entryCount = section.contentCountEntries.size
      Range(0, entryCount).map(i => {
        val entryTDCStartStop = List(i, i + 1).map(j => ((section.tdcStop - section.tdcStart) / entryCount * j + section.tdcStart - TDCTimeOfSectionStart) / 1e12)
        val entryHOMs = section.contentHOMEntries.map(j => j(i))
        val entryQBERs = section.contentQBEREntries(i)
        val entryCounts = section.contentCountEntries(i)
        new QBEREntry(entryTDCStartStop(0), entryTDCStartStop(1), entryHOMs, entryCounts, entryQBERs)
      })
    }).flatten.toArray
  }

  class QBERSection(meta: Map[String, Any]) {
    private val data = meta("Data").asInstanceOf[Map[String, Any]]
    private val mdiqkdQberMeta = data("MDIQKDQBER").asInstanceOf[Map[String, Any]]
    private val syncs = mdiqkdQberMeta("ChannelMonitorSync").asInstanceOf[IterableOnce[Any]].iterator.toArray
    private val dbID = meta("_id").toString
    val tdcStart: Long = syncs(0)
    val tdcStop: Long = syncs(1)
    val slowSync: Option[Long] = if (syncs.size > 2) Some(syncs(2)) else None
    val pcTime: Long = ZonedDateTime.parse(meta("FetchTime").toString).toEpochSecond

    lazy private val content = worker.Storage.get("TDCLocal", dbID, Map("Data.DataBlockCreationTime" -> 1, "Data.MDIQKDQBER" -> 1)).asInstanceOf[Map[String, Any]]
    lazy private val contentData = content("Data").asInstanceOf[Map[String, Any]]
    lazy private val contentQBER = contentData("MDIQKDQBER").asInstanceOf[Map[String, Any]]
    lazy val contentQBEREntries = contentQBER("QBER Sections").asInstanceOf[List[List[Int]]].map(_.toArray).toArray
    lazy val contentHOMEntries = contentQBER("HOM Sections").asInstanceOf[List[List[Double]]].map(_.toArray).toArray
    lazy val contentCountEntries = contentQBER("Count Sections").asInstanceOf[List[List[Int]]].map(_.toArray).toArray
  }

  class QBEREntry(val tdcStart: Double, val tdcStop: Double, val HOMs: Array[Double], val counts: Array[Int], val QBERs: Array[Int]) {
    private val relatedPower1 = new ArrayBuffer[Double]()
    private val relatedPower2 = new ArrayBuffer[Double]()

    def appendPowers(power1: Double, power2: Double) = {
      relatedPower1 += power1
      relatedPower2 += power2
    }

    def relatedPowerCount = relatedPower1.size

    def relatedPowers =
      if (relatedPowerCount == 0) (0.0, 0.0)
      else (relatedPower1.sum / relatedPowerCount, relatedPower2.sum / relatedPowerCount)
  }

  object Channels {
    def apply(entries: List[ChannelSection]) = {
      val syncedEntryIndices = entries.zipWithIndex.filter(z => z._1.trigger.isDefined).map(_._2)
      syncedEntryIndices.dropRight(1).zip(syncedEntryIndices.drop(1)).map(iz => new Channels(entries.slice(iz._1, iz._2 + 1)))
    }
  }

  class Channels(val sections: List[ChannelSection]) {
    val channelMonitorSyncs = List(sections.head, sections.last).map(s => s.trigger.get / 1000)
    val valid = math.abs(channelMonitorSyncs(1) - channelMonitorSyncs(0) - 10) < 0.1
    //  val systemTimes = sections.map(section => section("SystemTime"))
    lazy val entries = sections.map(section => {
      val channel1 = section.contentChannel1
      val channel2 = section.contentChannel2
      val pcTimeUnit = (section.timeLastSample - section.timeFirstSample) / (channel1.size - 1)
      Range(0, channel1.size).map(i => new ChannelEntry(channel1(i), channel2(i), section.timeFirstSample + i * pcTimeUnit))
    }).flatten.toArray
    lazy val riseIndices = channelMonitorSyncs.map(s => entries.indexWhere(_.pcTime > s))
  }

  class ChannelSection(meta: Map[String, Any]) {
    private val data = meta("Data").asInstanceOf[Map[String, Any]]
    private val triggers = data("Triggers").asInstanceOf[List[Any]].map(i => {
      val d: Double = i
      d
    })
    val dbID = meta("_id").toString
    val trigger = triggers.headOption
    private val timeFirstSample_ms: Double = data("TimeFirstSample")
    private val timeLastSample_ms: Double = data("TimeLastSample")
    val timeFirstSample = timeFirstSample_ms / 1e3
    val timeLastSample = timeLastSample_ms / 1e3

    lazy private val content = worker.Storage.get("MDIChannelMonitor", dbID, Map("Data.Channel1" -> 1, "Data.Channel2" -> 1)).asInstanceOf[Map[String, Any]]
    lazy private val contentData = content("Data").asInstanceOf[Map[String, Any]]
    lazy val contentChannel1 = contentData("Channel1").asInstanceOf[List[Double]].toArray
    lazy val contentChannel2 = contentData("Channel2").asInstanceOf[List[Double]].toArray
  }

  class ChannelEntry(val power1: Double, val power2: Double, val pcTime: Double) {
    val tdcTime = new AtomicReference[Double](-1)
  }

}

object Parser extends App {
  val worker = IFWorker("tcp://127.0.0.1:224", "TDCLocalParserTest")
  Thread.sleep(1000)
  try {
    val reviewer = new Reviewer(worker, "2020-04-30T23:34+08:00", "2020-05-01T00:59+08:00")
  }
  catch {
    case e: Throwable => e.printStackTrace()
  } finally {
    worker.close()
  }
}