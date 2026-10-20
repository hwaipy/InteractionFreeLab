from pytimetag import DataBlock, HistogramAnalyser, EncodingAnalyser, Parallels
import time
import numpy as np
import numba

if __name__ == '__main__':
  UNIT_SIZE = 20
  numba.set_num_threads(10)

  def run():
    print("\n ******** Start BenchMarking ******** \n")
    # benchMarkingSerDeser()
    benchMarkingMultiHistogramAnalyser()
    # benchMarkingEncodingAnalyser()
#     // doBenchMarkingSyncedDataBlock()
#     // doBenchMarkingMultiHistogramAnalyser()
#     // doBenchMarkingExceptionMonitorAnalyser()
#   }

  def benchMarkingSerDeser():
    configs = [
        ("Period List", (10000, 100000, 1000000, 4000000, 10000000), lambda r: {0: ("Period", r)}, 1e-12),
        ("Period List, 16 ps", (10000, 100000, 1000000, 4000000, 10000000), lambda r: {0: ("Period", r)}, 16e-12),
        ("Random List", (10000, 100000, 1000000, 4000000, 10000000), lambda r: {0: ("Random", r)}, 1e-12),
        ("Random List, 16 ps", (10000, 100000, 1000000, 4000000, 10000000), lambda r: {0: ("Random", r)}, 16e-12),
        ("Mixed List", (10000, 100000, 1000000, 4000000, 10000000), lambda r: {0: ("Period", int(r / 10)), 1: ("Random", int(r / 10 * 4)), 5: ("Random", int(r / 10 * 5)), 10: ("Period", 10), 12: ("Random", 1)}, 1e-12),
        ("Mixed List, 16 ps", (10000, 100000, 1000000, 4000000, 10000000), lambda r: {0: ("Period", int(r / 10)), 1: ("Random", int(r / 10 * 4)), 5: ("Random", int(r / 10 * 5)), 10: ("Period", 10), 12: ("Random", 1)}, 16e-12),
    ]
    for config in configs:
      rt = ReportTable(f'DataBlock serial/deserial: {config[0]}', ("Event Size", "Data Rate", "Serial Time", "Deserial Time")).setFormatter(0, formatterKMG).setFormatter(1, lambda dr: "{:.2f}".format(dr)).setFormatter(2, lambda second: "{:.2f} ms".format(second * 1000)).setFormatter(3, lambda second: "{:.2f} ms".format(second * 1000))
      for r in config[1]:
        bm = doBenchMarkingSerDeser(config[2](r), config[3])
        rt.addRow(r, bm[0], bm[1], bm[2])
      rt.output()

  def doBenchMarkingSerDeser(dataConfig, resolution=1e-12):
    generatedDB = DataBlock.generate({"CreationTime": 100, "DataTimeBegin": 10, "DataTimeEnd": 1000000000010}, dataConfig)
    testDataBlock = generatedDB if resolution == 1e-12 else generatedDB.convertResolution(resolution)
    data = testDataBlock.serialize()
    recovered = DataBlock.deserialize(data)
    consumingSerialization = doBenchMarkingOpertion(lambda: testDataBlock.serialize())
    infoRate = len(data) / sum([len(ch) for ch in testDataBlock.content])
    consumingDeserialization = doBenchMarkingOpertion(lambda: DataBlock.deserialize(data))
    return (infoRate, consumingSerialization, consumingDeserialization)

  def benchMarkingMultiHistogramAnalyser():
    rt = ReportTable('MultiHistogramAnalyser', ("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)")).setFormatter(0, formatterKMG).setFormatter(1, lambda second: f"{(second * 1000):.2f} ms").setFormatter(2, lambda second: f"{(second * 1000):.2f} ms").setFormatter(3, lambda second: f"{(second * 1000):.2f} ms")
    for r in [10000, 100000, 1000000, 4000000, 10000000]:
      bm = doBenchMarkingMultiHistogramAnalyser(r, [[1], [1, 1], [5, 3, 1, 1]])
      rt.addRow(r, bm[0], bm[1], bm[2])
    rt.output()

  def doBenchMarkingMultiHistogramAnalyser(totalSize, sizes):
    mha = HistogramAnalyser(16)
    mha.turnOn({"Sync": 0, "Signals": [1], "ViewStart": 0, "ViewStop": 40000000, "BinCount": 1000, "Divide": 1})
    bm = []
    for size in sizes:
      m = {}
      for s in range(len(size) + 1):
        if s == 0:
          m[s] = ["Period", 25000]
        else:
          m[s] = ["Pulse", 100000000, int(size[s - 1] / sum(size) * totalSize), 1000]
      dataBlock = DataBlock.generate({"CreationTime": 100, "DataTimeBegin": 0, "DataTimeEnd": 1000000000000}, m)
      mha.turnOn({"Signals": [i + 1 for i in range(len(size))]})
      bm.append(doBenchMarkingOpertion(lambda: mha.dataIncome(dataBlock)))
    return bm

  def benchMarkingEncodingAnalyser():
    rt = ReportTable('Encoding Analyser', ("Total Event Size", "RN (8)", "RN (32)", "RN (128)")).setFormatter(0, formatterKMG).setFormatter(1, lambda second: f"{(second * 1000):.2f} ms").setFormatter(2, lambda second: f"{(second * 1000):.2f} ms").setFormatter(3, lambda second: f"{(second * 1000):.2f} ms")
    for r in [10000, 100000, 1000000, 4000000, 10000000]:
      bm = doBenchMarkingEncodingAnalyser(r, [8, 32, 128], [8, 32, 128])
      rt.addRow(r, bm[0], bm[1], bm[2])
    rt.output()

    rt = ReportTable('Encoding Analyser (Long RandomNumber)', ("Total Event Size", "RN (8)", "RN (32)", "RN (128)")).setFormatter(0, formatterKMG).setFormatter(1, lambda second: f"{(second * 1000):.2f} ms").setFormatter(2, lambda second: f"{(second * 1000):.2f} ms").setFormatter(3, lambda second: f"{(second * 1000):.2f} ms")
    for r in [10000, 100000, 1000000, 4000000, 10000000]:
      bm = doBenchMarkingEncodingAnalyser(r, [8, 32, 128], [20000000] * 3)
      rt.addRow(r, bm[0], bm[1], bm[2])
    rt.output()

  def doBenchMarkingEncodingAnalyser(totalSize, rnLimits, rnLengths):
    bm = []
    for i in range(len(rnLimits)):
      rnLimit = rnLimits[i]
      rnLength = rnLengths[i]
      mha = EncodingAnalyser(16, rnLimit)
      mha.turnOn({"Period": 10000, "TriggerChannel": 0, "SignalChannel": 1, "RandomNumbers": np.linspace(0, rnLength - 1, rnLength, dtype='<i4') % rnLimit})
      dataBlock = DataBlock.generate({"CreationTime": 100, "DataTimeBegin": 0, "DataTimeEnd": 1000000000000}, {0: ["Period", 10000], 1: ["Pulse", 100000000, totalSize, 100]})
      bm.append(doBenchMarkingOpertion(lambda: mha.dataIncome(dataBlock)))
    return bm

  def doBenchMarkingOpertion(operation):
    operation()
    stop = time.time() + 1
    count = 0
    while time.time() < stop:
      operation()
      count += 1
    return (1 + time.time() - stop) / count

  def formatterKMG(value):
    if value < 0:
      return "-"
    if value < 1e2:
      return str(value)
    if value < 1e3:
      return f"{value / 1e3:.3f} K"
    if value < 1e4:
      return f"{value / 1e3:.2f} K"
    if value < 1e5:
      return f"{value / 1e3:.1f} K"
    if value < 1e6:
      return f"{value / 1e6:.3f} M"
    if value < 1e7:
      return f"{value / 1e6:.2f} M"
    if value < 1e8:
      return f"{value / 1e6:.1f} M"
    if value < 1e9:
      return f"{value / 1e9:.3f} G"
    if value < 1e10:
      return f"{value / 1e9:.2f} G"
    if value < 1e11:
      return f"{value / 1e9:.1f} G"
    if value < 1e12:
      return f"{value / 1e12:.3f} T"
    if value < 1e13:
      return f"{value / 1e12:.2f} T"
    if value < 1e14:
      return f"{value / 1e12:.1f} T"
    return str(value)

  class ReportTable:
    def __init__(self, title, headers, cellWidth=UNIT_SIZE):
      self.title = title
      self.headers = headers
      self.cellWidth = cellWidth
      self.rows = []
      self.formatters = {}

    def setFormatter(self, column, formatter):
      self.formatters[column] = formatter
      return self

    def addRow(self, *item):
      if len(item) != len(self.headers):
        raise RuntimeError("Dimension of table of matched.")
      self.rows.append(item)
      return self

