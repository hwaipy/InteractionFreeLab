"""Cache per-second unsifted statistics from Storage, falling back to historical Raw."""
from datetime import datetime, timedelta
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import quote
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import numpy as np

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'pytimetag'))
from pytimetag import DataBlock
from InteractionFreeLabLocal.Experiment.TFQKD.services.tdc.TFQKDQBERAnalyser import (
    DataBlockParser, TFQKDQBERAnalyser, QKDIntermediate,
)

TZ = ZoneInfo('Asia/Shanghai')
# IFView/public/configs/2502.json: live/archived pairs, AccessCampus/AccessField.
SOURCES = {
    '2502': {'endpoint': 'tcp://172.20.8.102:1161',
             'collection': 'TFQKD_TDC', 'raw_url': 'http://172.20.8.102:1001'},
    'archive': {'endpoint': 'tcp://172.20.8.102:1061',
                'collection': 'TFQKD_TDC_2502', 'raw_url': 'http://172.20.8.102:1003'},
    '2502-public': {'endpoint': 'tcp://code.qpqi.group:1161',
                    'collection': 'TFQKD_TDC', 'raw_url': 'http://code.qpqi.group:1001'},
    'archive-public': {'endpoint': 'tcp://code.qpqi.group:1061',
                       'collection': 'TFQKD_TDC_2502', 'raw_url': 'http://code.qpqi.group:1003'},
}


def parse_time(value):
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def raw_path(fetch_time):
    dt = parse_time(fetch_time)
    return f'{dt:%Y-%m-%d}/{dt:%H}/{dt:%Y-%m-%d %H-%M-%S}.{dt.microsecond // 1000:03d}.datablock'


def validate_block(block, configs):
    for key in ('AliceRandomNumbers', 'BobRandomNumbers'):
        rn = np.asarray(configs[key])
        if rn.ndim != 1 or not len(rn) or not np.issubdtype(rn.dtype, np.integer) or np.any((rn < 0) | (rn > 255)):
            raise ValueError(f'{key} must be a nonempty array of byte integers (resolve RN IDs before running)')
    if len(configs['AliceRandomNumbers']) != len(configs['BobRandomNumbers']):
        raise ValueError('Alice/Bob RN lengths differ')
    alice, bob = (np.asarray(configs[key]) for key in ('AliceRandomNumbers', 'BobRandomNumbers'))
    if np.any((alice & 192) != (bob & 192)) or np.any((alice & 192) == 192):
        raise ValueError('Alice/Bob reference and gap positions must match and be unambiguous')
    if configs['TimeEachBlock'] != 10**12 or block.resolution != 1e-12:
        raise ValueError('This version requires one-second blocks with picosecond timestamps')
    for key in ('FrequencyFrame', 'PhaseFrame', 'IntensityFrame'):
        if not isinstance(configs[key], int) or configs[key] <= 0:
            raise ValueError(f'{key} must be a positive integer in ps')
    period, center = configs['Period'], configs['PulsePosition']
    if not isinstance(period, int) or period <= 0 or not 0 < center < period:
        raise ValueError('Period must be a positive integer, with 0 < PulsePosition < Period')
    if configs['TriggerPeriod'] <= 0 or configs['TriggerPeriod'] % period:
        raise ValueError('TriggerPeriod must be a positive multiple of Period')
    for gate in ('Gate', 'GateRef'):
        if configs[gate] <= 0 or center - configs[gate] / 2 <= 0 or center + configs[gate] / 2 >= period:
            raise ValueError(f'{gate} must fit strictly inside a pulse period')
    channels = [configs[key] for key in ('TriggerChannel', 'Channel 1', 'Channel 2', 'SyncChannelAlice', 'SyncChannelBob')]
    if any(not isinstance(ch, int) or not 0 <= ch < len(block.content) for ch in channels):
        raise ValueError('Configured channel outside DataBlock')
    triggers = block.content[configs['TriggerChannel']]
    if not len(triggers):
        raise ValueError('No trigger events')


def interval(begin, end):
    begin, end = parse_time(begin), parse_time(end)
    if end <= begin:
        raise ValueError('end must be after begin; interval is [begin, end)')
    return begin, end


def file_path(root, fetch_time):
    dt = parse_time(fetch_time)
    return Path(root) / f'{dt:%Y-%m-%d}/{dt:%H}/{dt:%Y%m%dT%H%M%S%f}.npz'


