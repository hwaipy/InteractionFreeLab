package com.interactionfree.instrument.tdc

import com.interactionfree.IFException
import com.interactionfree.NumberTypeConversions._

import scala.collection.mutable
import scala.collection.mutable.ArrayBuffer
import scala.collection.mutable.ListBuffer

abstract class Analyser {
  private var on = false
  private val configuration = new mutable.HashMap[String, Tuple2[Any, Any => Boolean]]()

  def turnOn(paras: Map[String, Any] = Map()): Unit = {
    on = true
    configure(paras)
  }

  def turnOff(): Unit = on = false

  def isTurnedOn: Boolean = on

  def dataIncome(dataBlock: DataBlock): Option[Map[String, Any]] = if (on) Some(analysis(dataBlock) ++ Map("Configuration" -> configuration.map(e => (e._1, e._2._1)).toMap)) else None

  protected def analysis(dataBlock: DataBlock): Map[String, Any]

  def configure(paras: Map[String, Any]): Unit =
    paras.foreach(e =>
      configuration.get(e._1) match {
        case None     => throw new IFException(s"[${e._1}] is not a valid configuration key.")
        case Some(vv) => if (vv._2(e._2)) configuration(e._1) = (e._2, vv._2) else throw new IFException(s"Configuration ${e._1} -> ${e._2} is not valid.")
      }
    )

  protected def setConfiguration(key: String, defaultValue: Any, validator: Any => Boolean = a => true): Unit = configuration(key) = (defaultValue, validator)

  def getConfigurations: Map[String, Any] = configuration.map(z => (z._1, z._2._1)).toMap

  def getConfiguration(key: String) =
    configuration.get(key) match {
      case None     => throw new IFException(s"[$key] is not a valid configuration key.")
      case Some(vv) => vv._1
    }
}

object Validator {
  private def wrap(validator: Any => Boolean) =
    (any: Any) =>
      try {
        validator(any)
      } catch {
        case e: Throwable => false
      }

  def int(min: Int = Int.MinValue, max: Int = Int.MaxValue) = wrap(value => anyToInt(value) >= min && anyToInt(value) <= max)

  def double(min: Double = Double.NegativeInfinity, max: Double = Double.PositiveInfinity) = wrap(value => anyToDouble(value) >= min && anyToDouble(value) <= max)
}

class CounterAnalyser extends Analyser {

  override protected def analysis(dataBlock: DataBlock): Map[String, Int] = dataBlock.sizes.zipWithIndex.map(z => (z._2.toString(), z._1)).toMap
}

class MultiHistogramAnalyser(channelCount: Int) extends Analyser {
  setConfiguration("Sync", 0, Validator.int(0, channelCount - 1))
  setConfiguration("Signals", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < channelCount))
  setConfiguration("ViewStart", -100000, Validator.double())
  setConfiguration("ViewStop", 100000, Validator.double())
  setConfiguration("BinCount", 1000, Validator.int(1, 10000))
  setConfiguration("Divide", 1, Validator.int(min = 1))

  override protected def analysis(dataBlock: DataBlock) = {
    val syncChannel: Int = getConfiguration("Sync")
    val signalChannels = getConfiguration("Signals").asInstanceOf[List[Int]]
    val viewStart: Long = getConfiguration("ViewStart")
    val viewStop: Long = getConfiguration("ViewStop")
    val binCount: Int = getConfiguration("BinCount")
    val divide: Int = getConfiguration("Divide")
    val tList = dataBlock.getContent(syncChannel)
    val viewFrom = viewStart
    val viewTo = viewStop
    val histograms = signalChannels.map(signalChannel => {
      val deltas = new ArrayBuffer[Long]()
      val sList = dataBlock.getContent(signalChannel)
      if (tList.size > 0 && sList.size > 0) {
        var preStartT = 0
        val lengthT = tList.size
        var sp = 0
        while (sp < sList.size) {
          val s = sList(sp)
          var cont = true
          while (preStartT < lengthT && cont) {
            val t = tList(preStartT)
            val delta = s - t
            if (delta > viewTo) preStartT += 1 else cont = false
          }
          var tIndex = preStartT
          cont = true
          while (tIndex < lengthT && cont) {
            val t = tList(tIndex)
            val delta = s - t
            if (delta > viewFrom) {
              deltas += delta
              tIndex += 1
            } else cont = false
          }
          sp += 1
        }
      }
      new Histogram(deltas.toArray, binCount, viewFrom, viewTo, divide).yData.toList
    })
    Map[String, Any]("Histograms" -> histograms)
  }
}

