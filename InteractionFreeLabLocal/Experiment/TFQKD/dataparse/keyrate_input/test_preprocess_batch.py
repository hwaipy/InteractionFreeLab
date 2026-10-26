import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import msgpack
import preprocess
import preprocess_batch as batch
import test_scan
import scan


class BatchTest(unittest.TestCase):
    def test_multiple_records_per_natural_second_are_all_kept(self):
        fixture = test_scan.ScanTest()
        times = ['2026-10-26T00:00:00.001000+08:00',
                 '2026-10-26T00:00:00.968000+08:00',
                 '2026-10-26T00:00:02.001000+08:00']
        metas = []
        for stamp in times:
            obj, _, _ = fixture.make_payload(preprocess.parse_time(stamp).timestamp())
            metas.append({'FetchTime': stamp, 'Data': {'QKDQBER': {'Intermediate': obj.pack()}}})
        with tempfile.TemporaryDirectory() as temp:
            settings = SimpleNamespace(begin='2026-10-26T00:00:00+08:00', end='2026-10-26T00:00:03+08:00',
                source='2502', output=str(Path(temp)/'intermediate'), config=None,
                transform=None, timeout=30, skip_missing=False)
            root, manifest = preprocess.run(settings, metas=metas, return_manifest=True)
            self.assertEqual(len(manifest['processed']), 3)
            self.assertEqual(manifest['failures'], [])
            self.assertTrue(manifest['query_complete'])
            self.assertEqual(manifest['empty_timestamp_seconds'], ['2026-10-26T00:00:01+08:00'])
            args = SimpleNamespace(begin=settings.begin, end=settings.end, input=str(root),
                output=str(Path(temp)/'scan'), phase_bins=[7], intensity_min=[0], intensity_max=[1e300],
                intensity_ratio=[3], mu_x=[.03]*2, mu_y=[.48]*2, mu_z=[.49]*2, skip_missing=False)
            output = scan.run(args)
            self.assertEqual(len(json.loads((output/'manifest.json').read_text())['processed']), 3)

    def test_supplied_input_inclusion_and_exact_bounds(self):
        root = Path(batch.__file__).parent / 'batch_inputs'
        datasets, excluded = batch.load_datasets(root / '0_no_compensation.md', root / '1_compensation.csv')
        self.assertEqual(len(datasets), 71)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]['status'], 'interrupted')
        self.assertEqual(datasets[0]['end'], '2026-10-26T02:29:56.984000+08:00')
        self.assertEqual(datasets[1]['begin'], '2026-10-26T02:52:43.523907+08:00')
        chunks = batch.plan_chunks(datasets, 30)
        for dataset in datasets:
            jobs = [c for c in chunks if c['dataset'] == dataset['id']]
            self.assertEqual(jobs[0]['begin'], dataset['begin'])
            self.assertEqual(jobs[-1]['end'], dataset['end'])
            for left, right in zip(jobs, jobs[1:]):
                self.assertEqual(left['end'], right['begin'])

    def test_fractional_end_excludes_next_condition(self):
        fixture = test_scan.ScanTest()
        begin = preprocess.parse_time('2026-10-26T00:00:00.500000+08:00')
        payload, _, _ = fixture.make_payload(begin.timestamp())
        meta = {'FetchTime': begin.isoformat(), 'Data': {'QKDQBER': {'Intermediate': payload.pack()}}}
        with tempfile.TemporaryDirectory() as temp:
            settings = SimpleNamespace(begin='2026-10-26T00:00:00.600000+08:00',
                end='2026-10-26T00:00:00.900000+08:00', source='2502',output=temp,
                config=None, transform=None, timeout=30, skip_missing=False)
            _, manifest = preprocess.run(settings, metas=[meta], return_manifest=True)
            self.assertEqual(manifest['processed'], [])
            self.assertEqual(manifest['failures'], [])
            self.assertEqual(len(manifest['boundary_excluded_seconds']), 1)

    def test_two_spawned_workers_progress_and_cache_resume(self):
        fixture = test_scan.ScanTest()
        records = []
        for second in range(6):
            dt = preprocess.parse_time(f'2026-10-26T00:00:0{second}.500000+08:00')
            payload, _, _ = fixture.make_payload(dt.timestamp())
            records.append({'_id': str(second), 'FetchTime': dt.isoformat(),
                            'Data': {'QKDQBER': {'Intermediate': payload.pack()}}})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stub = root / 'stub'
            stub.mkdir()
            (stub / 'records.msgpack').write_bytes(msgpack.packb(records, use_bin_type=True))
            (stub / 'interactionfreepy.py').write_text('''
from pathlib import Path
from datetime import datetime
import msgpack
class Storage:
    def __init__(self):
        self.rows = msgpack.unpackb(Path(__file__).with_name('records.msgpack').read_bytes(), raw=False)
    def range(self, collection, begin, end, **kwargs):
        return [{'_id': r['_id'], 'FetchTime': r['FetchTime']} for r in self.rows
                if datetime.fromisoformat(begin) < datetime.fromisoformat(r['FetchTime']) < datetime.fromisoformat(end)]
    def get(self, collection, identity, **kwargs):
        return next(r for r in self.rows if r['_id'] == identity)
class IFWorker:
    def __init__(self, *args, **kwargs):
        self.Storage = Storage()
''')
            settings = SimpleNamespace(source='2502', output=str(root / 'output'), workers=2,
                chunk_seconds=2, progress_seconds=.1, config=None, transform=None,
                clock_frequency=25000, verify_realtime=True, timeout=2)
            datasets = [{'id': 'example', 'begin': '2026-10-26T00:00:00.200000+08:00',
                         'end': '2026-10-26T00:00:05.200000+08:00'}]
            sys.path.insert(0, str(stub))
            try:
                first = batch.run(settings, datasets=datasets)
                second = batch.run(settings, datasets=datasets)
            finally:
                sys.path.remove(str(stub))
            self.assertEqual(first['state'], 'completed')
            self.assertEqual(first['processed_files'], 5)
            self.assertEqual(first['storage_files'], 5)
            self.assertEqual(first['boundary_excluded_seconds'], 1)
            self.assertEqual(second['cached_files'], 5)
            self.assertEqual(second['failures'], 0)
            status = json.loads((root / 'output/status.json').read_text())
            self.assertEqual(status['done_slots'], status['total_slots'])
            self.assertEqual(status['eta_seconds'], 0)
            self.assertEqual(len(list((root / 'output/intermediate').rglob('*.npz'))), 5)


if __name__ == '__main__':
    unittest.main()
