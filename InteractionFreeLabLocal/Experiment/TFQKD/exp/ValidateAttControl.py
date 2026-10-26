"""Exercise AttSim attenuation control and measure detector attenuation from this Mac."""

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from interactionfreepy import IFWorker

from AttSim import _collect_counts


def main():
    worker = IFWorker('tcp://code.qpqi.group:1161', timeout=60)
    calibration = worker.AttSim.getAttenuationCalibration()
    result = {'started_at': datetime.now(timezone.utc).isoformat(), 'calibration': calibration,
              'settle_seconds': 2, 'acquisition_seconds': 5, 'channels': {},
              'restoration': 'Gen1 5 V; Gen2 0 V, matching pre-test constant settings'}
    output = Path(__file__).with_name('AttControlValidation.json')

    def save():
        output.write_text(json.dumps(result, indent=2)+'\n')

    def sample(channel, label, response=None):
        time.sleep(2)
        first, last, total4, total5, blocks = _collect_counts(worker, datetime.now(timezone.utc), 5)
        rate = (total4 if channel == 1 else total5)/5
        record = dict(label=label, first_fetch=first.isoformat(), last_fetch=last.isoformat(),
                      midpoint_timestamp=(first.timestamp()+last.timestamp())/2,
                      blocks=blocks, ch4_counts_per_s=total4/5, ch5_counts_per_s=total5/5,
                      target_counts_per_s=rate, control_response=response)
        print(label, f'CH{4 if channel == 1 else 5}={rate:.1f}/s', flush=True)
        return record

    for generator in ('gen1', 'gen2'):
        for channel in (1, 2):
            key = f'{generator}_ch{channel}'
            print('START', key, flush=True)
            entry = {'records': [], 'completed': False, 'restored': False}
            result['channels'][key] = entry
            save()
            try:
                response = worker.AttSim.setWaveform(generator, channel, [0 if generator == 'gen1' else 5])
                dark = sample(channel, 'dark', response)
                entry['records'].append(dark)
                response = worker.AttSim.setAttenuationWaveform(generator, channel, [0])
                before = sample(channel, 'reference_before', response)
                entry['records'].append(before)
                save()
                for target in (3, 10, 20):
                    response = worker.AttSim.setAttenuationWaveform(generator, channel, [target])
                    record = sample(channel, f'{target}_dB', response)
                    record['expected_attenuation_db'] = target
                    entry['records'].append(record)
                    save()
                response = worker.AttSim.setAttenuationWaveform(generator, channel, [0]*5000+[10]*5000)
                dynamic = sample(channel, 'half_second_0_10_dB', response)
                dynamic['expected_attenuation_db'] = -10*math.log10(0.55)
                entry['records'].append(dynamic)
                response = worker.AttSim.setAttenuationWaveform(generator, channel, [0])
                after = sample(channel, 'reference_after', response)
                entry['records'].append(after)
                entry['reference_change_percent'] = 100*(after['target_counts_per_s']/before['target_counts_per_s']-1)
                background = dark['target_counts_per_s']
                for record in entry['records']:
                    if 'expected_attenuation_db' not in record:
                        continue
                    fraction = (record['midpoint_timestamp']-before['midpoint_timestamp'])/(after['midpoint_timestamp']-before['midpoint_timestamp'])
                    reference = before['target_counts_per_s']*(1-fraction)+after['target_counts_per_s']*fraction
                    record['interpolated_reference_counts_per_s'] = reference
                    measured = -10*math.log10(record['target_counts_per_s']/reference)
                    record['measured_attenuation_db'] = measured
                    record['error_db'] = measured-record['expected_attenuation_db']
                    if reference > background and record['target_counts_per_s'] > background:
                        corrected = -10*math.log10((record['target_counts_per_s']-background)/(reference-background))
                        record['background_corrected_attenuation_db'] = corrected
                        record['background_corrected_error_db'] = corrected-record['expected_attenuation_db']
                    print(key, record['label'], 'error_db', round(record['error_db'],4), flush=True)
                entry['completed'] = True
            finally:
                worker.AttSim.setWaveform(generator, channel, [5 if generator == 'gen1' else 0])
                entry['restored'] = True
                save()
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    save()
    print('COMPLETE', str(output), flush=True)


if __name__ == '__main__':
    main()