class ExceptionMonitorAnalyser(channelCount: Int) extends Analyser {
  setConfiguration("SyncChannels", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < channelCount))

  override protected def analysis(dataBlock: DataBlock) = {
    val syncChannels: List[Int] = getConfiguration("SyncChannels").asInstanceOf[List[Int]]
    val reverseCounts = dataBlock.content match {
      case Some(content) => content.map(countReverse)
      case None          => dataBlock.sizes.map(_ => -1)
    }
    val syncs = dataBlock.content match {
      case Some(content) => syncChannels.map(sc => sc.toString -> syncMonitor(content(sc))).toMap
      case None          => syncChannels.map(_ => {})
    }
    Map[String, Any]("ReverseCounts" -> reverseCounts, "SyncMonitor" -> syncs)
  }

  private def syncMonitor(list: Array[Long]) =
    if (list.size >= 2) {
      var i = 0
      var max = Long.MinValue
      var min = Long.MaxValue
      while (i < list.size - 1) {
        val delta = list(i + 1) - list(i)
        if (delta > max) max = delta
        if (delta < min) min = delta
        i += 1
      }
      val average = (list.last - list.head) / (list.size - 1.0)
      Map("Average" -> average, "Max" -> max, "Min" -> min)
    }

  private def countReverse(list: Array[Long]) = {
    var i = 0
    var count = 0
    while (i < list.size - 1) {
      if (list(i) > list(i + 1)) count += 1
      i += 1
    }
    count
  }
}

class EncodingAnalyser(channelCount: Int, randomNumberLimit: Int) extends Analyser {
  setConfiguration("RandomNumbers", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < randomNumberLimit))
  setConfiguration("Period", 10000, Validator.double(min = 0))
  setConfiguration("TriggerChannel", 0, Validator.int(0, channelCount - 1))
  setConfiguration("SignalChannel", 1, Validator.int(0, channelCount - 1))
  setConfiguration("BinCount", 100, Validator.int(1, 1000))
  setConfiguration("Histograms", Map(), value => value.asInstanceOf[Map[String, List[Int]]].forall(entry => entry._2.size > 0 && entry._2.forall(c => c >= 0 && c < randomNumberLimit)))

  override protected def analysis(dataBlock: DataBlock) = {
    val randomNumbers: List[Int] = getConfiguration("RandomNumbers").asInstanceOf[List[Int]]
    val viewingHistograms: Map[String, List[Int]] = getConfiguration("Histograms").asInstanceOf[Map[String, List[Int]]]
    val period: Double = getConfiguration("Period")
    val triggerChannel: Int = getConfiguration("TriggerChannel")
    val signalChannel: Int = getConfiguration("SignalChannel")
    val binCount: Int = getConfiguration("BinCount")
    val map = mutable.HashMap[String, Any]()

    val triggerList = dataBlock.getContent(triggerChannel)
    val signalList = dataBlock.getContent(signalChannel)
    val meta = this.meta(triggerList, signalList, period, randomNumbers.toArray)
    val metaRNs = meta._1
    val metaDeltas = meta._2

    val result = Range(0, randomNumberLimit).toArray.map(_ => new ArrayBuffer[Long]())
    var i = 0
    while (i < meta._1.size) {
      val rn = metaRNs(i)
      val delta = metaDeltas(i)
      result(rn) += delta
      i += 1
    }
    val histograms = Range(0, randomNumberLimit).map(rn => new Histogram(result(rn).toArray, binCount, 0, period.toLong, 1))

    viewingHistograms.foreach(entry => {
      val mergedYData = new Array[Int](binCount)
      entry._2.foreach(rn => {
        val yData = histograms(rn).yData
        var i = 0;
        while (i < binCount) {
          mergedYData(i) += yData(i)
          i += 1
        }
      })
      map.put(s"Histogram[${entry._1}]", mergedYData.toList)
      map.put(s"PulseCount[${entry._1}]", entry._2.map(rn => randomNumbers.count(_ == rn)).sum)
    })
    // Range(0, randomNumberLimit).map(rn => {
    //   val histoPulse = new Histogram(result(rn).toArray, binCount, 0, period.toLong, 1)
    //   map.put(s"Histogram with RandomNumber [${rn}]", histoPulse.yData.toList)
    //   map.put(s"Pulse Count of RandomNumber [${rn}]", randomNumbers.count(_ == rn))
    // })
    map.toMap
  }

  private def meta(triggerList: Array[Long], signalList: Array[Long], period: Double, randomNumbers: Array[Int]) = {
    val triggerIterator = triggerList.iterator
    var currentTrigger = if (triggerIterator.hasNext) triggerIterator.next() else 0
    var nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
    var iSignal = 0
    val rnSize = randomNumbers.size
    val metaRNs = new Array[Int](signalList.size)
    val metaDeltas = new Array[Long](signalList.size)
    while (iSignal < signalList.size) {
      val time = signalList(iSignal)
      while (time >= nextTrigger) {
        currentTrigger = nextTrigger
        nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
      }
      val pulseIndex = ((time - currentTrigger) / period).toLong
      val randomNumberIndex = (pulseIndex % rnSize).toInt
      metaRNs(iSignal) = randomNumbers(if (randomNumberIndex >= 0) randomNumberIndex else randomNumberIndex + randomNumbers.size)
      metaDeltas(iSignal) = (time - currentTrigger - period * pulseIndex).toLong
      iSignal += 1
    }
    (metaRNs, metaDeltas)
  }
}

