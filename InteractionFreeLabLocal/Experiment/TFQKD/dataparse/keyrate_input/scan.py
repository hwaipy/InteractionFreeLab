"""Scan sifting thresholds using local per-second QKDIntermediate files only."""
import csv
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import numpy as np

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'pytimetag'))
from InteractionFreeLabLocal.Experiment.TFQKD.services.tdc.TFQKDQBERAnalyser import QKDIntermediate
TZ = ZoneInfo('Asia/Shanghai')
BASIS = [3, 0, 1, 2]
LABELS = ['Z信号态', 'X真空态', 'X诱骗态1', 'X诱骗态2']


def parse_time(value):
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def numbers(value, integer=False, allow_positive_infinity=False):
    """Comma list or inclusive start:stop:step, without float arange drift."""
    from decimal import Decimal
    if not isinstance(value, str):
        values = [value] if np.isscalar(value) else value
        value = ','.join(str(v) for v in values)
    result = []
    for part in value.split(','):
        if ':' in part:
            start, stop, step = map(Decimal, part.split(':'))
            if step <= 0 or stop < start:
                raise ValueError('Ranges require stop >= start and step > 0')
            count = int((stop - start) // step) + 1
            if count > 10000:
                raise ValueError('Too many scan values')
            result.extend(float(start + i * step) for i in range(count))
        else:
            result.append(float(part))
    if not result or not all(math.isfinite(v) or (allow_positive_infinity and v == math.inf) for v in result):
        raise ValueError('Thresholds must be finite')
    if integer:
        if any(v != int(v) for v in result):
            raise ValueError('Phase bins must be integers')
        return list(dict.fromkeys(int(v) for v in result))
    return list(dict.fromkeys(result))


def select_frames(result, minimum, maximum, ratio):
    a, b = result.syncCountsAlice, result.syncCountsBob
    # Strict inequalities match the intended condition in DataBlockParseResult.statistics.
    selected = (a > minimum) & (b > minimum) & (a < maximum) & (b < maximum)
    if math.isinf(ratio):
        return selected
    return selected & (a < b * ratio) & (b < a * ratio)


def new_total():
    return {'pulses': np.zeros((4, 4), dtype=np.int64),
            'detections': np.zeros((4, 4), dtype=np.int64),
            'errors': np.zeros((4, 2), dtype=np.int64), 'frames': 0, 'seconds': 0}


def scaled_count(value, factor):
    return int((Decimal(int(value)) * Decimal(str(factor))).to_integral_value(rounding=ROUND_HALF_UP))


def export_rows(total, phase_bin, intensities, sent_pulses=None, scale_factor=1):
    pulses = total['pulses']
    n = int(pulses.sum())
    if not n:
        raise ValueError('No signal pulses survive atmosphere filtering')
    ratios = pulses / n
    rows = [['', 'A-C', 'B-C']]
    for label, basis in [('X基下真空光源发射概率', 0), ('X基下弱源发射概率', 1),
                         ('X基下强光发射概率', 2), ('Z基发射概率', 3)]:
        rows.append([label, float(ratios[basis].sum()), float(ratios[:, basis].sum())])
    for label, values in zip(['X基弱源强度', 'X基强光强度', 'Z基光源强度'], intensities):
        rows.append([label, *values])
    rows += [[], ['发送总脉冲数', scaled_count(n if sent_pulses is None else sent_pulses, scale_factor)], [], ['实际发送组合比例', *LABELS]]
    rows += [[label, *[float(ratios[a, b]) for b in BASIS]] for label, a in zip(LABELS, BASIS)]
    # Preserve the original spelling in convert.py.
    rows += [[], ['实际引起有效相应个数', *LABELS]]
    rows += [[label, *[scaled_count(total['detections'][a, b], scale_factor) for b in BASIS]] for label, a in zip(LABELS, BASIS)]
    rows += [[], ['满足筛选条件', '总计数', '错误计数', '错误率']]
    for label, basis in [('X基1', 1), ('X基2', 2)]:
        correct, wrong = map(int, total['errors'][basis])
        count = correct + wrong
        rows.append([label, scaled_count(count, scale_factor), scaled_count(wrong, scale_factor), wrong / count if count else 'nan'])
    # Bin k includes [0, (k+1)*pi/128), because the analyser accumulates floor(bin):.
    rows += [[], ['X基筛选比例', f'{(phase_bin + 1) / 64 * 100}%']]
    return rows


def run(settings):
    if any(len(pair) != 2 or any(not math.isfinite(v) or v < 0 for v in pair)
           for pair in (settings.mu_x, settings.mu_y, settings.mu_z)):
        raise ValueError('Each intensity needs two finite nonnegative values')
    begin, end = parse_time(settings.begin), parse_time(settings.end)
    if end <= begin:
        raise ValueError('end must be after begin; interval is [begin, end)')
    intervals = sorted((parse_time(a), parse_time(b)) for a, b in
                       getattr(settings, 'intervals', [(settings.begin, settings.end)]))
    if not intervals or any(b <= a for a, b in intervals):
        raise ValueError('Every interval must have end after begin')
    if any(b > c for (_, b), (c, _) in zip(intervals, intervals[1:])):
        raise ValueError('Dataset intervals must not overlap')
    begin, end = intervals[0][0], intervals[-1][1]
    def in_intervals(stamp):
        return any(a <= stamp < b for a, b in intervals)
    phases = numbers(settings.phase_bins, integer=True)
    minima, maxima = numbers(settings.intensity_min), numbers(settings.intensity_max)
    ratios = numbers(settings.intensity_ratio, allow_positive_infinity=True)
    if any(k < 0 or k > 63 for k in phases) or min(minima) < 0 or min(maxima) <= max(minima) or min(ratios) <= 1:
        raise ValueError('Require phase bins 0..63, minimum >= 0, maximum > every minimum, ratio > 1')
    grid = list(itertools.product(phases, minima, maxima, ratios))
    pulse_modes = getattr(settings, 'sent_pulse_modes', ['filtered'])
    if isinstance(pulse_modes, str):
        pulse_modes = [pulse_modes]
    pulse_modes = list(dict.fromkeys(pulse_modes))
    if not pulse_modes or any(mode not in ('total', 'filtered') for mode in pulse_modes):
        raise ValueError('sent_pulse_modes must select total and/or filtered')
    scales = getattr(settings, 'scales', [None])
    if scales is None or np.isscalar(scales):
        scales = [scales]
    scales = list(dict.fromkeys(None if v is None else float(v) for v in scales))
    if not scales or any(v is not None and (not math.isfinite(v) or v <= 0) for v in scales):
        raise ValueError('scales must contain None or finite positive target pulse counts')
    if len(grid) * len(pulse_modes) * len(scales) > 10000:
        raise ValueError('At most 10000 threshold combinations supported')
    root = Path(settings.input)
    if not root.is_dir():
        raise ValueError('Intermediate directory does not exist; run preprocess.py first')
    files = {}
    for path in sorted(root.rglob('*.npz')):
        try:
            dt = datetime.strptime(path.stem, '%Y%m%dT%H%M%S%f').replace(tzinfo=TZ)
        except ValueError as exc:
            raise ValueError(f'Unexpected intermediate filename: {path.name}') from exc
        if in_intervals(dt):
            if dt in files:
                raise ValueError(f'Duplicate exact intermediate timestamp {dt.isoformat()}')
            files[dt] = (path, dt)
    missing = []
    observed_seconds = {stamp.replace(microsecond=0) for stamp in files}
    for interval_begin, interval_end in intervals:
        dt = interval_begin.replace(microsecond=0)
        while dt < interval_end:
            if dt not in observed_seconds:
                missing.append(dt.isoformat())
            dt += timedelta(seconds=1)
    # Natural timestamp gaps do not prove data loss. Use an explicit dataset manifest for completeness.
    expected_manifest = getattr(settings, 'dataset_manifest', None)
    expected_manifests = list(getattr(settings, 'dataset_manifests', []))
    if expected_manifest:
        expected_manifests.append(expected_manifest)
    for expected_manifest in expected_manifests:
        expected = json.loads(Path(expected_manifest).read_text())
        if expected.get('state') != 'completed' and not settings.skip_missing:
            raise ValueError('Dataset preprocessing is incomplete or has failures')
        expected_files = {entry['file'] for entry in expected['processed']
                          if in_intervals(parse_time(entry['FetchTime']))}
        actual_files = {str(path.relative_to(root)) for path, _ in files.values()}
        if not expected_files.issubset(actual_files):
            raise ValueError('Intermediate files listed in dataset manifest are missing')
    if not files:
        raise ValueError('No intermediate files in requested interval')
    output = Path(settings.output)
    output.mkdir(parents=True, exist_ok=False)
    totals = {p: new_total() for p in grid}
    processed = []
    compatibility = None
    fixed_metadata = None
    all_signal_pulses = 0
    try:
        for path, expected_time in files.values():
            payload = path.read_bytes()
            result = QKDIntermediate.unpack(payload)
            all_signal_pulses += int(result.pulseCounts.sum(dtype=np.int64))
            fetch_time = result.metadata['FetchTime']
            if abs((parse_time(fetch_time) - expected_time).total_seconds()) > .001:
                raise ValueError(f'Intermediate time does not match filename: {path.name}')
            current_key = result.compatibilityKey()
            if compatibility is None:
                compatibility = current_key
                fixed_metadata = json.loads(current_key)
            elif current_key != compatibility:
                raise ValueError(f'Incompatible gates, frames, algorithm or timing corrections: {path.name}')
            prepared = {}
            for minimum, maximum, ratio in itertools.product(minima, maxima, ratios):
                selected = select_frames(result, minimum, maximum, ratio)
                prepared[minimum, maximum, ratio] = (selected,
                    result.pulseCounts[:, :, selected].sum(axis=2, dtype=np.int64),
                    result.detectionStatistics[:, :, selected].sum(axis=2, dtype=np.int64))
            for params, total in totals.items():
                phase, minimum, maximum, ratio = params
                selected, pulses, detections = prepared[minimum, maximum, ratio]
                total['pulses'] += pulses
                total['detections'] += detections
                total['errors'] += result.phaseErrorStatistics[:, selected, phase, :].sum(axis=1, dtype=np.int64)
                total['frames'] += int(selected.sum())
                total['seconds'] += int(np.any(selected))
            processed.append({'FetchTime': fetch_time, 'file': str(path.relative_to(root)),
                              'sha256': hashlib.sha256(payload).hexdigest()})
            print(f'{fetch_time}: scanned', flush=True)
    except Exception as exc:
        (output / 'failure.json').write_text(json.dumps({'error': str(exc), 'processed': processed}, indent=2))
        raise
    summaries = []
    intensities = [settings.mu_x, settings.mu_y, settings.mu_z]
    for (params, total), pulse_mode, scale in itertools.product(totals.items(), pulse_modes, scales):
        phase, minimum, maximum, ratio = params
        selected_signal_pulses = int(total['pulses'].sum())
        sent_pulses = all_signal_pulses if pulse_mode == 'total' else selected_signal_pulses
        scale_factor = 1 if scale is None else (scale / selected_signal_pulses if selected_signal_pulses else None)
        entry = dict(zip(('phase_bin', 'intensity_min', 'intensity_max', 'intensity_ratio'), params))
        if math.isinf(ratio):
            entry['intensity_ratio'] = 'inf'
        entry.update(phase_upper_rad=(phase + 1) * math.pi / 128,
                     selected_frames=total['frames'], seconds_with_selected_frames=total['seconds'],
                     signal_pulses=selected_signal_pulses,
                     sent_pulse_mode=pulse_mode, sent_pulses=sent_pulses,
                     all_signal_pulses=all_signal_pulses)
        entry.update(scale=scale, scale_factor=scale_factor,
                     output_selected_signal_pulses=scaled_count(selected_signal_pulses, scale_factor) if scale_factor is not None else None,
                     output_sent_pulses=scaled_count(sent_pulses, scale_factor) if scale_factor is not None else None)
        if total['pulses'].sum():
            filename = (f'result_phase-{phase}_min-{minimum!r}_max-{maximum!r}'
                        f'_ratio-{ratio!r}_pulses-{pulse_mode}_scale-{scale!r}.txt')
            with (output / filename).open('w', encoding='utf-8', newline='') as f:
                csv.writer(f, delimiter='\t', lineterminator='\n').writerows(export_rows(total, phase, intensities, sent_pulses, scale_factor))
            entry['file'] = filename
        else:
            entry.update(file=None, status='no_selected_signal_pulses')
        summaries.append(entry)
    arguments = dict(vars(settings))
    arguments.update(phase_bins=phases, intensity_min=minima, intensity_max=maxima,
                     scales=scales,
                     intensity_ratio=['inf' if math.isinf(v) else v for v in ratios], sent_pulse_modes=pulse_modes,
                     mu_x=[float(v) for v in settings.mu_x],
                     mu_y=[float(v) for v in settings.mu_y],
                     mu_z=[float(v) for v in settings.mu_z])
    manifest = {'begin': begin.isoformat(), 'end_exclusive': end.isoformat(), 'arguments': arguments,
                'intervals': [[a.isoformat(), b.isoformat()] for a, b in intervals],
                'processed': processed, 'empty_timestamp_seconds': missing, 'results': summaries,
                'fixed_processing': fixed_metadata,
                'frequency_note': 'Uses existing analyser frequency=0 assumption',
                'pulse_note': 'sent_pulse_mode changes only the sent-pulse row; probabilities and detection/error counts use atmosphere-selected frames. total sums all frames in successfully loaded input records; cyclic RN counted at pulse centers'}
    manifest['scale_note'] = 'Scale factor is target / atmosphere-selected pulse count, independent of sent_pulse_mode. Output pulse and detection/error counts are rounded to integers (half up); probabilities and error rates stay unchanged.'
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return output


def dataset_settings(dataset='baseline_74dB_gen1_on_gen2_off'):
    # 后续筛选：只读本地初级文件，不联网，也不重新处理 DataBlock。
    base = Path(__file__).resolve().parent
    batch = base / 'results' / '20261026'
    dataset_manifest = batch / 'datasets' / dataset / 'manifest.json'
    interval = json.loads(dataset_manifest.read_text(encoding='utf-8'))
    return SimpleNamespace(
        begin=interval['begin'],
        end=interval['end'],
        input=str(batch / 'intermediate'),
        dataset_manifest=str(dataset_manifest),
        output=str(base / 'results' / ('scan_' + dataset + '_' + datetime.now(TZ).strftime('%Y%m%d_%H%M%S_%f'))),
        phase_bins=range(1, 16),
        sent_pulse_modes=['total', 'filtered'],  # 可单选：['total'] 全部，['filtered'] 筛选后；两者同时选则分别输出。
        scales=[None, 1e12],  # 独立遍历：None 不缩放；数值 / 筛选后脉冲数 为缩放系数。
        intensity_min=[5],
        intensity_max=[1e300],
        intensity_ratio=[1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, float('inf')],
        mu_x=[0.0303853, 0.0303853],
        mu_y=[0.482834, 0.482834],
        mu_z=[0.494035, 0.494035],
        skip_missing=False,  # 有失败记录的采集段默认拒绝扫描；设 True 才允许只用成功记录。
    )

def main():
    print(run(dataset_settings()))


if __name__ == '__main__':
    main()
