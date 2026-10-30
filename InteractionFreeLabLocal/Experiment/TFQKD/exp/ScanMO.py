"""Scan nearby MO settings and fit the MO giving zero delay drift.

Examples:
    python ScanMO.py Alice
    python ScanMO.py Bob --offsets -20 -10 0 10 20 --interval 30

The original MO is restored after scanning; the fitted MO is only reported.
Stop other automatic MO/delay adjustments before starting a scan.
"""

import argparse
from datetime import datetime
import math
import time

import numpy as np


def fetchDelay(storage, target, collection='TFQKD_TDC'):
    """Return (record ID, data timestamp in seconds, delay in ns)."""
    analyser = f'TFQKDSync{target}'
    record = storage.latest(
        collection=collection,
        filter={'_id': 1, 'FetchTime': 1, f'Data.{analyser}.Delay': 1},
    )
    if not record:
        raise RuntimeError('No delay record is available.')
    delay = record.get('Data', {}).get(analyser, {}).get('Delay')
    if delay is None or not math.isfinite(float(delay)):
        raise RuntimeError(f'{target} delay is invalid: {delay}')
    timestamp = record['FetchTime']
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp).timestamp()
    elif isinstance(timestamp, datetime):
        timestamp = timestamp.timestamp()
    return str(record['_id']), float(timestamp), float(delay) / 1000


def fetchNewDelay(storage, target, previous, collection, timeout=10):
    """Wait for a different record with a strictly newer data timestamp."""
    deadline = time.monotonic() + timeout
    while True:
        sample = fetchDelay(storage, target, collection)
        if sample[0] != previous[0] and sample[1] > previous[1]:
            return sample
        if time.monotonic() >= deadline:
            raise RuntimeError('Delay data did not update within the timeout.')
        time.sleep(0.2)


def scanMO(target='Alice', offsets=(-20, -10, 0, 10, 20), interval=30,
           settle=2, collection='TFQKD_TDC'):
    """Measure drift in ns/s at each MO, then fit drift = a*(MO-current) + b."""
    if target not in ('Alice', 'Bob'):
        raise ValueError('target must be Alice or Bob.')
    if interval <= 0 or settle < 0:
        raise ValueError('interval must be positive and settle must be nonnegative.')
    offsets = list(offsets)
    if len(offsets) < 2 or len(set(offsets)) != len(offsets):
        raise ValueError('Provide at least two distinct integer MO offsets.')
    if any(int(offset) != offset for offset in offsets):
        raise ValueError('MO offsets must be integers.')

    # Import only when the scan is explicitly called: this module opens no
    # hardware connections merely by being imported.
    from AutoSyncExra_wmy import MoMethod, worker

    storage = worker.Storage
    originalMO = MoMethod.getMO(target=target)
    settings = [originalMO + int(offset) for offset in offsets]
    if any(mo < 2300 or mo > 3600 for mo in settings):
        raise ValueError(f'Scan settings exceed the FS725 MO range [2300, 3600]: {settings}')
    print(f'{target}: current MO={originalMO}; scan={settings}', flush=True)
    measurements = []
    try:
        for mo in settings:
            MoMethod.setMO(MO=mo, target=target)
            time.sleep(settle)
            # Require a fresh record after settling, rather than an old result
            # computed before the MO change.
            baseline = fetchDelay(storage, target, collection)
            first = fetchNewDelay(storage, target, baseline, collection)
            print(f'MO={mo}: first delay={first[2]:.6f} ns; waiting {interval:g} s', flush=True)
            time.sleep(interval)
            second = fetchNewDelay(storage, target, first, collection)
            elapsed = second[1] - first[1]
            slope = (second[2] - first[2]) / elapsed
            measurements.append({
                'mo': mo, 'delay_start_ns': first[2], 'delay_end_ns': second[2],
                'elapsed_s': elapsed, 'slope_ns_per_s': slope,
            })
            print(f'MO={mo}: second delay={second[2]:.6f} ns; '
                  f'dt={elapsed:.3f} s; slope={slope:+.9f} ns/s', flush=True)
    finally:
        MoMethod.setMO(MO=originalMO, target=target)
        print(f'Restored {target} MO={originalMO}', flush=True)

    x = np.array([point['mo'] - originalMO for point in measurements], dtype=float)
    y = np.array([point['slope_ns_per_s'] for point in measurements], dtype=float)
    a, b = np.polyfit(x, y, 1)
    if not np.isfinite([a, b]).all() or np.isclose(a, 0, rtol=0, atol=1e-12):
        raise RuntimeError('Drift has no measurable dependence on MO; cannot fit a zero.')
    fittedMO = float(originalMO - b / a)
    rmse = float(np.sqrt(np.mean((y - (a * x + b)) ** 2)))
    print(f'Fit: drift = {a:+.9g} * (MO - {originalMO}) {b:+.9g} ns/s')
    print(f'Fit RMSE: {rmse:.9g} ns/s')
    print(f'Zero-drift MO: {fittedMO:.6f}; nearest integer: {round(fittedMO)} (not applied)')
    if not min(settings) <= fittedMO <= max(settings):
        print('The fitted zero is outside the scan range; extend the scan to verify it.')
    if not 2300 <= fittedMO <= 3600:
        print('The fitted zero is outside the FS725 MO range [2300, 3600].')
    return {'target': target, 'original_mo': originalMO, 'fitted_mo': fittedMO,
            'fit_a': float(a), 'fit_b': float(b), 'rmse_ns_per_s': rmse,
            'measurements': measurements}


if __name__ == '__main__':
    scanMO(
        target='Bob', 
        offsets=[-40, -20, 0, 20, 40],
        interval=30,
        settle=2,
        collection='TFQKD_TDC'
    )