class ChannelMonitorAnalyser(channelCount: Int) extends Analyser {
  setConfiguration("SyncChannel", 2, Validator.int(0, channelCount - 1))
  setConfiguration("Channels", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < channelCount))
  setConfiguration("SectionCount", 100, Validator.int(1, 1000))

  override protected def analysis(dataBlock: DataBlock) = {
    val map = mutable.HashMap[String, Any]()
    val syncChannel: Int = getConfiguration("SyncChannel")
    val sectionCount: Int = getConfiguration("SectionCount")
    val channels: List[Int] = getConfiguration("Channels").asInstanceOf[List[Int]]

    val syncList = dataBlock.getContent(syncChannel)
    map.put("DataBlockBegin", dataBlock.dataTimeBegin)
    map.put("DataBlockEnd", dataBlock.dataTimeEnd)
    map.put(
      "Sync",
      syncList.size match {
        case s if s > 10 => {
          println("Error: counting rate at syncChannel exceed 10!")
          new Array[Long](0)
        }
        case s => syncList
      }
    )
    val countSections = channels
      .map(channel =>
        (
          channel.toString, {
            val countSectionsForChannel = new Array[Int](sectionCount)
            val list = dataBlock.getContent(channel)
            var i = 0;
            val sectionTimeReverse = sectionCount.toDouble / (dataBlock.dataTimeEnd - dataBlock.dataTimeBegin)
            while (i < list.size) {
              val sectionIndex = ((list(i) - dataBlock.dataTimeBegin) * sectionTimeReverse).toInt
              if (sectionIndex >= 0 && sectionIndex < sectionCount) countSectionsForChannel(sectionIndex) += 1
              i += 1
            }
            countSectionsForChannel
          }
        )
      )
      .toMap
    map.put("CountSections", countSections)
    map.toMap
  }
}

class MDIQKDQBERAnalyser(channelCount: Int, randomNumberLimit: Int) extends Analyser {
  setConfiguration("AliceRandomNumbers", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < randomNumberLimit))
  setConfiguration("BobRandomNumbers", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < randomNumberLimit))
  setConfiguration("Period", 10000, Validator.double(min = 0))
  setConfiguration("PulsePosition", 5000, Validator.double(min = 0))
  setConfiguration("Gate", 1000, Validator.double(min = 0))
  setConfiguration("TriggerChannel", 0, Validator.int(0, channelCount - 1))
  setConfiguration("Channel 1", 4, Validator.int(0, channelCount - 1))
  setConfiguration("Channel 2", 5, Validator.int(0, channelCount - 1))
