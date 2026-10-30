"""Validate clock-lock timing logs without connecting to experimental services."""
from datetime import datetime
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services'))
import RealtimeClockLock as lock


class RealtimeClockLockLogTest(unittest.TestCase):
  def sample(self, sequence=1, delays=None, age=0):
    offered = time.time() - age
    return {'Sequence': sequence, 'OfferTime': offered, 'FetchTime': offered - .1,
            'ProcessingTime': .003, 'Delays': [10077., -10100.] if delays is None else delays}

  def test_default_log_uses_working_directory_and_invalid_delay_is_visible(self):
    source, output = MagicMock(), MagicMock()
    source.blockingInvoker.return_value.getRecent.return_value = [self.sample(delays=[None, None])]
    console = io.StringIO()
    with tempfile.TemporaryDirectory() as root:
      with patch.object(lock.Path, 'cwd', return_value=Path(root)), \
           patch.object(lock, 'IFWorker', side_effect=[source, output]), \
           patch.object(lock, 'sendDelay') as send, \
           patch.object(lock.time, 'sleep', side_effect=KeyboardInterrupt), \
           contextlib.redirect_stdout(console):
        lock.run('tdc', 'output')
      files = list((Path(root) / 'logs').glob('RealtimeClockLock_*.log'))
      self.assertEqual(len(files), 1)
      records = [json.loads(line) for line in files[0].read_text().splitlines()]
      self.assertTrue(any(r['Event'] == 'sample_skipped' and r['Reason'] == 'invalid' for r in records))
      self.assertIn('创建读取连接：tdc', console.getvalue())
      self.assertIn('创建外发连接：output', console.getvalue())
      self.assertIn('delay 无效', console.getvalue())
      self.assertIn('[None, None]', console.getvalue())
      send.assert_not_called()

  def test_tdc_identity_and_actual_send_times_are_logged_and_flushed(self):
    source, output = MagicMock(), MagicMock()
    sample = self.sample()
    sample['SyncStatistics'] = {
      'Alice': {'InputCounts': 250, 'InputCountRateHz': 2500, 'CentroidCounts': 200, 'MinimumCounts': 200},
      'Bob': {'InputCounts': 500, 'InputCountRateHz': 5000, 'CentroidCounts': 450, 'MinimumCounts': 200},
    }
    source.blockingInvoker.return_value.getRecent.return_value = [sample]
    actual_times = []
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'run.log'
      def send(worker, bob, service):
        self.assertIs(worker, output)
        self.assertEqual(bob, -100)
        self.assertEqual(service, 'DDSClock')
        # Confirm the preceding record is available before sending completes.
        records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(records[-1]['Event'], 'send_begin')
        actual_times.append(time.time_ns())
        return {'State': 'Success'}
      with patch.object(lock, 'IFWorker', side_effect=[source, output]), \
           patch.object(lock, 'sendDelay', side_effect=send), \
           patch.object(lock.time, 'sleep', side_effect=KeyboardInterrupt):
        lock.run('tdc', 'output', period=5000, logFile=path)
      records = [json.loads(line) for line in path.read_text().splitlines()]
      sent = next(r for r in records if r['Event'] == 'send_result')
      self.assertTrue(sent['CallReturned'])
      self.assertEqual(sent['Result'], {'State': 'Success'})
      self.assertEqual(sent['RawDelaysPs'], sample['Delays'])
      self.assertEqual(sent['DelaysPs'], [77, -100])
      for key in ('Sequence', 'FetchTime', 'OfferTime', 'ProcessingTime'):
        self.assertEqual(sent[key], sample[key])
      self.assertEqual(sent['SyncStatistics'], sample['SyncStatistics'])
      self.assertLessEqual(sent['BeginUnixTimeNs'], actual_times[0])
      self.assertGreaterEqual(sent['EndUnixTimeNs'], actual_times[0])
      self.assertGreaterEqual(sent['DurationMs'], 0)
      self.assertEqual(records[-1]['Event'], 'run_stop')
      for row in records:
        self.assertIsNotNone(datetime.fromisoformat(row['LocalTime']).utcoffset())
        self.assertRegex(row['LocalTime'], r'\.\d{6}[+-]\d{2}:\d{2}$')
        self.assertIsInstance(row['UnixTimeNs'], int)
        self.assertIsInstance(row['MonotonicNs'], int)
    source.close.assert_called_once()
    output.close.assert_called_once()

  def test_skips_and_rpc_errors_are_logged_without_repeated_feedback(self):
    source, output = MagicMock(), MagicMock()
    valid = self.sample()
    next_sample = self.sample(sequence=4)
    source.blockingInvoker.return_value.getRecent.side_effect = [
      [valid], [valid], [self.sample(sequence=2, delays=[1, None])],
      [self.sample(sequence=3, age=10)], [next_sample], [next_sample], [], OSError('fetch failed'),
    ]
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'run.log'
      with patch.object(lock, 'IFWorker', side_effect=[source, output]), \
           patch.object(lock, 'sendDelay', side_effect=[{'State': 'Success'}, OSError('send failed')]) as send, \
           patch.object(lock.time, 'sleep', side_effect=[None] * 7 + [KeyboardInterrupt]):
        lock.run('tdc', 'output', logFile=path)
      records = [json.loads(line) for line in path.read_text().splitlines()]
      self.assertEqual(send.call_count, 2)
      self.assertEqual([r['Reason'] for r in records if r['Event'] == 'sample_skipped'],
                       ['duplicate', 'invalid', 'stale', 'duplicate'])
      self.assertEqual([r['Stage'] for r in records if r['Event'] == 'cycle_error'], ['send', 'fetch'])
      self.assertTrue(any(r['Event'] == 'no_data' for r in records))
      failed = next(r for r in records if r['Event'] == 'send_result' and not r['CallReturned'])
      self.assertIn('send failed', failed['Error'])
      self.assertGreaterEqual(failed['EndUnixTimeNs'], failed['BeginUnixTimeNs'])

  def test_bob_uses_real_dds_call_and_does_not_require_alice(self):
    source, output = MagicMock(), MagicMock()
    source.blockingInvoker.return_value.getRecent.return_value = [self.sample(delays=[None, -10100])]
    result = {'State': 'Success', 'Attempts': 2}
    output.blockingInvoker.return_value.correctDelay.return_value = result
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'run.log'
      with patch.object(lock, 'IFWorker', side_effect=[source, output]) as factory, \
           patch.object(lock.time, 'sleep', side_effect=KeyboardInterrupt):
        lock.run('tdc', 'output', period=5000, logFile=path, ddsServiceName='DDSClockBob')
      self.assertEqual(factory.call_args_list[0].kwargs, {'timeout': 2.0})
      self.assertEqual(factory.call_args_list[1].kwargs, {'timeout': None})
      output.blockingInvoker.assert_called_once_with('DDSClockBob', timeout=None)
      output.blockingInvoker.return_value.correctDelay.assert_called_once_with(-100)
      records = [json.loads(line) for line in path.read_text().splitlines()]
      sent = next(r for r in records if r['Event'] == 'send_result')
      self.assertEqual(sent['Result'], result)
      self.assertEqual(sent['ControlTarget'], 'Bob')
      self.assertEqual(sent['DDSServiceName'], 'DDSClockBob')
      self.assertEqual(sent['DelaysPs'], [None, -100])
      self.assertEqual(sent['CommandDelayPs'], -100)

  def test_direction_and_wait_interval(self):
    source, output = MagicMock(), MagicMock()
    source.blockingInvoker.return_value.getRecent.return_value = [self.sample(delays=[None, 10123])]
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'run.log'
      with patch.object(lock, 'IFWorker', side_effect=[source, output]), \
           patch.object(lock, 'sendDelay', return_value={'State': 'Success'}) as send, \
           patch.object(lock.time, 'sleep', side_effect=KeyboardInterrupt) as sleep:
        lock.run('tdc', 'output', interval=.35, direction=-1, logFile=path)
      send.assert_called_once_with(output, -123, 'DDSClock')
      sleep.assert_called_once_with(.35)
      records = [json.loads(line) for line in path.read_text().splitlines()]
      sent = next(r for r in records if r['Event'] == 'send_result')
      self.assertEqual(sent['DelaysPs'], [None, 123])
      self.assertEqual(sent['CommandDelayPs'], -123)
      self.assertEqual(sent['Direction'], -1)
      events = [r['Event'] for r in records]
      self.assertLess(events.index('send_result'), events.index('wait_begin'))

  def test_small_clock_skew_allowed_and_large_skew_rejected(self):
    source, output = MagicMock(), MagicMock()
    source.blockingInvoker.return_value.getRecent.side_effect = [
      [self.sample(sequence=1, delays=[None, 10], age=-.08)],
      [self.sample(sequence=2, delays=[None, 10], age=-.3)],
    ]
    output.blockingInvoker.return_value.correctDelay.return_value = {'State': 'Success', 'Attempts': 1}
    with tempfile.TemporaryDirectory() as root:
      path = Path(root) / 'run.log'
      with patch.object(lock, 'IFWorker', side_effect=[source, output]), \
           patch.object(lock.time, 'sleep', side_effect=[None, KeyboardInterrupt]):
        lock.run('tdc', 'output', logFile=path, clockSkewTolerance=.2)
      output.blockingInvoker.return_value.correctDelay.assert_called_once_with(10)
      records = [json.loads(line) for line in path.read_text().splitlines()]
      skipped = next(r for r in records if r['Event'] == 'sample_skipped')
      self.assertEqual(skipped['Reason'], 'stale')
      self.assertLess(skipped['AgeMs'], -200)

  def test_unsuccessful_dds_result_is_an_error(self):
    output = MagicMock()
    output.blockingInvoker.return_value.correctDelay.return_value = {'State': 'Failed'}
    with self.assertRaisesRegex(RuntimeError, 'DDS 补偿未成功'):
      lock.sendDelay(output, 10)


if __name__ == '__main__':
  unittest.main()
