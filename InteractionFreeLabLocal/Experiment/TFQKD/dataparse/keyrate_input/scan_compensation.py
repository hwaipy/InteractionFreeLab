"""Combine rotation intervals by compensation rho, with no count-ratio filtering."""
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import scan


def main():
    base = Path(__file__).resolve().parent
    batch = base / 'results' / '20261026'
    plan = json.loads((batch / 'datasets.json').read_text(encoding='utf-8'))
    groups = defaultdict(list)
    for dataset in plan['datasets']:
        if (dataset.get('condition') == 'compensation' and dataset.get('status') == 'complete'
                and dataset.get('include_in_complete_analysis')):
            groups[dataset['rho']].append(dataset)
    if not groups:
        raise ValueError('No complete compensation acquisition intervals found')
    output = base / 'results' / ('scan_compensation_' + datetime.now(scan.TZ).strftime('%Y%m%d_%H%M%S_%f'))
    output.mkdir(exist_ok=False)
    summary = []
    for rho, datasets in sorted(groups.items(), key=lambda item: float(item[0])):
        datasets.sort(key=lambda d: d['begin'])
        settings = scan.dataset_settings(datasets[0]['id'])
        settings.begin, settings.end = datasets[0]['begin'], datasets[-1]['end']
        settings.intervals = [[d['begin'], d['end']] for d in datasets]
        settings.dataset_manifest = None
        settings.dataset_manifests = [str(batch / 'datasets' / d['id'] / 'manifest.json') for d in datasets]
        settings.dataset_ids = [d['id'] for d in datasets]
        settings.compensation_rho = rho
        settings.intensity_ratio = [float('inf')]
        settings.excluded_preprocessing_failures = []
        for manifest_path in settings.dataset_manifests:
            manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
            if manifest.get('state') not in ('completed', 'completed_with_failures') or manifest.get('unprocessed_chunks'):
                raise ValueError(f'Unfinished preprocessing: {manifest_path}')
            settings.excluded_preprocessing_failures.extend(manifest.get('failures', []))
        # 未通过预处理一致性校验的记录继续排除，并在输出清单中明确保留详情。
        settings.skip_missing = True
        settings.output = str(output / f'rho-{rho}')
        print(f"rho={rho}: combining {len(datasets)} intervals; excluded={len(settings.excluded_preprocessing_failures)}", flush=True)
        scan.run(settings)
        summary.append({'rho': rho, 'datasets': settings.dataset_ids,
                        'excluded_preprocessing_failures': settings.excluded_preprocessing_failures,
                        'output': settings.output})
        (output / 'groups.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output, flush=True)


if __name__ == '__main__':
    main()