#     def addRows(rows: List[Any]*) = rows.map(addRow).head

    def output(self):
      output = ''
      totalWidth = len(self.headers) * (1 + self.cellWidth) + 1
      output += ("+" + "-" * (totalWidth - 2) + "+\n")
      output += ("|" + self.complete(self.title, totalWidth - 2, alignment="center") + "|\n")
      output += ("+" + '-' * (totalWidth - 2) + "+\n")
      output += ("|" + '|'.join([self.complete(header, self.cellWidth) for header in self.headers]) + "|\n")
      for row in self.rows:
        output += '|' + '|'.join([(self.complete(self.__getFormatter(i)(row[i]), self.cellWidth)) for i in range(len(row))]) + "|\n"
      output += ("+" + "-" * (totalWidth - 2) + "+")
      print(output)

    def complete(self, content, width, filler=" ", alignment="Center"):
      if len(content) > width:
        return content[0: width - 3] + "..."
      else:
        diff = width - len(content)
        alignment = alignment.lower()
        if alignment == 'left':
          return content + filler * diff
        elif alignment == 'right':
          return filler * diff + content
        elif alignment == 'center':
          return filler * int(diff / 2) + content + filler * (diff - int(diff / 2))
        else:
          raise RuntimeError('bad alignment: {}'.format(alignment))

    def __getFormatter(self, name):
      if self.formatters.__contains__(name):
        return self.formatters[name]
      else:
        return lambda item: str(item)

  run()


