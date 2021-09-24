# from DataBlock import DataBlock
# import time
#
# if __name__ == '__main__':
#     UNIT_SIZE = 20
#
#     def run():
#         print("\n ******** Start BenchMarking ******** \n")
#         benchMarkingSerDeser()
#         #     doBenchMarkingMultiHistogramAnalyser()
#
#     def benchMarkingSerDeser():
#         configs = [
#             ("Period List", (40000,), lambda r: {0: ("Period", r)}, 1e-12),
#             # ("Period List", (10000, 100000, 1000000, 4000000), lambda r: {0: ("Period", r)}, 1e-12),
#     #       ("Period List, 16 ps", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Period", r)), 16e-12),
#     #       ("Random List", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Random", r)), 1e-12),
#     #       ("Random List, 16 ps", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Random", r)), 16e-12),
#     #       ("Mixed List", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Period", r / 10), 1 -> List("Random", r / 10 * 4), 5 -> List("Random", r / 10 * 5), 10 -> List("Period", 10), 12 -> List("Random", 1)), 1e-12),
#     #       ("Mixed List, 16 ps", List(10000, 100000, 1000000, 4000000), (r: Int) => Map(0 -> List("Period", r / 10), 1 -> List("Random", r / 10 * 4), 5 -> List("Random", r / 10 * 5), 10 -> List("Period", 10), 12 -> List("Random", 1)), 16e-12),
#         ]
#         for config in configs:
#             rt = ReportTable("DataBlock serial/deserial: {}".format(config[0]), ("Event Size", "Data Rate", "Serial Time", "Deserial Time")).setFormatter(0, formatterKMG).setFormatter(1, lambda dr: "{:.2f}".format(dr)).setFormatter(2, lambda second: "{:.2f} ms".format(second * 1000)).setFormatter(3, lambda second: "{:.2f} ms".format(second * 1000))
#             for r in config[1]:
#                 bm = doBenchMarkingSerDeser(config[2](r), config[3])
#                 rt.addRow(r, bm[0], bm[1], bm[2])
#             rt.output()
#
#     def doBenchMarkingSerDeser(dataConfig, resolution=1e-12):
#         generatedDB = DataBlock.generate({"CreationTime": 100, "DataTimeBegin": 10, "DataTimeEnd": 1000000000010}, dataConfig)
#         testDataBlock = generatedDB if resolution == 1e-12 else generatedDB.convertResolution(resolution)
#         data = testDataBlock.serialize()
#         # recovered = DataBlock.deserialize(data)
#         consumingSerialization = doBenchMarkingOpertion(lambda: testDataBlock.serialize())
#         infoRate = len(data) / sum([len(ch) for ch in testDataBlock.content])
#         # consumingDeserialization = doBenchMarkingOpertion(lambda: DataBlock.deserialize(data))
#         # return (infoRate, consumingSerialization, consumingDeserialization)
#         return (infoRate, consumingSerialization, 0)
#
# #   private def doBenchMarkingMultiHistogramAnalyser(): Unit = {
# #     val rt = ReportTable(s"MultiHistogramAnalyser", List("Total Event Size", "1 Ch", "2 Ch (1, 1)", "4 Ch (5, 3, 1, 1)"))
# #       .setFormatter(0, formatterKMG)
# #       .setFormatter(1, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
# #       .setFormatter(2, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
# #       .setFormatter(3, (second) => f"${second.asInstanceOf[Double] * 1000}%.2f ms")
# #     List(10000, 100000, 1000000, 4000000).foreach(r => {
# #       val bm = doBenchMarkingMultiHistogramAnalyser(
# #         r,
# #         List(
# #           List(1),
# #           List(1, 1),
# #           List(5, 3, 1, 1)
# #         )
# #       )
# #       rt.addRow(r, bm(0), bm(1), bm(2))
# #     })
# #     rt.output()
# #   }
#
# #   private def doBenchMarkingMultiHistogramAnalyser(totalSize: Int, sizes: List[List[Double]]): List[Double] = {
# #     val mha = new MultiHistogramAnalyser(16)
# #     mha.turnOn(Map("Sync" -> 0, "Signals" -> List(1), "ViewStart" -> -1000000, "ViewStop" -> 1000000, "BinCount" -> 100, "Divide" -> 100))
# #     sizes.map(size => {
# #       val m = Range(0, size.size + 1).map(s => s -> (if (s == 0) List("Period", 10000) else List("Pulse", 100000000, (size(s - 1) / size.sum * totalSize).toInt, 1000))).toMap
# #       val dataBlock = DataBlock.generate(Map("CreationTime" -> 100, "DataTimeBegin" -> 0L, "DataTimeEnd" -> 1000000000000L), m)
# #       doBenchMarkingOpertion(() => mha.dataIncome(dataBlock))
# #     })
# #   }
#
#     def doBenchMarkingOpertion(operation):
#         stop = time.time() + 1
#         count = 0
#         while time.time() < stop:
#             operation()
#             count += 1
#         return (1 + time.time() - stop) / count
#
#     def formatterKMG(value):
# #     value match {
# #       case data if data.isInstanceOf[Int] || data.isInstanceOf[Long] || data.isInstanceOf[String] =>
# #         data.toString.toLong match {
# #           case d if d < 0    => "-"
# #           case d if d < 1e2  => d.toString
# #           case d if d < 1e3  => f"${d / 1e3}%.3f K"
# #           case d if d < 1e4  => f"${d / 1e3}%.2f K"
# #           case d if d < 1e5  => f"${d / 1e3}%.1f K"
# #           case d if d < 1e6  => f"${d / 1e6}%.3f M"
# #           case d if d < 1e7  => f"${d / 1e6}%.2f M"
# #           case d if d < 1e8  => f"${d / 1e6}%.1f M"
# #           case d if d < 1e9  => f"${d / 1e9}%.3f G"
# #           case d if d < 1e10 => f"${d / 1e9}%.2f G"
# #           case d if d < 1e11 => f"${d / 1e9}%.1f G"
# #           case d if d < 1e12 => f"${d / 1e12}%.3f T"
# #           case d if d < 1e13 => f"${d / 1e12}%.2f T"
# #           case d if d < 1e14 => f"${d / 1e12}%.1f T"
# #           case d             => "--"
# #         }
# #     }
#         return str(value)
#
#     class ReportTable:
#         def __init__(self, title, headers, cellWidth=UNIT_SIZE):
#             self.title = title
#             self.headers = headers
#             self.cellWidth = cellWidth
#             self.rows = []
#             self.formatters = {}
#
#         def setFormatter(self, column, formatter):
#             self.formatters[column] = formatter
#             return self
#
#         def addRow(self, *item):
#             if len(item) != len(self.headers): raise RuntimeError("Dimension of table of matched.")
#             self.rows.append(item)
#             return self
#
# #     def addRows(rows: List[Any]*) = rows.map(addRow).head
#
#         def output(self):
#             output = ''
#             totalWidth = len(self.headers) * (1 + self.cellWidth) + 1
#             output += ("+" + "-" * (totalWidth - 2) + "+\n")
#             output += ("|" + self.complete(self.title, totalWidth - 2, alignment="center") + "|\n")
#             output += ("+" + '-' * (totalWidth - 2) + "+\n")
#             output += ("|" + '|'.join([self.complete(header, self.cellWidth) for header in self.headers]) + "|\n")
#             for row in self.rows:
#                 output += '|' + '|'.join([(self.complete(self.__getFormatter(i)(row[i]), self.cellWidth)) for i in range(len(row))]) + "|\n"
#             output += ("+" + "-" * (totalWidth - 2) + "+")
#             print(output)
#
#         def complete(self, content, width, filler=" ", alignment="Center"):
#             if len(content) > width:
#                 return content[0: width - 3] + "..."
#             else:
#                 diff = width - len(content)
#                 alignment = alignment.lower()
#                 if alignment == 'left':
#                     return content + filler * diff
#                 elif alignment == 'right':
#                     return filler * diff + content
#                 elif alignment == 'center':
#                     return filler * int(diff / 2) + content + filler * (diff - int(diff / 2))
#                 else:
#                     raise RuntimeError('bad alignment: {}'.format(alignment))
#
#         def __getFormatter(self, name):
#             if self.formatters.__contains__(name):
#                 return self.formatters[name]
#             else:
#                 return lambda item: str(item)
#
#     run()
