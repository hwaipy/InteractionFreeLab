package com.interactionfree.instrument.tdc

import java.io.PrintStream
import java.util.concurrent.atomic.AtomicInteger

import scala.collection.mutable
import scala.collection.mutable.ListBuffer
import scala.util.Random
import javax.sound.sampled.AudioFormat.Encoding

object BenchMarker extends App {
  private val UNIT_SIZE = 20

  def run(): Unit = {
    println(s"${System.lineSeparator()} ******** Start BenchMarking ******** ${System.lineSeparator()}")
    doBenchMarkingSerDeser()
    // doBenchMarkingSyncedDataBlock()
    // doBenchMarkingMultiHistogramAnalyser()
    // doBenchMarkingExceptionMonitorAnalyser()
    doBenchMarkingEncodingAnalyser()
  }

  private def doBenchMarkingSerDeser(): Unit =
    List(
      ("Period List", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Period", r)), 1e-12),
      ("Period List, 16 ps", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Period", r)), 16e-12),
      ("Random List", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Random", r)), 1e-12),
      ("Random List, 16 ps", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Random", r)), 16e-12),
      ("Mixed List", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Period", r / 10), 1 -> List("Random", r / 10 * 4), 5 -> List("Random", r / 10 * 5), 10 -> List("Period", 10), 12 -> List("Random", 1)), 1e-12),
      ("Mixed List, 16 ps", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Period", r / 10), 1 -> List("Random", r / 10 * 4), 5 -> List("Random", r / 10 * 5), 10 -> List("Period", 10), 12 -> List("Random", 1)), 16e-12)
    ).foreach(config => {
      val rt = ReportTable(s"DataBlock serial/deserial: ${config._1}", List("Event Size", "Data Rate", "Serial Time", "Deserial Time")).setFormatter(0, formatterKMG).setFormatter(1, (dr) => f"${dr.asInstanceOf[Double]}%.2f").setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms").setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
      config._2.foreach(r => {
        val bm = doBenchMarkingSerDeser(config._3(r), config._4)
        rt.addRow(r, bm._1, bm._2, bm._3)
      })
      rt.output()
    })

  private def doBenchMarkingSerDeser(dataConfig: Map[Int, List[Any]], resolution: Double = 1e-12): Tuple3[Double, Double, Double] = {
    val testDataBlock = {
      val generatedDB = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L), dataConfig)
      if (resolution == 1e-12) generatedDB else generatedDB.convertResolution(resolution)
    }
    val consumingSerialization = doBenchMarkingOpertion(() => testDataBlock.serialize())
    val data = testDataBlock.serialize()
    val infoRate = data.length.toDouble / testDataBlock.getContent.map(_.length).sum
    val consumingDeserialization = doBenchMarkingOpertion(() => DataBlock.deserialize(data))
    (infoRate, consumingSerialization, consumingDeserialization)
  }

  // private def doBenchMarkingSyncedDataBlock(): Unit = {
  //   List(false, true).foreach(hasSync => {
  //     val rt = ReportTable(if (hasSync) s"Delay & Sync" else "Delay", List("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)"))
  //       .setFormatter(0, formatterKMG)
  //       .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
  //       .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
  //       .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
  //     List(10000, 100000, 1000000, 4000000).foreach(r => {
  //       val bm = doBenchMarkingSyncedDataBlock(
  //         r,
  //         List(
  //           List(1),
  //           List(1, 1),
  //           List(5, 3, 1, 1)
  //         ),
  //         hasSync
  //       )
  //       rt.addRow(r, bm(0), bm(1), bm(2))
  //     })
  //     rt.output()
  //   })
  // }

  // private def doBenchMarkingSyncedDataBlock(totalSize: Int, sizes: List[List[Double]], hasSync: Boolean): List[Double] = {
  //   sizes.map(size => {
  //     val m = Range(0, size.size + 1).map(s => s -> (if (s == 0) List("Period", 10000) else List("Pulse", 100000000, (size(s - 1) / size.sum * totalSize).toInt, 1000))).toMap
  //     val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), m)
  //     doBenchMarkingOpertion(() => { dataBlock.synced(Range(0, 16).toList.map(_ => 100000), if (hasSync) Map("Method" -> "PeriodSignal", "SyncChannel" -> "0", "Period" -> "2e8") else Map()) })
  //   })
  // }

  private def doBenchMarkingMultiHistogramAnalyser(): Unit = {
    val rt = ReportTable(s"MultiHistogramAnalyser", List("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)"))
      .setFormatter(0, formatterKMG)
      .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
      .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
      .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
    List(10000, 100000, 1000000, 4000000).foreach(r => {
      val bm = doBenchMarkingMultiHistogramAnalyser(
        r,
        List(
          List(1),
          List(1, 1),
          List(5, 3, 1, 1)
        )
      )
      rt.addRow(r, bm(0), bm(1), bm(2))
    })
    rt.output()
  }

  private def doBenchMarkingMultiHistogramAnalyser(totalSize: Int, sizes: List[List[Double]]): List[Double] = {
    val mha = new MultiHistogramAnalyser(16)
    mha.turnOn(Map("Sync" -> 0, "Signals" -> List(1), "ViewStart" -> -1000000, "ViewStop" -> 1000000, "BinCount" -> 100, "Divide" -> 100))
    sizes.map(size => {
      val m = Range(0, size.size + 1).map(s => s -> (if (s == 0) List("Period", 10000) else List("Pulse", 100000000, (size(s - 1) / size.sum * totalSize).toInt, 1000))).toMap
      val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), m)
      doBenchMarkingOpertion(() => mha.dataIncome(dataBlock))
    })
  }

  private def doBenchMarkingExceptionMonitorAnalyser(): Unit = {
    val rt = ReportTable(s"ExceptionMonitorAnalyser", List("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)"))
      .setFormatter(0, formatterKMG)
      .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
      .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
      .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
    List(10000, 100000, 1000000, 4000000).foreach(r => {
      val bm = doBenchMarkingExceptionMonitorAnalyser(
        r,
        List(
          List(1),
          List(1, 1),
          List(5, 3, 1, 1)
        )
      )
      rt.addRow(r, bm(0), bm(1), bm(2))
    })
    rt.output()
  }

  private def doBenchMarkingExceptionMonitorAnalyser(totalSize: Int, sizes: List[List[Double]]): List[Double] = {
    val mha = new ExceptionMonitorAnalyser(16)
    mha.turnOn(Map("SyncChannels" -> List(0, 1, 2, 3, 4, 5, 6)))
    sizes.map(size => {
      val m = Range(0, size.size + 1).map(s => s -> (if (s == 0) List("Period", 10000) else List("Pulse", 100000000, (size(s - 1) / size.sum * totalSize).toInt, 1000))).toMap
      val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), m)
      doBenchMarkingOpertion(() => mha.dataIncome(dataBlock))
    })
  }

