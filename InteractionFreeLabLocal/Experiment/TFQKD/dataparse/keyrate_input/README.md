# 成码率输入：逐秒预处理与本地筛选

两个阶段独立运行，参数均写在各自 `main()` 的 `settings` 中，不读取命令行参数。

```text
Meta.QKDQBER.Intermediate ───────────────┐
                                      ↓
历史 Meta + Raw → 初级计算 → preprocess.py → 逐秒 .npz → scan.py → 多组结果 .txt
```

## 1. preprocess.py：准备逐秒文件

编辑 `preprocess.py` 底部：

```python
begin='2026-10-26T01:30:00+08:00',
end='2026-10-26T01:30:02+08:00',
source='2502-public',
output='...',  # 默认 intermediate_clock_corrected；允许重跑、续传
config=None,
clock_frequency=25000,
transform=None,
verify_realtime=True,
timeout=30,
skip_missing=False,
```

- 逐秒读取 Meta 并处理落盘，不把整个时间段的完整 Meta 预载入内存：若存在 `Data.QKDQBER.Intermediate`，直接校验并保存该二进制数据，不下载 Raw。
- 老记录缺少该字段时，根据 Meta 的 `QKDQBER.Configuration` 下载 Raw，先按在线流程的 25 kHz 参考时钟缩放时间戳，再解析，一秒只解析一次。
- 已有 Meta.Intermediate 本身基于在线校正后的数据，直接保存，不会重复缩放。
- 存在 `config` 覆盖或 `transform` 时，从 Raw 重算，避免错误复用服务器已经生成的结果。
- 不应用大气阈值、相位阈值；`config` 也不应包含筛选阈值。
- 默认 `verify_realtime=True`：如果 Meta 有完整实时汇总且没有覆盖固定配置，则按实时的原相位阈值和帧选择核对 X/Y/Z1 正误计数及 Z 计数；不一致立即报错，避免遗漏时钟或 Doppler 校正而生成错误文件。历史 Meta.Valid 为全帧时也兼容旧 `or True` 行为。
- 输出日期/小时目录下 `YYYYMMDDTHHMMSSffffff.npz`，名称保留实际 FetchTime 的微秒信息。
- 文件先写临时文件再原子替换。已有文件通过时间、格式、配置和随机数指纹检查后复用；损坏或不匹配时明确报错，不静默覆盖。
- 每次运行追加记录到 `preprocess_<唯一ID>.jsonl`，结束或中止时写 `.json` 汇总，记录文件、校验和、大小、来源（storage/raw/cache）、缺秒及失败。重跑不删除之前的记录。
- 按实际 FetchTime 逐条处理全部记录；同一个自然秒有多条 Meta 是允许的。空自然秒记为 empty_timestamp_seconds 诊断，不直接当作数据丢失。完全重复的精确时间戳、Raw缺失或实时校验不一致仍报错；批处理记录失败并继续其他记录。

数据源对应 IFView `public/configs/2502.json` 的 AccessCampus / AccessField：

| source | 网络 / 数据 | Meta 地址 | collection | Raw HTTP 地址 |
| --- | --- | --- | --- | --- |
| `2502` | 研究院局域网 / 实时 | `tcp://172.20.8.102:1161` | `TFQKD_TDC` | `http://172.20.8.102:1001` |
| `archive` | 研究院局域网 / 总服务器归档 | `tcp://172.20.8.102:1061` | `TFQKD_TDC_2502` | `http://172.20.8.102:1003` |
| `2502-public` | 外网 / 实时 | `tcp://code.qpqi.group:1161` | `TFQKD_TDC` | `http://code.qpqi.group:1001` |
| `archive-public` | 外网 / 总服务器归档 | `tcp://code.qpqi.group:1061` | `TFQKD_TDC_2502` | `http://code.qpqi.group:1003` |

`config` 是可选 JSON 文件路径，可覆盖固定的门宽、帧长、通道、随机数等；时间单位 ps。
历史数据的随机数必须是等长整数数组，若 Meta 中只是随机数 ID，需要先取得实际数组。

