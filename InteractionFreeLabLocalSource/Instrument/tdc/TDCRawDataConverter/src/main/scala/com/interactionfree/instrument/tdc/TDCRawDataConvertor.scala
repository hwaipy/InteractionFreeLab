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
import java.nio.file.Path
import scala.jdk.CollectionConverters._
import java.text.DateFormat
import java.util.Date
import com.interactionfree.MsgpackSerializer
import java.io.BufferedOutputStream
import com.hydra.services.tdc.device.adapters.GroundTDCDataAdapter;
import java.nio.ByteBuffer
import java.nio.LongBuffer
import scala.collection.mutable.ArrayBuffer

object TDCRawDaataServer extends App {
  val srcPath = Paths.get(if (args.length >= 1) args(0) else "testData/")
  val targetPath = srcPath.resolve(s"Converted_${System.currentTimeMillis()}")
  val srcFiles: List[Path] = Files.list(srcPath).iterator.asScala.toList
  Files.createDirectories(targetPath)

  srcFiles.foreach(srcFile => {
    loadDataBlocks(
      srcFile,
      (dataBlock) => {
        val data = MsgpackSerializer.serialize(dataBlock)
        val out = new BufferedOutputStream(new FileOutputStream(targetPath.resolve(s"${formatTime(dataBlock("CreationTime").asInstanceOf[Long])}.rtm").toFile()))
        out.write(data)
        out.close()
      }
    )
  })

  // val srcFile = if (args.length >= 1) args(0) else "testData/2021-03-25 20-20-19.646.datablock"
  // val targetFile = if (args.length >= 2) args(0) else s"$srcFile.rtm"
  // val data = srcFile match {
  //   case f if f.toLowerCase.endsWith(".datablock") => loadDataBlock()
  // }

  // val data = loadDataBlockFile(Paths.get("testData/2021-03-25 20-20-19.646.datablock"))

  def formatTime(time: Long) = {
    val date = new Date()
    date.setTime(time)
    val sdf = new SimpleDateFormat("yyyy-MM-dd HH-mm-ss.SSS")
    sdf.format(date)
  }

  def loadDataBlocks(path: Path, saver: Map[String, Any] => Unit) = {
    path.getFileName().toString().toLowerCase() match {
      case filename if filename.endsWith(".datablock") => saver(loadCompressedDataBlockFile(path))
      case filename if filename.endsWith(".dat")       => loadGroundTDCFile(path, saver)
      case _                                           => List()
    }
  }

  def loadCompressedDataBlockFile(path: Path) = {
    val raf = new RandomAccessFile(path.toFile(), "r")
    val buffer = new Array[Byte](raf.length().toInt)
    raf.readFully(buffer)
    raf.close()
    val dataBlock = DataBlock.deserialize(buffer)
    Map(
      "CreationTime" -> dataBlock.creationTime,
      "Resolution" -> dataBlock.resolution,
      "DataTimeBegin" -> dataBlock.dataTimeBegin,
      "DataTimeEnd" -> dataBlock.dataTimeEnd,
      "Content" -> dataBlock.getContent
    )
  }

  def loadGroundTDCFile(path: Path, saver: Map[String, Any] => Unit) = {
    val bufferSize = 4096 * 4096
    val raf = new RandomAccessFile(path.toFile(), "r")
    val channel = raf.getChannel()
    val adapter = new GroundTDCDataAdapter(16)
    val buffer = ByteBuffer.allocate(bufferSize);
    val format = new SimpleDateFormat("yyyyMMddHHmmss")
    val creationTimeStart = format.parse(path.getFileName().toString())

    var DEBUG_loop = 0
    val contentRef = new AtomicReference[Array[ArrayBuffer[Long]]]()
    var dataBlockEnd = -1L
    val dataBlockUnit = 1000000000000L
    var dataBlockIndex = 0
    while (channel.read(buffer) > 0) {
      buffer.flip();
      val timeEvents = adapter.offer(buffer).asInstanceOf[LongBuffer]
      buffer.rewind();
      while (timeEvents.hasRemaining()) {
        val event = timeEvents.get()
        val time = event >> 4
        val channel = (event % 16).toInt
        if (dataBlockEnd < 0) dataBlockEnd = time + dataBlockUnit
        if (time >= dataBlockEnd) {
          val content = contentRef.getAndSet(null)
          val creationTime = new Date()
          creationTime.setTime(creationTimeStart.getTime() + dataBlockIndex * 1000)
          saver(
            Map(
              "CreationTime" -> (creationTimeStart.getTime() + dataBlockIndex * 1000),
              "Resolution" -> 1e-12,
              "DataTimeBegin" -> (dataBlockEnd - dataBlockUnit),
              "DataTimeEnd" -> dataBlockEnd,
              "Content" -> content.map(_.toArray)
            )
          )
          dataBlockIndex += 1
          dataBlockEnd += dataBlockUnit
        }
        if (contentRef.get() == null) contentRef set (Range(0, 16).map(i => new ArrayBuffer[Long]).toArray)
        contentRef.get()(channel) += time
      }
    }
    raf.close()
  }
}
