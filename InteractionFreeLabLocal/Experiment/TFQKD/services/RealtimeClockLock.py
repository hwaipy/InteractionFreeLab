"""独立运行的时钟锁定循环；使用 --help 查看命令行配置。"""
import argparse
import math
import json
from datetime import datetime
from pathlib import Path
import time

if __name__ == '__main__':
  print(f'[启动] {Path(__file__).resolve()}，工作目录：{Path.cwd()}', flush=True)
  print('[启动] 正在导入 interactionfreepy…', flush=True)

from interactionfreepy import IFWorker


def sendDelay(outputWorker, bobDelay, ddsServiceName='DDSClock'):
  """Bob delay 的单位为 ps；阻塞到 DDS 重试成功并完成稳定等待。"""
  result = outputWorker.blockingInvoker(ddsServiceName, timeout=None).correctDelay(bobDelay)
  if not isinstance(result, dict) or result.get('State') != 'Success':
    raise RuntimeError(f'DDS 补偿未成功：{result}')
  return result


def logEvent(stream, event, **fields):
  now_ns = time.time_ns()
  seconds, nanoseconds = divmod(now_ns, 1000000000)
  localTime = datetime.fromtimestamp(seconds).astimezone().replace(microsecond=nanoseconds // 1000)
  record = {'LocalTime': localTime.isoformat(timespec='microseconds'),
            'UnixTimeNs': now_ns, 'MonotonicNs': time.perf_counter_ns(),
            'Event': event, **fields}
  stream.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
  stream.flush()


def run(tdcEndpoint, outputEndpoint, interval=0.1, serviceName='RealTimeTDC',
        timeout=2.0, maxAge=1.0, period=10000, logFile=None,
        ddsServiceName='DDSClock', clockSkewTolerance=0.2, direction=1):
  """读取最新值 → 外发 → 等待 interval 秒，逐事件记录本机时间。"""
  if any(not math.isfinite(v) or v <= 0 for v in (interval, timeout, maxAge)):
    raise ValueError('interval、timeout、maxAge 必须为正的有限秒数')
  if not math.isfinite(period) or period <= 0:
    raise ValueError('period 必须为正的有限数，单位 ps')
  if not math.isfinite(clockSkewTolerance) or clockSkewTolerance < 0:
    raise ValueError('clockSkewTolerance 必须为非负的有限秒数')
  if isinstance(direction, bool) or direction not in (-1, 1):
    raise ValueError('direction 必须为 +1 或 -1')
  if logFile is None:
    logFile = Path.cwd() / 'logs' / f'RealtimeClockLock_{datetime.now():%Y%m%d_%H%M%S_%f}.log'
  logFile = Path(logFile).resolve()
  logFile.parent.mkdir(parents=True, exist_ok=True)
  print(f'时钟锁定运行日志：{logFile}', flush=True)
  with logFile.open('a', encoding='utf-8') as log:
    logEvent(log, 'run_start', TDCEndpoint=tdcEndpoint, OutputEndpoint=outputEndpoint,
             ServiceName=serviceName, IntervalS=interval, TimeoutS=timeout,
             MaxAgeS=maxAge, PeriodPs=period, LogFile=str(logFile),
             ControlTarget='Bob', DDSServiceName=ddsServiceName,
             DDSTimeoutS=None, ClockSkewToleranceS=clockSkewTolerance, Direction=direction)
    inputWorker = outputWorker = None
    lastSample = None
    cycle = 0
    lastStatusTime = float('-inf')
    sendAnnounced = False

    def showStatus(message):
      nonlocal lastStatusTime
      now = time.monotonic()
      if now - lastStatusTime >= 1:
        print(f'[{datetime.now().astimezone().isoformat(timespec="milliseconds")}] {message}', flush=True)
        lastStatusTime = now

    try:
      print(f'[启动] 创建读取连接：{tdcEndpoint}，服务={serviceName}，超时={timeout} s', flush=True)
      inputWorker = IFWorker(tdcEndpoint, timeout=timeout)
      print(f'[启动] 创建外发连接：{outputEndpoint}，DDS={ddsServiceName}，阻塞等待完成', flush=True)
      outputWorker = IFWorker(outputEndpoint, timeout=None)
      realtimeTDC = inputWorker.blockingInvoker(serviceName, timeout=timeout)
      logEvent(log, 'workers_connected')
      print(f'[启动] 开始读取 delay，每轮结束后等待 {interval} s，周期={period} ps，方向={direction:+d}', flush=True)
      while True:
        cycle += 1
        stage = 'fetch'
        try:
          logEvent(log, 'fetch_begin', Cycle=cycle)
          fetchBeginNs, fetchBeginMono = time.time_ns(), time.perf_counter_ns()
          rows = realtimeTDC.getRecent(1, reversed=True, delayOnly=True)
          fetchEndNs, fetchEndMono = time.time_ns(), time.perf_counter_ns()
          logEvent(log, 'fetch_result', Cycle=cycle, Count=len(rows),
                   BeginUnixTimeNs=fetchBeginNs, EndUnixTimeNs=fetchEndNs,
                   DurationMs=(fetchEndMono - fetchBeginMono) / 1e6)
          stage = 'process'
          if rows:
            sample = rows[0]
            sampleID = (sample['OfferTime'], sample['Sequence'])
            delays = sample['Delays']
            age = fetchEndNs / 1e9 - sample['OfferTime']
            # 两台机器存在小幅时钟偏差时，允许有限的负数据年龄，实际值完整写日志。
            fresh = -clockSkewTolerance <= age <= maxAge
            valid = len(delays) == 2 and delays[1] is not None and math.isfinite(delays[1])
            sampleInfo = dict(Sequence=sample['Sequence'], FetchTime=sample.get('FetchTime'),
                              OfferTime=sample['OfferTime'], ProcessingTime=sample.get('ProcessingTime'),
                              RawDelaysPs=delays, AgeMs=age * 1000, PeriodPs=period,
                              SyncStatistics=sample.get('SyncStatistics'),
                              ControlTarget='Bob', DDSServiceName=ddsServiceName, Direction=direction)
            if sampleID != lastSample and fresh and valid:
              wrapped = [None if d is None or not math.isfinite(d) else
                         (d + period / 2) % period - period / 2 for d in delays]
              commandDelay = direction * wrapped[1]
              # 外发超时时结果可能已生效，避免对同一块自动重复外发。
              lastSample = sampleID
              stage = 'send'
              logEvent(log, 'send_begin', Cycle=cycle, DelaysPs=wrapped,
                       CommandDelayPs=commandDelay, **sampleInfo)
              if not sendAnnounced:
                print(f'[外发] {ddsServiceName}.correctDelay({commandDelay})，Bob，'
                      f'Sequence={sample["Sequence"]}，等待补偿完成…', flush=True)
                sendAnnounced = True
              sendBeginNs, sendBeginMono = time.time_ns(), time.perf_counter_ns()
              try:
                result = sendDelay(outputWorker, commandDelay, ddsServiceName)
              except Exception as exc:
                sendEndNs, sendEndMono = time.time_ns(), time.perf_counter_ns()
                logEvent(log, 'send_result', Cycle=cycle, CallReturned=False,
                         BeginUnixTimeNs=sendBeginNs, EndUnixTimeNs=sendEndNs,
                         DurationMs=(sendEndMono - sendBeginMono) / 1e6,
                         Error=repr(exc), DelaysPs=wrapped, CommandDelayPs=commandDelay, **sampleInfo)
                raise
              sendEndNs, sendEndMono = time.time_ns(), time.perf_counter_ns()
              logEvent(log, 'send_result', Cycle=cycle, CallReturned=True,
                       BeginUnixTimeNs=sendBeginNs, EndUnixTimeNs=sendEndNs,
                       DurationMs=(sendEndMono - sendBeginMono) / 1e6,
                       FetchToReturnMs=None if sample.get('FetchTime') is None else
                           (sendEndNs / 1e9 - sample['FetchTime']) * 1000,
                       OfferToReturnMs=(sendEndNs / 1e9 - sample['OfferTime']) * 1000,
                       Result=result, DelaysPs=wrapped, CommandDelayPs=commandDelay, **sampleInfo)
              showStatus(f'第 {cycle} 轮，Sequence={sample["Sequence"]}，delay={wrapped} ps，'
                         f'外发补偿={commandDelay} ps，方向={direction:+d}，DDS 返回成功，'
                         f'耗时 {(sendEndMono - sendBeginMono) / 1e6:.2f} ms')
            else:
              reason = 'duplicate' if sampleID == lastSample else ('invalid' if not valid else 'stale')
              logEvent(log, 'sample_skipped', Cycle=cycle, Reason=reason, **sampleInfo)
              reasons = {'duplicate': '尚无新的数据块', 'invalid': 'Bob delay 无效，等待有效同步数据',
                         'stale': '数据过期或时钟偏差，请检查两台机器的时间'}
              showStatus(f'第 {cycle} 轮，{reasons[reason]}；Sequence={sample["Sequence"]}，'
                         f'delay={delays}，数据年龄={age * 1000:.1f} ms')
          else:
            logEvent(log, 'no_data', Cycle=cycle)
            showStatus(f'第 {cycle} 轮，RealTimeTDC 暂无数据，等待中…')
        except Exception as exc:
          logEvent(log, 'cycle_error', Cycle=cycle, Stage=stage, Error=repr(exc))
          print(f'时钟锁定本轮失败：{exc}', flush=True)
        # 每轮处理完成后再等待，而不是按固定时刻追赶下一轮。
        logEvent(log, 'wait_begin', Cycle=cycle, IntervalS=interval)
        time.sleep(interval)
    except KeyboardInterrupt:
      logEvent(log, 'interrupted', Cycle=cycle)
      print('时钟锁定循环已停止。', flush=True)
    except Exception as exc:
      logEvent(log, 'run_error', Cycle=cycle, Error=repr(exc))
      raise
    finally:
      for role, worker in [('output', outputWorker), ('input', inputWorker)]:
        if worker is not None:
          try:
            worker.close()
          except Exception as exc:
            logEvent(log, 'close_error', Worker=role, Error=repr(exc))
      logEvent(log, 'run_stop', Cycle=cycle)


def positiveNumber(value):
  try:
    number = float(value)
  except ValueError:
    raise argparse.ArgumentTypeError('必须为正的有限数')
  if not math.isfinite(number) or number <= 0:
    raise argparse.ArgumentTypeError('必须为正的有限数')
  return number


def nonnegativeNumber(value):
  try:
    number = float(value)
  except ValueError:
    raise argparse.ArgumentTypeError('必须为非负的有限数')
  if not math.isfinite(number) or number < 0:
    raise argparse.ArgumentTypeError('必须为非负的有限数')
  return number


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--tdc-endpoint', default='tcp://code.qpqi.group:1161',
                      help='RealTimeTDC 所在的 Broker 地址')
  parser.add_argument('--output-endpoint', default='tcp://tf.qpqi.group:1161',
                      help='外发控制所使用的 Broker 地址')
  parser.add_argument('--service-name', default='RealTimeTDC', help='实时 TDC 服务名')
  parser.add_argument('--dds-service-name', default='DDSClock', help='控制 Bob 时钟的 DDS 服务名')
  parser.add_argument('--direction', type=int, choices=(-1, 1), default=1,
                      help='补偿方向：+1 原样外发 Bob delay，-1 反向外发')
  parser.add_argument('--interval', type=positiveNumber, default=0.1,
                      help='每轮处理完成后的等待时间，单位 s')
  parser.add_argument('--timeout', type=positiveNumber, default=2.0,
                      help='读取 TDC 的请求超时，单位 s；DDS 补偿不设超时')
  parser.add_argument('--max-age', type=positiveNumber, default=1.0,
                      help='结果最大年龄，单位 s；跨机器需时钟同步')
  parser.add_argument('--period', type=positiveNumber, default=10000,
                      help='同步周期，单位 ps，必须与同步分析器的 Period 一致')
  parser.add_argument('--clock-skew-tolerance', type=nonnegativeNumber, default=0.2,
                      help='允许 TDC 时间领先本机的最大秒数，实际数据年龄仍写入日志')
  parser.add_argument('--log-file', default=None, help='日志文件路径；默认在当前工作目录 logs/ 下按启动时间新建')
  args = parser.parse_args(argv)
  run(tdcEndpoint=args.tdc_endpoint, outputEndpoint=args.output_endpoint,
      interval=args.interval, serviceName=args.service_name, timeout=args.timeout,
      maxAge=args.max_age, period=args.period, logFile=args.log_file,
      ddsServiceName=args.dds_service_name, clockSkewTolerance=args.clock_skew_tolerance,
      direction=args.direction)