#   private def doBenchMarkingSerDeser(): Unit =
#     List(
#       ("Period List", List(10000, 100000, 1000000, 4000000, 10000000, 100000000), (r: Int) => Map(0 -> List("Period", r)), 1e-12),
#       ("Period List, 16 ps", List(10000, 100000, 1000000, 4000000, 10000000, 100000000), (r: Int) => Map(0 -> List("Period", r)), 16e-12),
#       ("Random List", List(10000, 100000, 1000000, 4000000, 10000000, 100000000), (r: Int) => Map(0 -> List("Random", r)), 1e-12),
#       ("Random List, 16 ps", List(10000, 100000, 1000000, 4000000, 10000000, 100000000), (r: Int) => Map(0 -> List("Random", r)), 16e-12),
#       ("Mixed List", List(10000, 100000, 1000000, 4000000, 10000000, 100000000), (r: Int) => Map(0 -> List("Period", r / 10), 1 -> List("Random", r / 10 * 4), 5 -> List("Random", r / 10 * 5), 10 -> List("Period", 10), 12 -> List("Random", 1)), 1e-12),
#       ("Mixed List, 16 ps", List(10000, 100000, 1000000, 4000000, 10000000, 100000000), (r: Int) => Map(0 -> List("Period", r / 10), 1 -> List("Random", r / 10 * 4), 5 -> List("Random", r / 10 * 5), 10 -> List("Period", 10), 12 -> List("Random", 1)), 16e-12)
#     ).foreach(config => {
#       val rt = ReportTable(s"DataBlock serial/deserial: ${config._1}", List("Event Size", "Data Rate", "Serial Time", "Deserial Time")).setFormatter(0, formatterKMG).setFormatter(1, (dr) => f"${dr.asInstanceOf[Double]}%.2f").setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms").setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#       config._2.foreach(r => {
#         val bm = doBenchMarkingSerDeser(config._3(r), config._4)
#         rt.addRow(r, bm._1, bm._2, bm._3)
#       })
#       rt.output()
#     })

#   private def doBenchMarkingSerDeser(dataConfig: Map[Int, List[Any]], resolution: Double = 1e-12): Tuple3[Double, Double, Double] = {
#     val testDataBlock = {
#       val generatedDB = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 10, "DataTimeEnd" -> 1000000000010L), dataConfig)
#       if (resolution == 1e-12) generatedDB else generatedDB.convertResolution(resolution)
#     }
#     val consumingSerialization = doBenchMarkingOpertion(() => testDataBlock.serialize())
#     val data = testDataBlock.serialize()
#     val infoRate = data.length.toDouble / testDataBlock.getContent.map(_.length).sum
#     val consumingDeserialization = doBenchMarkingOpertion(() => DataBlock.deserialize(data))
#     (infoRate, consumingSerialization, consumingDeserialization)
#   }