//   configuration("Channel Monitor Alice") = 4
//   configuration("Channel Monitor Bob") = 5
//   configuration("QBERSectionCount") = 1000
//   configuration("HOMSidePulses") = List(-100, -99, -98, 98, 99, 100)
//   configuration("ChannelMonitorSyncChannel") = 2
//   val executionContext = ExecutionContext.fromExecutorService(Executors.newFixedThreadPool(4))
//   private val benchMarker = ListBuffer[BenchMarking]()

  override protected def analysis(dataBlock: DataBlock) = {
//     benchMarker.foreach(b => b.tag("begin analysis"))

    val map = mutable.HashMap[String, Any]()
//     val randomNumbersAlice = configuration("AliceRandomNumbers").asInstanceOf[List[Int]].map(r => new RandomNumber(r)).toArray
//     val randomNumbersBob = configuration("BobRandomNumbers").asInstanceOf[List[Int]].map(r => new RandomNumber(r)).toArray
//     val period: Double = configuration("Period")
//     val delay: Double = configuration("Delay")
//     val pulseDiff: Double = configuration("PulseDiff")
//     val gate: Double = configuration("Gate")
//     val triggerChannel: Int = configuration("TriggerChannel")
//     val channel1: Int = configuration("Channel 1")
//     val channel2: Int = configuration("Channel 2")
//     val channelMonitorAlice: Int = configuration("Channel Monitor Alice")
//     val channelMonitorBob: Int = configuration("Channel Monitor Bob")
//     val qberSectionCount: Int = configuration("QBERSectionCount")
//     val HOMSidePulses = configuration("HOMSidePulses").asInstanceOf[List[Int]]
//     val channelMonitorSyncChannel: Int = configuration("ChannelMonitorSyncChannel")

//     val triggerList = dataBlock.content(triggerChannel)
//     val signalList1 = dataBlock.content(channel1)
//     val signalList2 = dataBlock.content(channel2)
//     val monitorListAlice = dataBlock.content(channelMonitorAlice)
//     val monitorListBob = dataBlock.content(channelMonitorBob)

//     // bellow consider parallels
//     benchMarker.foreach(b => b.tag("config done"))

//     val item1sFuture = Future[Tuple2[Array[Tuple4[Long, Long, Int, Long]], Array[Tuple4[Long, Long, Int, Long]]]] {
//       val items = analysisSingleChannel(triggerList, signalList1, period, delay, gate, pulseDiff, randomNumbersAlice.size)
//       (items, items.filter(_._3 >= 0))
//     }(executionContext)
//     val item2sFuture = Future[Tuple2[Array[Tuple4[Long, Long, Int, Long]], Array[Tuple4[Long, Long, Int, Long]]]] {
//       val items = analysisSingleChannel(triggerList, signalList2, period, delay, gate, pulseDiff, randomNumbersBob.size)
//       (items, items.filter(_._3 >= 0))
//     }(executionContext)
//     val item1sFutureResult = Await.result(item1sFuture, Duration.Inf)
//     val item2sFutureResult = Await.result(item2sFuture, Duration.Inf)
//     val item1s = item1sFutureResult._1
//     val validItem1s = item1sFutureResult._2
//     val item2s = item2sFutureResult._1
//     val validItem2s = item2sFutureResult._2
//     benchMarker.foreach(b => b.tag("valid items's"))

//     def generateCoincidences(iterator1: Iterator[Tuple4[Long, Long, Int, Long]], iterator2: Iterator[Tuple4[Long, Long, Int, Long]]) = {
//       val item1Ref = new AtomicReference[Tuple4[Long, Long, Int, Long]]()
//       val item2Ref = new AtomicReference[Tuple4[Long, Long, Int, Long]]()

//       def fillRef = {
//         if (item1Ref.get == null && iterator1.hasNext) item1Ref set iterator1.next()
//         if (item2Ref.get == null && iterator2.hasNext) item2Ref set iterator2.next()
//         item1Ref.get != null && item2Ref.get != null
//       }

//       val resultBuffer = new ArrayBuffer[Coincidence]()
//       while (fillRef) {
//         val item1 = item1Ref.get
//         val item2 = item2Ref.get
//         if (item1._1 > item2._1) item2Ref set null
//         else if (item1._1 < item2._1) item1Ref set null
//         else if (item1._2 > item2._2) item2Ref set null
//         else if (item1._2 < item2._2) item1Ref set null
//         else {
//           resultBuffer += new Coincidence(item1._3, item2._3, randomNumbersAlice(item1._2 % randomNumbersAlice.size), randomNumbersBob(item1._2 % randomNumbersBob.size), item1._4, item1._1, item1._2)
//           item1Ref set null
//           item2Ref set null
//         }
//       }
//       resultBuffer.toList
//     }

//     def generateCoincidencesInFuture(delta: Int) = {
//       Future[List[Coincidence]] {
//         val i2it = if (delta == 0) validItem2s.iterator else validItem2s.map(i => (i._1 + delta, i._2, i._3, i._4)).iterator
//         generateCoincidences(validItem1s.iterator, i2it)
//       }(executionContext)
//     }

//     val coincidencesFuture = generateCoincidencesInFuture(0)
//     val sideCoincidencesFutures = HOMSidePulses.map(delta => generateCoincidencesInFuture(delta))

// //    val coincidences = generateCoincidences(validItem1s.iterator, validItem2s.iterator)
//     val coincidences = Await.result(coincidencesFuture, Duration.Inf)
//     val validCoincidences = coincidences.filter(_.valid)
//     val basisMatchedCoincidences = coincidences.filter(_.basisMatched)
//     benchMarker.foreach(b => b.tag("coincidences"))

//     val basisStrings = List("O", "X", "Y", "Z")
//     val qberSections = Range(0, qberSectionCount).toArray.map(i => new Array[Int](4 * 4 * 2)) // 4 basis * 4 basis * (right/wrong)
//     Range(0, 4).foreach(basisAlice => Range(0, 4).foreach(basisBob => {
//       val coincidences = validCoincidences.filter(c => c.randomNumberAlice.intensity == basisAlice && c.randomNumberBob.intensity == basisBob)
//       map.put(s"${basisStrings(basisAlice)}-${basisStrings(basisBob)}, Correct", coincidences.filter(_.isCorrect).size)
//       map.put(s"${basisStrings(basisAlice)}-${basisStrings(basisBob)}, Wrong", coincidences.filterNot(_.isCorrect).size)
//     }))
//     validCoincidences.foreach(c => {
//       val sectionIndex = ((c.triggerTime - dataBlock.dataTimeBegin).toDouble / (dataBlock.dataTimeEnd - dataBlock.dataTimeBegin) * qberSectionCount).toInt
//       val category = (c.randomNumberAlice.intensity * 4 + c.randomNumberBob.intensity) * 2 + (if (c.isCorrect) 0 else 1)
//       if (sectionIndex >= 0 && sectionIndex < qberSections.size) qberSections(sectionIndex)(category) += 1
//     })
//     map.put(s"QBER Sections", qberSections)
//     map.put(s"QBER Sections Detail", s"1000*32 Array. 1000 for 1000 sections. 32 for (Alice[O,X,Y,Z] * 4 + Bob[O,X,Y,Z]) * 2 + (0 for Correct and 1 for Wrong)")
//     benchMarker.foreach(b => b.tag("QBER sections"))

//     val sideCoincidences = sideCoincidencesFutures.map(f => Await.result(f, Duration.Inf).filter(c => (c.r1 == 0) && (c.r2 == 0)))
//     benchMarker.foreach(b => b.tag("side coincidences"))

//     val ccsXX0Coincidences = basisMatchedCoincidences.filter(c => c.randomNumberAlice.isX && c.randomNumberBob.isX).filter(c => (c.r1 == 0) && (c.r2 == 0))
// //    val ccsXXOtherCoincidences = HOMSidePulses.map(delta => generateCoincidences(validItem1s.iterator, validItem2s.map(i => (i._1 + delta, i._2, i._3, i._4)).iterator)
// //      .filter(_.basisMatched).filter(c => c.randomNumberAlice.isX && c.randomNumberBob.isX).filter(c => (c.r1 == 0) && (c.r2 == 0)))
//     val ccsXXOtherCoincidences = sideCoincidences.map(sideCs => sideCs.filter(c => c.randomNumberAlice.isX && c.randomNumberBob.isX))
//     val ccsXX0 = ccsXX0Coincidences.size
//     val ccsXXOther = ccsXXOtherCoincidences.map(_.size)
//     map.put("HOM X0-X0", List(ccsXX0, ccsXXOther.sum.toDouble / ccsXXOther.size))

//     val ccsYY0Coincidences = basisMatchedCoincidences.filter(c => c.randomNumberAlice.isY && c.randomNumberBob.isY).filter(c => (c.r1 == 0) && (c.r2 == 0))
// //    val ccsYYOtherCoincidences = HOMSidePulses.map(delta => generateCoincidences(validItem1s.iterator, validItem2s.map(i => (i._1 + delta, i._2, i._3, i._4)).iterator)
// //      .filter(_.basisMatched).filter(c => c.randomNumberAlice.isY && c.randomNumberBob.isY).filter(c => (c.r1 == 0) && (c.r2 == 0)))
//     val ccsYYOtherCoincidences = sideCoincidences.map(sideCs => sideCs.filter(c => c.randomNumberAlice.isY && c.randomNumberBob.isY))
//     val ccsYY0 = ccsYY0Coincidences.size
//     val ccsYYOther = ccsYYOtherCoincidences.map(_.size)
//     map.put("HOM Y0-Y0", List(ccsYY0, ccsYYOther.sum.toDouble / ccsYYOther.size))

//     val ccsAll0Coincidences = coincidences.filter(c => (c.r1 == 0) && (c.r2 == 0))
// //    val ccsAllOtherCoincidences = HOMSidePulses.map(delta => generateCoincidences(validItem1s.iterator, validItem2s.map(i => (i._1 + delta, i._2, i._3, i._4)).iterator).filter(c => (c.r1 == 0) && (c.r2 == 0)))
//     val ccsAllOtherCoincidences = sideCoincidences

//     val ccsAll0 = ccsAll0Coincidences.size
//     val ccsAllOther = ccsAllOtherCoincidences.map(_.size)
//     map.put("HOM, All0-All0", List(ccsAll0, ccsAllOther.sum.toDouble / ccsAllOther.size))

//     def statisticCoincidenceSection(cll: List[List[Coincidence]]) = {
//       val sections = new Array[Int](qberSectionCount)
//       cll.foreach(cl => cl.foreach(c => {
//         val sectionIndex = ((c.triggerTime - dataBlock.dataTimeBegin).toDouble / (dataBlock.dataTimeEnd - dataBlock.dataTimeBegin) * qberSectionCount).toInt
//         if (sectionIndex >= 0 && sectionIndex < qberSections.size) sections(sectionIndex) += 1
//       }))
//       sections.map(c => c.toDouble / cll.size)
//     }

//     val homSections = Array(List(ccsXX0Coincidences), ccsXXOtherCoincidences, List(ccsYY0Coincidences), ccsYYOtherCoincidences, List(ccsAll0Coincidences), ccsAllOtherCoincidences).map(statisticCoincidenceSection)
//     val homTransposed = Range(0, homSections(0).size).map(_ => new Array[Double](homSections.size)).toArray
//     homSections.zipWithIndex.foreach(z1 => z1._1.zipWithIndex.foreach(z2 => homTransposed(z2._2)(z1._2) = homSections(z1._2)(z2._2)))
//     map.put(s"HOM Sections", homTransposed)
//     benchMarker.foreach(b => b.tag("HOM Sections"))

//     val channelMonitorSyncList = dataBlock.content(channelMonitorSyncChannel)
//     map.put("ChannelMonitorSync", Array[Long](dataBlock.dataTimeBegin, dataBlock.dataTimeEnd) ++ (channelMonitorSyncList.size match {
//       case s if s > 10 => {
//         println("Error: counting rate at ChannelMonitorSyncChannel exceed 10!")
//         new Array[Long](0)
//       }
//       case s => channelMonitorSyncList
//     }))
//     benchMarker.foreach(b => b.tag("CMS"))

//     val countSections = Range(0, qberSectionCount).toArray.map(i => new Array[Int](2))
//     List(monitorListAlice, monitorListBob).zipWithIndex.foreach(z => z._1.foreach(event => {
//       val sectionIndex = ((event - dataBlock.dataTimeBegin).toDouble / (dataBlock.dataTimeEnd - dataBlock.dataTimeBegin) * qberSectionCount).toInt
//       if (sectionIndex >= 0 && sectionIndex < qberSections.size) countSections(sectionIndex)(z._2) += 1
//     }))
//     map.put(s"Count Sections", countSections)
//     benchMarker.foreach(b => b.tag("Count Sections"))
//     benchMarker.foreach(b => b.tag("Finish"))

    map.toMap
  }