if __name__ == '__main__':
  main()


# Windows PowerShell 启动脚本：复制以下内容到 .ps1，去掉每行开头的“# ”。
# 按实际部署位置修改 $scriptpath；周期必须与同步分析器的 Period 一致。
# $host.UI.RawUI.WindowTitle = "TF-RealtimeClockLock"
# $ifnoderoot = "C:\Users\Administrator\Desktop\IFNode"
# $env:PYTHONPATH += ";" + $ifnoderoot + "\applications\Lib\Python" + ";C:\Users\Administrator\Desktop\TF\ExpControl_final" + ";C:\Users\Administrator\Desktop\TF\ExpControl_final\TriggerBoardV2" + ";C:\Users\Administrator\Desktop\TF\ExpControl_final\RWG"
# $pythondir = $ifnoderoot + "\venv\Scripts\python.exe"
# $scriptpath = $ifnoderoot + "\applications\Lib\Python\Experiment\TFQKD\services\RealtimeClockLock.py"
# $tdcEndpoint = "tcp://code.qpqi.group:1161"
# $outputEndpoint = "tcp://tf.qpqi.group:1161"
# $serviceName = "RealTimeTDC"
# $ddsServiceName = "DDSClock"
# $direction = 1
# $interval = 0.1
# $timeout = 2
# $maxAge = 1
# $period = 10000
# $clockSkewTolerance = 0.2
# $logFile = Join-Path (Get-Location) ("logs\RealtimeClockLock_" + (Get-Date -Format "yyyyMMdd_HHmmss_ffffff") + ".log")
# & $pythondir $scriptpath --tdc-endpoint $tdcEndpoint --output-endpoint $outputEndpoint --service-name $serviceName --dds-service-name $ddsServiceName --direction $direction --interval $interval --timeout $timeout --max-age $maxAge --period $period --clock-skew-tolerance $clockSkewTolerance --log-file $logFile
#
# pause
