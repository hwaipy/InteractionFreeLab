package com.interactionfree.instrument.tdc

import java.io.FileInputStream
import java.util.Properties
import java.util.concurrent.Executors
import java.util.concurrent.atomic.{AtomicBoolean, AtomicInteger, AtomicLong, AtomicReference}
import scala.concurrent.duration.Duration
import scala.jdk.CollectionConverters._
import com.interactionfree.instrument.tdc.adapters.GroundTDCDataAdapter
import scala.collection.mutable
import scala.io.Source
import com.interactionfree.{IFWorker, AsynchronousRemoteObject}
import scala.concurrent.{Await, ExecutionContext, Future}
import scala.util.{Success, Failure}

object GroundTDC extends App {
  val properties = new Properties()
  val propertiesIn = new FileInputStream("config.properties")
  properties.load(propertiesIn)
  propertiesIn.close()

  val dataSourceListeningPort = properties.getOrDefault("DataSource.Port", 20156).toString.toInt
  val IFServerAddress = properties.getOrDefault("IFServer.Address", "tcp://127.0.0.1:224").toStrings
  val IFServerServiceName = properties.getOrDefault("IFServer.ServiceName", "GroundTDCAdapter").toString
  val TDCServerAddress = properties.getOrDefault("TDCServer.Address", "tcp://127.0.0.1:224").toString
  val TDCServerServiceName = properties.getOrDefault("TDCServer.ServiceName", "TDCServer").toString
  val ChannelMapStr = properties.getOrDefault("ChannelMap", "-1 -> -1").toString
  val channelMap = ChannelMapStr.split(" *, *").toList.map(s => {
    val ss = s.split(" *-> *").toList.map(_.toInt)
    (ss(0), ss(1))
  }).toMap
  val tdcServerWorker = IFWorker.async(TDCServerAddress)
  val tdcServer = tdcServerWorker.asynchronousInvoker(TDCServerServiceName)
  val process = new TDCProcessService(dataSourceListeningPort, tdcServer, channelMap)

  val worker = IFWorker(IFServerAddress, IFServerServiceName, process)
  println(s"Ground TDC Adapter started on port $dataSourceListeningPort.")
  Source.stdin.getLines().filter(line => line.toLowerCase() == "q").next()
  println("Stoping Ground TDC...")
  worker.close()
  tdcServerWorker.close()
  process.stop()
}

class TDCProcessService(private val port: Int, private val tdcServer: AsynchronousRemoteObject, channelMap: Map[Int, Int] = Map()) {
  private val channelCount = 16
  private val groundTDA = new GroundTDCDataAdapter(channelCount, channelMap.map(e => (new Integer(e._1), new Integer(e._2))).asJava)
  private val dataTDA = new LongBufferToDataBlockListTDCDataAdapter(channelCount)
  private val server = new TDCProcessServer(port, dataIncome, List(groundTDA, dataTDA))
  private val running = new AtomicBoolean(true)
  private val bufferSize = 50 * 1000000
  private val executionContext = ExecutionContext.fromExecutorService(Executors.newSingleThreadExecutor())

  def stop() = {
    running set false
    server.stop()
    executionContext.shutdown()
  }

  private def dataIncome(data: Any) = {
    if (!data.isInstanceOf[List[_]]) throw new IllegalArgumentException(s"Wrong type: ${data.getClass}")
    data.asInstanceOf[List[DataBlock]].foreach(dataBlock => dataBlockIncome(dataBlock))
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