`clock_frequency=25000` 是这套 TDC 服务器的参考时钟频率，独立于 QKD 配置中的 TriggerPeriod。
默认复用在线 `frequencyRescaleAdaptor` 的公式，用通道 0 的平均周期计算 scale，并以通道 1 的 PPS 为时间锚点。
Raw 已包含 TDCServer 的通道延迟校正，不能重复应用 Meta.Configurations.Delays。
时钟缩放作用于所有通道，并保持原始数组不变；校正参数随文件保存。缺少时钟/PPS 时明确报错。

`transform='package.module:function'` 是时钟缩放后的额外校正函数，接收并返回 DataBlock。
需要额外 Doppler 重映射等实验校正时，可在该函数内复用相同逻辑、参数和状态。
若自定义函数本身已包含完整时钟缩放，应显式设置 `clock_frequency=None`，避免重复缩放。
函数名相同时也应保证其代码及外部校正文件不变。

## 2. scan.py：只进行本地筛选

编辑 `scan.py` 底部：

```python
begin='2026-10-26T01:30:00+08:00',
end='2026-10-26T01:30:02+08:00',
input='...',             # preprocess 的输出目录，默认 intermediate_clock_corrected
output='...',            # 新的结果目录，不可覆盖已有目录
phase_bins=[7, 15],
intensity_min=[5, 10, 20],
intensity_max=[1e300],
intensity_ratio=[3],
mu_x=[0.0303853, 0.0303853],
mu_y=[0.482834, 0.482834],
mu_z=[0.494035, 0.494035],
skip_missing=False,
```

上述例子产生 2×3×1×1=6 组结果。列表也可改为单个数值，或 `'0:20:5'` 这样的含终点范围字符串。

- `phase_bins`：0..63，沿用原分析器的累计数组索引。bin k 保留相位距离 `< (k+1)π/128`；bin 7 对应 π/16，bin 15 对应 π/8。
- `intensity_min`：每个强度帧的两侧同步计数均严格大于此值。
- `intensity_max`：两侧同步计数均严格小于此值；`1e300` 相当于无上限。
- `intensity_ratio`：两侧计数比及其倒数均严格小于此值，要求 >1。零同步计数不会通过。
- `mu_x/y/z`：`[Alice强度, Bob强度]`，默认沿用 convert.py，实际使用需按实验填写。
- 一个自然秒可有多个中间文件，全部参与汇总。文件损坏、精确时间戳重复、固定处理参数不兼容仍报错。
- 批数据扫描建议在 settings 中设置 dataset_manifest 为对应 datasets/<条件ID>/manifest.json；默认要求该段预处理状态 completed 且索引列出的文件完整。仅靠自然秒有无文件不能判定完整性。

扫描不联网、不读取 DataBlock，也不重新估计相位。
不同门宽、帧长、算法或校正来源的文件不能混合汇总；随机数可以变化，程序使用已经保存的实际逐帧脉冲数计算概率。

`result_0000.txt` 等是 UTF-8、Tab 分隔的 convert.py 格式文件；`manifest.json` 记录参数与文件对应关系及实际输入文件校验和。
没有 signal 脉冲通过的组合记录为 `file=null`；X/Y 没有筛选计数时错误率为 `nan`。
“X基筛选比例”为均匀相位理论比例 `(bin+1)/64`，不是实测计数保留比例。

## 3. 公共格式与在线输出

压缩、解压、校验全部在 `services/tdc/TFQKDQBERAnalyser.py` 的 `QKDIntermediate` 类内，没有另建公共模块。

`TFQKDQBERAnalyser.analysis()` 一次解析后，保留原有汇总字段，并新增：

```python
result['Intermediate'] = ...  # bytes，np.savez_compressed 格式
```

现有 `Analyser.dataIncome()` 仍添加 Configuration，TDCServer 把整个结果写入 Storage：

```python
payload = meta['Data']['QKDQBER']['Intermediate']
intermediate = QKDIntermediate.unpack(payload)
```

载荷只使用数值数组和 UTF-8 JSON 元信息，不使用 pickle、base64 或 JSON 展开的计数数组。
逐秒 `.npz` 与 Meta 的二进制字段使用完全相同的格式。

| 数组 | 维度 | 含义 |
| --- | --- | --- |
| syncCountsAlice / syncCountsBob | F | 未筛选同步计数 |
| pulseCounts | 4×4×F | 未筛选 signal 发射脉冲数 |
| detectionStatistics | 4×4×F | 门内未筛选探测计数 |
| phaseHistogram | 4×F×64×2 | 非累计相位区间正确/错误计数 |