#   // private def doBenchMarkingSyncedDataBlock(): Unit = {
#   //   List(false, true).foreach(hasSync => {
#   //     val rt = ReportTable(if (hasSync) s"Delay & Sync" else "Delay", List("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)"))
#   //       .setFormatter(0, formatterKMG)
#   //       .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#   //       .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#   //       .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#   //     List(10000, 100000, 1000000, 4000000).foreach(r => {
#   //       val bm = doBenchMarkingSyncedDataBlock(
#   //         r,
#   //         List(
#   //           List(1),
#   //           List(1, 1),
#   //           List(5, 3, 1, 1)
#   //         ),
#   //         hasSync
#   //       )
#   //       rt.addRow(r, bm(0), bm(1), bm(2))
#   //     })
#   //     rt.output()
#   //   })
#   // }

#   // private def doBenchMarkingSyncedDataBlock(totalSize: Int, sizes: List[List[Double]], hasSync: Boolean): List[Double] = {
#   //   sizes.map(size => {
#   //     val m = Range(0, size.size + 1).map(s => s -> (if (s == 0) List("Period", 10000) else List("Pulse", 100000000, (size(s - 1) / size.sum * totalSize).toInt, 1000))).toMap
#   //     val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), m)
#   //     doBenchMarkingOpertion(() => { dataBlock.synced(Range(0, 16).toList.map(_ => 100000), if (hasSync) Map("Method" -> "PeriodSignal", "SyncChannel" -> "0", "Period" -> "2e8") else Map()) })
#   //   })
#   // }

#   private def doBenchMarkingMultiHistogramAnalyser(): Unit = {
#     val rt = ReportTable(s"MultiHistogramAnalyser", List("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)"))
#       .setFormatter(0, formatterKMG)
#       .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#       .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#       .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#     List(10000, 100000, 1000000, 4000000, 10000000).foreach(r => {
#       val bm = doBenchMarkingMultiHistogramAnalyser(
#         r,
#         List(
#           List(1),
#           List(1, 1),
#           List(5, 3, 1, 1)
#         )
#       )
#       rt.addRow(r, bm(0), bm(1), bm(2))
#     })
#     rt.output()
#   }

#   private def doBenchMarkingMultiHistogramAnalyser(totalSize: Int, sizes: List[List[Double]]): List[Double] = {
#     val mha = new MultiHistogramAnalyser(16)
#     mha.turnOn(Map("Sync" -> 0, "Signals" -> List(1), "ViewStart" -> -1000000, "ViewStop" -> 1000000, "BinCount" -> 100, "Divide" -> 100))
#     sizes.map(size => {
#       val m = Range(0, size.size + 1).map(s => s -> (if (s == 0) List("Period", 10000) else List("Pulse", 100000000, (size(s - 1) / size.sum * totalSize).toInt, 1000))).toMap
#       val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), m)
#       doBenchMarkingOpertion(() => mha.dataIncome(dataBlock))
#     })
#   }

#   private def doBenchMarkingExceptionMonitorAnalyser(): Unit = {
#     val rt = ReportTable(s"ExceptionMonitorAnalyser", List("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)"))
#       .setFormatter(0, formatterKMG)
#       .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#       .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#       .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
#     List(10000, 100000, 1000000, 4000000).foreach(r => {
#       val bm = doBenchMarkingExceptionMonitorAnalyser(
#         r,
#         List(
#           List(1),
#           List(1, 1),
#           List(5, 3, 1, 1)
#         )
#       )
#       rt.addRow(r, bm(0), bm(1), bm(2))
#     })
#     rt.output()
#   }

#   private def doBenchMarkingExceptionMonitorAnalyser(totalSize: Int, sizes: List[List[Double]]): List[Double] = {
#     val mha = new ExceptionMonitorAnalyser(16)
#     mha.turnOn(Map("SyncChannels" -> List(0, 1, 2, 3, 4, 5, 6)))
#     sizes.map(size => {
#       val m = Range(0, size.size + 1).map(s => s -> (if (s == 0) List("Period", 10000) else List("Pulse", 100000000, (size(s - 1) / size.sum * totalSize).toInt, 1000))).toMap
#       val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), m)
#       doBenchMarkingOpertion(() => mha.dataIncome(dataBlock))
#     })
#   }

