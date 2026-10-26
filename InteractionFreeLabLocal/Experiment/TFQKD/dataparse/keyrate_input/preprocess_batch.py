"""Multiprocess preprocessing of experiment intervals, with resumable caches and ETA."""
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import re
import signal
import sys
import time
from types import SimpleNamespace
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

# Prevent each process from starting an additional BLAS/Numba thread pool.
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[_name] = '1'

try:
    from . import preprocess
except ImportError:
    import preprocess

_WORKER = None


def load_datasets(markdown, csv_path):
    """Read timestamps as data; CSV exclusion flags determine which intervals run."""
    markdown, csv_path = Path(markdown), Path(csv_path)
    text = markdown.read_text(encoding='utf-8-sig')
    stamps = re.findall(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?', text)
    if len(stamps) != 2:
        raise ValueError('Markdown must contain exactly one start/end timestamp pair')
    start, end = preprocess.interval(*stamps)
    datasets = [{'id': 'baseline_74dB_gen1_on_gen2_off', 'condition': 'no_compensation',
                 'begin': start.isoformat(), 'end': end.isoformat(), 'source_file': markdown.name,
                 'status': 'recorded', 'include_in_complete_analysis': True,
                 'quality_scope': 'user_record_not_optical_quality_validated'}]
    excluded = []
    with csv_path.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row['status'] != 'complete' or row['include_in_complete_analysis'] != '1':
                excluded.append(row)
                continue
            start, end = preprocess.interval(row['start_beijing'], row['end_beijing'])
            identifier = f"{row['run_id']}_r{row['round']}_i{row['index']}_{row['condition']}_rho{row['rho'] or 'none'}"
            datasets.append({'id': identifier, 'begin': start.isoformat(), 'end': end.isoformat(),
                             'condition': row['condition'], 'round': int(row['round']),
                             'index': int(row['index']), 'rho': row['rho'] or None,
                             'run_id': row['run_id'], 'status': row['status'],
                             'source_file': csv_path.name, 'include_in_complete_analysis': True,
                             'quality_scope': row['quality_scope']})
    ids = [d['id'] for d in datasets]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate dataset identifiers')
    ordered = sorted(datasets, key=lambda d: preprocess.parse_time(d['begin']))
    for left, right in zip(ordered, ordered[1:]):
        if preprocess.parse_time(left['end']) > preprocess.parse_time(right['begin']):
            raise ValueError(f"Overlapping datasets: {left['id']} and {right['id']}")
    return datasets, excluded


def plan_chunks(datasets, chunk_seconds):
    if not isinstance(chunk_seconds, int) or not 1 <= chunk_seconds <= 300:
        raise ValueError('chunk_seconds must be an integer in 1..300')
    chunks = []
    for dataset in datasets:
        begin, end = preprocess.interval(dataset['begin'], dataset['end'])
        cursor = begin.replace(microsecond=0)
        while cursor < end:
            stop = min(cursor + timedelta(seconds=chunk_seconds), end)
            actual_begin = max(cursor, begin)
            chunks.append({'id': len(chunks), 'dataset': dataset['id'],
                           'begin': actual_begin.isoformat(), 'end': stop.isoformat(),
                           'slots': math.ceil((stop - cursor).total_seconds())})
            cursor += timedelta(seconds=chunk_seconds)
    return chunks


def _initialize_worker(endpoint, timeout):
    global _WORKER
    from interactionfreepy import IFWorker
    _WORKER = IFWorker(endpoint, timeout=timeout)
    # SIGINT is handled by the parent, which terminates its own child processes.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def process_chunk(chunk, options):
    """One bounded job; the IF connection and JIT cache are reused by each process."""
    root = Path(options['output'])
    journal_dir = root / 'journals' / options['invocation'] / f"chunk_{chunk['id']:05d}"
    settings = SimpleNamespace(begin=chunk['begin'], end=chunk['end'], source=options['source'],
        output=str(root / 'intermediate'), config=options.get('config'),
        clock_frequency=options['clock_frequency'], transform=options.get('transform'),
        verify_realtime=options['verify_realtime'], timeout=options['timeout'],
        skip_missing=True, quiet=True, journal_dir=str(journal_dir))
    started = time.monotonic()
    try:
        source = preprocess.SOURCES[settings.source]
        begin, end = preprocess.interval(chunk['begin'], chunk['end'])
        rows = _WORKER.Storage.range(source['collection'],
            (begin - timedelta(microseconds=1)).isoformat(), end.isoformat(),
            by='FetchTime', filter={'FetchTime': 1}, limit=1000)
        if len(rows) >= 1000:
            raise ValueError('Metadata range limit reached')
        metas = []
        for row in rows:
            if begin <= preprocess.parse_time(row['FetchTime']) < end:
                metas.append(_WORKER.Storage.get(source['collection'], row['_id'],
                    filter={'FetchTime': 1, 'Data.QKDQBER': 1}))
        _, manifest = preprocess.run(settings, metas=metas, return_manifest=True)
        error = None
    except Exception as exc:
        manifests = list(journal_dir.glob('*.json'))
        manifest = json.loads(manifests[-1].read_text()) if manifests else {
            'processed': [], 'missing_seconds': [], 'boundary_excluded_seconds': [],
            'query_complete': False, 'empty_timestamp_seconds': [],
            'failures': [{'FetchTime': chunk['begin'], 'error': str(exc)}]}
        error = str(exc)
    return {'chunk': chunk, 'elapsed_seconds': time.monotonic() - started,
            'processed': manifest['processed'], 'failures': manifest['failures'],
            'missing_seconds': manifest['missing_seconds'],
            'boundary_excluded_seconds': manifest.get('boundary_excluded_seconds', []),
            'empty_timestamp_seconds': manifest.get('empty_timestamp_seconds', []),
            'query_complete': manifest.get('query_complete', False),
            'error': error}


def format_duration(seconds):
    if seconds is None:
        return 'estimating'
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def run(settings, *, datasets=None):
    input_hashes = {}
    if datasets is None:
        datasets, excluded = load_datasets(settings.markdown, settings.csv)
        input_hashes = {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        for p in (settings.markdown, settings.csv)}
    else:
        excluded = []
    if not datasets:
        raise ValueError('No included datasets')
    if settings.source not in preprocess.SOURCES:
        raise ValueError('Unknown source')
    if not isinstance(settings.workers, int) or settings.workers < 1:
        raise ValueError('workers must be a positive integer')
    root = Path(settings.output)
    root.mkdir(parents=True, exist_ok=True)
    from uuid import uuid4
    invocation = uuid4().hex
    chunks = plan_chunks(datasets, settings.chunk_seconds)
    total_slots = sum(c['slots'] for c in chunks)
    options = {**vars(settings), 'output': str(root), 'invocation': invocation}
    plan = {'datasets': datasets, 'excluded': excluded, 'chunks': chunks, 'input_sha256': input_hashes,
            'interval_semantics': '[begin,end), by actual FetchTime',
            'boundary_note': 'FetchTime is the acquisition record timestamp; no optical-quality validation is implied.',
            'total_seconds_of_intervals': sum((preprocess.parse_time(d['end']) - preprocess.parse_time(d['begin'])).total_seconds() for d in datasets)}
    # Dataset lists are immutable inputs for a resumable cache directory.
    plan_file = root / 'datasets.json'
    if plan_file.exists() and json.loads(plan_file.read_text()) != plan:
        raise ValueError('Existing datasets.json differs; use a new output directory')
    preprocess.atomic_write(plan_file, json.dumps(plan, ensure_ascii=False, indent=2).encode())
    dataset_state = {d['id']: {**d, 'processed': [], 'failures': [], 'missing_seconds': [],
        'boundary_excluded_seconds': [], 'empty_timestamp_seconds': [], 'state': 'running',
        'chunks_total': sum(c['dataset'] == d['id'] for c in chunks), 'chunks_done': 0,
        'unprocessed_chunks': []} for d in datasets}
    status = {'invocation': invocation, 'state': 'running', 'code_revision': 'actual-fetchtime-v2', 'workers': settings.workers,
              'total_datasets': len(datasets), 'excluded_datasets': len(excluded),
              'total_chunks': len(chunks), 'done_chunks': 0, 'total_slots': total_slots,
              'done_slots': 0, 'processed_files': 0, 'raw_files': 0, 'cached_files': 0,
              'storage_files': 0, 'failures': 0, 'failed_chunks': 0, 'unprocessed_slots': 0,
              'boundary_excluded_seconds': 0,
              'empty_timestamp_seconds': 0,
              'started_beijing': datetime.now(preprocess.TZ).isoformat()}
    started = time.monotonic()
    last_progress = 0
    # One parent journal makes progress visible even if the SSH session is lost.
    events = (root / f'batch_{invocation}.jsonl').open('a', encoding='utf-8')
    failures = (root / f'failures_{invocation}.jsonl').open('a', encoding='utf-8')
    def progress(force=False):
        nonlocal last_progress
        now = time.monotonic()
        if not force and now - last_progress < settings.progress_seconds:
            return
        last_progress = now
        elapsed = now - started
        rate = status['done_slots'] / elapsed if elapsed else 0
        eta = (total_slots - status['done_slots']) / rate if rate else None
        status.update(elapsed_seconds=elapsed, data_seconds_per_wall_second=rate,
                      eta_seconds=eta, updated_beijing=datetime.now(preprocess.TZ).isoformat())
        status['expected_finish_beijing'] = (datetime.now(preprocess.TZ) + timedelta(seconds=eta)).isoformat() if eta is not None else None
        preprocess.atomic_write(root / 'status.json', json.dumps(status, ensure_ascii=False, indent=2).encode())
        percent = 100 * status['done_slots'] / total_slots if total_slots else 100
        print(f"[{status['state']}] {status['done_slots']}/{total_slots} ({percent:.1f}%) | "
              f"files={status['processed_files']} cache={status['cached_files']} failed={status['failures']} | "
              f"{rate:.2f} data-s/s | elapsed {format_duration(elapsed)} | ETA {format_duration(eta)} | "
              f"finish {status['expected_finish_beijing'] or 'estimating'}", flush=True)
    executor = ProcessPoolExecutor(max_workers=settings.workers, mp_context=mp.get_context('spawn'),
        initializer=_initialize_worker, initargs=(preprocess.SOURCES[settings.source]['endpoint'], settings.timeout))
    pending = {}
    iterator = iter(chunks)
    fatal = None
    def submit():
        try:
            chunk = next(iterator)
        except StopIteration:
            return False
        pending[executor.submit(process_chunk, chunk, options)] = chunk
        return True
    progress(True)
    try:
        for _ in range(settings.workers * 2):
            if not submit():
                break
        while pending:
            ready, _ = wait(pending, timeout=min(settings.progress_seconds, 2), return_when=FIRST_COMPLETED)
            for future in ready:
                chunk = pending.pop(future)
                result = future.result()
                events.write(json.dumps(result, ensure_ascii=False) + '\n')
                events.flush()
                group = dataset_state[chunk['dataset']]
                group['chunks_done'] += 1
                if not result['query_complete']:
                    group['unprocessed_chunks'].append(chunk)
                for key in ('processed', 'failures', 'missing_seconds', 'boundary_excluded_seconds', 'empty_timestamp_seconds'):
                    group[key].extend(result[key])
                status['done_chunks'] += 1
                status['done_slots'] += chunk['slots']
                status['processed_files'] += len(result['processed'])
                status['failures'] += len(result['failures'])
                status['failed_chunks'] += int(bool(result['error'] or result['failures']))
                status['unprocessed_slots'] += 0 if result['query_complete'] else chunk['slots']
                if result['error'] and not result['failures']:
                    status['failures'] += 1
                status['boundary_excluded_seconds'] += len(result['boundary_excluded_seconds'])
                status['empty_timestamp_seconds'] += len(result['empty_timestamp_seconds'])
                for key, origin in (('raw_files', 'raw'), ('cached_files', 'cache'), ('storage_files', 'storage')):
                    status[key] += sum(entry['origin'] == origin for entry in result['processed'])
                for failure in result['failures']:
                    failures.write(json.dumps({'dataset': chunk['dataset'], **failure}, ensure_ascii=False) + '\n')
                failures.flush()
                folder = root / 'datasets' / chunk['dataset']
                group['processed'].sort(key=lambda x: x['FetchTime'])
                if group['chunks_done'] == group['chunks_total']:
                    group['state'] = 'completed' if not group['failures'] and not group['unprocessed_chunks'] else 'completed_with_failures'
                preprocess.atomic_write(folder / 'manifest.json', json.dumps(group, ensure_ascii=False, indent=2).encode())
                submit()
            progress()
        status['state'] = 'completed' if status['failures'] == 0 and status['unprocessed_slots'] == 0 else 'completed_with_failures'
    except BaseException as exc:
        fatal = exc
        status['state'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
        status['error'] = str(exc) or type(exc).__name__
        for future in pending:
            future.cancel()
        for process in (getattr(executor, '_processes', {}) or {}).values():
            process.terminate()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
        events.close()
        failures.close()
        progress(True)
        preprocess.atomic_write(root / f'summary_{invocation}.json', json.dumps(status, ensure_ascii=False, indent=2).encode())
    if fatal:
        raise fatal
    return status


def main():
    base = Path(__file__).resolve().parent
    settings = SimpleNamespace(
        markdown=str(base / 'batch_inputs' / '0_no_compensation.md'),
        csv=str(base / 'batch_inputs' / '1_compensation.csv'),
        source='2502',
        output=os.environ.get('TFQKD_BATCH_OUTPUT', str(base / 'batch_output' / '20261026')),
        workers=int(os.environ.get('TFQKD_WORKERS', '16')), # LabServer2共80逻辑CPU，先用16进程
        chunk_seconds=30,         # 每个任务处理最多30秒；进程复用连接和Numba缓存
        progress_seconds=5,
        config=None,
        clock_frequency=25000,
        transform=None,
        verify_realtime=True,
        timeout=30,
    )
    result = run(settings)
    if result['state'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