  private def doBenchMarkingEncodingAnalyser(): Unit = {
    val rt = ReportTable(s"Encoding Analyser", List("Total Event Size", "RN (8)", "RN (32)", "RN (128)"))
      .setFormatter(0, formatterKMG)
      .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
      .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
      .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
    List(10000, 100000, 1000000, 4000000).foreach(r => {
      val bm = doBenchMarkingEncodingAnalyser(r, List(8, 32, 128))
      rt.addRow(r, bm(0), bm(1), bm(2))
    })
    rt.output()
  }

  private def doBenchMarkingEncodingAnalyser(totalSize: Int, rnLimits: List[Int]): List[Double] = {
    rnLimits.map(rnLimit => {
      val mha = new EncodingAnalyser(16, rnLimit)
      mha.turnOn(Map("Period" -> 10000, "TriggerChannel" -> 0, "SignalChannel" -> 1, "RandomNumbers" -> Range(0, rnLimit).toList))
      val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), Map(0 -> List("Period", 10000), 1 -> List("Pulse", 100000000, totalSize, 100)))
      doBenchMarkingOpertion(() => mha.dataIncome(dataBlock))
    })
  }

  private def doBenchMarkingOpertion(operation: () => Unit) = {
    val stop = System.nanoTime() + 1000000000
    val count = new AtomicInteger(0)
    while (System.nanoTime() < stop) {
      operation()
      count.incrementAndGet()
    }
    (1e9 + System.nanoTime() - stop) / 1e9 / count.get
  }

  object ReportTable {
    def apply(title: String, headers: List[String], cellWidth: Int = UNIT_SIZE) = new ReportTable(title, headers, cellWidth = cellWidth)
  }

  private def formatterKMG(value: Any): String =
    value match {
      case data if data.isInstanceOf[Int] || data.isInstanceOf[Long] || data.isInstanceOf[String] =>
        data.toString.toLong match {
          case d if d < 0    => "-"
          case d if d < 1e2  => d.toString
          case d if d < 1e3  => f"${d / 1e3}%.3f K"
          case d if d < 1e4  => f"${d / 1e3}%.2f K"
          case d if d < 1e5  => f"${d / 1e3}%.1f K"
          case d if d < 1e6  => f"${d / 1e6}%.3f M"
          case d if d < 1e7  => f"${d / 1e6}%.2f M"
          case d if d < 1e8  => f"${d / 1e6}%.1f M"
          case d if d < 1e9  => f"${d / 1e9}%.3f G"
          case d if d < 1e10 => f"${d / 1e9}%.2f G"
          case d if d < 1e11 => f"${d / 1e9}%.1f G"
          case d if d < 1e12 => f"${d / 1e12}%.3f T"
          case d if d < 1e13 => f"${d / 1e12}%.2f T"
          case d if d < 1e14 => f"${d / 1e12}%.1f T"
          case d             => "--"
        }
    }

  class ReportTable private (val title: String, val headers: List[String], val cellWidth: Int = UNIT_SIZE) {
    private val rows = ListBuffer[List[Any]]()
    private val formatters = new mutable.HashMap[Int, Any => String]()

    def setFormatter(column: Int, formatter: Any => String) = {
      formatters(column) = formatter
      this
    }

    def addRow(item: Any*) = {
      if (item.size != headers.size) throw new RuntimeException("Dimension of table of matched.")
      rows += item.toList
      this
    }

    def addRows(rows: List[Any]*) = rows.map(addRow).head

    def output(target: PrintStream = System.out): Unit = {
      val totalWidth = headers.size * (1 + cellWidth) + 1
      target.println("+" + Range(0, totalWidth - 2).map(_ => "-").mkString("") + "+")
      target.println("|" + complete(title, totalWidth - 2, alignment = "center") + "|")
      target.println("+" + Range(0, totalWidth - 2).map(_ => "-").mkString("") + "+")
      target.println("|" + headers.map(header => complete(header, cellWidth)).mkString("|") + "|")
      rows.foreach(row =>
        target.println(
          "|" + row.zipWithIndex
            .map(z =>
              complete(
                formatters.get(z._2) match {
                  case Some(f) => f(z._1)
                  case None    => z._1.toString
                },
                cellWidth
              )
            )
            .mkString("|") + "|"
        )
      )
      target.println("+" + Range(0, totalWidth - 2).map(_ => "-").mkString("") + "+")
    }

    private def complete(content: String, width: Int, filler: String = " ", alignment: String = "Center"): String = {
      if (content.length > width) content.slice(0, width - 3) + "..."
      else {
        val diff = width - content.length
        alignment.toLowerCase match {
          case "left"   => content + Range(0, diff).map(_ => filler).mkString("")
          case "right"  => Range(0, diff).map(_ => filler).mkString("") + content
          case "center" => Range(0, diff / 2).map(_ => filler).mkString("") + content + Range(0, diff - diff / 2).map(_ => filler).mkString("")
        }
      }
    }
  }

  run()
}
