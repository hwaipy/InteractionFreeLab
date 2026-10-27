"""Boundary and event conservation checks for runtime realtime windows."""
from pathlib import Path
import sys
import unittest

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO / 'pytimetag'), str(REPO / 'InteractionFreeLabLocal'),
               str(REPO / 'InteractionFreeLabLocal/Experiment/TFQKD/services')]
from Instrument.tdc.SwabianTimeTag.SwabianTimeTag import (
    SwabianTimeTag, TimeTagDataStreamConbiner,
)
from TF_TDCServer_Doppler import ReadTimeTDC


class RuntimeBlockDurationTest(unittest.TestCase):
  def drain(self, combiner):
    blocks = []
    while not combiner.dataBlockQueue.empty():
      blocks.append(combiner.dataBlockQueue.get_nowait())
    return blocks

  def feed(self, combiner, timestamps, channels=None):
    timestamps = np.asarray(timestamps, dtype='int64')
    if channels is None:
      channels = np.zeros(len(timestamps), dtype='int64')
    combiner.deal(timestamps, channels)

  def assertContinuous(self, blocks):
    for left, right in zip(blocks, blocks[1:]):
      self.assertEqual(left.dataTimeEnd, right.dataTimeBegin)
    for block in blocks:
      for channel in block.content:
        self.assertTrue(np.all(channel >= block.dataTimeBegin))
        self.assertTrue(np.all(channel < block.dataTimeEnd))

  def test_switch_after_current_block_and_preserve_events(self):
    combiner = TimeTagDataStreamConbiner(splitBy=None, timeRange=100_000_000_000)
    # Same timestamp can occur on multiple channels, including at boundaries.
    timestamps = np.repeat(np.arange(0, 310_000_000_001, 1_000_000_000), 2)
    channels = np.tile(np.array([0, 4], dtype='int64'), len(timestamps) // 2)
    self.feed(combiner, timestamps[:82], channels[:82])  # 0..40 ms
    self.assertEqual(combiner.setBlockDuration(.03),
                     {'ActiveSeconds': .1, 'PendingSeconds': .03})
    self.feed(combiner, timestamps[82:], channels[82:])
    blocks = self.drain(combiner)
    self.assertContinuous(blocks)
    self.assertEqual([(b.dataTimeEnd - b.dataTimeBegin) for b in blocks],
                     [100_000_000_000] + [30_000_000_000] * 7)
    for ch in (0, 4):
      actual = np.concatenate([b.content[ch] for b in blocks])
      expected = timestamps[(channels == ch) & (timestamps < blocks[-1].dataTimeEnd)]
      np.testing.assert_array_equal(actual, expected)
    self.assertEqual(combiner.getBlockStatus(),
                     {'ActiveSeconds': .03, 'PendingSeconds': None})

  def test_nondivisor_crosses_pps_without_losing_events(self):
    for duration in (.03, .07, .15):
      with self.subTest(duration=duration):
        combiner = TimeTagDataStreamConbiner(splitBy=None, timeRange=100_000_000_000, queueSize=1000)
        combiner.setBlockDuration(duration)
        timestamps = np.arange(0, 2_100_000_000_001, 1_000_000_000, dtype='int64')
        channels = np.where(timestamps % 10**12 == 0, 1, 4).astype('int64')
        # Deliberately use input batches spanning multiple output windows.
        for start in range(0, len(timestamps), 173):
          self.feed(combiner, timestamps[start:start + 173], channels[start:start + 173])
        blocks = self.drain(combiner)
        self.assertContinuous(blocks)
        self.assertTrue(any(b.dataTimeBegin < 10**12 < b.dataTimeEnd for b in blocks))
        for ch in (1, 4):
          actual = np.concatenate([b.content[ch] for b in blocks])
          expected = timestamps[(channels == ch) & (timestamps < blocks[-1].dataTimeEnd)]
          np.testing.assert_array_equal(actual, expected)

  def test_pending_update_replaced_cancelled_and_lengthened(self):
    combiner = TimeTagDataStreamConbiner(splitBy=None, timeRange=100_000_000_000)
    self.feed(combiner, [0, 50_000_000_000])
    combiner.setBlockDuration(.03)
    combiner.setBlockDuration(.07)
    self.assertEqual(combiner.getBlockStatus()['PendingSeconds'], .07)
    combiner.setBlockDuration(.1)
    self.assertIsNone(combiner.getBlockStatus()['PendingSeconds'])
    combiner.setBlockDuration(.15)
    self.feed(combiner, [100_000_000_000, 250_000_000_000, 400_000_000_000])
    blocks = self.drain(combiner)
    self.assertEqual([b.dataTimeEnd - b.dataTimeBegin for b in blocks],
                     [100_000_000_000, 150_000_000_000, 150_000_000_000])
    self.assertContinuous(blocks)

  def test_empty_windows_and_input_and_queue_limit(self):
    combiner = TimeTagDataStreamConbiner(splitBy=None, timeRange=100_000_000_000, queueSize=3)
    self.assertFalse(combiner.deal(np.array([], dtype='int64'), np.array([], dtype='int64')))
    self.feed(combiner, [0, 500_000_000_000])
    blocks = self.drain(combiner)
    self.assertEqual(len(blocks), 3)
    self.assertContinuous(blocks)
    self.assertTrue(all(sum(b.sizes) == 0 for b in blocks))

  def test_api_validation_and_readback(self):
    stream = SwabianTimeTag('SIM', 1)
    rt = ReadTimeTDC(stream.conbinerByTime)
    self.assertEqual(rt.getRealtimeBlockDuration(), .1)
    self.assertEqual(rt.setRealtimeBlockDuration(.07),
                     {'ActiveSeconds': .07, 'PendingSeconds': None})
    self.feed(stream.conbinerByTime, [0])
    for value in (True, '0.03', None, 0, -.1, .0001, 1.01, float('nan'), float('inf')):
      with self.subTest(value=value), self.assertRaises(ValueError):
        rt.setRealtimeBlockDuration(value)
    self.assertEqual(rt.getRealtimeBlockDuration(), .07)
    self.assertIsNone(rt.getRealtimeBlockStatus()['PendingSeconds'])
    self.assertEqual(rt.setRealtimeBlockDuration(.03)['PendingSeconds'], .03)
    with self.assertRaises(RuntimeError):
      ReadTimeTDC().setRealtimeBlockDuration(.03)

  def test_pps_duration_configuration_is_rejected(self):
    combiner = TimeTagDataStreamConbiner(splitBy=1)
    with self.assertRaises(RuntimeError):
      combiner.setBlockDuration(.03)
    with self.assertRaises(RuntimeError):
      combiner.getBlockStatus()
    self.assertIsNone(combiner.splitDataRange)

  def test_existing_driver_default_and_pps_combiner_unchanged(self):
    original = SwabianTimeTag('SIM', 1)
    updated = SwabianTimeTag('SIM', 1)
    self.assertIs(type(original.conbinerByTime), TimeTagDataStreamConbiner)
    self.assertIs(type(updated.conbinerByChannel), TimeTagDataStreamConbiner)
    # Changing time windows must not change the separate PPS block stream.
    for t in range(0, 4):
      timestamps = np.array([t * 10**12, t * 10**12 + 10**9], dtype='int64')
      channels = np.array([1, 4], dtype='int64')
      updated.conbinerByTime.setBlockDuration(.07 if t % 2 else .03)
      updated.conbinerByTime.deal(timestamps, channels)
      original.conbinerByChannel.deal(timestamps, channels)
      updated.conbinerByChannel.deal(timestamps, channels)
    left, right = self.drain(original.conbinerByChannel), self.drain(updated.conbinerByChannel)
    self.assertEqual(len(left), 3)
    self.assertEqual(len(left), len(right))
    for i, (a, b) in enumerate(zip(left, right)):
      self.assertEqual((b.dataTimeBegin, b.dataTimeEnd), (i * 10**12, (i + 1) * 10**12))
      # Preserve the existing PPS startup behavior: its first batch primes
      # the combiner and is not included in the first emitted block.
      np.testing.assert_array_equal(b.content[1], [] if i == 0 else [i * 10**12])
      np.testing.assert_array_equal(b.content[4], [] if i == 0 else [i * 10**12 + 10**9])
      self.assertEqual((a.dataTimeBegin, a.dataTimeEnd), (b.dataTimeBegin, b.dataTimeEnd))
      for x, y in zip(a.content, b.content):
        np.testing.assert_array_equal(x, y)


if __name__ == '__main__':
  unittest.main()