def atomic_write(path, payload):
    import os
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as f:
            temporary = Path(f.name)
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def processing_label(clock_frequency, transform):
    label = f'tdc-clock-v1:{clock_frequency:g}Hz' if clock_frequency is not None else 'raw-unadapted'
    return label + '+transform:' + transform if transform else label


def verify_realtime(intermediate, qber):
    """Check the original threshold/frame selection, independent of later scans."""
    required = ('CountsZ', 'PhaseErrorX', 'PhaseErrorY', 'PhaseErrorZ1', 'Valid', 'PhaseThreshold')
    if not all(key in qber for key in required):
        return False
    frames = len(intermediate.syncCountsAlice)
    if qber['Valid'][1] != frames:
        raise ValueError('Realtime frame count does not match intermediate')
    if qber['Valid'][0] == frames:
        # Historical servers used `or True` and retained every frame.
        selected = np.ones(frames, dtype=bool)
    else:
        config = qber['Configuration']
        a, b = intermediate.syncCountsAlice, intermediate.syncCountsBob
        minimum, ratio = config['IntensityThreshold'], config['IntensityRatioThreshold']
        selected = (a > minimum) & (b > minimum) & (a < b * ratio) & (b < a * ratio)
    errors = intermediate.phaseErrorStatistics[:, selected, int(qber['PhaseThreshold']), :].sum(axis=1, dtype=np.int64)
    actual = {'PhaseErrorX': errors[1].tolist(), 'PhaseErrorY': errors[2].tolist(),
              'PhaseErrorZ1': errors[3].tolist(), 'Valid': [int(selected.sum()), frames],
              'CountsZ': [int(intermediate.detectionStatistics[a, b, selected].sum())
                          for a, b in ((0, 0), (0, 3), (3, 0), (3, 3))]}
    differences = {key: {'realtime': qber[key], 'recomputed': value}
                   for key, value in actual.items() if qber[key] != value}
    if differences:
        raise ValueError(f'Realtime comparison failed; check timing/Doppler correction: {differences}')
    return True


def assert_identity(intermediate, fetch_time, overrides, transform, expected_config=None, clock_frequency=25000):
    actual = parse_time(intermediate.metadata['FetchTime'])
    if abs((actual - parse_time(fetch_time)).total_seconds()) > .001:
        raise ValueError('Intermediate timestamp does not match metadata FetchTime')
    for key, value in overrides.items():
        if key in ('IntensityThreshold', 'IntensityRatioThreshold', 'PhaseThreshold'):
            continue
        if key in ('AliceRandomNumbers', 'BobRandomNumbers'):
            continue
        if intermediate.metadata['configuration'].get(key) != value:
            raise ValueError(f'Cached intermediate does not match override {key}; use a new output directory')
    label = intermediate.metadata['processing']
    expected_label = processing_label(clock_frequency, transform)
    if label != expected_label and not (label == 'tdc-adapted' and not transform):
        raise ValueError('Cached intermediate has different/missing timing correction; use a new output directory')
    if expected_config:
        for key, value in intermediate.metadata['configuration'].items():
            if key in expected_config and expected_config[key] != value:
                raise ValueError(f'Cached intermediate does not match metadata {key}; use a new output directory')
        if all(k in expected_config for k in ('AliceRandomNumbers', 'BobRandomNumbers')):
            digest = hashlib.sha256()
            for key in ('AliceRandomNumbers', 'BobRandomNumbers'):
                digest.update(np.asarray(expected_config[key], dtype='<i8').tobytes())
            if intermediate.metadata['random_numbers_sha256'] != digest.hexdigest():
                raise ValueError('Cached intermediate random numbers differ; use a new output directory')


