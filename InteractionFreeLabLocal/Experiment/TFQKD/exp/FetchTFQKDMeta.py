"""Lossless local meta archive; direct IFWorker + incremental local analysis.

This Mac reads Storage directly; ZIP mode needs no GPUClaw, SSH or datablocks.
All original fields, including binary
Intermediate and random numbers, are preserved. Download resumes by checksum.

Run continuously: python FetchTFQKDMeta.py
Also analyzes committed ZIP entries locally and writes <zip>.analysis/index.html,
by_rho.csv, seconds.csv and distribution/keyrate plots (updates every 30 s).
Use --analyze-only for an existing ZIP, or --download-only to disable analysis.
Resume: run the same command again. Ctrl+C finalizes the ZIP and checkpoints completed entries.
Live mode writes one ZIP, with one .msgpack.xz member per second containing meta.
An adjacent .state.xz stores recovery state, not a second metadata archive.
Read while downloading: iter_metas('tdc_meta/live.zip', begin=TIME, end=TIME).
Each call sees one fixed checkpoint; get_download_status(path) reports progress.
Historical snapshot: --begin TIME --end TIME --output DIRECTORY
Time-bounded live ZIP: --begin TIME --end TIME --output run.zip ([begin,end)).
Repair an interrupted ZIP without downloading: --repair-only --output run.zip
Filter a stopped download: --filter-only --output DIRECTORY --zero-run-ms 5
Read accepted records: iter_metas(output_directory, selection='valid').
The archive retains all original records; quality.jsonl, valid_seconds.csv,
rejected_seconds.csv and quality_intervals.json describe the selection without
duplicating or deleting the original metadata. Times refer to Storage FetchTime.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import lzma
import math
from pathlib import Path
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
import os

import msgpack

TZ = timezone(timedelta(hours=8))

# Edit these when running directly in VS Code. CLI arguments override them.
# Both accept "YYYY-MM-DD HH:MM:SS" (China time) or an ISO timestamp.
# DATA_BEGIN = None  # Example: "2026-10-31 17:00:00"; None starts now / resumes.
# DATA_END = None    # Example: "2026-11-02 06:00:00"; None follows indefinitely.
# OUTPUT_ZIP = Path(__file__).parent/'tdc_meta/live.zip'
DATA_BEGIN = "2026-10-31 22:00:00"
DATA_END = "2026-11-02 06:00:00"
OUTPUT_ZIP = Path(__file__).parent / "tdc_meta/run_20261031B.zip"
META_ENDPOINT = 'tcp://code.qpqi.group:1161'

def timestamp(value):
    t = datetime.fromisoformat(value)
    return t.replace(tzinfo=TZ) if t.tzinfo is None else t.astimezone(TZ)


def save_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)


def download(root, begin, end, chunk_seconds=60,endpoint=META_ENDPOINT):
    root = Path(root)
    (root/'chunks').mkdir(parents=True, exist_ok=True)
    path = root/'manifest.json'
    manifest = json.loads(path.read_text()) if path.exists() else {
        'begin': timestamp(begin).isoformat(), 'requested_end': timestamp(end).isoformat(),
        'chunk_seconds': chunk_seconds, 'chunks': [], 'state': 'downloading',
        'collection': 'TFQKD_TDC', 'period_seconds': 15,
        'rho': [7**(i/13) for i in range(14)], 'uncompensated_second': 15,
        'format': 'Compressed MessagePack list (.xz or .gz); all original meta fields preserved'}
    if (manifest['begin'] != timestamp(begin).isoformat()
            or manifest['requested_end'] != timestamp(end).isoformat()
            or manifest['chunk_seconds'] != chunk_seconds):
        raise ValueError('Output directory belongs to a different download')
    manifest['format'] = 'Compressed MessagePack list (.xz or .gz); all original meta fields preserved'
    for c in manifest['chunks']:
        if hashlib.sha256((root/c['file']).read_bytes()).hexdigest() != c['sha256']:
            raise ValueError('Corrupt local chunk: '+c['file'])
    if manifest['state'] == 'complete':
        save_json(path, manifest)
        return manifest
    remote_end = manifest.get('actual_end', manifest['requested_end'])
    packets=_direct_snapshot(manifest['begin'],remote_end,len(manifest['chunks']),chunk_seconds,endpoint)
    try:
        finished = False
        for entry,payload in packets:
            if entry['kind'] == 'snapshot':
                if 'actual_end' in manifest and manifest['actual_end'] != entry['actual_end']:
                    raise ValueError('Source snapshot end changed')
                manifest.update(actual_end=entry['actual_end'], latest_at_download=entry['latest'])
                save_json(path, manifest)
            elif entry['kind'] == 'chunk':
                if entry['index'] != len(manifest['chunks']):
                    raise ValueError('Unexpected chunk index')
                if hashlib.sha256(payload).hexdigest() != entry['sha256']:
                    raise ValueError('Transfer checksum mismatch')
                extension = entry.get('compression', 'gz')
                filename = f'chunks/{entry["index"]:05d}.msgpack.{extension}'
                temporary = root/(filename+'.tmp')
                temporary.write_bytes(payload)
                temporary.replace(root/filename)
                entry['file'] = filename
                manifest['chunks'].append(entry)
                save_json(path, manifest)
                print(entry['end'], 'records:', sum(c['records'] for c in manifest['chunks']), flush=True)
            elif entry['kind'] == 'done':
                if entry['chunks'] != len(manifest['chunks']):
                    raise ValueError('Missing chunks')
                finished = True
        if not finished:
            raise IOError('Download interrupted; rerun the same command to resume')
    finally:
        packets.close()
    manifest.update(state='complete', records=sum(c['records'] for c in manifest['chunks']),
                    compressed_bytes=sum(c['bytes'] for c in manifest['chunks']))
    save_json(path, manifest)
    return manifest


def _stop_process(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _direct_follow(begin,index,poll_seconds,settle_seconds,end=None,endpoint=META_ENDPOINT,worker=None):
    """Yield the existing archive protocol locally; full meta is intentionally
    fetched for lossless archival. Only latest/index queries use projection.
    """
    owned=worker is None
    if owned:
        from interactionfreepy import IFWorker
        worker=IFWorker(endpoint,timeout=180)
    try:
        yield from _direct_packets(begin,index,poll_seconds,settle_seconds,end,worker)
    finally:
        if owned:worker.close()


def _fetch_full_meta(worker,a,b):
    try:
        rows=worker.Storage.range('TFQKD_TDC',(a-timedelta(seconds=3)).isoformat(),
                                  (b+timedelta(seconds=3)).isoformat(),by='FetchTime',limit=128)
    except Exception as e:raise IOError('Storage request failed: '+str(e)) from e
    rows=[rows] if isinstance(rows,dict) else list(rows or [])
    if len(rows)>=128:
        if (b-a).total_seconds()<=.000002:raise ValueError('Too many records at one timestamp')
        middle=a+(b-a)/2
        return _fetch_full_meta(worker,a,middle)+_fetch_full_meta(worker,middle,b)
    return sorted((r for r in rows if a<=timestamp(r['FetchTime'])<b),key=lambda r:(r['FetchTime'],str(r['_id'])))


def _direct_snapshot(begin,end,skip,chunk_seconds,endpoint=META_ENDPOINT,worker=None):
    owned=worker is None
    if owned:
        from interactionfreepy import IFWorker
        worker=IFWorker(endpoint,timeout=180)
    try:
        latest=worker.Storage.latest('TFQKD_TDC',by='FetchTime',length=1,filter={'_id':1,'FetchTime':1})
        if isinstance(latest,list):latest=latest[0] if latest else None
        if not latest:raise ValueError('Storage collection is empty')
        start,stop=timestamp(begin),min(timestamp(end),timestamp(latest['FetchTime'])+timedelta(microseconds=1))
        yield ({'kind':'snapshot','latest':latest['FetchTime'],'actual_end':stop.isoformat()},b'')
        index=0;cursor=start
        while cursor<stop:
            upper=min(cursor+timedelta(seconds=chunk_seconds),stop)
            if index>=skip:
                rows=_fetch_full_meta(worker,cursor,upper)
                if len({str(r['_id']) for r in rows})!=len(rows):raise ValueError('Duplicate metadata IDs')
                payload=lzma.compress(msgpack.packb(rows,use_bin_type=True),preset=1)
                yield ({'kind':'chunk','index':index,'begin':cursor.isoformat(),'end':upper.isoformat(),
                        'records':len(rows),'bytes':len(payload),'compression':'xz',
                        'sha256':hashlib.sha256(payload).hexdigest()},payload)
            cursor,index=upper,index+1
        yield ({'kind':'done','chunks':index},b'')
    finally:
        if owned:worker.close()


def _direct_packets(begin,index,poll_seconds,settle_seconds,end,worker):
    cursor=timestamp(begin);stop=timestamp(end) if end else None
    def request(method,*args,**kwargs):
        try:return method(*args,**kwargs)
        except Exception as e:raise IOError('Storage request failed: '+str(e)) from e
    def fetch(a,b):
        return _fetch_full_meta(worker,a,b)
    while True:
        latest=request(worker.Storage.latest,'TFQKD_TDC',by='FetchTime',length=1,filter={'_id':1,'FetchTime':1})
        if isinstance(latest,list):latest=latest[0] if latest else None
        watermark=datetime.now(TZ)-timedelta(seconds=settle_seconds)
        available=timestamp(latest['FetchTime'])+timedelta(microseconds=1) if latest else cursor
        if stop is not None:
            available=stop if watermark>=stop else min(available,stop)
            watermark=min(watermark,stop)
        while cursor<available and cursor+timedelta(seconds=1)<=watermark:
            windows=min(30,int((watermark-cursor).total_seconds()),math.ceil((available-cursor).total_seconds()))
            batch=fetch(cursor,cursor+timedelta(seconds=windows))
            ids=[str(r['_id']) for r in batch]
            if len(ids)!=len(set(ids)):raise ValueError('Duplicate metadata IDs')
            for _ in range(windows):
                upper=cursor+timedelta(seconds=1)
                rows=[r for r in batch if cursor<=timestamp(r['FetchTime'])<upper]
                payload=lzma.compress(msgpack.packb(rows,use_bin_type=True),preset=1)
                yield ({'kind':'chunk','index':index,'begin':cursor.isoformat(),'end':upper.isoformat(),
                        'records':len(rows),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()},payload)
                cursor,index=upper,index+1
        if stop is not None and cursor>=stop:
            yield ({'kind':'done','windows':index,'end':stop.isoformat()},b'');return
        yield ({'kind':'idle','latest':latest['FetchTime'] if latest else None},b'')
        time.sleep(poll_seconds)


def _show_analysis(path):
    report_path=Path(str(Path(path).resolve())+'.analysis')/'summary.json'
    try:
        report=json.loads(report_path.read_text())
        previous=getattr(_show_analysis,'last',{})
        if previous.get(str(path))==report['updated_at']:return
        from LiveMetaAnalysis import show_summary
        show_summary(report)
        previous[str(path)]=report['updated_at'];_show_analysis.last=previous
    except (FileNotFoundError,json.JSONDecodeError,ImportError):
        pass


def _zip_state_path(path):
    return Path(str(path)+'.state.xz')


def resolve_live_range(path,begin=None,end=None,*,default_begin=None,default_end=None):
    """Explicit CLI bounds are checked; defaults never redefine an old ZIP."""
    state_path=_zip_state_path(path)
    if not state_path.exists():
        return (begin if begin is not None else default_begin,
                end if end is not None else default_end,None)
    saved=msgpack.unpackb(lzma.decompress(state_path.read_bytes()),raw=False)['manifest']
    for name,value,key in (('begin',begin,'begin'),('end',end,'requested_end')):
        stored=saved.get(key)
        if value is not None and (stored is None or timestamp(value)!=timestamp(stored)):
            raise ValueError(f'--{name}={value} 与已有 ZIP 的 {name}={stored} 不一致。'
                             '续传请省略起止参数；使用新的起止时间请通过 --output 指定新 ZIP。')
    return saved['begin'],saved.get('requested_end'),saved


def _checkpoint_zip(path, archive, manifest):
    """Keep a compressed copy of the ZIP directory for crash-safe recovery.

    Appending ZIP entries overwrites its old central directory. This sidecar
    lets a restart restore the last committed directory and redownload only
    the uncommitted tail. Metadata payloads are never duplicated in the state.
    """
    if len(archive.infolist()) != manifest['files']:
        raise ValueError('ZIP write interrupted before metadata checkpoint; resume to recover')
    directory_offset = archive.start_dir
    archive.close()
    import os
    with path.open('rb') as stream:
        os.fsync(stream.fileno())
        stream.seek(directory_offset)
        directory = stream.read()
    state = {'manifest': manifest, 'checkpoint_time': datetime.now(TZ).isoformat(),
             'directory_offset': directory_offset,
             'directory': directory}
    payload = lzma.compress(msgpack.packb(state, use_bin_type=True), preset=1)
    state_path = _zip_state_path(path)
    temporary = Path(str(state_path)+'.tmp')
    with temporary.open('wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(state_path)


def _restore_zip(path):
    state = msgpack.unpackb(lzma.decompress(_zip_state_path(path).read_bytes()), raw=False)
    if path.stat().st_size < state['directory_offset']:
        raise ValueError('ZIP is shorter than its committed metadata; cannot resume')
    # Validate the saved index before overwriting anything in the real ZIP.
    with _CheckpointZipReader(path,state) as snapshot:
        with zipfile.ZipFile(snapshot) as archive:
            if len(archive.infolist()) != state['manifest']['files']:
                raise ValueError('ZIP checkpoint directory does not match its saved file count')
    with path.open('r+b') as stream:
        stream.seek(state['directory_offset'])
        stream.write(state['directory'])
        stream.truncate()
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) != state['manifest']['files']:
            raise ValueError('ZIP recovery directory does not match its checkpoint')
    return state['manifest']


def repair_zip(zip_path):
    """Remove uncommitted tail entries using the saved checkpoint; no network.

    Also rolls back complete entries written after the last checkpoint. A
    subsequent download fetches those seconds again. Committed member payloads
    are untouched. Refuses to run while a downloader holds the archive lock.
    """
    import fcntl
    path = Path(zip_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f'ZIP not found: {path}')
    if not _zip_state_path(path).is_file():
        raise FileNotFoundError(f'Recovery state missing: {_zip_state_path(path)}; cannot safely repair')
    with Path(str(path)+'.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Stop the downloader before repairing this ZIP') from error
        before = path.stat().st_size
        manifest = _restore_zip(path)
        if manifest['state'] != 'complete':
            manifest['state'] = 'paused'
        manifest['last_repair_at'] = datetime.now(TZ).isoformat()
        _checkpoint_zip(path,zipfile.ZipFile(path,'a'),manifest)
        after = path.stat().st_size
        return {'archive':str(path.resolve()),'retained_records':manifest['records'],
                'retained_files':manifest['files'],
                'downloaded_through':manifest.get('downloaded_through',manifest['begin']),
                'bytes_before':before,'bytes_after':after,'removed_tail_bytes':max(0,before-after),
                'note':'Restored the last checkpoint; uncommitted tail seconds will be fetched again on resume'}


def _receive_follow(path, manifest, checkpoint_seconds=60,packets=None):
    if packets is None:raise ValueError('A local metadata packet iterator is required')
    archive = zipfile.ZipFile(path, 'a', compression=zipfile.ZIP_STORED, allowZip64=True)
    checkpoint_at = time.monotonic()
    try:
        for entry,payload in packets:
            if entry['kind'] == 'done':
                if (entry['windows'] != manifest['windows']
                        or entry['end'] != manifest.get('downloaded_through')
                        or entry['end'] != manifest.get('requested_end')):
                    raise ValueError('Completion packet does not match the requested interval')
                return
            if entry['kind'] == 'idle':
                manifest['latest_seen'] = entry['latest']
                if time.monotonic()-checkpoint_at >= checkpoint_seconds:
                    _checkpoint_zip(path, archive, manifest)
                    archive = zipfile.ZipFile(path, 'a', compression=zipfile.ZIP_STORED, allowZip64=True)
                    checkpoint_at = time.monotonic()
                    print('Waiting for new meta; saved through',
                          manifest.get('downloaded_through', manifest['begin']), flush=True)
                    _show_analysis(path)
                continue
            if entry['kind'] != 'chunk' or entry['index'] != manifest['windows']:
                raise ValueError('Unexpected streaming packet or chunk index')
            cursor = manifest.get('downloaded_through', manifest['begin'])
            if entry['begin'] != cursor:
                raise ValueError('Noncontiguous streaming chunk')
            if timestamp(entry['end'])-timestamp(entry['begin']) != timedelta(seconds=1):
                raise ValueError('Unexpected streaming chunk duration')
            if len(payload)!=entry['bytes'] or hashlib.sha256(payload).hexdigest() != entry['sha256']:
                raise ValueError('Streaming transfer checksum mismatch')
            if entry['records']:
                stamp = timestamp(entry['begin'])
                filename = stamp.strftime('%Y-%m-%d/%H/%Y%m%d_%H%M%S.msgpack.xz')
                try:
                    archive.getinfo(filename)
                except KeyError:
                    pass
                else:
                    raise ValueError('Duplicate ZIP member: '+filename)
                # Payload is already XZ-compressed by the fetcher; ZIP stores it
                # directly. CRC and source SHA256 protect each complete member.
                archive.writestr(filename, payload)
            manifest.update(state='following', downloaded_through=entry['end'],
                files=manifest['files']+bool(entry['records']), windows=manifest['windows']+1,
                records=manifest['records']+entry['records'],
                compressed_bytes=manifest['compressed_bytes']+entry['bytes'])
            if time.monotonic()-checkpoint_at >= checkpoint_seconds:
                _checkpoint_zip(path, archive, manifest)
                archive = zipfile.ZipFile(path, 'a', compression=zipfile.ZIP_STORED, allowZip64=True)
                checkpoint_at = time.monotonic()
                print(entry['end'], 'records:', manifest['records'], '(ZIP checkpoint)', flush=True)
                _show_analysis(path)
        raise IOError('Metadata packet stream ended before completion')
    finally:
        pending_error = sys.exc_info()[0]
        if packets is not None and hasattr(packets,'close'):packets.close()
        try:
            if len(archive.infolist()) != manifest['files']:
                # Ctrl+C can arrive between a finished ZIP write and the
                # atomic manifest update. Roll back to the last checkpoint;
                # those seconds will be fetched again instead of duplicated.
                archive.close()
                recovered = _restore_zip(path)
                manifest.clear()
                manifest.update(recovered)
                if pending_error is None:
                    raise ValueError('Uncommitted ZIP member; recovered the last checkpoint')
            else:
                _checkpoint_zip(path, archive, manifest)
        finally:
            archive.close()


def follow_download(root, begin=None, chunk_seconds=1, poll_seconds=5, settle_seconds=10,
                    retry_seconds=5, checkpoint_seconds=60, end=None,endpoint=META_ENDPOINT,on_ready=None):
    """Append one-second entries to one ZIP; reconnect and resume automatically.

    A new archive starts at now unless begin is specified. Existing archives
    retain their original begin. Pending partial windows are fetched on resume.
    ZIP is finalized on Ctrl+C and at checkpoints. After an abrupt termination,
    its sidecar restores the checkpoint; the uncommitted tail is redownloaded.
    The settling delay tolerates late inserts; inserts later than that delay
    require a separate historical recovery download. Analysis is a separate
    read-only process; raw archival never discards invalid seconds.
    With end set, downloads only [begin,end), waits until end has settled, and
    closes automatically. Begin/end must lie on whole-second boundaries.
    """
    import fcntl
    if chunk_seconds != 1:
        raise ValueError('Continuous ZIP mode uses one-second entries')
    for name, value in (('chunk_seconds', chunk_seconds), ('poll_seconds', poll_seconds),
                        ('retry_seconds', retry_seconds), ('checkpoint_seconds', checkpoint_seconds)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(name+' must be finite and positive')
    if not math.isfinite(settle_seconds) or settle_seconds < 0:
        raise ValueError('settle_seconds must be finite and nonnegative')
    stop = timestamp(end) if end else None
    if stop is not None and stop.microsecond:
        raise ValueError('ZIP end must be a whole second')
    root = Path(root).expanduser()
    if root.suffix.lower() != '.zip':
        raise ValueError('Continuous output must be a .zip file')
    root.parent.mkdir(parents=True, exist_ok=True)
    with Path(str(root)+'.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another downloader is already using this output directory') from error
        path = _zip_state_path(root)
        if path.exists():
            saved = msgpack.unpackb(lzma.decompress(path.read_bytes()), raw=False)['manifest']
            if begin is not None and timestamp(begin).isoformat() != saved['begin']:
                raise ValueError('Begin differs from the existing continuous download')
            if stop is not None and stop.isoformat() != saved.get('requested_end'):
                raise ValueError('End differs from the existing download; use a new ZIP for a different interval')
            manifest = _restore_zip(root)
        else:
            start = timestamp(begin) if begin else datetime.now(TZ).replace(microsecond=0)
            if start.microsecond:
                raise ValueError('ZIP begin must be a whole second')
            if stop is not None and stop <= start:
                raise ValueError('end must be later than begin')
            manifest = {'mode': 'follow', 'state': 'following', 'collection': 'TFQKD_TDC',
                'begin': start.isoformat(), 'requested_end': stop.isoformat() if stop else None,
                'chunk_seconds': chunk_seconds,
                'windows': 0, 'files': 0, 'records': 0, 'compressed_bytes': 0,
                'format': 'One ZIP containing one XZ/MessagePack list per occupied second; original fields preserved'}
            with zipfile.ZipFile(root, 'x'):
                pass
        manifest.update(poll_seconds=poll_seconds, settle_seconds=settle_seconds, state='following')
        _checkpoint_zip(root, zipfile.ZipFile(root, 'a'), manifest)
        if on_ready is not None:on_ready()
        print('Continuous download:', root.resolve(), '\nBegin:', manifest['begin'],
              '\nEnd (exclusive):', manifest.get('requested_end') or 'not limited',
              '\nCtrl+C stops; rerun the same command to resume.', flush=True)
        try:
            while True:
                cursor = manifest.get('downloaded_through', manifest['begin'])
                if manifest.get('requested_end') and timestamp(cursor) >= timestamp(manifest['requested_end']):
                    manifest['state'] = 'complete'
                    _checkpoint_zip(root, zipfile.ZipFile(root,'a'), manifest)
                    return manifest
                try:
                    packets=_direct_follow(cursor,manifest['windows'],poll_seconds,settle_seconds,
                                           manifest.get('requested_end'),endpoint)
                    _receive_follow(root, manifest, checkpoint_seconds=checkpoint_seconds,packets=packets)
                    manifest['state'] = 'complete'
                    _checkpoint_zip(root, zipfile.ZipFile(root,'a'), manifest)
                    print('Completed requested interval. Saved', manifest['records'], 'records.',flush=True)
                    return manifest
                except OSError as error:
                    import errno
                    if error.errno in (errno.ENOSPC, errno.EACCES, errno.EROFS):
                        raise
                    manifest['state'] = 'retrying'
                    print(f'{error}; reconnecting in {retry_seconds}s from the last saved window.', flush=True)
                    time.sleep(retry_seconds)
        except KeyboardInterrupt:
            manifest['state'] = 'paused'
            manifest['paused_at'] = datetime.now(TZ).isoformat()
            _checkpoint_zip(root, zipfile.ZipFile(root, 'a'), manifest)
            print('Stopped. Saved', manifest['records'], 'records; through',
                  manifest.get('downloaded_through', manifest['begin']),
                  '(exclusive; pending tail will be fetched on resume).', flush=True)
        return manifest


def _quality_root(path):
    path = Path(path)
    return path.with_name(path.stem+'_quality') if path.suffix.lower()=='.zip' else path


class _CheckpointZipReader(io.RawIOBase):
    """Read-only view: immutable committed data + saved central directory.

    The writer only overwrites bytes at/after this checkpoint's directory
    offset. Reading that suffix from the sidecar avoids touching the writer's
    in-progress directory. Metadata payloads are read directly, never copied.
    """
    def __init__(self, path, state):
        super().__init__()
        self._stream = None
        self._stream = Path(path).open('rb')
        self._offset = state['directory_offset']
        self._directory = state['directory']
        self._size = self._offset+len(self._directory)
        self._position = 0
        if self._stream.seek(0,2) < self._offset:
            self.close()
            raise ValueError('ZIP is shorter than the checkpoint data')

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        self._checkClosed()
        return self._position

    def seek(self, offset, whence=0):
        self._checkClosed()
        if whence not in (0, 1, 2):
            raise ValueError('Invalid seek origin')
        target = offset+(self._position if whence==1 else self._size if whence==2 else 0)
        if target < 0:
            raise ValueError('Negative seek position')
        self._position = target
        return target

    def read(self, size=-1):
        self._checkClosed()
        remaining = max(0,self._size-self._position)
        count = remaining if size is None or size < 0 else min(size,remaining)
        pieces = []
        if self._position < self._offset and count:
            prefix_size = min(count,self._offset-self._position)
            self._stream.seek(self._position)
            prefix = self._stream.read(prefix_size)
            if len(prefix) != prefix_size:
                raise IOError('Committed ZIP data was truncated during reading')
            pieces.append(prefix)
            self._position += prefix_size
            count -= prefix_size
        if count:
            start = self._position-self._offset
            pieces.append(self._directory[start:start+count])
            self._position += count
        return b''.join(pieces)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def close(self):
        if not self.closed and self._stream is not None:
            self._stream.close()
        super().close()


def get_download_status(zip_path):
    """Read the latest committed checkpoint without locking or changing the ZIP."""
    path = Path(zip_path).expanduser()
    state = msgpack.unpackb(lzma.decompress(_zip_state_path(path).read_bytes()),raw=False)
    manifest = state['manifest']
    return {key:manifest.get(key) for key in ('state','begin','requested_end','downloaded_through','records','files')} | {
        'checkpoint_time':state.get('checkpoint_time'), 'archive':str(path.resolve())}


def iter_metas(root, selection='all', *, begin=None, end=None):
    """Yield a fixed snapshot of full meta; ZIPs can be read while downloading.

    Uses the last checkpoint when a sidecar exists. A new call sees the newest
    checkpoint; an existing iterator never picks up later entries. Optional
    begin/end restrict FetchTime to [begin, end). selection: all/valid/rejected.
    """
    if selection not in ('all', 'valid', 'rejected'):
        raise ValueError('Invalid selection')
    root = Path(root).expanduser()
    start = timestamp(begin) if begin else None
    stop = timestamp(end) if end else None
    if start is not None and stop is not None and stop <= start:
        raise ValueError('end must be after begin')
    def in_range(record):
        stamp = timestamp(record['FetchTime'])
        return (start is None or stamp >= start) and (stop is None or stamp < stop)
    is_zip = root.suffix.lower()=='.zip'
    checkpoint = None
    if is_zip:
        # A finalized ZIP is self-contained and can be shared without its
        # recovery sidecar. The sidecar is needed only to resume writing.
        if _zip_state_path(root).exists():
            checkpoint = msgpack.unpackb(lzma.decompress(_zip_state_path(root).read_bytes()),raw=False)
        manifest = checkpoint['manifest'] if checkpoint else {'state':'complete','files':None,'records':None}
    else:
        manifest = json.loads((root/'manifest.json').read_text())
    if manifest['state'] != 'complete' and manifest.get('mode') != 'follow':
        raise ValueError('Download incomplete')
    chosen = None
    if selection != 'all':
        reports = _quality_root(root)
        summary = json.loads((reports/'quality_summary.json').read_text())
        if manifest.get('records') is not None and summary['records'] != manifest['records']:
            raise ValueError('Quality selection is stale; stop downloading and rerun filtering')
        with (reports/'quality.jsonl').open() as stream:
            chosen = {r['id'] for r in map(json.loads, stream) if r['valid'] == (selection == 'valid')}
    seen = set()
    if is_zip:
        snapshot = _CheckpointZipReader(root,checkpoint) if checkpoint else None
        try:
            archive = zipfile.ZipFile(snapshot or root)
        except BaseException as error:
            if snapshot is not None:
                snapshot.close()
            if isinstance(error,zipfile.BadZipFile):
                raise ValueError('No usable ZIP checkpoint; stop the downloader or rerun to recover') from error
            raise
        try:
            with archive:
                if manifest['files'] is not None and len(archive.infolist()) != manifest['files']:
                    raise ValueError('ZIP and checkpoint file counts differ')
                for entry in archive.infolist():
                    # Live ZIP member names specify the second in UTC+08:00.
                    # Skip unrelated entries before reading/decompressing them.
                    try:
                        stamp = datetime.strptime(Path(entry.filename).name.split('.')[0],'%Y%m%d_%H%M%S').replace(tzinfo=TZ)
                    except ValueError:
                        stamp = None
                    if stamp is not None and ((start is not None and stamp+timedelta(seconds=1)<=start)
                                              or (stop is not None and stamp>=stop)):
                        continue
                    payload = archive.read(entry)  # ZIP checks the stored CRC here.
                    for record in msgpack.unpackb(lzma.decompress(payload),raw=False,strict_map_key=False):
                        identity = str(record['_id'])
                        if identity in seen:
                            raise ValueError('Duplicate meta ID: '+identity)
                        seen.add(identity)
                        if (chosen is None or identity in chosen) and in_range(record):
                            yield record
        finally:
            if snapshot is not None:
                snapshot.close()
        return
    for c in manifest['chunks']:
        if ((start is not None and 'end' in c and timestamp(c['end']) <= start)
                or (stop is not None and 'begin' in c and timestamp(c['begin']) >= stop)):
            continue
        payload = (root/c['file']).read_bytes()
        if hashlib.sha256(payload).hexdigest() != c['sha256']:
            raise ValueError('Corrupt chunk: '+c['file'])
        unpacked = lzma.decompress(payload) if c['file'].endswith('.xz') else gzip.decompress(payload)
        for meta in msgpack.unpackb(unpacked, raw=False, strict_map_key=False):
            identity = str(meta['_id'])
            if identity in seen:
                raise ValueError('Duplicate meta ID: '+identity)
            seen.add(identity)
            if (chosen is None or identity in chosen) and in_range(meta):
                yield meta


def filter_zero_runs(root, zero_run_ms=5):
    """Reject entire records touched by >= N consecutive zero 1-ms bins.

    Also checks runs crossing adjacent records. Missing/invalid monitor arrays
    are rejected explicitly. No other intensity or QBER selection is applied.
    """
    if not isinstance(zero_run_ms, int) or zero_run_ms < 2:
        raise ValueError('zero_run_ms must be an integer >= 2')
    source = Path(root)
    root = _quality_root(source)
    root.mkdir(parents=True,exist_ok=True)
    rows, states = [], {ch: {'length': 0, 'records': set()} for ch in ('4','5')}
    previous_slot = None
    for meta in iter_metas(source):
        slot = math.floor(timestamp(meta['FetchTime']).timestamp())
        if previous_slot is not None and slot != previous_slot+1:
            for state in states.values():
                state.update(length=0, records=set())
        row = {'id': str(meta['_id']), 'FetchTime': meta['FetchTime'], 'valid': True, 'reasons': [],
               'counts': {}, 'zero_bins': {}, 'max_zero_run_ms': {}}
        rows.append(row)
        index = len(rows)-1
        monitor = meta.get('Data',{}).get('ChannelMonitor',{})
        for ch, state in states.items():
            values = monitor.get('CountSections',{}).get(ch)
            if (monitor.get('Configuration',{}).get('Frequency') != 1000
                    or not isinstance(values,(list,tuple)) or len(values) != 1000
                    or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v < 0 for v in values)):
                row['reasons'].append('missing_or_invalid_1ms_counts_ch'+ch)
                state.update(length=0, records=set())
                continue
            row['counts'][ch] = sum(values)
            row['zero_bins'][ch] = sum(v == 0 for v in values)
            within, longest = 0, 0
            for v in values:
                if v == 0:
                    within += 1
                    longest = max(longest, within)
                    state['length'] += 1
                    state['records'].add(index)
                    if state['length'] >= zero_run_ms:
                        reason = 'consecutive_zero_ms_ch'+ch
                        touched_records = state['records'] if state['length'] == zero_run_ms else (index,)
                        for touched in touched_records:
                            if reason not in rows[touched]['reasons']:
                                rows[touched]['reasons'].append(reason)
                else:
                    within = 0
                    state.update(length=0, records=set())
            row['max_zero_run_ms'][ch] = longest
        previous_slot = slot
    for row in rows:
        row['valid'] = not row['reasons']
    with (root/'quality.jsonl').open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row)+'\n')
    for filename, keep in (('quality.csv', None), ('valid_seconds.csv', True), ('rejected_seconds.csv', False)):
        with (root/filename).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream)
            writer.writerow(['FetchTime','id','valid','ch4_counts','ch5_counts','ch4_zero_ms','ch5_zero_ms',
                             'ch4_max_zero_run_within_second_ms','ch5_max_zero_run_within_second_ms','reasons'])
            for r in rows:
                if keep is not None and r['valid'] != keep:
                    continue
                writer.writerow([r['FetchTime'],r['id'],r['valid'],r['counts'].get('4'),r['counts'].get('5'),
                    r['zero_bins'].get('4'),r['zero_bins'].get('5'),r['max_zero_run_ms'].get('4'),
                    r['max_zero_run_ms'].get('5'),';'.join(r['reasons'])])
    intervals=[]
    for row in rows:
        same_group = (intervals and intervals[-1]['valid'] == row['valid']
            and .5 < (timestamp(row['FetchTime'])-timestamp(intervals[-1]['last_FetchTime'])).total_seconds() < 1.5)
        if same_group:
            intervals[-1]['last_FetchTime'] = row['FetchTime']
            intervals[-1]['records'] += 1
        else:
            intervals.append({'valid':row['valid'],'first_FetchTime':row['FetchTime'],
                              'last_FetchTime':row['FetchTime'],'records':1})
    save_json(root/'quality_intervals.json', intervals)
    summary={'records':len(rows),'valid':sum(r['valid'] for r in rows),
        'rejected':sum(not r['valid'] for r in rows),'zero_run_ms':zero_run_ms,'channels':[4,5],
        'first_FetchTime':rows[0]['FetchTime'] if rows else None,
        'last_FetchTime':rows[-1]['FetchTime'] if rows else None,
        'gaps': [{'after':a['FetchTime'],'before':b['FetchTime'],
                  'fetch_time_separation_seconds':(timestamp(b['FetchTime'])-timestamp(a['FetchTime'])).total_seconds()}
                 for a,b in zip(rows,rows[1:])
                 if not .5 < (timestamp(b['FetchTime'])-timestamp(a['FetchTime'])).total_seconds() < 1.5],
        'note':'Whole-second rejection only; cross-second zero runs included; originals preserved'}
    save_json(root/'quality_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--begin',help='Inclusive begin; new ZIP uses DATA_BEGIN, existing ZIP keeps its saved begin')
    parser.add_argument('--end',help='Exclusive end; new ZIP uses DATA_END, existing ZIP keeps its saved end')
    parser.add_argument('--output',type=Path,help='Live: ZIP path; historical snapshot: directory')
    parser.add_argument('--chunk-seconds',type=int,help='Live must be 1 s; historical snapshot defaults to 60 s')
    parser.add_argument('--poll-seconds',type=float,default=5)
    parser.add_argument('--settle-seconds',type=float,default=10)
    parser.add_argument('--checkpoint-seconds',type=float,default=60,
                        help='Finalize ZIP directory and save crash-recovery state (default 60 s)')
    parser.add_argument('--zero-run-ms',type=int,default=5)
    parser.add_argument('--download-only',action='store_true',help='Disable the analysis companion')
    parser.add_argument('--endpoint',default=META_ENDPOINT,help='Direct Storage IFWorker endpoint')
    parser.add_argument('--analysis-interval',type=float,default=30,help='Local analysis/report update interval')
    local_mode=parser.add_mutually_exclusive_group()
    local_mode.add_argument('--filter-only',action='store_true',help='Filter existing local chunks without downloading')
    local_mode.add_argument('--repair-only',action='store_true',help='Remove uncommitted ZIP tail using checkpoint; no downloading')
    local_mode.add_argument('--analyze-only',action='store_true',help='Continuously analyze an existing ZIP without downloading')
    args=parser.parse_args(argv)
    if args.output is None:
        args.output=OUTPUT_ZIP
    if args.chunk_seconds is not None and args.chunk_seconds <= 0:
        parser.error('--chunk-seconds must be positive')
    if args.analysis_interval<=0:parser.error('--analysis-interval must be positive')
    if not (args.analyze_only or args.repair_only or args.filter_only):
        if args.output.suffix.lower()=='.zip':
            try:
                args.begin,args.end,saved=resolve_live_range(args.output,args.begin,args.end,
                                                          default_begin=DATA_BEGIN,default_end=DATA_END)
            except ValueError as e:parser.error(str(e))
            if saved:
                print('续传已有 ZIP：沿用归档起止时间。\nBegin:',args.begin,'\nEnd:',args.end,
                      '\nSaved through:',saved.get('downloaded_through'),flush=True)
                if ((DATA_BEGIN is not None and timestamp(DATA_BEGIN)!=timestamp(args.begin))
                        or (DATA_END is not None and (args.end is None or timestamp(DATA_END)!=timestamp(args.end)))):
                    print('注意：代码中的 DATA_BEGIN/DATA_END 默认值不覆盖旧 ZIP；'
                          '如需按新时间开始，请用 --output 指定新 ZIP。',flush=True)
        else:
            args.begin=DATA_BEGIN if args.begin is None else args.begin
            args.end=DATA_END if args.end is None else args.end
    if args.analyze_only:
        subprocess.run([sys.executable,str(Path(__file__).with_name('LiveMetaAnalysis.py')),'--archive',str(args.output),
                        '--interval',str(args.analysis_interval)],check=True)
    elif args.repair_only:
        print(json.dumps(repair_zip(args.output),indent=2,ensure_ascii=False))
    elif args.filter_only:
        import fcntl
        lock_path=Path(str(args.output)+'.lock') if args.output.suffix.lower()=='.zip' else args.output/'.download.lock'
        with lock_path.open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.error('Stop the downloader before filtering this directory')
            filter_zero_runs(args.output,args.zero_run_ms)
    elif args.end and args.output.suffix.lower()!='.zip':
        if not args.begin:
            parser.error('--begin is required when --end is specified')
        download(args.output,args.begin,args.end,chunk_seconds=args.chunk_seconds or 60,endpoint=args.endpoint)
        if not args.download_only:
            filter_zero_runs(args.output,args.zero_run_ms)
    else:
        analysis=None;analysis_log=None
        def start_analysis():
            nonlocal analysis,analysis_log
            if args.download_only:return
            out=Path(str(args.output.resolve())+'.analysis');out.mkdir(parents=True,exist_ok=True)
            analysis_log=(out/'worker.log').open('a')
            analysis=subprocess.Popen([sys.executable,'-u',str(Path(__file__).with_name('LiveMetaAnalysis.py')),
                '--archive',str(args.output.resolve()),'--interval',str(args.analysis_interval),
                '--parent-pid',str(os.getpid())],
                stdin=subprocess.DEVNULL,stdout=analysis_log,stderr=subprocess.STDOUT)
            print('Local live report:',out/'index.html','\nAnalysis log:',out/'worker.log',flush=True)
        try:
            follow_download(args.output,args.begin,args.chunk_seconds or 1,args.poll_seconds,args.settle_seconds,
                            checkpoint_seconds=args.checkpoint_seconds,end=args.end,endpoint=args.endpoint,
                            on_ready=start_analysis)
        finally:
            if analysis is not None:_stop_process(analysis)
            if analysis_log is not None:analysis_log.close()


if __name__=='__main__':main()