//   private def analysisSingleChannel(triggerList: Array[Long], signalList: Array[Long], period: Double, delay: Double, gate: Double, pulseDiff: Double, randomNumberSize: Int) = {
//     val triggerIterator = triggerList.iterator
//     val currentTriggerRef = new AtomicLong(if (triggerIterator.hasNext) triggerIterator.next() else 0)
//     val nextTriggerRef = new AtomicLong(if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue)
//     val meta = signalList.map(time => {
//       while (time >= nextTriggerRef.get) {
//         currentTriggerRef set nextTriggerRef.get
//         nextTriggerRef.set(if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue)
//       }
//       val pulseIndex = ((time - currentTriggerRef.get) / period).toLong
//       val delta = (time - currentTriggerRef.get - period * pulseIndex).toLong
//       val p = if (math.abs(delta - delay) < gate / 2) 0 else if (math.abs(delta - delay - pulseDiff) < gate / 2) 1 else -1
//       ((currentTriggerRef.get / period / randomNumberSize).toLong, pulseIndex, p, currentTriggerRef.get)
//     })
//     meta
//   }
}

// class Coincidence(val r1: Int, val r2: Int, val randomNumberAlice: RandomNumber, val randomNumberBob: RandomNumber, val triggerTime: Long, val triggerIndex: Long, val pulseIndex: Long) {
//   val basisMatched = randomNumberAlice.intensity == randomNumberBob.intensity
//   val valid = (r1 == 0 && r2 == 1) || (r1 == 1 && r2 == 0)
//   val isCorrect = randomNumberAlice.encode != randomNumberBob.encode
// }

