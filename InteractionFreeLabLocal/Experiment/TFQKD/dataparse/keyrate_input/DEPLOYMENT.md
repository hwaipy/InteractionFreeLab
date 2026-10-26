# LabServer2 部署与手动运行

代码部署目录：`/home/freespace/code/InteractionFreeLab_preprocess_20261026`

生产批处理输出目录：`/data/TFQKD/preprocessed/20261026`

运行使用 `/home/freespace/miniconda3/bin/python`（Python 3.11），不改变系统 Python 或其他实验服务。
默认局域网 `2502` 数据源；预检时本次数据在实时库中存在，归档库尚未查到最早段。

## 输入范围

- Markdown：2026-10-26 01:29:03 至 02:29:56.984，北京时间。
- CSV：仅 status=complete 且 include_in_complete_analysis=1 的 70 段。
- 合计 71 段，约 12.6816 小时；中断的最后一段明确排除。
- 保留 CSV 的 round、index、rho、run_id、quality_scope；每段独立生成索引。
- 按实际 FetchTime 属于 `[begin,end)` 选择记录，不把小数秒起止时间四舍五入。
- 采集块约1秒，FetchTime 条件归属不等于逐事件的光学有效性验证，原 quality_scope 保留。

## 启动

```bash
ssh LabServer2
cd /home/freespace/code/InteractionFreeLab_preprocess_20261026
./run_preprocess.sh
```

这是前台运行；Ctrl+C 可中断，重新运行同一命令会校验并复用已有文件。
若要断开 SSH 后继续运行：

```bash
nohup ./run_preprocess.sh > /data/TFQKD/preprocessed/20261026/launcher.log 2>&1 < /dev/null &
tail -f /data/TFQKD/preprocessed/20261026/launcher.log
```

同一个输出目录通过 flock 防止重复启动。完整批处理不会因部署或测试而自动启动。

## 并行与进度

默认16个进程，每进程只有1个 BLAS/Numba 线程。服务器有80个逻辑CPU，保留余量供数据及其他服务使用。
每个任务最多30秒，子进程复用 IF 连接和 JIT 缓存；主进程同时最多挂起32个任务，避免预载全量数据。

每5秒打印：时间槽进度、百分比、成功文件数、缓存数、失败数、数据秒/墙钟秒、已用时间、ETA及预计完成北京时间。
最初 JIT/连接预热阶段显示 estimating；ETA 使用包含获取数据和计算在内的实测速率。
计划共45724个自然秒时间槽；实际文件数会少于时间槽数，因为起止边界可能没有满足条件的 FetchTime。

改为8进程可以直接运行：

```bash
TFQKD_WORKERS=8 ./run_preprocess.sh
```

其他参数在 `InteractionFreeLabLocal/Experiment/TFQKD/dataparse/keyrate_input/preprocess_batch.py` 的 main() 中设置。
改变数据段或 chunk_seconds 后应使用新输出目录；只改变进程数允许复用现有缓存。

## 输出

`/data/TFQKD/preprocessed/20261026/` 下：

- `intermediate/日期/小时/*.npz`：逐秒无损未筛选统计，已应用25kHz时钟校正。
- `datasets.json`：输入文件哈希、71段原始边界、排除记录、分块计划。
- `datasets/<条件ID>/manifest.json`：该段文件列表、失败和边界排除记录，保留轮次及rho。
- `status.json`：最近进度、速率、ETA和状态，运行中持续原子更新。
- `logs/latest.log`：最近一次前台日志。
- `batch_<ID>.jsonl`、`failures_<ID>.jsonl`：逐任务结果、失败详情。
- `summary_<ID>.json`：本次最终状态。
- `journals/`：各任务逐秒记录，用于故障定位。

查看状态：

```bash
cat /data/TFQKD/preprocessed/20261026/status.json
tail -f /data/TFQKD/preprocessed/20261026/logs/latest.log
```

出现坏数据或实时汇总不一致时，该秒记失败并继续其他任务；最终状态为 completed_with_failures 且退出码为1，不能把这种状态当作全量完成。
程序整体中断会标为 interrupted；原子写入的缓存可以续用。网络故障后重新运行会重试失败数据。

## 部署验证

在服务器运行与本地相同的测试，并用基线、第一轮无补偿、第一轮rho=1、最后完整rho=5四类真实数据做有限多进程检查。
测试输出在代码目录的 smoke_output 内，与正式数据目录隔离。

服务器已有 SciPy 与 NumPy 版本提示会在导入 Numba 时出现，现有测试未受影响；未修改共享环境依赖。

## 时间戳分组修复（actual-fetchtime-v2）

采集创建时间存在抖动：同一自然秒可以有两个独立DataBlock，邻近自然秒也可能没有记录。程序改为按精确FetchTime逐条处理，不再因此跳过30秒块。空自然秒仅作诊断；真实Raw读取失败、重复精确时间戳和实时校验差异仍记录为失败。

旧版首轮结果为 completed_with_failures：308个块因分组假设失败，另有5个空自然秒误报、6条实时计数校验差异，并留下8932个未处理时间槽。更新代码后执行相同启动命令，会校验并复用已有文件，再处理此前跳过的记录；旧日志保留。新 status.json 的 code_revision 为 actual-fetchtime-v2。
