package com.interactionfree.instrument.adc

import java.time.{LocalDateTime, ZonedDateTime}
import java.util.concurrent.atomic.{AtomicBoolean, AtomicInteger, AtomicLong, AtomicReference}
import scala.io.Source
import com.interactionfree.{IFWorker, MsgpackSerializer}
import Automation.BDaq._
import scala.collection.mutable.ListBuffer
import java.io.BufferedOutputStream
import java.io.FileOutputStream
import java.io.PrintWriter

object ADCMonitor extends App {
  println("ChannelMonitor started!")
  val startTime = System.currentTimeMillis()
  val clockRate = 10000
  val recordCollection = "TFQKD_ChannelMonitor"
  val target = new ADCTarget(clockRate)
  val worker = IFWorker("tcp://192.168.25.5:224", "TFQKD_ChannelMonitor", target)
  val asyInvoker = worker.asynchronousInvoker("Storage")

  val deviceName = "PCIE-1816H,BID#0"
  val valueRange = "+/- 5 V"
  val aiCtrl = new WaveformAiCtrl()
  aiCtrl.setSelectedDevice(new DeviceInformation(deviceName))
  val channels = aiCtrl.getChannels()
  channels.foreach(c => c.setSignalType(AiSignalType.SingleEnded))

  aiCtrl.getConversion().setChannelStart(0)
  aiCtrl.getConversion().setChannelCount(3)
  aiCtrl.getRecord().setSectionLength(clockRate)
  aiCtrl.getRecord().setSectionCount(0) //0 means Streaming mode;
  aiCtrl.getConversion().setClockRate(clockRate)
  aiCtrl.addDataReadyListener(new DataReadyEventListener())

  val startTimeMilli = System.currentTimeMillis()
  val startTimeNano = System.nanoTime()
  val previousTime = new AtomicReference[Option[Long]](None)
  val sectionIndex = new AtomicInteger(0)
  val lastDiff = new AtomicLong(-100000000)
  val triggerThreshold = 1

  class DataReadyEventListener extends BfdAiEventListener {
    def BfdAiEvent(sender: Any, args: BfdAiEventArgs) = {
      val currentTime = startTimeMilli + ((System.nanoTime() - startTimeNano) / 1e6).toLong

      try {
        // val diff = currentTime - startTimeMilli - sectionIndex.getAndIncrement() * 1000
        // // println(s"DIFF = $diff")
        // if (lastDiff.get != -100000000 && math.abs(lastDiff.get - diff) > 100) {
        //   //        println("exiting...")
        //   val stopTime = System.currentTimeMillis()
        //   println(s"runned ${(stopTime - startTime) / 1000} s.")
        //   //        aiCtrl.Stop()
        //   //      System.exit(0)
        //   println("Error!!!")
        // }
        // lastDiff set diff

        if (args.Count % 3 != 0) println(s"Not 3N!!!! ${args.Count}")
        val data = new Array[Double](args.Count)
        val errorCode = aiCtrl.GetData(args.Count, data, 0, null, null, null, null)
        if (previousTime.get.isDefined) {
          // val timeStep = (currentTime - previousTime.get.get) / 1.0 / clockRate
          //        val dbd = Range(0, clockRatePerChan).toList.map(i => data.slice(i * 3, i * 3 + 3).toList ++ List(previousTime.get.get + i * timeStep))
          val dataSize = args.Count / 3
          val dbd = Range(0, dataSize).map(i => data.slice(i * 3, i * 3 + 3)).toArray
          target.record(dbd)

          if (target.isStoring()) {
            // println("Store!!!")
            val data = dbd
            val dataTrigger = data.map(r => r(0))
            val triggerIndices = dataTrigger.dropRight(1).zip(dataTrigger.drop(1)).zipWithIndex.filter(z => (z._1._1 < triggerThreshold) && (z._1._2 > triggerThreshold)).map(z => z._2)
            val result = Map(
              "TimeBegin" -> previousTime.get.get,
              "TimeEnd" -> currentTime,
              "Channel1" -> MsgpackSerializer.serialize(data.map(r => (r(1) / 5 * 10000).toShort)),
              "Channel2" -> MsgpackSerializer.serialize(data.map(r => (r(2) / 5 * 10000).toShort)),
              "Triggers" -> triggerIndices
            )
            //            val dump = Map("Data" -> dbd, "TimeDuration" -> List(previousTime.get.get, currentTime))
            asyInvoker.append(recordCollection, result, fetchTime = LocalDateTime.now().toString.dropRight(3) + "+08:00")
          }
        }
      } catch {
        case e: Throwable => e.printStackTrace()
      }
      previousTime set Some(currentTime)
    }
  }

  aiCtrl.Start()
  Source.stdin.getLines().filter(line => line.toLowerCase() == "q").next()
  aiCtrl.Stop()
  aiCtrl.Release()
  worker.close()
}

class ADCTarget(val clockRate: Double) {
  private val voltages = new AtomicReference[Array[Array[Double]]](null)
  private val recordTime = new AtomicLong(System.currentTimeMillis())
  //  val recordingChannelReversed = new AtomicBoolean(false)
  // val storeConfigChannel1 = new AtomicInteger(0)
  // val storeConfigChannel2 = new AtomicInteger(1)

  def record(r: Array[Array[Double]]) = {
    this.voltages set r
    recordTime set System.currentTimeMillis()
    // val out = new PrintWriter(s"${System.currentTimeMillis()}.csv")
    // r.foreach(row => {
    //   out.println(row.map(item => item.toString()).mkString(", "))
    // })
    // out.close()
  }

  def getRecentVoltages(validity: Double = 2, aperture: Double = 0.8): List[Double] = if (System.currentTimeMillis() - recordTime.get > validity * 1e3) Nil
  else {
    val sampleCount = (aperture * clockRate).toInt
    val data = voltages.get
    if (data == null || data.isEmpty) Nil
    else
      Range(0, data(0).size)
        .map(ch => {
          val dch = data.map(di => di(ch))
          val slicedDCH = dch.slice(dch.size - sampleCount, dch.size)
          slicedDCH.sum / slicedDCH.size
        })
        .toList
  }

  private val storing = new AtomicBoolean(false)

  def setStoring(s: Boolean) = storing.set(s)

  def isStoring() = storing.get()

  //  def setRecordingChannelReversed(isReversed: Boolean) = recordingChannelReversed set isReversed
  //
  // def configStorage(c1: Int, c2: Int) = {
  //   storeConfigChannel1 set c1
  //   storeConfigChannel2 set c2
  // }
}