// object DebugT {
//   private val previousT = new AtomicLong(System.nanoTime())

//   def tag(msg: String): Unit = {
//     val currentT = System.nanoTime()
//     val deltaT = currentT - previousT.get
//     previousT set currentT
//     println(f"${deltaT / 1e6}%.0f -- $msg")
//   }
// }

//class CoincidenceHistogramAnalyser(channelCount: Int) extends DataAnalyser {
//  configuration("ChannelA") = 0
//  configuration("ChannelB") = 1
//  configuration("ViewStart") = -100000
//  configuration("ViewStop") = 100000
//  configuration("BinCount") = 1000
//
//  override def configure(key: String, value: Any) = {
//    key match {
//      case "ChannelA" => {
//        val sc: Int = value
//        sc >= 0 && sc < channelCount
//      }
//      case "ChannelB" => {
//        val sc: Int = value
//        sc >= 0 && sc < channelCount
//      }
//      case "ViewStart" => true
//      case "ViewStop" => true
//      case "BinCount" => {
//        val sc: Int = value
//        sc > 0 && sc < 2000
//      }
//      case _ => false
//    }
//  }
//
//  override protected def analysis(dataBlock: DataBlock) = {
//    val deltas = new ArrayBuffer[Long]()
//    val syncChannel: Int = configuration("ChannelA")
//    val signalChannel: Int = configuration("ChannelB")
//    val viewStart: Long = configuration("ViewStart")
//    val viewStop: Long = configuration("ViewStop")
//    val binCount: Int = configuration("BinCount")
//    val tList = dataBlock.content(syncChannel)
//    val sList = dataBlock.content(signalChannel)
//    val viewFrom = viewStart
//    val viewTo = viewStop
//    if (tList.size > 0 && sList.size > 0) {
//      var preStartT = 0
//      val lengthT = tList.size
//      sList.foreach(s => {
//        var cont = true
//        while (preStartT < lengthT && cont) {
//          val t = tList(preStartT)
//          val delta = s - t
//          if (delta > viewTo) {
//            preStartT += 1
//          } else cont = false
//        }
//        var tIndex = preStartT
//        cont = true
//        while (tIndex < lengthT && cont) {
//          val t = tList(tIndex)
//          val delta = s - t
//          if (delta > viewFrom) {
//            deltas += delta
//            tIndex += 1
//          } else cont = false
//        }
//      })
//    }
//    val histo = new Histogram(deltas.toArray, binCount, viewFrom, viewTo, 1)
//    Map[String, Any]("Histogram" -> histo.yData.toList)
//  }
//}

class DeltaMetaAnalyser(channelCount: Int) extends Analyser {
  setConfiguration("SyncChannel", 0, Validator.int(0, channelCount - 1))
  setConfiguration("Channel1", 2, Validator.int(0, channelCount - 1))
  setConfiguration("Channel2", 3, Validator.int(0, channelCount - 1))
  setConfiguration("Period", 10000, Validator.double(min = 0))
  setConfiguration("Center", 5000, Validator.double())
  setConfiguration("GateWidth", 1000, Validator.double(min = 0))
  setConfiguration("GroupBy", 25, Validator.int(1, 25000))

