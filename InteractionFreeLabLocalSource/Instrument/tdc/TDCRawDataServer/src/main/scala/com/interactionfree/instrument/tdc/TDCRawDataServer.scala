package com.interactionfree.instrument.tdc

import java.io.FileInputStream
import java.util.Properties
import java.util.concurrent.Executors
import java.util.concurrent.atomic.{AtomicBoolean, AtomicLong, AtomicReference}
import scala.concurrent.duration.Duration
import scala.collection.mutable
import scala.io.Source
import com.interactionfree.IFWorker
import scala.concurrent.{Await, ExecutionContext, Future}
import java.util.concurrent.LinkedBlockingQueue
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.nio.file.Files
import java.nio.file.Paths
import java.io.RandomAccessFile
import java.io.File
import java.net.URL
import java.net.HttpURLConnection
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream 

object TDCRawDaataServer extends App {
  val properties = new Properties()
  val propertiesIn = new FileInputStream("config.properties")
  properties.load(propertiesIn)
  propertiesIn.close()

  val IFServerAddress = properties.getOrDefault("IFServer.Address", "tcp://172.16.60.200:224").toString
  val IFServerServiceName = properties.getOrDefault("IFServer.ServiceName", "TDCServer_Test").toString

  val process = new TDCRawDataServerProcessor()
  val worker = IFWorker(IFServerAddress, IFServerServiceName, process)
  println(s"TDCRawDataServer started.")
  Source.stdin.getLines().filter(line => line.toLowerCase() == "q").next()
  println("Stoping TDCServer ...")
  worker.close()
  // process.stop()

  // process.fetchDeltaMeta("http://172.16.60.200:1001/", "2021-03-14 16-46-45.879", 0, 2, 10000)

  class TDCRawDataServerProcessor() {
    private def loadDataBlock(dir: String, fetchTime: String) = {
      val date = fetchTime.split(" ").head
      val hour = fetchTime.split(" ")(1).split("-").head
      val url = s"$dir/$date/$hour/$fetchTime.datablock"
      // val raf = new RandomAccessFile(new File(path), "r")
      // val data = new Array[Byte](raf.length().toInt)
      // raf.readFully(data)
      // raf.close()

      val connection = new URL(url).openConnection().asInstanceOf[HttpURLConnection]
      connection.getResponseCode() match {
        case 200 => {
          val dataStream = new ByteArrayOutputStream(connection.getContentLength())
          val in = new BufferedInputStream(connection.getInputStream())
          var cont = true
          val buffer = new Array[Byte](10000)
          while(cont) {
            in.read(buffer) match {
              case -1 => cont = false
              case r => dataStream.write(buffer, 0, r)
            }
          }
          in.close()
          val data = dataStream.toByteArray()
          dataStream.close()
          connection.disconnect()
          DataBlock.deserialize(data)
        }
        case _ => throw new IllegalStateException(s"Resource $url not existed.")
      }
    }

    def fetchRawDataBlock(dir: String, fetchTime: String) = {
      val dataBlock = loadDataBlock(dir, fetchTime)
      Map(
        "CreationTime" -> dataBlock.creationTime,
        "Resolution" -> dataBlock.resolution,
        "DataTimeBegin" -> dataBlock.dataTimeBegin,
        "DataTimeEnd" -> dataBlock.dataTimeEnd,
        "Content" -> dataBlock.getContent
      )
    }

    def fetchDeltaMeta(dir: String, fetchTime: String, triggerChannel: Int, signalChannel: Int, period: Double) = {
      val dataBlock = loadDataBlock(dir, fetchTime)
      deltaMeta(dataBlock.getContent(triggerChannel), dataBlock.getContent(signalChannel), period)
    }

    private def deltaMeta(triggerList: Array[Long], signalList: Array[Long], period: Double) = {
      val triggerIterator = triggerList.iterator
      var currentTrigger = if (triggerIterator.hasNext) triggerIterator.next() else 0
      var nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
      var iSignal = 0
      var iTrigger = 0
      val deltaMetas = new Array[Array[Int]](signalList.size)
      while (iSignal < signalList.size) {
        val time = signalList(iSignal)
        while (time >= nextTrigger) {
          currentTrigger = nextTrigger
          iTrigger += 1
          nextTrigger = if (triggerIterator.hasNext) triggerIterator.next() else Long.MaxValue
        }
        val pulseIndex = ((time - currentTrigger) / period).toInt
        deltaMetas(iSignal) = Array[Int](iTrigger, pulseIndex, (time - currentTrigger - period * pulseIndex).toInt) //(time - currentTrigger - period * pulseIndex).toLong
        iSignal += 1
      }
      deltaMetas
    }
  }
}
