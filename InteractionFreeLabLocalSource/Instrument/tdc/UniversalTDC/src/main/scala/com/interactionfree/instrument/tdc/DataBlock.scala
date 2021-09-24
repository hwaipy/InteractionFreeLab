package com.interactionfree.instrument.tdc

import java.nio.{ByteBuffer, LongBuffer}
import java.util.concurrent.atomic.AtomicReference
import scala.collection.mutable.ListBuffer
import com.interactionfree.NumberTypeConversions._
import com.interactionfree.{IFException, MsgpackSerializer}
import scala.collection.IterableOnce
import scala.util.Random
import javax.xml.crypto.Data

object DataBlock {
  private val FINENESS = 100000
  val PROTOCOL_V1 = "DataBlock_V1"
  private val DEFAULT_PROTOCOL = PROTOCOL_V1

  def create(content: Array[Array[Long]], creationTime: Long, dataTimeBegin: Long, dataTimeEnd: Long, resolution: Double = 1e-12): DataBlock = {
    val dataBlock = new DataBlock(creationTime, dataTimeBegin, dataTimeEnd, content.map(_.length), resolution)
    dataBlock.contentRef set content
    dataBlock
  }

  def generate(generalConfig: Map[String, Long], channelConfig: Map[Int, List[Any]]): DataBlock = {
    val creationTime = generalConfig.get("CreationTime") match {
      case Some(ct) => ct
      case None     => System.currentTimeMillis()
    }
    val dataTimeBegin = generalConfig.get("DataTimeBegin") match {
      case Some(dtb) => dtb
      case None      => 0
    }
    val dataTimeEnd = generalConfig.get("DataTimeEnd") match {
      case Some(dte) => dte
      case None      => 0
    }
    val content = Range(0, 16).toArray.map(channel =>
      channelConfig.get(channel) match {
        case None => Array[Long]()
        case Some(config) =>
          config.head.toString match {
            case "Period" => {
              val count: Int = config(1)
              val period = (dataTimeEnd - dataTimeBegin) / count.toDouble
              Range(0, count).toArray.map(i => dataTimeBegin + (i * period).toLong)
            }
            case "Random" => {
              val count: Int = config(1)
              val averagePeriod = (dataTimeEnd - dataTimeBegin) / count
              val random = new Random()
              val randomGaussians = Range(0, count).toArray.map(_ => (1 + random.nextGaussian() / 3) * averagePeriod)
              val randGaussSumRatio = (dataTimeEnd - dataTimeBegin) / randomGaussians.sum
              val randomDeltas = randomGaussians.map(rg => rg * randGaussSumRatio)
              val deltas = ListBuffer[Long]()
              randomDeltas.foldLeft(0.0)((a, b) => {
                deltas += a.toLong
                a + b
              })
              deltas.toArray
            }
            case "Pulse" => {
              val pulseCount: Int = config(1)
              val eventCount: Int = config(2)
              val sigma: Double = config(3)
              val period = (dataTimeEnd - dataTimeBegin) / pulseCount
              val random = new Random()
              Range(0, eventCount).toArray.map(_ => dataTimeBegin + random.nextInt(pulseCount) * period + (random.nextGaussian() * sigma).toLong).sorted
            }
            case _ => throw new RuntimeException
          }
      }
    )
    create(content, creationTime, dataTimeBegin, dataTimeEnd)
  }

  def deserialize(data: Array[Byte], partial: Boolean = false) = {
    val recovered = MsgpackSerializer.deserialize(data).asInstanceOf[Map[String, Any]]
    val protocol = recovered("Format").toString()
    if (protocol != PROTOCOL_V1) throw new IFException(s"Data format not supported: ${recovered("Format")}")
    val sizes = recovered("Sizes").asInstanceOf[IterableOnce[Int]].iterator.toArray
    val dataBlock = new DataBlock(recovered("CreationTime"), recovered("DataTimeBegin"), recovered("DataTimeEnd"), sizes, recovered("Resolution"))
    val chDatas = recovered("Content").asInstanceOf[IterableOnce[List[Array[Byte]]]].iterator.toArray
    dataBlock.binaryRef set chDatas
    if (!partial) {
      // val content = chDatas.map(chData => Array.concat(chData.map(section => DataBlockSerializers(protocol).deserialize(section)): _*))
      // dataBlock.contentRef set (if (content.isEmpty) null else content)
      dataBlock.unpack()
    }
    dataBlock
  }

