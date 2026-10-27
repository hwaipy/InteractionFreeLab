"""独立运行的时钟锁定循环；使用 --help 查看命令行配置。"""
import argparse
import math
import time

from interactionfreepy import IFWorker


def sendDelay(outputWorker, aliceDelay, bobDelay):
  """外发入口，delay 单位为 ps；确定控制语句后在此处替换。"""
  # TODO: 使用 outputWorker 调用实际的时钟控制服务。
  # 在确定接口、反馈方向和单位前，只打印，不执行调钟。
  print(f'[待配置外发] Alice={aliceDelay:.2f} ps, Bob={bobDelay:.2f} ps', flush=True)


def run(tdcEndpoint, outputEndpoint, interval=0.1, serviceName='RealTimeTDC',
        timeout=2.0, maxAge=1.0, period=10000):
  """读取最新值 → 外发 → 等待 interval 秒，Ctrl+C 退出。"""
  if any(not math.isfinite(v) or v <= 0 for v in (interval, timeout, maxAge)):
    raise ValueError('interval、timeout、maxAge 必须为正的有限秒数')
  if not math.isfinite(period) or period <= 0:
    raise ValueError('period 必须为正的有限数，单位 ps')
  inputWorker = IFWorker(tdcEndpoint, timeout=timeout)
  outputWorker = None
  lastSample = None
  try:
    outputWorker = IFWorker(outputEndpoint, timeout=timeout)
    realtimeTDC = inputWorker.blockingInvoker(serviceName, timeout=timeout)
    while True:
      try:
        rows = realtimeTDC.getRecent(1, reversed=True, delayOnly=True)
        if rows:
          sample = rows[0]
          # OfferTime 区分服务重启后的相同序号，避免重复反馈同一块。
          sampleID = (sample['OfferTime'], sample['Sequence'])
          delays = sample['Delays']
          fresh = 0 <= time.time() - sample['OfferTime'] <= maxAge
          valid = len(delays) == 2 and all(d is not None and math.isfinite(d) for d in delays)
          if sampleID != lastSample and fresh and valid:
            # 将粗同步的整周期偏移去掉，保留最近方向的相位误差。
            aliceDelay, bobDelay = [(d + period / 2) % period - period / 2 for d in delays]
            # 外发超时时结果可能已生效，避免对同一块自动重复外发。
            lastSample = sampleID
            sendDelay(outputWorker, aliceDelay, bobDelay)
      except Exception as exc:
        print(f'时钟锁定本轮失败：{exc}', flush=True)
      # 每轮处理完成后再等待，而不是按固定时刻追赶下一轮。
      time.sleep(interval)
  except KeyboardInterrupt:
    print('时钟锁定循环已停止。', flush=True)
  finally:
    if outputWorker is not None:
      outputWorker.close()
    inputWorker.close()


def positiveNumber(value):
  try:
    number = float(value)
  except ValueError:
    raise argparse.ArgumentTypeError('必须为正的有限数')
  if not math.isfinite(number) or number <= 0:
    raise argparse.ArgumentTypeError('必须为正的有限数')
  return number


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--tdc-endpoint', default='tcp://127.0.0.1:2240',
                      help='RealTimeTDC 所在的 Broker 地址')
  parser.add_argument('--output-endpoint', default='tcp://127.0.0.1:2240',
                      help='外发控制所使用的 Broker 地址')
  parser.add_argument('--service-name', default='RealTimeTDC', help='实时 TDC 服务名')
  parser.add_argument('--interval', type=positiveNumber, default=0.1,
                      help='每轮处理完成后的等待时间，单位 s')
  parser.add_argument('--timeout', type=positiveNumber, default=2.0,
                      help='IFWorker 请求超时，单位 s')
  parser.add_argument('--max-age', type=positiveNumber, default=1.0,
                      help='结果最大年龄，单位 s；跨机器需时钟同步')
  parser.add_argument('--period', type=positiveNumber, default=10000,
                      help='同步周期，单位 ps，必须与同步分析器的 Period 一致')
  args = parser.parse_args(argv)
  run(tdcEndpoint=args.tdc_endpoint, outputEndpoint=args.output_endpoint,
      interval=args.interval, serviceName=args.service_name, timeout=args.timeout,
      maxAge=args.max_age, period=args.period)


if __name__ == '__main__':
  main()


# Windows PowerShell 启动脚本：复制以下内容到 .ps1，去掉每行开头的“# ”。
# 按实际部署位置修改 $scriptpath；周期必须与同步分析器的 Period 一致。
# $host.UI.RawUI.WindowTitle = "TF-RealtimeClockLock"
# $ifnoderoot = "C:\Users\Administrator\Desktop\IFNode"
# $env:PYTHONPATH += ";" + $ifnoderoot + "\applications\Lib\Python" + ";C:\Users\Administrator\Desktop\TF\ExpControl_final" + ";C:\Users\Administrator\Desktop\TF\ExpControl_final\TriggerBoardV2" + ";C:\Users\Administrator\Desktop\TF\ExpControl_final\RWG"
# $pythondir = $ifnoderoot + "\venv\Scripts\python.exe"
# $scriptpath = $ifnoderoot + "\applications\Lib\Python\Experiment\TFQKD\services\RealtimeClockLock.py"
# $tdcEndpoint = "tcp://127.0.0.1:2240"
# $outputEndpoint = "tcp://127.0.0.1:2240"
# $serviceName = "RealTimeTDC"
# $interval = 0.1
# $timeout = 2
# $maxAge = 1
# $period = 10000
# & $pythondir $scriptpath --tdc-endpoint $tdcEndpoint --output-endpoint $outputEndpoint --service-name $serviceName --interval $interval --timeout $timeout --max-age $maxAge --period $period
#
# pause