  override protected def analysis(dataBlock: DataBlock) = {
    val syncChannel: Int = getConfiguration("SyncChannel")
    val channel1: Int = getConfiguration("Channel1")
    val channel2: Int = getConfiguration("Channel2")
    val period: Double = getConfiguration("Period")
    val center: Double = getConfiguration("Center")
    val gateWidth: Double = getConfiguration("GateWidth")
    val groupBy: Int = getConfiguration("GroupBy")

    val deltaMetas1 = deltaMeta(dataBlock.getContent(syncChannel), dataBlock.getContent(channel1), period).filter(z => z._3 > center - gateWidth / 2 && z._3 < center + gateWidth / 2)
    val deltaMetas2 = deltaMeta(dataBlock.getContent(syncChannel), dataBlock.getContent(channel2), period).filter(z => z._3 > center - gateWidth / 2 && z._3 < center + gateWidth / 2)
    val deltaMetas1A = deltaMetas1.filter(z => z._2 % 2 == 0)
    val deltaMetas1B = deltaMetas1.filter(z => z._2 % 2 == 1)
    val deltaMetas2A = deltaMetas2.filter(z => z._2 % 2 == 0)
    val deltaMetas2B = deltaMetas2.filter(z => z._2 % 2 == 1)
    val deltaMetas1AStat = metaStatByTrigger(deltaMetas1A, groupBy)
    val deltaMetas1BStat = metaStatByTrigger(deltaMetas1B, groupBy)
    val deltaMetas2AStat = metaStatByTrigger(deltaMetas2A, groupBy)
    val deltaMetas2BStat = metaStatByTrigger(deltaMetas2B, groupBy)
    Map[String, Any]("DeltaMetas1AStat" -> deltaMetas1AStat, "DeltaMetas1BStat" -> deltaMetas1BStat, "DeltaMetas2AStat" -> deltaMetas2AStat, "DeltaMetas2BStat" -> deltaMetas2BStat)
  }

  private def metaStatByTrigger(deltaMetas: Array[Tuple3[Int, Int, Int]], groupBy: Int) = deltaMetas.isEmpty match {
    case true => Array[Int](0)
    case false =>  {
      val stat: Array[Int] = new Array[Int]((deltaMetas.last._1 / groupBy + 1).toInt)
      deltaMetas.foreach(deltaMeta => stat((deltaMeta._1 / groupBy).toInt) += 1)
      stat
    }
  }

  private def deltaMeta(triggerList: Array[Long], signalList: Array[Long], period: Double) = {
    val triggerIterator = triggerList.iterator
    var currentTrigger = if (triggerIterator.hasNext) triggerIterator.next() else 0
    var nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
    var iSignal = 0
    var iTrigger = 0
    val deltaMetas = new Array[Tuple3[Int, Int, Int]](signalList.size)
    while (iSignal < signalList.size) {
      val time = signalList(iSignal)
      while (time >= nextTrigger) {
        currentTrigger = nextTrigger
        iTrigger += 1
        nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
      }
      val pulseIndex = ((time - currentTrigger) / period).toInt
      deltaMetas(iSignal) = (iTrigger, pulseIndex, (time - currentTrigger - period * pulseIndex).toInt) //(time - currentTrigger - period * pulseIndex).toLong
      iSignal += 1
    }
    deltaMetas
  }
}

