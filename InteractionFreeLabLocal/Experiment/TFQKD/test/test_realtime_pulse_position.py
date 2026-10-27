"""Check independent fast PulsePosition and unchanged stored analysis."""
from pathlib import Path
import sys
import unittest

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO / 'pytimetag'), str(REPO / 'InteractionFreeLabLocal'),
               str(REPO / 'InteractionFreeLabLocal/Experiment/TFQKD/services')]
from pytimetag import DataBlock
from TF_TDCServer_Doppler import LongRandomNumberEncodingAnalyser, ReadTimeTDC, RealTimeSyncAnalyser
from tdc.SyncAnalyser import SyncAnalyser


class RealtimePulsePositionTest(unittest.TestCase):
  def setUp(self):
    self.sources = {}
    self.rt = ReadTimeTDC()
    content = [np.array([], dtype='int64') for _ in range(16)]
    content[0] = np.arange(3, dtype='int64') * 40_000_000
    content[4] = np.arange(2000, dtype='int64') * 10000 + 5500
    content[5] = content[4].copy()
    self.block = DataBlock.create(content, 0, 0, 100_000_000)
    for side, channel in [('Alice', 4), ('Bob', 5)]:
      name = f'TFQKDSync{side}'
      source = LongRandomNumberEncodingAnalyser(None, 16, 256)
      source.turnOn({'Period': 10000, 'TriggerChannel': 0, 'SignalChannel': channel,
                     'RandomNumbers': [0], 'Histograms': {'Sync': [0]}})
      self.sources[name] = source
      self.rt.analysers[name] = RealTimeSyncAnalyser(source)

  def test_fast_count_threshold_is_200_and_default_remains_1000(self):
    fast = self.rt.analysers['TFQKDSyncAlice']
    normal = SyncAnalyser(16, 256)
    normal.turnOn(self.sources['TFQKDSyncAlice'].getConfigurations())
    for count in (199, 200, 999, 1000):
      with self.subTest(count=count):
        content = [ch.copy() for ch in self.block.content]
        content[4] = content[4][:count]
        block = DataBlock.create(content, 0, 0, 100_000_000)
        self.assertEqual(fast.dataIncome(block)['Delay'], 500 if count >= 200 else None)
        normalResult = normal.dataIncome(block)
        self.assertEqual(normalResult['Delay'], 500 if count >= 1000 else None)
        self.assertNotIn('SyncStatistics', normalResult)

  def test_statistics_distinguish_all_photons_from_centroid_selection(self):
    content = [ch.copy() for ch in self.block.content]
    peak = np.arange(200, dtype='int64') * 10000 + 5500
    background = np.arange(50, dtype='int64') * 10000 + 2000
    content[4] = np.sort(np.concatenate([peak, background]))
    block = DataBlock.create(content, 0, 0, 100_000_000_000)
    result = self.rt.analysers['TFQKDSyncAlice'].dataIncome(block)
    stats = result['SyncStatistics']
    self.assertEqual(result['Delay'], 500)
    self.assertEqual(stats['MinimumCounts'], 200)
    self.assertEqual(stats['InputCounts'], 250)
    self.assertEqual(stats['HistogramCounts'], 250)
    self.assertTrue(stats['AllInputHistogrammed'])
    self.assertEqual(stats['CentroidCounts'], 200)
    self.assertEqual(stats['CentroidFraction'], .8)
    self.assertEqual(stats['ShiftCounts'], 250)
    self.assertAlmostEqual(stats['BlockDurationS'], .1)
    self.assertAlmostEqual(stats['InputCountRateHz'], 2500)
    self.assertAlmostEqual(stats['CentroidCountRateHz'], 2000)
    self.assertTrue(stats['Valid'])
    self.assertIsNone(stats['InvalidReason'])
    self.rt.offer({'FetchTime': 1, 'TFQKDSyncAlice': result, 'TFQKDSyncBob': None})
    recent = self.rt.getRecent(1, delayOnly=True)[0]
    self.assertEqual(recent['SyncStatistics']['Alice'], stats)
    self.assertIsNone(recent['SyncStatistics']['Bob'])

  def test_statistics_report_low_counts_flat_pulses_and_missing_trigger(self):
    analyser = self.rt.analysers['TFQKDSyncAlice']
    content = [ch.copy() for ch in self.block.content]
    content[4] = content[4][:199]
    result = analyser.dataIncome(DataBlock.create(content, 0, 0, 100_000_000_000))
    self.assertIsNone(result['Delay'])
    self.assertEqual(result['SyncStatistics']['InvalidReason'], 'insufficient_counts')
    self.assertEqual(result['SyncStatistics']['InputCounts'], 199)
    self.assertEqual(result['SyncStatistics']['CentroidCounts'], 0)
    self.assertEqual(result['SyncStatistics']['ShiftCounts'], 0)
    content[4] = np.arange(1000, dtype='int64') * 100 + 50
    result = analyser.dataIncome(DataBlock.create(content, 0, 0, 100_000_000_000))
    self.assertEqual(result['SyncStatistics']['InvalidReason'], 'low_peak_to_mean')
    content[0] = np.array([], dtype='int64')
    result = analyser.dataIncome(DataBlock.create(content, 0, 0, 100_000_000_000))
    self.assertEqual(result['SyncStatistics']['InvalidReason'], 'no_trigger')

  def test_target_changes_error_and_remains_independent(self):
    alice, bob = self.rt.analysers.values()
    source = self.sources['TFQKDSyncAlice']
    before = source.dataIncome(self.block)
    self.assertEqual(alice.dataIncome(self.block)['Delay'], 500)
    self.rt.configureAnalyser('TFQKDSyncAlice', {'PulsePosition': 5200})
    self.assertEqual(alice.dataIncome(self.block)['Delay'], 300)
    self.assertEqual(alice.dataIncome(self.block)['Delay'], 300)
    self.assertEqual(bob.dataIncome(self.block)['Delay'], 500)
    self.assertEqual(self.rt.getAnalyserConfiguration('TFQKDSyncAlice')['PulsePosition'], 5200)
    self.assertEqual(before, source.dataIncome(self.block))
    self.assertNotIn('PulsePosition', source.getConfigurations())

  def test_period_updates_do_not_reset_target(self):
    self.rt.configureAnalyser('TFQKDSyncAlice', {'PulsePosition': 5200})
    for name, source in self.sources.items():
      source.configure({'Period': 5000})
      self.rt.analysers[name].dataIncome(self.block)
    self.assertEqual(self.rt.getAnalyserConfiguration('TFQKDSyncAlice')['PulsePosition'], 5200)
    self.assertEqual(self.rt.getAnalyserConfiguration('TFQKDSyncBob')['PulsePosition'], 5000)
    self.assertEqual(self.rt.getAnalyserConfiguration('TFQKDSyncAlice')['Period'], 5000)

  def test_invalid_target_and_shared_configuration_rejected(self):
    for value in (-1, float('nan'), float('inf'), True, '5000'):
      with self.subTest(value=value), self.assertRaises(ValueError):
        self.rt.configureAnalyser('TFQKDSyncAlice', {'PulsePosition': value})
    with self.assertRaises(ValueError):
      self.rt.configureAnalyser('TFQKDSyncAlice', {'Period': 5000})
    self.assertEqual(self.rt.getAnalyserConfiguration('TFQKDSyncAlice')['PulsePosition'], 5000)


if __name__ == '__main__':
  unittest.main()
