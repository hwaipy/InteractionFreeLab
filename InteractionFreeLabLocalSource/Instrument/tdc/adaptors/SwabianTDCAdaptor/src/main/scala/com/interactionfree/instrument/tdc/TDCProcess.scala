package com.interactionfree.instrument.tdc

import java.io.FileInputStream
import java.util.Properties
import java.util.concurrent.Executors
import java.util.concurrent.atomic.{AtomicBoolean, AtomicInteger, AtomicLong, AtomicReference}
import scala.concurrent.duration.Duration
import scala.jdk.CollectionConverters._
import scala.collection.mutable
import scala.io.Source
import com.interactionfree.{IFWorker, AsynchronousRemoteObject}
import scala.concurrent.{Await, ExecutionContext, Future}
import scala.util.{Success, Failure}
import scala.collection.mutable.ArrayBuffer
import java.nio.LongBuffer

object SwabianTDC extends App {
  val properties = new Properties()
  val propertiesIn = new FileInputStream("config.properties")
  properties.load(propertiesIn)
  propertiesIn.close()

  val IFServerAddress = properties.getOrDefault("IFServer.Address", "tcp://127.0.0.1:224").toString
  val IFServerServiceName = properties.getOrDefault("IFServer.ServiceName", "GroundTDCAdapter").toString
  val TDCServerAddress = properties.getOrDefault("TDCServer.Address", "tcp://127.0.0.1:224").toString
  val TDCServerServiceName = properties.getOrDefault("TDCServer.ServiceName", "TDCServer").toString
  val tdcServerWorker = IFWorker.async(TDCServerAddress)
  val tdcServer = tdcServerWorker.asynchronousInvoker(TDCServerServiceName)
  val process = new TDCProcess(tdcServer)

  val worker = IFWorker(IFServerAddress, IFServerServiceName, process)
  println(s"Swabian TDC Adaptor started.")
  Source.stdin.getLines().filter(line => line.toLowerCase() == "q").next()
  println("Stoping Ground TDC...")
  worker.close()
  tdcServerWorker.close()
  process.stop()
}

class TDCProcess(private val tdcServer: AsynchronousRemoteObject) {
  private val channelCount = 16
  private val swabianTDA = new SwabianTDCDataAdapter()
  private val dataTDA = new LongBufferToDataBlockListTDCDataAdapter(channelCount)
  private val running = new AtomicBoolean(true)
  private val bufferSize = 50 * 1000000
  private val executionContext = ExecutionContext.fromExecutorService(Executors.newSingleThreadExecutor())
  private val tdcParser = new TDCParser(
    new TDCDataProcessor {
      override def process(data: Any): Unit = dataParsed(data)
    },
    Array(swabianTDA, dataTDA)
  )

  def stop() = {
    running set false
    executionContext.shutdown()
    tdcParser.stop()
  }

  def dataIncome(data: Any) = data match {
    case data: Array[Byte] => tdcParser.offer(data)
    case _                 => throw new IllegalArgumentException(s"Wrong type: ${data.getClass}")
  }

  private def dataParsed(data: Any) = data match {
    case data: List[_] =>
      data.foreach(d =>
        d match {
          case d: DataBlock => dataBlockIncome(d)
          case _            => throw new IllegalArgumentException(s"Wrong type: ${d.getClass}")
        }
      )
    case _ => throw new IllegalArgumentException(s"Wrong type: ${data.getClass}")
  }

  private val dataBlockQueue = new collection.mutable.ListBuffer[DataBlock]

  private def dataBlockIncome(dataBlock: DataBlock) = {
    this.synchronized {
      dataBlockQueue += dataBlock
      while (bufferStatus._3 >= bufferSize) dataBlockQueue.filter(!_.isReleased).head.release()
    }
  }

  // DataBlock count, released DataBlock count, valid size.
  def bufferStatus = (dataBlockQueue.size, dataBlockQueue.filter(_.isReleased).size, dataBlockQueue.filter(!_.isReleased).map(_.sizes.sum).sum)

  Future[Any] {
    while (running.get) {
      this.synchronized {
        dataBlockQueue.size match {
          case 0 => None
          case _ => Some(dataBlockQueue.remove(0))
        }
      } match {
        case Some(next) => {
          val bytes = next.serialize()
          println(s"Dealing a DataBlock with Size ${bytes.size}, Counts [${next.sizes.map(c => c.toString).mkString(", ")}]")
          tdcServer.send(bytes).onComplete{
            case Success(s) =>
            case Failure(f) => println(f)
          }(executionContext)
        }
        case None => Thread.sleep(100)
      }
    }
  }(ExecutionContext.fromExecutorService(Executors.newSingleThreadExecutor((r) => {
    val t = new Thread(r)
    t.setDaemon(true)
    t
  })))
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