class PhaseComparingAnalyser(channelCount: Int, randomNumberLimit: Int, phaseLimit: Int) extends Analyser {
  setConfiguration("SyncChannel", 0, Validator.int(0, channelCount - 1))
  setConfiguration("Channel1", 2, Validator.int(0, channelCount - 1))
  setConfiguration("Channel2", 3, Validator.int(0, channelCount - 1))
  setConfiguration("Period", 10000, Validator.double(min = 0))
  setConfiguration("Center", 5000, Validator.double())
  setConfiguration("ReferenceGateWidth", 1000, Validator.double(min = 0))
  setConfiguration("SignalGateWidth", 1000, Validator.double(min = 0))
  setConfiguration("SectionPulseCount", 10000, Validator.int(1, 1000000))
  setConfiguration("TriggerPulseCount", 4000, Validator.int(1, 1000000))
  setConfiguration("AliceRandomNumbers", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < randomNumberLimit))
  setConfiguration("BobRandomNumbers", List(1), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < randomNumberLimit))
  setConfiguration("DeltaPhasesReference", List(0, 4, 8, 12), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < phaseLimit))
  setConfiguration("DeltaPhasesSignal", Range(0, 16).map(i => i), value => value.asInstanceOf[List[Int]].forall(c => c >= 0 && c < phaseLimit))

  override protected def analysis(dataBlock: DataBlock) = {
    val syncChannel: Int = getConfiguration("SyncChannel")
    val channel1: Int = getConfiguration("Channel1")
    val channel2: Int = getConfiguration("Channel2")
    val period: Double = getConfiguration("Period")
    val center: Double = getConfiguration("Center")
    val referenceGateWidth: Double = getConfiguration("ReferenceGateWidth")
    val signalGateWidth: Double = getConfiguration("SignalGateWidth")
    val sectionPulseCount: Int = getConfiguration("SectionPulseCount")
    val triggerPulseCount: Int = getConfiguration("TriggerPulseCount")
    val randomNumbersAlice = getConfiguration("AliceRandomNumbers").asInstanceOf[List[Int]].toArray
    val randomNumbersBob = getConfiguration("BobRandomNumbers").asInstanceOf[List[Int]].toArray
  
    val randomNumberDeltasRef = randomNumbersAlice.zip(randomNumbersBob).map(z => {
      if (z._1 >= 64 && z._2 >= 64) {
        ((z._1 - z._2) >> 2) match {
          case dd if dd < 0 => dd + phaseLimit
          case dd if dd >= 0 => dd
        }
      } else -1
    })
    val randomNumberDeltasSignal = randomNumbersAlice.zip(randomNumbersBob).map(z => {
      if (z._1 < 64 && z._2 < 64) {
        ((z._1 - z._2) >> 2) match {
          case dd if dd < 0 => dd + phaseLimit
          case dd if dd >= 0 => dd
        }
      } else -1
    })

    println(randomNumberDeltasRef.toList)
    println(randomNumberDeltasSignal.toList)

    val pcMeta1 = pcMeta(dataBlock.getContent(syncChannel), dataBlock.getContent(channel1), period)
    val pcMeta2 = pcMeta(dataBlock.getContent(syncChannel), dataBlock.getContent(channel2), period)
    
    val deltaMetasRef1 = metaStat(pcMeta1, sectionPulseCount, triggerPulseCount, center, referenceGateWidth, randomNumberDeltasRef)
    //.filter(z => z._3 > center - gateWidth / 2 && z._3 < center + gateWidth / 2)
    // val deltaMetas1A = deltaMetas1.filter(z => z._2 % 2 == 0)
    // val deltaMetas1B = deltaMetas1.filter(z => z._2 % 2 == 1)
    // val deltaMetas2A = deltaMetas2.filter(z => z._2 % 2 == 0)
    // val deltaMetas2B = deltaMetas2.filter(z => z._2 % 2 == 1)
    // val deltaMetas1BStat = metaStatByTrigger(deltaMetas1B, groupBy)
    // val deltaMetas2AStat = metaStatByTrigger(deltaMetas2A, groupBy)
    // val deltaMetas2BStat = metaStatByTrigger(deltaMetas2B, groupBy)
    // Map[String, Any]("DeltaMetas1AStat" -> deltaMetas1AStat, "DeltaMetas1BStat" -> deltaMetas1BStat, "DeltaMetas2AStat" -> deltaMetas2AStat, "DeltaMetas2BStat" -> deltaMetas2BStat)
    Map[String, Any]()
  }

  private def metaStat(deltaMetas: Array[Tuple3[Int, Int, Int]], sectionPulseCount: Int, triggerPulseCount: Int, center: Double, gateWidth: Double, randomNumberDeltas: Array[Int]) = deltaMetas.isEmpty match {
    case true => Array[Int](0)
    case false =>  {
      val validDM = deltaMetas.filter(z => (z._3 > center - gateWidth / 2) && (z._3 < center + gateWidth / 2)).map(z => {
        val pulseIndex = z._1 * triggerPulseCount + z._2
        val randomNumberDelta = randomNumberDeltas(z._2)
      })

  //     val stat: Array[Int] = new Array[Int]((deltaMetas.last._1 / groupBy + 1).toInt)
  //     deltaMetas.foreach(deltaMeta => stat((deltaMeta._1 / groupBy).toInt) += 1)
  //     stat
    }
  }

  private def pcMeta(triggerList: Array[Long], signalList: Array[Long], period: Double) = {
    val triggerIterator = triggerList.iterator
    var currentTrigger = if (triggerIterator.hasNext) triggerIterator.next() else 0
    var nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
    var iSignal = 0
    var iTrigger = 0
    val deltaMetas = new Array[Tuple3[Int, Int, Int]](signalList.size)
    while (iSignal < signalList.size) {
      val time = signalList(iSignal)
      while (time >= nextTrigger) {
        currentTrigger = nextTrigger
        iTrigger += 1
        nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
      }
      val pulseIndex = ((time - currentTrigger) / period).toInt
      deltaMetas(iSignal) = (iTrigger, pulseIndex, (time - currentTrigger - period * pulseIndex).toInt) //(time - currentTrigger - period * pulseIndex).toLong
      iSignal += 1
    }
    deltaMetas
  }
}

class Histogram(deltas: Array[Long], binCount: Int, viewFrom: Long, viewTo: Long, divide: Int) {
  val min = viewFrom.toDouble
  val max = viewTo.toDouble
  val binSize = (max - min) / binCount / divide
  val xData = Range(0, binCount).map(i => (i * binSize + min) + binSize / 2).toArray
  val yData = new Array[Int](binCount)
  initData()

  private def initData(): Unit = {
    var dp = 0
    while (dp < deltas.size) {
      val delta = deltas(dp)
      val deltaDouble = delta.toDouble
      if (deltaDouble < min) {
        /* this data is smaller than min */
      } else if (deltaDouble == max) { // the value falls exactly on the max value
        yData(binCount - 1) += 1
      } else if (deltaDouble > max) {
        /* this data point is bigger than max */
      } else {
        val bin = ((deltaDouble - min) / binSize).toInt % binCount
        yData(bin) += 1
      }
      dp += 1
    }
  }
}