  def merge(dataBlocks: Iterable[DataBlock], allowDiscrete: Boolean = false) = {
    if (!(dataBlocks.dropRight(1) zip dataBlocks.drop(1)).forall(z => z._1.dataTimeEnd <= z._2.dataTimeBegin)) throw new IllegalArgumentException("DataTimeBegin of later DataBlok should not earlier than the previous one's DataTimeEnd.")
    if (!allowDiscrete && ((dataBlocks.dropRight(1) zip dataBlocks.drop(1)).forall(z => z._1.dataTimeEnd != z._2.dataTimeBegin))) throw new IllegalArgumentException("DataTimeBegin of later DataBlok should equals to the previous one's DataTimeEnd.")
    val creationTime = dataBlocks.head.creationTime
    val dataTimeBegin = dataBlocks.head.dataTimeBegin
    val dataTimeEnd = dataBlocks.last.dataTimeEnd
    val resolution = dataBlocks.map(_.resolution).min
    val channelCount = dataBlocks.map(_.sizes.size).max
    val content = Range(0, channelCount).toArray.map(ch => dataBlocks.map(db => db.getContent(ch)).foldLeft(Array[Long]())((a, b) => a ++ b))
    create(content, creationTime, dataTimeBegin, dataTimeEnd, resolution)
  }
}

class DataBlock protected[tdc] (val creationTime: Long, val dataTimeBegin: Long, val dataTimeEnd: Long, val sizes: Array[Int], val resolution: Double = 1e-12) {
  protected[tdc] val contentRef = new AtomicReference[Array[Array[Long]]]()
  private val binaryRef = new AtomicReference[Array[List[Array[Byte]]]]()

  def release(): Unit = {
    contentRef set null
    binaryRef set null
  }

  def isReleased: Boolean = (contentRef.get == null) && (binaryRef.get == null)

  def content: Option[Array[Array[Long]]] =
    contentRef.get match {
      case null => None
      case c    => Some(c)
    }

  def getContent: Array[Array[Long]] = contentRef.get

  def serialize(protocol: String = DataBlock.DEFAULT_PROTOCOL): Array[Byte] = {
    val serializedContent = content match {
      case Some(c) => c.map(ch => Range(0, Math.ceil(ch.size / DataBlock.FINENESS.toDouble).toInt).map(i => DataBlockSerializers(protocol).serialize(ch.slice(i * DataBlock.FINENESS, (i + 1) * DataBlock.FINENESS))))
      case None    => null
    }
    val result = Map(
      "Format" -> DataBlock.PROTOCOL_V1,
      "CreationTime" -> creationTime,
      "Resolution" -> resolution,
      "DataTimeBegin" -> dataTimeBegin,
      "DataTimeEnd" -> dataTimeEnd,
      "Sizes" -> sizes,
      "Content" -> serializedContent
    )
    MsgpackSerializer.serialize(result)
  }

  def convertResolution(resolution: Double) = {
    val ratio = this.resolution / resolution
    val newDB = new DataBlock(creationTime, (dataTimeBegin * ratio).toLong, (dataTimeEnd * ratio).toLong, sizes, resolution)
    content.foreach(c => {
      val newContent = c.map(ch => ch.map(n => (n * ratio).toLong))
      newDB.contentRef set newContent
    })
    newDB
  }

  def unpack() = {
    if (binaryRef.get != null) {
      val content = binaryRef.get.map(chData => Array.concat(chData.map(section => DataBlockSerializers(DataBlock.PROTOCOL_V1).deserialize(section)): _*))
      binaryRef set null
      contentRef set (if (content.isEmpty) null else content)
    }
  }

  def binarySize() =
    binaryRef.get match {
      case null   => 0
      case binary => binary.map(l => l.map(a => a.size).sum).sum
    }

  // def synced(delays: List[Long], syncConfig: Map[String, String] = Map()) = new SyncedDataBlock(this, delays, syncConfig)
  def synced(delays: List[Long]) = new SyncedDataBlock(this, delays)

  def ranged(after: Long = Long.MinValue, before: Long = Long.MaxValue) = {
    val dataTimeBegin = List(this.dataTimeBegin, after).max
    val dataTimeEnd = List(this.dataTimeEnd, before).min
    val content = getContent match {
      case null => throw new IllegalStateException("Can not create Ranged DataBlock from a released or packed DataBlock.")
      case content =>
        content.map(ch => {
          var startI = 0
          var stopI = ch.size
          while (startI < ch.size && ch(startI) < dataTimeBegin) { startI += 1 }
          while (stopI > 0 && ch(stopI - 1) > dataTimeEnd) { stopI -= 1 }
          ch.slice(startI, stopI)
        })
    }
    DataBlock.create(content, creationTime, dataTimeBegin, dataTimeEnd, resolution)
  }
}

class SyncedDataBlock protected[tdc] (val sourceDataBlock: DataBlock, val delays: List[Long], val syncConfig: Map[String, String] = Map()) extends DataBlock(sourceDataBlock.creationTime, sourceDataBlock.dataTimeBegin, sourceDataBlock.dataTimeEnd, sourceDataBlock.sizes.toArray, sourceDataBlock.resolution) {
  sourceDataBlock.content.foreach(content => {
    if (delays.size != content.size) throw new IllegalArgumentException(s"The size of delays does not math the number of channels: ${delays.size} != ${content.size}")
    val newContent = content
      .zip(delays)
      .map(z => {
        val source = z._1
        val target = new Array[Long](source.length)
        var i = 0
        val delay = z._2
        while (i < source.length) {
          target(i) = source(i) + delay
          i += 1
        }
        target
      })
    // syncConfig
    //   .get("Method")
    //   .foreach(
    //     _ match {
    //       case "PeriodSignal" => syncPeriodSignal(syncConfig, newContent)
    //       case s              => throw new IllegalArgumentException(s"'${s}' is not a valid sync method.")
    //     }
    //   )
    this.contentRef set newContent
    newContent.zipWithIndex.foreach(z => this.sizes(z._2) = z._1.size)
  })

