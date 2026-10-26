"""Run: python3 -m unittest discover -s <this directory> -v"""
from types import SimpleNamespace
import csv
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import scan
import preprocess
from InteractionFreeLabLocal.Experiment.TFQKD.services.tdc.TFQKDQBERAnalyser import (
    DataBlockParser, TFQKDQBERAnalyser, QKDIntermediate, DataBlockParseResult,
)


class ScanTest(unittest.TestCase):
    def configs(self):
        # All 16 signal basis pairs, then aligned reference pulses.
        return dict(IntensityRatioThreshold=3, IntensityThreshold=5, PhaseThreshold=7,
                    AliceRandomNumbers=[a for a in range(4) for b in range(4)] + [64] * 16,
                    BobRandomNumbers=[b for a in range(4) for b in range(4)] + [64] * 16,
                    TimeEachBlock=10**12, FrequencyFrame=10**12, PhaseFrame=250_000_000_000,
                    IntensityFrame=500_000_000_000, Period=10_000, TriggerPeriod=40_000_000,
                    PulsePosition=5000, Gate=1000, GateRef=1000, TriggerChannel=0,
                    **{'Channel 1': 2, 'Channel 2': 3, 'SyncChannelAlice': 4, 'SyncChannelBob': 5})

    def test_range_and_path(self):
        self.assertEqual(scan.numbers('3:7:2,10', True), [3, 5, 7, 10])
        self.assertEqual(scan.numbers([7, 15], True), [7, 15])
        self.assertEqual(scan.numbers(5), [5])
        self.assertEqual(preprocess.raw_path('2026-10-25T16:00:01.123456Z'),
                         '2026-10-26/00/2026-10-26 00-00-01.123.datablock')
        with self.assertRaises(ValueError):
            scan.numbers('1:2:0')

    def test_sources_route_metadata_and_raw_together(self):
        import io
        import types
        fetch = '2026-10-26T00:00:00.123456+08:00'
        block = preprocess.DataBlock.create([[0], [], [5000], [], [1], [1]], 0, 0, 10**12)
        raw = block.serialize()
        with tempfile.TemporaryDirectory() as temp:
            for source, endpoint, collection, raw_url in (
                    ('2502', 'tcp://172.20.8.102:1161', 'TFQKD_TDC', 'http://172.20.8.102:1001'),
                    ('archive', 'tcp://172.20.8.102:1061', 'TFQKD_TDC_2502', 'http://172.20.8.102:1003'),
                    ('2502-public', 'tcp://code.qpqi.group:1161', 'TFQKD_TDC', 'http://code.qpqi.group:1001'),
                    ('archive-public', 'tcp://code.qpqi.group:1061', 'TFQKD_TDC_2502', 'http://code.qpqi.group:1003')):
                with self.subTest(source=source):
                    args = SimpleNamespace(
                        begin='2026-10-26T00:00:00', end='2026-10-26T00:00:01',
                        source=source, output=str(Path(temp) / source),
                        config=None, transform=None, clock_frequency=None, timeout=30, skip_missing=False)
                    worker = MagicMock()
                    worker.Storage.range.return_value = [{'_id': 'record', 'FetchTime': fetch}]
                    worker.Storage.get.return_value = {'FetchTime': fetch, 'Configuration': self.configs()}
                    factory = MagicMock(return_value=worker)
                    with patch.dict(sys.modules, {'interactionfreepy': types.SimpleNamespace(IFWorker=factory)}), \
                            patch.object(preprocess, 'urlopen', return_value=io.BytesIO(raw)) as http:
                        output = preprocess.run(args)
                    factory.assert_called_once_with(endpoint, timeout=30)
                    self.assertEqual(worker.Storage.range.call_args.args[0], collection)
                    self.assertEqual(worker.Storage.get.call_args.args[0], collection)
                    http.assert_called_once_with(raw_url + '/2026-10-26/00/2026-10-26%2000-00-00.123.datablock', timeout=30)
                    manifest = json.loads(next(output.glob('preprocess_*.json')).read_text())
                    self.assertEqual(manifest['source']['collection'], collection)

    def test_exact_cyclic_pulses(self):
        config = self.configs()
        config.update(TimeEachBlock=1000, FrequencyFrame=1000, PhaseFrame=100,
                      IntensityFrame=200, Period=10, PulsePosition=5)
        parser = DataBlockParser(None, config)
        counts = parser.pulseCountStat()
        expected = np.zeros_like(counts)
        for pulse, time in enumerate(range(5, 1000, 10)):
            rn = parser.matchedRandomNumbers[pulse % 32]
            if (rn & 0xC00) == 0:
                expected[(rn >> 3) & 7, rn & 7, time // 200] += 1
        np.testing.assert_array_equal(counts, expected)

    def test_trigger_window_excludes_edges_without_mutating_raw(self):
        config = self.configs()
        origin = 10_000
        stop = origin + 10**12
        events = [origin - 1, origin, origin + 5000, stop - 165000, stop, stop + 5000]
        raw = preprocess.DataBlock.create([[origin], [], events, [], events, []], 0, 0, stop + 10_000)
        preprocess.validate_block(raw, config)
        windowed, report = DataBlockParser.analysisWindow(raw, config)
        np.testing.assert_array_equal(raw.content[2], events)
        np.testing.assert_array_equal(windowed.content[2], events[1:4])
        self.assertEqual(report['excluded_events']['2'], {'before': 1, 'after': 2})
        self.assertEqual(windowed.sizes[2], 3)
        parser = DataBlockParser(windowed, config)
        result = parser.parseIntermediate()
        # At the two in-window pulse centers; t=0 is outside the pulse gate.
        self.assertEqual(int(result.detectionStatistics.sum()), 2)
        self.assertEqual(int(result.syncCountsAlice.sum()), 3)

    def test_clock_drift_correction_restores_basis_and_phase_counts(self):
        config = self.configs()
        clocks = np.arange(25000, dtype=np.int64) * 40_000_000
        detectors = np.array([i * 10000 + 5000 + offset
                              for offset in (0, 500_000_000_000) for i in range(32)], dtype=np.int64)
        ideal = preprocess.DataBlock.create([clocks, [0], detectors, [], [1], [1]], 0, 0, 10**12)
        drift, origin = 6.416e-7, 10**16
        raw = preprocess.DataBlock.create(
            [np.array([int(round(int(t) * (1 + drift))) + origin for t in ch], dtype=np.int64)
             for ch in ideal.content], 0, origin, origin + int(10**12 * (1 + drift)))
        before = raw.content[2].copy()
        corrected, info = DataBlockParser.rescaleTDCClock(raw)
        np.testing.assert_array_equal(raw.content[2], before)
        self.assertAlmostEqual(info['scale'], 1 / (1 + drift), places=12)
        expected = DataBlockParser(ideal, config).parseIntermediate()
        uncorrected = DataBlockParser(raw, config).parseIntermediate()
        actual = DataBlockParser(corrected, config).parseIntermediate()
        self.assertFalse(np.array_equal(uncorrected.detectionStatistics, expected.detectionStatistics))
        np.testing.assert_array_equal(actual.detectionStatistics, expected.detectionStatistics)
        np.testing.assert_array_equal(actual.phaseErrorStatistics, expected.phaseErrorStatistics)
        with self.assertRaisesRegex(ValueError, 'requires at least two'):
            DataBlockParser.rescaleTDCClock(preprocess.DataBlock.create([[0], [], [], [], [], []], 0, 0, 10**12))

    def test_old_uncorrected_cache_is_rejected(self):
        intermediate, _, _ = self.make_payload(processing='raw-unadapted')
        with self.assertRaisesRegex(ValueError, 'different/missing timing correction'):
            preprocess.assert_identity(intermediate, intermediate.metadata['FetchTime'], {}, None)

    def test_atmosphere_and_phase_are_independent(self):
        from types import SimpleNamespace
        result = SimpleNamespace(syncCountsAlice=np.array([6, 5, 8, 20, 50]),
                                 syncCountsBob=np.array([6, 8, 24, 20, 50]))
        np.testing.assert_array_equal(scan.select_frames(result, 5, 50, 3), [True, False, False, True, False])

    def test_online_statistics_apply_atmosphere_filter(self):
        from InteractionFreeLabLocal.Experiment.TFQKD.services.tdc.TFQKDQBERAnalyser import DataBlockParseResult
        detections = np.ones((4, 4, 3), dtype=np.int32)
        detections[:, :, 1:] = 100  # Rejected frames must not contribute.
        errors = np.zeros((4, 3, 64, 2), dtype=np.int32)
        errors[:, 0, 7, :] = [2, 3]
        errors[:, 1:, 7, :] = [100, 100]
        result = DataBlockParseResult(
            np.array([6, 5, 8]), np.array([6, 8, 24]),
            np.ones((4, 4), dtype=np.int32), detections, errors, np.zeros(3))
        stats = result.statistics(3, 5, 7)
        self.assertEqual(stats['Valid'], [1, 3])
        self.assertEqual(stats['CountsZ'], [1, 1, 1, 1])
        for key in ('PhaseErrorX', 'PhaseErrorY', 'PhaseErrorZ1'):
            self.assertEqual(stats[key], [2, 3])
        rejected = result.statistics(3, 100, 7)
        self.assertEqual(rejected['Valid'], [0, 3])
        self.assertEqual(rejected['CountsZ'], [0, 0, 0, 0])
        self.assertEqual(rejected['PhaseErrorX'], [0, 0])

    def test_two_seconds_full_pipeline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self.configs()
            metas = []
            begin = scan.parse_time('2026-10-26T00:00:00+08:00')
            for second in range(2):
                fetch = (begin + timedelta(seconds=second)).isoformat()
                # One set of signal/reference events in each intensity frame.
                detectors = [i * 10000 + 5000 + offset for offset in (0, 500_000_000_000) for i in range(32)]
                content = [[0], [], detectors, [], [1, 2, 3, 500_000_000_001], [1, 2, 3, 500_000_000_001]]
                block = preprocess.DataBlock.create(content, begin.timestamp() + second, 0, 10**12)
                file = root / preprocess.raw_path(fetch)
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(block.serialize())
                metas.append({'FetchTime': fetch, 'Configuration': config})
            pre = SimpleNamespace(begin=begin.isoformat(), end=(begin + timedelta(seconds=2)).isoformat(),
                output=str(root / 'intermediate'), source='2502', config=None, transform=None, clock_frequency=None,
                timeout=30, skip_missing=False)
            with patch.object(DataBlockParser, 'parseIntermediate', autospec=True,
                              side_effect=DataBlockParser.parseIntermediate) as parse:
                intermediate_dir = preprocess.run(pre, metas=metas,
                    fetch_raw=lambda fetch: (root / preprocess.raw_path(fetch)).read_bytes())
                self.assertEqual(parse.call_count, 2)
            # Resume consumes validated files and never fetches Raw again.
            with patch.object(DataBlockParser, 'parseIntermediate', side_effect=AssertionError('reparsed')):
                preprocess.run(pre, metas=metas, fetch_raw=lambda _: self.fail('refetched Raw'))
            args = SimpleNamespace(begin=begin.isoformat(), end=(begin + timedelta(seconds=2)).isoformat(),
                input=str(intermediate_dir), output=str(root / 'output'),
                phase_bins=range(7, 64, 56), intensity_min=[0, 2, 10], intensity_max=[1e300], intensity_ratio=[3],
                skip_missing=False, mu_x=[.0303853]*2, mu_y=[.482834]*2, mu_z=[.494035]*2)
            # Scanning must never call the parser or open the network.
            with patch.object(DataBlockParser, 'parseIntermediate', side_effect=AssertionError('reparsed')), \
                    patch.object(preprocess, 'urlopen', side_effect=AssertionError('network')):
                output = scan.run(args)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(len(manifest['processed']), 2)
            self.assertEqual(manifest['arguments']['phase_bins'], [7, 63])
            self.assertEqual(len(manifest['results']), 6)
            first, filtered, empty = manifest['results'][:3]
            self.assertEqual(first['selected_frames'], 4)
            self.assertEqual(filtered['selected_frames'], 2)
            self.assertIsNone(empty['file'])
            self.assertEqual(first['signal_pulses'], filtered['signal_pulses'] * 2)
            with (output / first['file']).open() as f:
                rows = list(csv.reader(f, delimiter='\t'))
            self.assertEqual(rows[0], ['', 'A-C', 'B-C'])
            self.assertEqual(len(rows), 28)
            self.assertEqual(rows[-1], ['X基筛选比例', '12.5%'])
            for row in rows[18:22]:
                self.assertEqual(row[1:], ['4'] * 4)
            saved = QKDIntermediate.unpack(next(intermediate_dir.rglob('*.npz')).read_bytes())
            self.assertEqual(saved.detectionStatistics.shape, (4, 4, 2))
            args.output = str(root / 'both_pulse_modes')
            args.sent_pulse_modes = ['total', 'filtered']
            both_output = scan.run(args)
            both = json.loads((both_output / 'manifest.json').read_text())['results']
            self.assertEqual(len(both), 12)
            unfiltered_count, selected_count = both[2:4]
            self.assertEqual(unfiltered_count['sent_pulses'], first['signal_pulses'])
            self.assertEqual(selected_count['sent_pulses'], filtered['signal_pulses'])
            mode_rows = []
            for entry in (unfiltered_count, selected_count):
                with (both_output / entry['file']).open() as f:
                    mode_rows.append(list(csv.reader(f, delimiter='\t')))
            differences = [(a, b) for a, b in zip(*mode_rows) if a != b]
            self.assertEqual(differences, [(['发送总脉冲数', str(first['signal_pulses'])],
                                          ['发送总脉冲数', str(filtered['signal_pulses'])])])
            args.output = str(root / 'scaled')
            args.scales = [None, 1e12]
            scaled_output = scan.run(args)
            scaled = json.loads((scaled_output / 'manifest.json').read_text())['results']
            self.assertEqual(len(scaled), 24)
            # The filtered pulse count sets the factor even in total mode.
            target = scaled[5]
            self.assertEqual(target['sent_pulse_mode'], 'total')
            self.assertEqual(target['scale_factor'], 1e12 / filtered['signal_pulses'])
            self.assertEqual(target['output_sent_pulses'], 2e12)
            with (scaled_output / target['file']).open() as f:
                scaled_rows = list(csv.reader(f, delimiter='\t'))
            self.assertEqual(scaled_rows[:8], mode_rows[0][:8])
            factor = target['scale_factor']
            for a, b in zip(mode_rows[0], scaled_rows):
                if a and a[0] in scan.LABELS and len(a) == 5 and all(v.isdigit() for v in a[1:]):
                    self.assertEqual([float(v) for v in b[1:]], [scan.scaled_count(int(v), factor) for v in a[1:]])
                if a and a[0] in ('X基1', 'X基2'):
                    self.assertEqual(float(b[1]), scan.scaled_count(int(a[1]), factor))
                    self.assertEqual(float(b[2]), scan.scaled_count(int(a[2]), factor))
                    self.assertEqual(b[3], a[3])
            args.scales = [None]
            args.sent_pulse_modes = ['filtered']
            args.output = str(root / 'missing')
            args.end = (begin + timedelta(seconds=3)).isoformat()
            gap_output = scan.run(args)
            gap_manifest = json.loads((gap_output / 'manifest.json').read_text())
            self.assertEqual(len(gap_manifest['processed']), 2)
            self.assertEqual(gap_manifest['empty_timestamp_seconds'], [(begin + timedelta(seconds=2)).isoformat()])

    def make_payload(self, timestamp=0, processing='tdc-adapted'):
        config = self.configs()
        block = preprocess.DataBlock.create([[0], [], [5000], [], [1], [1]], timestamp, 0, 10**12)
        parser = DataBlockParser(block, config)
        result = parser.parseIntermediate()
        return QKDIntermediate.fromParser(parser, result, config, processing), result, block

    def test_codec_exact_round_trip_and_corruption(self):
        intermediate, result, _ = self.make_payload()
        payload = intermediate.pack()
        restored = QKDIntermediate.unpack(payload)
        np.testing.assert_array_equal(restored.phaseErrorStatistics, result.phaseErrorStatistics)
        np.testing.assert_array_equal(restored.pulseCounts, intermediate.pulseCounts)
        for name in ('syncCountsAlice', 'syncCountsBob', 'detectionStatistics'):
            np.testing.assert_array_equal(getattr(restored, name), getattr(result, name))
        with self.assertRaises(ValueError):
            QKDIntermediate.unpack(payload[:100])
        restored.metadata['format_version'] = 999
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            restored.pack()
        # Counts beyond uint32 are retained rather than wrapped.
        np.testing.assert_array_equal(QKDIntermediate.compactCounts(np.array([2**32 + 1], dtype=np.int64)), [2**32 + 1])
        with self.assertRaises(ValueError):
            QKDIntermediate.compactCounts(np.array([-1]))

    def test_online_result_and_storage_preference(self):
        import msgpack
        timestamp = preprocess.parse_time('2026-10-26T00:00:00.123456+08:00').timestamp()
        intermediate, expected, block = self.make_payload(timestamp)
        analyser = TFQKDQBERAnalyser(16)
        analyser.turnOn(self.configs())
        # Same message serialization and Data envelope as Storage/backup.
        record = {'FetchTime': intermediate.metadata['FetchTime'], 'Data': {'QKDQBER': analyser.dataIncome(block)}}
        record = msgpack.unpackb(msgpack.packb(record, use_bin_type=True), raw=False)
        stored = record['Data']['QKDQBER']
        stats = expected.statistics(3, 5, 7)
        for key, value in stats.items():
            self.assertEqual(stored[key], value)
        self.assertIn('Configuration', stored)
        self.assertIsInstance(stored['Intermediate'], bytes)
        with tempfile.TemporaryDirectory() as temp:
            settings = SimpleNamespace(begin='2026-10-26T00:00:00', end='2026-10-26T00:00:01',
                output=temp, source='2502', config=None, transform=None, clock_frequency=None, timeout=30, skip_missing=False)
            preprocess.run(settings, metas=[record], fetch_raw=lambda _: self.fail('Raw fetched despite Intermediate'))
            path = next(Path(temp).rglob('*.npz'))
            self.assertEqual(path.read_bytes(), stored['Intermediate'])
            stored['PhaseErrorX'][0] += 1
            with self.assertRaisesRegex(RuntimeError, 'Realtime comparison failed'):
                preprocess.run(settings, metas=[record], fetch_raw=lambda _: self.fail('Raw fetched'))
            stored['PhaseErrorX'][0] -= 1
            # Corrupt cached file fails instead of silently recomputing it.
            path.write_bytes(b'corrupt')
            with self.assertRaises(RuntimeError):
                preprocess.run(settings, metas=[record], fetch_raw=lambda _: self.fail('Raw fetched'))

    def test_scan_rejects_mixed_corrections(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            begin = preprocess.parse_time('2026-10-26T00:00:00')
            for second, processing in enumerate(('tdc-adapted', 'raw-unadapted')):
                intermediate, _, _ = self.make_payload((begin + timedelta(seconds=second)).timestamp(), processing)
                path = preprocess.file_path(root / 'input', intermediate.metadata['FetchTime'])
                preprocess.atomic_write(path, intermediate.pack())
            settings = SimpleNamespace(begin=begin.isoformat(), end=(begin + timedelta(seconds=2)).isoformat(),
                input=str(root / 'input'), output=str(root / 'output'), phase_bins=[7], intensity_min=[0],
                intensity_max=[1e300], intensity_ratio=[3], skip_missing=False,
                mu_x=[.03]*2, mu_y=[.48]*2, mu_z=[.49]*2)
            with self.assertRaisesRegex(ValueError, 'Incompatible'):
                scan.run(settings)
            self.assertFalse(list((root / 'output').glob('result_*.txt')))

    def test_missing_second_and_cache_config_mismatch(self):
        begin = preprocess.parse_time('2026-10-26T00:00:00')
        intermediate, _, _ = self.make_payload((begin + timedelta(seconds=1)).timestamp())
        record = {'FetchTime': intermediate.metadata['FetchTime'],
                  'Data': {'QKDQBER': {'Intermediate': intermediate.pack(), 'Configuration': self.configs()}}}
        with tempfile.TemporaryDirectory() as temp:
            settings = SimpleNamespace(begin=begin.isoformat(), end=(begin + timedelta(seconds=2)).isoformat(),
                output=temp, source='2502', config=None, transform=None, clock_frequency=None, timeout=30, skip_missing=False)
            _, gap_manifest = preprocess.run(settings, metas=[record], return_manifest=True,
                fetch_raw=lambda _: self.fail('Raw fetched'))
            self.assertEqual(gap_manifest['failures'], [])
            self.assertEqual(len(gap_manifest['empty_timestamp_seconds']), 1)
            settings.skip_missing = True
            preprocess.run(settings, metas=[record], fetch_raw=lambda _: self.fail('Raw fetched'))
            self.assertEqual(len(list(Path(temp).rglob('*.npz'))), 1)
            record['Data']['QKDQBER']['Configuration']['Gate'] = 800
            settings.begin = (begin + timedelta(seconds=1)).isoformat()
            settings.skip_missing = False
            with self.assertRaisesRegex(RuntimeError, 'does not match metadata Gate'):
                preprocess.run(settings, metas=[record], fetch_raw=lambda _: self.fail('Raw fetched'))



if __name__ == '__main__':
    unittest.main()