#   private def doBenchMarkingOpertion(operation: () => Unit) = {
#     val stop = System.nanoTime() + 1000000000
#     val count = new AtomicInteger(0)
#     while (System.nanoTime() < stop) {
#       operation()
#       count.incrementAndGet()
#     }
#     (1e9 + System.nanoTime() - stop) / 1e9 / count.get
#   }

#   object ReportTable {
#     def apply(title: String, headers: List[String], cellWidth: Int = UNIT_SIZE) = new ReportTable(title, headers, cellWidth = cellWidth)
#   }

#   private def formatterKMG(value: Any): String =
#     value match {
#       case data if data.isInstanceOf[Int] || data.isInstanceOf[Long] || data.isInstanceOf[String] =>
#         data.toString.toLong match {
#           case d if d < 0    => "-"
#           case d if d < 1e2  => d.toString
#           case d if d < 1e3  => f"${d / 1e3}%.3f K"
#           case d if d < 1e4  => f"${d / 1e3}%.2f K"
#           case d if d < 1e5  => f"${d / 1e3}%.1f K"
#           case d if d < 1e6  => f"${d / 1e6}%.3f M"
#           case d if d < 1e7  => f"${d / 1e6}%.2f M"
#           case d if d < 1e8  => f"${d / 1e6}%.1f M"
#           case d if d < 1e9  => f"${d / 1e9}%.3f G"
#           case d if d < 1e10 => f"${d / 1e9}%.2f G"
#           case d if d < 1e11 => f"${d / 1e9}%.1f G"
#           case d if d < 1e12 => f"${d / 1e12}%.3f T"
#           case d if d < 1e13 => f"${d / 1e12}%.2f T"
#           case d if d < 1e14 => f"${d / 1e12}%.1f T"
#           case d             => "--"
#         }
#     }

#   class ReportTable private (val title: String, val headers: List[String], val cellWidth: Int = UNIT_SIZE) {
#     private val rows = ListBuffer[List[Any]]()
#     private val formatters = new mutable.HashMap[Int, Any => String]()

#     def setFormatter(column: Int, formatter: Any => String) = {
#       formatters(column) = formatter
#       this
#     }

#     def addRow(item: Any*) = {
#       if (item.size != headers.size) throw new RuntimeException("Dimension of table of matched.")
#       rows += item.toList
#       this
#     }

#     def addRows(rows: List[Any]*) = rows.map(addRow).head

#     def output(target: PrintStream = System.out): Unit = {
#       val totalWidth = headers.size * (1 + cellWidth) + 1
#       target.println("+" + Range(0, totalWidth - 2).map(_ => "-").mkString("") + "+")
#       target.println("|" + complete(title, totalWidth - 2, alignment = "center") + "|")
#       target.println("+" + Range(0, totalWidth - 2).map(_ => "-").mkString("") + "+")
#       target.println("|" + headers.map(header => complete(header, cellWidth)).mkString("|") + "|")
#       rows.foreach(row =>
#         target.println(
#           "|" + row.zipWithIndex
#             .map(z =>
#               complete(
#                 formatters.get(z._2) match {
#                   case Some(f) => f(z._1)
#                   case None    => z._1.toString
#                 },
#                 cellWidth
#               )
#             )
#             .mkString("|") + "|"
#         )
#       )
#       target.println("+" + Range(0, totalWidth - 2).map(_ => "-").mkString("") + "+")
#     }

#     private def complete(content: String, width: Int, filler: String = " ", alignment: String = "Center"): String = {
#       if (content.length > width) content.slice(0, width - 3) + "..."
#       else {
#         val diff = width - content.length
#         alignment.toLowerCase match {
#           case "left"   => content + Range(0, diff).map(_ => filler).mkString("")
#           case "right"  => Range(0, diff).map(_ => filler).mkString("") + content
#           case "center" => Range(0, diff / 2).map(_ => filler).mkString("") + content + Range(0, diff - diff / 2).map(_ => filler).mkString("")
#         }
#       }
#     }
#   }