  private def syncPeriodSignal(config: Map[String, String], targetContent: Array[Array[Long]]) = {
    val syncChannel = config("SyncChannel").toInt
    val period = config("Period").toDouble
    val syncList = targetContent(syncChannel).clone()
    if (syncList.size >= 2) targetContent.zipWithIndex.map(z => targetContent(z._2) = syncASignalList(syncList, z._1))
    def syncASignalList(syncList: Array[Long], signalList: Array[Long]) = {
      val itSync = syncList.iterator
      var syncBegin = itSync.next()
      var syncEnd = itSync.next()
      var syncDelta = (syncEnd - syncBegin).toDouble
      var mappingBegin = 0.0
      var iSignal = 0

      while (iSignal < signalList.length && syncEnd != -1) {
        val signal = signalList(iSignal)
        while (syncEnd < signal && itSync.hasNext) {
          syncBegin = syncEnd
          syncEnd = itSync.next()
          syncDelta = (syncEnd - syncBegin).toDouble
          mappingBegin += period
        }
        if (signal < syncBegin || signal > syncEnd) signalList(iSignal) = -1
        else signalList(iSignal) = ((signal - syncBegin) / syncDelta * period + mappingBegin).toLong
        iSignal += 1
      }
      signalList.slice(signalList.indexWhere(l => l >= 0), signalList.lastIndexWhere(l => l >= 0) + 1)
    }
  }
}

abstract class DataBlockSerializer {
  def serialize(data: Array[Long]): Array[Byte]
  def deserialize(data: Array[Byte]): Array[Long]
}

object DataBlockSerializers {
  val pv1DBS = new DataBlockSerializer {
    private val MAX_VALUE = 1e16

    def serialize(list: Array[Long]) =
      list.size match {
        case 0 => Array[Byte]()
        case _ => {
          val buffer = ByteBuffer.allocate(list.length * 8)
          buffer.putLong(list(0))

          val unitSize = 15
          val unit = new Array[Byte](unitSize + 1)
          var hasHalfByte = false
          var halfByte: Byte = 0
          var i = 0
          while (i < list.length - 1) {
            val delta = (list(i + 1) - list(i))
            i += 1
            if (delta > MAX_VALUE || delta < -MAX_VALUE) throw new IllegalArgumentException(s"The value to be serialized exceed MAX_VALUE: ${delta}")
            var value = delta
            var length = 0
            var keepGoing = true
            val valueBase = if (delta >= 0) 0 else 0xffffffffffffffffL
            while (keepGoing) {
              unit(unitSize - length) = (value & 0xf).toByte
              value >>= 4
              length += 1
              if (value == valueBase) {
                keepGoing = (unit(unitSize - length + 1) & 0x8) == (if (delta >= 0) 0x8 else 0x0)
              } else if (length >= unitSize) keepGoing = false
            }
            unit(unitSize - length) = length.toByte
            var p = 0
            while (p <= length) {
              if (hasHalfByte) buffer.put(((halfByte << 4) | unit(unitSize - length + p)).toByte) else halfByte = unit(unitSize - length + p)
              hasHalfByte = !hasHalfByte
              p += 1
            }
          }
          if (hasHalfByte) buffer.put((halfByte << 4).toByte)
          buffer.array().slice(0, buffer.position())
        }
      }

    def deserialize(data: Array[Byte]): Array[Long] =
      data.size match {
        case 0 => Array[Long]()
        case _ => {
          val offset = (ByteBuffer.wrap(data.slice(0, 8))).getLong()
          val longBuffer = LongBuffer.allocate(data.length)
          longBuffer.put(offset)
          var previous = offset

          var positionC = 8
          var positionF = 0
          def hasNext = positionC < data.length
          def getNext = {
            val b = data(positionC)
            if (positionF == 0) {
              positionF = 1
              (b >> 4) & 0xf
            } else {
              positionF = 0
              positionC += 1
              b & 0xf
            }
          }

          while (hasNext) {
            var length = getNext - 1
            if (length >= 0) {
              var value: Long = (getNext & 0xf)
              if ((value & 0x8) == 0x8) value |= 0xfffffffffffffff0L
              while (length > 0) {
                value <<= 4
                value |= (getNext & 0xf)
                length -= 1
              }
              previous += value
              longBuffer.put(previous)
            }
          }
          longBuffer.array().slice(0, longBuffer.position())
        }
      }
  }
  private val DBS = Map(
    // "NAIVE" -> naiveDBS,
    DataBlock.PROTOCOL_V1 -> pv1DBS
  )

  def apply(name: String) = DBS(name)
}
