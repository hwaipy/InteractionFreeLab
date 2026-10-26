"""Finite deployment check: four short samples, never the full experiment."""
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timedelta
import os
import preprocess_batch as batch


def main():
    base = Path(__file__).resolve().parent
    datasets, _ = batch.load_datasets(base/'batch_inputs/0_no_compensation.md',base/'batch_inputs/1_compensation.csv')
    selected = [datasets[i] for i in (0, 1, 2, len(datasets)-1)]
    samples = []
    sample_seconds = int(os.environ.get('TFQKD_SMOKE_SECONDS', '4'))
    if not 1 <= sample_seconds <= 30:
        raise ValueError('Finite smoke samples must be in 1..30 seconds')
    for dataset in selected:
        start = batch.preprocess.parse_time(dataset['begin'])
        samples.append({**dataset, 'id': dataset['id']+'_smoke', 'end':(start+timedelta(seconds=sample_seconds)).isoformat()})
    settings = SimpleNamespace(source='2502',
        output=str(base/'smoke_output'/datetime.now(batch.preprocess.TZ).strftime('%Y%m%d_%H%M%S')),
        workers=4,chunk_seconds=4,progress_seconds=5,config=None,clock_frequency=25000,
        transform=None,verify_realtime=True,timeout=30)
    result=batch.run(settings,datasets=samples)
    if result['state']!='completed' or result['processed_files']<12:
        raise SystemExit('Deployment smoke check failed; inspect status.json/failure logs')
    print('PASS: multiprocess real-data preprocessing, clock correction, realtime checks and ETA.')
    print(settings.output)


if __name__=='__main__':
    main()