### 2023-01-17
# 
# +-----------------------------------------------------------------------------------+
# |                      DataBlock serial/deserial: Period List                       |
# +-----------------------------------------------------------------------------------+
# |     Event Size     |     Data Rate      |    Serial Time     |   Deserial Time    |
# |       10.0 K       |        4.02        |      0.23 ms       |      0.22 ms       |
# |      0.100 M       |        4.00        |      2.34 ms       |      1.84 ms       |
# |       1.00 M       |        3.50        |      20.60 ms      |      20.52 ms      |
# |       4.00 M       |        3.00        |      66.53 ms      |      72.75 ms      |
# |       10.0 M       |        3.00        |     192.85 ms      |     197.78 ms      |
# +-----------------------------------------------------------------------------------+
# +-----------------------------------------------------------------------------------+
# |                   DataBlock serial/deserial: Period List, 16 ps                   |
# +-----------------------------------------------------------------------------------+
# |     Event Size     |     Data Rate      |    Serial Time     |   Deserial Time    |
# |       10.0 K       |        3.52        |      0.19 ms       |      0.20 ms       |
# |      0.100 M       |        3.50        |      1.89 ms       |      1.62 ms       |
# |       1.00 M       |        3.00        |      16.56 ms      |      14.76 ms      |
# |       4.00 M       |        2.50        |      57.45 ms      |      63.33 ms      |
# |       10.0 M       |        2.50        |     161.39 ms      |     173.78 ms      |
# +-----------------------------------------------------------------------------------+
# +-----------------------------------------------------------------------------------+
# |                      DataBlock serial/deserial: Random List                       |
# +-----------------------------------------------------------------------------------+
# |     Event Size     |     Data Rate      |    Serial Time     |   Deserial Time    |
# |       10.0 K       |        4.09        |      0.27 ms       |      0.23 ms       |
# |      0.100 M       |        3.84        |      2.73 ms       |      2.02 ms       |
# |       1.00 M       |        3.46        |      27.84 ms      |      17.93 ms      |
# |       4.00 M       |        3.00        |      67.95 ms      |      72.18 ms      |
# |       10.0 M       |        2.99        |     223.87 ms      |     203.55 ms      |
# +-----------------------------------------------------------------------------------+
# +-----------------------------------------------------------------------------------+
# |                   DataBlock serial/deserial: Random List, 16 ps                   |
# +-----------------------------------------------------------------------------------+
# |     Event Size     |     Data Rate      |    Serial Time     |   Deserial Time    |
# |       10.0 K       |        3.59        |      0.23 ms       |      0.22 ms       |
# |      0.100 M       |        3.34        |      2.47 ms       |      1.87 ms       |
# |       1.00 M       |        2.96        |      25.44 ms      |      15.26 ms      |
# |       4.00 M       |        2.50        |      60.71 ms      |      64.85 ms      |
# |       10.0 M       |        2.49        |     194.03 ms      |     175.51 ms      |
# +-----------------------------------------------------------------------------------+
# +-----------------------------------------------------------------------------------+
# |                       DataBlock serial/deserial: Mixed List                       |
# +-----------------------------------------------------------------------------------+
# |     Event Size     |     Data Rate      |    Serial Time     |   Deserial Time    |
# |       10.0 K       |        4.46        |      0.33 ms       |      0.25 ms       |
# |      0.100 M       |        3.99        |      2.63 ms       |      1.86 ms       |
# |       1.00 M       |        3.55        |      21.01 ms      |      17.55 ms      |
# |       4.00 M       |        3.30        |     100.42 ms      |      80.10 ms      |
# |       10.0 M       |        3.05        |     194.05 ms      |     198.66 ms      |
# +-----------------------------------------------------------------------------------+
# +-----------------------------------------------------------------------------------+
# |                   DataBlock serial/deserial: Mixed List, 16 ps                    |
# +-----------------------------------------------------------------------------------+
# |     Event Size     |     Data Rate      |    Serial Time     |   Deserial Time    |
# |       10.0 K       |        3.96        |      0.30 ms       |      0.23 ms       |
# |      0.100 M       |        3.49        |      2.29 ms       |      1.65 ms       |
# |       1.00 M       |        3.05        |      17.59 ms      |      14.93 ms      |
# |       4.00 M       |        2.80        |      89.44 ms      |      69.67 ms      |
# |       10.0 M       |        2.55        |     168.39 ms      |     173.34 ms      |
# +-----------------------------------------------------------------------------------+
# 
# 
# 
# 
# 
# 
# 
# ###