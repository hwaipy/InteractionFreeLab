package com.interactionfree.instrument.tdc

import java.net.ServerSocket
import java.nio.{ByteBuffer, LongBuffer}
import java.util.concurrent.Executors
import java.util.concurrent.atomic.{AtomicLong, AtomicReference}

import scala.collection.mutable.{ArrayBuffer, ListBuffer}
import scala.concurrent.{ExecutionContext, Future}
import com.interactionfree.NumberTypeConversions._
import com.interactionfree.MsgpackSerializer

import scala.collection.IterableOnce
import scala.util.Random

class TDCProcessServer(port: Int, dataIncome: Any => Unit, adapters: List[TDCDataAdapter]) {
  private val executionContext = ExecutionContext.fromExecutorService(Executors.newSingleThreadExecutor(r => {
    val t = new Thread(r)
    t.setDaemon(true)
    t
  }))
  private val tdcParser = new TDCParser(
    new TDCDataProcessor {
      override def process(data: Any): Unit = dataIncome(data)
    },
    adapters.toArray
  )
  private val server = new ServerSocket(port)
  val buffer = new Array[Byte](10000000)
  Future[Any] {
    while (!server.isClosed) {
      val socket = server.accept
      val remoteAddress = socket.getRemoteSocketAddress
      println(s"Connection from $remoteAddress accepted.")
      val totalDataSize = new AtomicLong(0)
      try {
        val in = socket.getInputStream
        while (!socket.isClosed) {
          val read = in.read(buffer)
          if (read < 0) socket.close()
          else {
            totalDataSize.set(totalDataSize.get + read)
            val array = new Array[Byte](read)
            Array.copy(buffer, 0, array, 0, read)
            tdcParser.offer(array)
          }
        }
      } catch {
        case _: Throwable => // e.printStackTrace()
      } finally {
        println(s"End of connection: $remoteAddress. Total Data Size: ${totalDataSize.get}")
      }
    }
  }(executionContext)

  def stop(): Unit = {
    server.close()
    tdcParser.stop()
  }
}

class LongBufferToDataBlockListTDCDataAdapter(channelCount: Int) extends TDCDataAdapter {
  private val dataBlocks = new ArrayBuffer[DataBlock]()

  def offer(data: Any): AnyRef = {
    dataBlocks.clear()
    dataIncome(data)
    dataBlocks.toList
  }

  def flush(data: Any): AnyRef = offer(data)

  private def dataIncome(data: Any): Unit = {
    if (!data.isInstanceOf[LongBuffer]) throw new IllegalArgumentException(s"LongBuffer expected, not ${data.getClass}")
    val buffer = data.asInstanceOf[LongBuffer]
    while (buffer.hasRemaining) {
      val item = buffer.get
      val time = item >> 4
      val channel = (item & 0xf).toInt
      feedTimeEvent(channel, time)
    }
  }

  private val timeEvents = Range(0, channelCount).map(_ => ArrayBuffer[Long]()).toList
  private var unitEndTime = Long.MinValue
  private val timeUnitSize = 1000000000000L

  private def feedTimeEvent(channel: Int, time: Long) = {
    if (time > unitEndTime) {
      if (unitEndTime == Long.MinValue) unitEndTime = time
      else flush()
    }
    timeEvents(channel) += time
  }

  private def flush(): Unit = {
    val data = timeEvents.map(_.toArray).toArray
    timeEvents.foreach(_.clear())
    val creationTime = System.currentTimeMillis() - 1000
    dataBlocks += DataBlock.create(data, creationTime, unitEndTime - timeUnitSize, unitEndTime)
    unitEndTime += timeUnitSize
  }
}
