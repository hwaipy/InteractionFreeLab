"""Scan complete no-compensation intervals from the rotation experiment."""
import json
from pathlib import Path
import scan
from datetime import datetime


def main():
    # 筛选参数共用 scan.py 的 dataset_settings；累加各轮无补偿时间段，输出一套结果。
    base = Path(__file__).resolve().parent
    batch = base / 'results' / '20261026'
    plan = json.loads((batch / 'datasets.json').read_text(encoding='utf-8'))
    datasets = [d for d in plan['datasets']
                if d.get('condition') == 'no_compensation'
                and d.get('status') == 'complete'
                and d.get('include_in_complete_analysis')
                and 'round' in d]
    if not datasets:
        raise ValueError('No complete no-compensation rotation intervals found')
    datasets.sort(key=lambda d: d['begin'])
    settings = scan.dataset_settings(datasets[0]['id'])
    settings.begin, settings.end = datasets[0]['begin'], datasets[-1]['end']
    settings.intervals = [[d['begin'], d['end']] for d in datasets]
    settings.dataset_manifest = None
    settings.dataset_manifests = [str(batch / 'datasets' / d['id'] / 'manifest.json') for d in datasets]
    settings.dataset_ids = [d['id'] for d in datasets]
    settings.output = str(base / 'results' / ('scan_rotation_no_compensation_' +
                           datetime.now(scan.TZ).strftime('%Y%m%d_%H%M%S_%f')))
    print(f"Combining {len(datasets)} no-compensation intervals", flush=True)
    print(scan.run(settings), flush=True)


if __name__ == '__main__':
    main()