F 是一秒的强度帧数。基顺序为 O/X/Y/Z，错误轴为正确/错误。
加载后 `phaseErrorStatistics` 自动对 phaseHistogram 累加，精确恢复原分析器的累计统计。
计数通常为 uint32；超出范围时用 uint64，不截断。汇总时使用 64 位计数。

元信息包含版本、算法、实际 FetchTime、固定配置、随机数哈希、分析窗口和边界排除数量。
不重复保存完整随机数序列，也不保存当前筛选阈值或逐相位帧的 phaseDeltas。
门宽、帧长、相位估计算法或时序校正发生变化时，必须重新初级处理。

## 4. 处理口径与部署

- 数据范围为 `[begin, end)`，输入不带时区时按北京时间解释，支持小数秒边界。
- 初级处理以首个 TriggerChannel 的事件为时间原点，只保留探测和同步通道中相对 `[0, TimeEachBlock)` 的事件。原始数组不被修改，边界排除数量随文件保存。
- 发射脉冲只计 signal 段，按循环随机数序列和脉冲中心归属的强度帧精确计数，不含 reference/gap。
- 大气筛选同时作用于脉冲数、探测计数和相位计数；组合比例以筛选后 signal 脉冲数归一化。4×4 探测计数不应用相位筛选。
- 相位算法仍沿用现有分析器的频差为 0 假设。
- 在线数据标为 `tdc-adapted`；默认历史补算标为 `tdc-clock-v1:25000Hz`。显式关闭时钟缩放时才标为 `raw-unadapted`。扫描仍禁止混用不同来源，因为在线还可能有额外 Doppler 校正。
- 旧 `intermediate` 目录中的 raw-unadapted 文件遗漏在线时钟缩放，会产生错误的门内事件和随机数归属，不能继续用于可信的误码率计算。修复后的默认目录为 `intermediate_clock_corrected`，旧文件保留；旧缓存不会被新默认设置静默复用。
- 新字段只会出现在**更新分析器并重新启动相关 TDC 服务之后的新采集记录**中。此代码修改不会追溯更新历史 Meta，也不会自行重启实验服务。
- 现有 DataBackup_2502.py 整体复制 entry['Data']，因此无需单独增加字段复制逻辑。

## 运行与测试

从仓库根目录运行（或在 IDE 分别执行两个文件）：

```bash
python3 InteractionFreeLabLocal/Experiment/TFQKD/dataparse/keyrate_input/preprocess.py
python3 InteractionFreeLabLocal/Experiment/TFQKD/dataparse/keyrate_input/scan.py
```

依赖 numpy、numba、msgpack；只有 preprocess 的远程读取另外需要 interactionfreepy。

```bash
python3 -m unittest discover -s InteractionFreeLabLocal/Experiment/TFQKD/dataparse/keyrate_input -v
```

测试覆盖在线汇总兼容、二进制消息往返、压缩解压无损、原始数据回退、Storage 优先、缓存续跑、坏文件和不兼容校正拒绝，以及逐秒处理后扫描。
未向生产数据库写入测试记录；生产 Storage 的实际写入/备份回读仍需在服务部署后确认。

最初的两秒拆分验证只证明拆分前后结果相同，未验证与实时 Meta 一致；已发现并补齐历史 Raw 的 TDC 时钟缩放。用相同相位阈值及相同帧选择与实时 Meta 对照，才能验证处理口径。

时钟校正验证：2026-10-26 01:30:00 至 01:31:00 共 60 秒，按实时相同相位阈值和帧选择核对，X/Y/Z1 正误计数和 Z 计数全部逐秒一致。修正后的 6 组输出保存在 results/scan_clock_corrected，旧结果保留。以 bin7、同步计数下限5、计数比3为例，X基1错误率5.263%，X基2错误率5.066%。

## 多CPU批处理与LabServer2

`preprocess_batch.py` 读取 batch_inputs 中的两份采集记录，默认16进程、每任务30秒，保留精确时间边界及条件标签。只纳入CSV的70条完整记录，加上Markdown基线共71段；中断段排除。
进度、ETA、失败详情和每段索引会持续落盘。部署和手动启动说明见同目录 DEPLOYMENT.md。