def run(settings, *, metas=None, fetch_raw=None, worker=None, return_manifest=False):
    begin, end = interval(settings.begin, settings.end)
    if settings.source not in SOURCES:
        raise ValueError(f'Source must be one of {list(SOURCES)}')
    if not math.isfinite(settings.timeout) or settings.timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    source = SOURCES[settings.source]
    clock_frequency = getattr(settings, 'clock_frequency', 25000)
    if clock_frequency is not None and (not math.isfinite(clock_frequency) or clock_frequency <= 0):
        raise ValueError('clock_frequency must be finite and positive, or None to explicitly disable correction')
    overrides = json.loads(Path(settings.config).read_text()) if settings.config else {}
    if any(k in overrides for k in ('IntensityThreshold', 'IntensityRatioThreshold', 'PhaseThreshold')):
        raise ValueError('Preprocessing has no sifting thresholds; set them in scan.py')
    output = Path(settings.output)
    output.mkdir(parents=True, exist_ok=True)
    if metas is None:
        from interactionfreepy import IFWorker
        if worker is None:
            worker = IFWorker(source['endpoint'], timeout=settings.timeout)
        def iterate_records():
            dt = begin.replace(microsecond=0)
            while dt < end:
                rows = worker.Storage.range(source['collection'], (dt - timedelta(microseconds=1)).isoformat(),
                    (dt + timedelta(seconds=1)).isoformat(), by='FetchTime', filter={'FetchTime': 1}, limit=1000)
                if len(rows) >= 1000:
                    raise ValueError(f'Metadata query limit reached at {dt.isoformat()}')
                rows = [r for r in rows if begin <= parse_time(r['FetchTime']) < end
                        and dt <= parse_time(r['FetchTime']) < dt + timedelta(seconds=1)]
                if not rows:
                    manifest['empty_timestamp_seconds'].append(dt.isoformat())
                for row in sorted(rows, key=lambda r: parse_time(r['FetchTime'])):
                    try:
                        meta = worker.Storage.get(source['collection'], row['_id'],
                            filter={'FetchTime': 1, 'Data.QKDQBER': 1})
                        if meta is None:
                            raise ValueError('Metadata record disappeared after range query')
                    except Exception as exc:
                        meta = {'FetchTime': row['FetchTime'], '_fetch_error': str(exc)}
                    yield meta
                dt += timedelta(seconds=1)
    else:
        records = sorted((m for m in metas if begin <= parse_time(m['FetchTime']) < end),
                         key=lambda m: parse_time(m['FetchTime']))
        def iterate_records():
            observed = {parse_time(m['FetchTime']).replace(microsecond=0) for m in records}
            dt = begin.replace(microsecond=0)
            while dt < end:
                if dt not in observed:
                    manifest['empty_timestamp_seconds'].append(dt.isoformat())
                dt += timedelta(seconds=1)
            yield from records
    if fetch_raw is None:
        def fetch_raw(fetch_time):
            with urlopen(source['raw_url'] + '/' + quote(raw_path(fetch_time)), timeout=settings.timeout) as response:
                return response.read()
    transform = None
    if settings.transform:
        module, function = settings.transform.split(':', 1)
        transform = getattr(importlib.import_module(module), function)
    manifest = {'begin': begin.isoformat(), 'end_exclusive': end.isoformat(), 'source': source,
                'arguments': vars(settings), 'processed': [], 'missing_seconds': [], 'boundary_excluded_seconds': [], 'failures': [],
                'empty_timestamp_seconds': [], 'metadata_records': 0, 'query_complete': False}
    # One journal per invocation: repeated/resumed ranges do not erase earlier run provenance.
    from uuid import uuid4
    journal_dir = Path(getattr(settings, 'journal_dir', output))
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal = journal_dir / ('preprocess_' + uuid4().hex + '.json')
    def log_event(event):
        with journal.with_suffix('.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    log_event({'type': 'begin', 'begin': begin.isoformat(), 'end_exclusive': end.isoformat(),
               'source': source, 'arguments': vars(settings)})
    seen_timestamps = set()
    for meta in iterate_records():
        fetch_time = meta['FetchTime']
        manifest['metadata_records'] += 1
        try:
            if '_fetch_error' in meta:
                raise ValueError(meta['_fetch_error'])
            stamp = parse_time(fetch_time)
            if stamp in seen_timestamps:
                raise ValueError('Duplicate exact FetchTime; cannot distinguish raw file identity')
            seen_timestamps.add(stamp)
            path = file_path(output, fetch_time)
            qber = meta.get('Data', {}).get('QKDQBER') or {}
            expected_config = {**meta.get('Configuration', qber.get('Configuration', {})), **overrides}
            if path.exists():
                payload = path.read_bytes()
                intermediate = QKDIntermediate.unpack(payload)
                assert_identity(intermediate, fetch_time, overrides, settings.transform, expected_config, clock_frequency)
                origin = 'cache'
            else:
                if 'Intermediate' in qber and not overrides and not transform:
                    # A present but corrupt payload must fail, never silently fall back to Raw.
                    payload = qber['Intermediate']
                    intermediate = QKDIntermediate.unpack(payload)
                    assert_identity(intermediate, fetch_time, {}, None, expected_config, clock_frequency)
                    origin = 'storage'
                else:
                    stored = meta.get('Configuration', qber.get('Configuration', {}))
                    configs = {**stored, **overrides}
                    required = ('AliceRandomNumbers', 'BobRandomNumbers', 'TimeEachBlock', 'FrequencyFrame',
                        'PhaseFrame', 'IntensityFrame', 'Period', 'TriggerPeriod', 'PulsePosition', 'Gate', 'GateRef',
                        'TriggerChannel', 'Channel 1', 'Channel 2', 'SyncChannelAlice', 'SyncChannelBob')
                    absent = [key for key in required if key not in configs]
                    if absent:
                        raise ValueError(f'Missing analyser configuration: {absent}')
                    analyser = TFQKDQBERAnalyser(16)
                    analyser.configure(configs)
                    configs = analyser.getConfigurations()
                    block = DataBlock.deserialize(fetch_raw(fetch_time))
                    correction = None
                    if clock_frequency is not None:
                        block, correction = DataBlockParser.rescaleTDCClock(block, clock_frequency)
                    if transform:
                        block = transform(block)
                    validate_block(block, configs)
                    parser = DataBlockParser(block, configs)
                    intermediate = QKDIntermediate.fromParser(parser, parser.parseIntermediate(), configs,
                        processing=processing_label(clock_frequency, settings.transform))
                    intermediate.metadata['timing_correction'] = correction
                    # Storage FetchTime has millisecond precision; retain the authoritative lookup time.
                    intermediate.metadata['FetchTime'] = fetch_time
                    payload = intermediate.pack()
                    origin = 'raw'
            verified = verify_realtime(intermediate, qber) if getattr(settings, 'verify_realtime', True) and not overrides else False
            if not path.exists():
                atomic_write(path, payload)
            manifest['processed'].append({'FetchTime': fetch_time, 'file': str(path.relative_to(output)),
                'origin': origin, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                'processing': intermediate.metadata['processing'], 'realtime_verified': verified})
            log_event({'type': 'processed', **manifest['processed'][-1]})
            if not getattr(settings, 'quiet', False):
                print(f'{fetch_time}: {origin}, {len(payload)} bytes', flush=True)
        except Exception as exc:
            manifest['failures'].append({'FetchTime': fetch_time, 'error': str(exc)})
            log_event({'type': 'failure', **manifest['failures'][-1]})
            if not settings.skip_missing:
                atomic_write(journal, json.dumps(manifest, ensure_ascii=False, indent=2).encode())
                raise RuntimeError(f'{fetch_time}: {exc}') from exc
            if not getattr(settings, 'quiet', False):
                print(f'{fetch_time}: SKIPPED: {exc}', file=sys.stderr, flush=True)
    manifest['query_complete'] = True
    # Empty natural timestamp bins are not missing DataBlocks: acquisition timestamps jitter.
    manifest['boundary_excluded_seconds'] = [t for t in manifest['empty_timestamp_seconds']
        if parse_time(t) < begin or parse_time(t) + timedelta(seconds=1) > end]
    if not manifest['metadata_records'] and (end - begin).total_seconds() >= 1:
        manifest['failures'].append({'FetchTime': begin.isoformat(), 'error': 'No metadata records in interval'})
    atomic_write(journal, json.dumps(manifest, ensure_ascii=False, indent=2).encode())
    if not manifest['processed'] and manifest['failures']:
        raise ValueError('No successfully preprocessed DataBlocks')
    return (output, manifest) if return_manifest else output


def main():
    # 初级处理：优先读取 Meta.Intermediate，历史数据缺少该字段时才处理 Raw。
    settings = SimpleNamespace(
        begin='2026-10-26T01:30:00+08:00',
        end='2026-10-26T01:31:00+08:00',
        source='2502-public',  # '2502' / 'archive' / '2502-public' / 'archive-public'
        output=str(Path(__file__).resolve().parent / 'intermediate_clock_corrected'),
        config=None,          # 可选：固定分析配置覆盖 JSON 文件
        clock_frequency=25000, # 历史 Raw 必须先按在线 25 kHz 参考时钟缩放；None 显式关闭
        transform=None,       # 可选：时钟缩放之后的额外校正；若函数已做缩放，设置 clock_frequency=None
        verify_realtime=True, # 有实时汇总时，按原阈值和帧选择逐项核对；不一致则报错
        timeout=30,
        skip_missing=False,
    )
    print(run(settings))


if __name__ == '__main__':
    main()
