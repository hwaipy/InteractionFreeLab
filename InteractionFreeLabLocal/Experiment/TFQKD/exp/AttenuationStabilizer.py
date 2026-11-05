"""Incremental Z-yield stabilizer; no connection or hardware action on import.

Run from VS Code or: python AttenuationStabilizer.py (observe only).
Enable explicitly: python AttenuationStabilizer.py --enable
Optional common target: --alice-target-db 26 --bob-target-db 26
Both arms default to a fixed 30 dB target; CLI arguments or keys may override it.
Ctrl+C stops updates and holds the last voltage. Gen1/Gen2 are never modified.
Large, statistically significant errors use fast acquisition (gain .8, <=.1V).
Near the target or within per-second 3-sigma noise, switch to EWMA maintenance.
Rich dashboard: pip install rich. Keys: o observe, e implement, a/b edit one
target, t edit both (one common value or two values), q quit. Enter submits,
Esc cancels. Data acquisition continues while typing. --plain keeps JSON output.

Historical meta learns the sequence phase but NEVER drives voltage writes.
At most 1000 slim meta are held. Binary QBER Intermediate is requested only for
new, valid no-compensation seconds and is reduced immediately to Z statistics.
No intensity or QBER cuts. The two voltage slopes are approximate local values
provided by the experimenter, not an absolute optical calibration.
"""
import argparse
from collections import OrderedDict, Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import io
import json
import math
from pathlib import Path
import threading
import time

import numpy as np

ROOT = Path(__file__).resolve().parent
INDEX_FILTER = {'_id': 1, 'FetchTime': 1}
META_FILTER = {'_id': 1, 'FetchTime': 1, 'Data.Counter.2': 1, 'Data.Counter.3': 1,
               'Data.ChannelMonitor.CountSections': 1,
               'Data.ChannelMonitor.Configuration.Frequency': 1}
Z_FILTER = {'_id': 1, 'FetchTime': 1, 'Data.QKDQBER.Intermediate': 1}


def timestamp(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError('FetchTime must have a timezone')
    return dt.timestamp()


def as_list(value):
    return [value] if isinstance(value, dict) else list(value or [])


def zeros(values):
    x = np.asarray(values, dtype=float)
    if x.shape != (1000,) or not np.all(np.isfinite(x)) or np.any(x < 0):
        raise ValueError('Expected nonnegative 1000 x 1ms counts')
    longest = run = prefix = suffix = 0
    for v in x:
        run = run + 1 if v == 0 else 0
        longest = max(longest, run)
    for v in x:
        if v: break
        prefix += 1
    for v in x[::-1]:
        if v: break
        suffix += 1
    return longest, prefix, suffix


class WaveformClassifier:
    """Match all 15 stages and four playing/held Gen1 modes, +/-12ms shift."""
    def __init__(self, path=ROOT / 'CountsTransmission100us.json'):
        data = json.loads(Path(path).read_text())
        a, b = [np.asarray(data['channels'][n]['transmission_100us'], float) for n in ('Alice', 'Bob')]
        if any(v.shape != (10000,) or not np.all(np.isfinite(v)) or np.any(v <= 0) for v in (a,b)):
            raise ValueError('Invalid 100us transmission data')
        self.matrices = []
        for base, other in ((a,b),(b,a)):
            templates = []
            for held in (False, True):
                for rho in [7**(i/13) for i in range(14)] + [None]:
                    comp = np.minimum(1, rho*other/base) if rho is not None else np.ones_like(base)
                    y = (comp * (np.ones_like(base) if held else base)).reshape(1000,10).mean(axis=1)
                    y /= y.mean()
                    templates.extend(np.roll(y, lag) for lag in range(-12,13))
            m = np.asarray(templates)
            self.matrices.append((m, np.mean(m*m, axis=1)))

    def frame(self, record):
        f = {'id':str(record['_id']), 'FetchTime':record['FetchTime'],
             'slot':math.floor(timestamp(record['FetchTime'])), 'reasons':[], 'zeros':{},
             'costs':None, 'counter':{}, 'sync_counts':{}}
        try:
            data = record['Data']; mon = data['ChannelMonitor']
            if mon['Configuration']['Frequency'] != 1000: raise ValueError('Monitor must be 1000Hz')
            costs = []
            for ch, (matrix,norm) in zip(('4','5'), self.matrices):
                x = np.asarray(mon['CountSections'][ch],float)
                f['zeros'][ch] = zeros(x)
                f['sync_counts'][ch] = int(x.sum())
                if f['zeros'][ch][0] >= 5: f['reasons'].append('sync_zero_run_ch'+ch)
                if not x.mean(): raise ValueError('No synchronization photons')
                x /= x.mean()
                c = np.maximum(0, np.mean(x*x) + norm - 2*matrix.dot(x)/1000)
                costs.append(c.reshape(2,15,25).min(axis=2))
            f['costs'] = np.asarray([costs[0][i]+costs[1][j] for i,j in ((0,0),(1,0),(0,1),(1,1))])
            for ch in ('2','3'):
                count = float(data['Counter'][ch])
                if not math.isfinite(count) or count <= 0: raise ValueError('Detector stopped, CH'+ch)
                f['counter'][ch] = count
        except (KeyError, ValueError, TypeError) as e:
            f['reasons'].append(str(e))
        return f


@dataclass
class Actuator:
    service: str
    channel: int
    slope_db_per_volt: float
    min_voltage: float | None = None
    max_voltage: float | None = None

    def limits(self):
        """Optional experiment limits, otherwise only the IT6322 hardware rails."""
        return (0 if self.min_voltage is None else self.min_voltage,
                (6 if self.channel==2 else 30) if self.max_voltage is None else self.max_voltage)


def default_actuators():
    return {'Alice':Actuator('TF_PowerSupply_Alice_3',2,10*math.log10(726/626)/.1),
            'Bob':Actuator('TF_PowerSupply_Bob_4',2,10*math.log10(1050/982)/.1)}


class AttenuationStabilizer:
    def __init__(self, worker=None, endpoint='tcp://code.qpqi.group:1161', *,
                 waveform_path=ROOT/'CountsTransmission100us.json', max_meta=1000,
                 history_seconds=300, target_db=None, mu_z=.494035,
                 alpha=.2, gain=.2, deadband_db=.05, max_step_db=.02,
                 fast_enter_db=.25, fast_exit_db=.10, fast_gain=.8,
                 max_step_voltage=.1, max_total_voltage=None,
                 actuators=None, output_dir=ROOT/'attenuation_stabilizer'):
        if not 90 <= max_meta <= 1000 or not 90 <= history_seconds <= max_meta:
            raise ValueError('Require 90 <= history_seconds <= max_meta <= 1000')
        if not (0 < alpha <= 1 and 0 < gain <= 1 and mu_z > 0
                and deadband_db > 0 and max_step_db > 0
                and math.isfinite(fast_enter_db) and math.isfinite(fast_exit_db)
                and fast_enter_db > fast_exit_db >= deadband_db and 0 < fast_gain <= 1
                and math.isfinite(max_step_voltage) and max_step_voltage > 0
                and (max_total_voltage is None or (math.isfinite(max_total_voltage)
                     and max_total_voltage >= min(max_step_voltage,.1)))):
            raise ValueError('Invalid feedback parameters')
        self._worker, self.endpoint = worker, endpoint
        self.model = WaveformClassifier(waveform_path)
        self.max_meta, self.history_seconds = max_meta, history_seconds
        self.targets = {'Alice':30.0,'Bob':30.0}
        self.targets.update(target_db or {})
        self.target_variance_db = {}
        if any(k not in ('Alice','Bob') or not math.isfinite(v) for k,v in self.targets.items()):
            raise ValueError('target_db must map Alice/Bob to finite dB values')
        self.mu, self.alpha, self.gain = mu_z, alpha, gain
        self.deadband_db, self.max_step_db = deadband_db, max_step_db
        self.fast_enter_db,self.fast_exit_db,self.fast_gain=fast_enter_db,fast_exit_db,fast_gain
        self.max_step_voltage, self.max_total_voltage = min(max_step_voltage,.1), max_total_voltage
        self.actuators = actuators or default_actuators()
        if set(self.actuators) != {'Alice','Bob'}: raise ValueError('Need two actuator configurations')
        for c in self.actuators.values():
            lower,upper=c.limits()
            if (not c.service or type(c.channel) is not int or not 0<=c.channel<3
                    or not all(math.isfinite(v) for v in (c.slope_db_per_volt,lower,upper))
                    or c.slope_db_per_volt == 0 or not 0<=lower<upper<=(6 if c.channel==2 else 30)):
                raise ValueError('Invalid actuator slope/range')
        if len({(c.service,c.channel) for c in self.actuators.values()}) != 2:
            raise ValueError('Actuators must be independent')
        self.output = Path(output_dir)
        self.cache = OrderedDict()
        self.done = set()
        self.phase = None
        self.phase_info = {}
        self.state = 'idle'
        self.stop_event = threading.Event()
        self.filters = {}
        self.signature = None
        self.voltages, self.initial_voltages = {}, {}
        self.suppress_until = -math.inf
        self.last_consumed = -math.inf
        self.live_after = math.inf
        self.cursor = None
        self.latest = None
        self.last_progress = None
        self.enabled = False
        self.pause_writes = threading.Event()
        self._dashboard = None

    def log(self, event, **fields):
        row = {'logged_at':datetime.now(timezone.utc).isoformat(),'event':event,**fields}
        self.output.mkdir(parents=True,exist_ok=True)
        with (self.output/'events.jsonl').open('a') as f: f.write(json.dumps(row,allow_nan=False)+'\n')
        if self._dashboard is not None:
            self._dashboard.record(row)
        elif event not in ('second','sample'):
            print(json.dumps(row),flush=True)

    def worker(self):
        if self._worker is None:
            from interactionfreepy import IFWorker
            self._worker = IFWorker(self.endpoint,timeout=10)
        return self._worker

    def ingest(self, records):
        """Pure incremental classification; a seen ID is never re-fitted."""
        for r in sorted(records,key=lambda r:r['FetchTime']):
            key = str(r['_id'])
            if key not in self.cache: self.cache[key] = self.model.frame(r)
        if not self.cache: return
        high = max(f['slot'] for f in self.cache.values())
        for key in list(self.cache):
            if self.cache[key]['slot'] < high-self.max_meta+1: del self.cache[key]
        while len(self.cache)>self.max_meta: self.cache.popitem(last=False)
        self.done.intersection_update({f['slot'] for f in self.cache.values()})

    def learn_phase(self):
        if not self.cache: return
        high = max(f['slot'] for f in self.cache.values())
        counts = Counter(f['slot'] for f in self.cache.values())
        frames = [f for f in self.cache.values() if not f['reasons'] and counts[f['slot']]==1
                  and f['slot']>=high-179 and f['costs'] is not None]
        if len(frames)<45:
            self.phase = None; return
        scores = [float(np.median([f['costs'][:,(f['slot']-p)%15].min() for f in frames])) for p in range(15)]
        order = np.argsort(scores); p=int(order[0]); margin=scores[int(order[1])]-scores[p]
        cycles = Counter((f['slot']-p)//15 for f in frames)
        supported = sum(n>=12 for n in cycles.values())
        confirmed = scores[p]<=.25 and margin>=.002 and supported>=3
        new = p if confirmed else None
        if new != self.phase:
            self.filters.clear()
            self.log('phase',previous=self.phase,phase=new,score=scores[p],margin=margin,supported_cycles=supported)
        self.phase = new
        self.phase_info={'scores':scores,'margin':margin,'supported_cycles':supported}

    def quality(self, f, slots):
        reasons = list(f['reasons'])
        if any(len(slots.get(s,[]))!=1 for s in (f['slot']-1,f['slot'],f['slot']+1)):
            return reasons+['missing_or_duplicate_neighbor']
        for ch in ('4','5'):
            prev,cur,nxt=[slots[s][0]['zeros'].get(ch) for s in (f['slot']-1,f['slot'],f['slot']+1)]
            if not all(v is not None for v in (prev,cur,nxt)):
                reasons.append('invalid_sync_neighbor'); continue
            if ((prev[2] and cur[1] and prev[2]+cur[1]>=5) or (cur[2] and nxt[1] and cur[2]+nxt[1]>=5)):
                reasons.append('cross_second_sync_zero_ch'+ch)
        if self.phase is None: return reasons+['phase_not_confirmed']
        if f['costs'] is not None:
            stage=(f['slot']-self.phase)%15; c=f['costs']; score=float(c[:,stage].min())
            if score>.25 or score>max(float(c.min())+.12,4*float(c.min())): reasons.append('waveform_mismatch')
            if c[0,stage]-score>max(.04,.5*c[0,stage]): reasons.append('gen1_waiting_or_constant')
            # Reject major detector loss relative to the SAME sequence stage.
            peers=[r for r in self.cache.values() if r['slot']<f['slot'] and not r['reasons']
                   and (r['slot']-self.phase)%15==stage]
            for ch in ('2','3'):
                baseline=[r['counter'][ch] for r in peers if ch in r['counter']][-20:]
                if len(baseline)>=5 and f['counter'].get(ch,0)<.2*float(np.median(baseline)):
                    reasons.append('detector_major_drop_ch'+ch)
        return reasons

    def decode_z(self, record):
        with np.load(io.BytesIO(record['Data']['QKDQBER']['Intermediate']),allow_pickle=False) as z:
            m=json.loads(z['metadata'].tobytes().decode());cfg=m['configuration']
            if (m['format_version']!=1 or m['basis_order']!=['O','X','Y','Z']
                    or m['algorithm']!='TFQKDQBER-frequency-zero-v1' or cfg['TimeEachBlock']!=10**12
                    or cfg['IntensityFrame']<=0 or 10**12%cfg['IntensityFrame']
                    or m['analysis_window']['end_exclusive_ps']-m['analysis_window']['origin_ps']!=10**12):
                raise ValueError('Unsupported/incomplete QBER Intermediate')
            arrays=[z[k] for k in ('pulseCounts','detectionStatistics')]
            for a in arrays:
                if a.shape!=(4,4,10**12//cfg['IntensityFrame']) or a.dtype.kind!='u': raise ValueError('Invalid Z arrays')
            n,d=[a.sum(axis=2,dtype=np.uint64) for a in arrays]
            signature=json.dumps({k:m[k] for k in ('algorithm','configuration','processing','random_numbers_sha256')},sort_keys=True)
            if self.signature is not None and signature!=self.signature: raise RuntimeError('QKD configuration changed')
            self.signature=signature
            if not n[0,0]: raise ValueError('Missing vacuum pulse count')
            bg=int(d[0,0])/int(n[0,0])
            result={}
            for arm,a,b in (('Alice',3,0),('Bob',0,3)):
                if not n[a,b]: raise ValueError('Missing single-arm pulse count')
                y=int(d[a,b])/int(n[a,b])
                if not 0<=bg<y<1: raise ValueError('Signal yield does not exceed vacuum background')
                eta=-math.log((1-y)/(1-bg))/self.mu
                variance=(y/int(n[a,b])/(1-y)**2+bg/int(n[0,0])/(1-bg)**2)/self.mu**2
                result[arm]={'counts':int(d[a,b]),'pulses':int(n[a,b]),'yield':y,'background':bg,
                             'efficiency':eta,'variance':variance,'attenuation_db':-10*math.log10(eta)}
            return result

    def update(self, z, slot, *, enable=False):
        for arm, obs in z.items():
            eta, variance=obs['efficiency'],obs['variance']
            s=self.filters.setdefault(arm,{'values':deque(maxlen=7),'initial':[],
                                          'initial_variances':[],'eta':None,'variance':0.,'phase':'hold'})
            jumps=s.setdefault('jumps',deque(maxlen=3))
            response=s.get('response')
            if response is not None:
                observed_db=10*math.log10(response['eta']/eta)
                response_sigma=10/math.log(10)*math.sqrt(
                    variance/eta**2+response['variance']/response['eta']**2)
                direction=math.copysign(1,response['applied_db'])
                plausible=(observed_db*direction>=-3*response_sigma and
                           abs(observed_db)<=max(1.,3*abs(response['applied_db']),6*response_sigma))
                if plausible:
                    # The slope is approximate. A plausible, correctly directed
                    # response must not be vetoed by pre-adjustment history.
                    s['values'].clear();s['eta']=None;s['response']=None;jumps.clear()
                    self.log('response_checked',arm=arm,slot=slot,observed_db=observed_db,
                             predicted_db=response['applied_db'])
            if s['values']:
                med=float(np.median(s['values']))
                if abs(eta-med)>max(.1*med,6*math.sqrt(variance)):
                    if jumps and slot-jumps[-1]['slot']>45: jumps.clear()
                    jumps.append({'slot':slot,'eta':eta,'variance':variance})
                    center=float(np.median([v['eta'] for v in jumps]))
                    coherent=len(jumps)==3 and all(abs(v['eta']-center)<=
                        max(.05*center,6*math.sqrt(v['variance'])) for v in jumps)
                    if not coherent:
                        self.log('isolated_z_jump',arm=arm,slot=slot,confirmations=len(jumps),needed=3,**obs)
                        continue
                    # A sustained level change is not an isolated dropout.
                    # Preserve the target, discard stale filter history, and let
                    # the current error choose fast acquisition versus hold.
                    s['values'].clear();s['eta']=None;s['response']=None
                    self.log('jump_reacquired',arm=arm,slot=slot,confirmed_slots=[v['slot'] for v in jumps],
                             efficiency=eta)
            jumps.clear()
            s['values'].append(eta)
            raw_attenuation=-10*math.log10(eta)
            raw_sigma=math.sqrt((10/math.log(10)/eta)**2*variance+self.target_variance_db.get(arm,0))
            old_phase=s['phase']
            if arm in self.targets:
                raw_error=abs(self.targets[arm]-raw_attenuation)
                if raw_error>=max(self.fast_enter_db,4*raw_sigma): s['phase']='fast'
                # A fast controller must not wait forever for an error smaller
                # than its per-second noise gate; averaging belongs to hold.
                elif s['phase']=='fast' and raw_error<=max(self.fast_exit_db,3*raw_sigma): s['phase']='hold'
            if s['phase']!=old_phase:
                self.log('control_phase',arm=arm,phase=s['phase'],raw_error_db=self.targets[arm]-raw_attenuation)
            # Fast acquisition uses the current valid second directly. Reset on
            # return to hold so model prediction errors do not linger in EWMA.
            if s['eta'] is None or s['phase']=='fast' or old_phase!=s['phase']:
                s['eta'],s['variance']=eta,variance
            else:
                s['eta']=(1-self.alpha)*s['eta']+self.alpha*eta
                s['variance']=(1-self.alpha)**2*s['variance']+self.alpha**2*variance
            if arm not in self.targets:
                s['initial'].append(eta)
                s['initial_variances'].append(variance)
                if len(s['initial'])<5: continue
                reference=float(np.mean(s['initial']))
                self.targets[arm]=-10*math.log10(reference)
                self.target_variance_db[arm]=(10/math.log(10)/reference)**2*sum(s['initial_variances'])/25
                self.log('target_captured',arm=arm,target_db=self.targets[arm],
                         sigma_db=math.sqrt(self.target_variance_db[arm]))
            attenuation=-10*math.log10(s['eta']);error=self.targets[arm]-attenuation
            sigma_db=math.sqrt((10/math.log(10)/s['eta'])**2*s['variance']+self.target_variance_db.get(arm,0))
            fast=s['phase']=='fast'
            required=abs(error)>max(self.deadband_db,3*sigma_db) and (fast or len(s['values'])>=3)
            # The fast dB cap comes from the signed local response and the
            # voltage cap. Hold retains the smaller dB step and gain.
            limit=abs(self.actuators[arm].slope_db_per_volt)*self.max_step_voltage if fast else self.max_step_db
            step=float(np.clip((self.fast_gain if fast else self.gain)*error,-limit,limit))
            self.log('estimate',arm=arm,slot=slot,raw=obs,smoothed_db=attenuation,target_db=self.targets[arm],
                     error_db=error,sigma_db=sigma_db,required=required,proposed_db=step,enabled=enable,
                     control_phase=s['phase'])
            if required and enable and not self.stop_event.is_set() and not self.pause_writes.is_set():
                actual=self.adjust(arm,step,slot)
                if actual is not None:
                    factor=10**(-actual/10)
                    s['eta']*=factor;s['variance']*=factor**2
                    s['values']=deque((v*factor for v in s['values']),maxlen=7)
                    if actual:
                        s['response']={'eta':eta,'variance':variance,'applied_db':actual}

    def arm(self):
        for arm,c in self.actuators.items():
            lower,upper=c.limits()
            remote=getattr(self.worker(),c.service)
            v=float(remote.getVoltageSetpoints()[c.channel]);measured=float(remote.measureVoltages()[c.channel])
            if (not remote.getOutputStatuses()[c.channel] or not lower<=v<=upper
                    or not math.isfinite(measured) or abs(v-measured)>.02):
                raise RuntimeError(arm+' voltage/output outside configured operating range')
            self.voltages[arm]=self.initial_voltages[arm]=v
        self.log('armed',voltages=self.voltages,slopes={a:c.slope_db_per_volt for a,c in self.actuators.items()})

    def adjust(self,arm,db,slot):
        if self.pause_writes.is_set() or self.stop_event.is_set(): return None
        c=self.actuators[arm];remote=getattr(self.worker(),c.service);old=self.voltages[arm]
        actual=float(remote.getVoltageSetpoints()[c.channel])
        if not math.isfinite(actual) or abs(actual-old)>.0015 or not remote.getOutputStatuses()[c.channel]:
            raise RuntimeError(arm+' voltage changed externally/output disabled')
        if self.last_progress is not None and time.monotonic()-self.last_progress>10:
            self.log('stale_measurement',arm=arm,slot=slot)
            return None
        delta=float(np.clip(db/c.slope_db_per_volt,-self.max_step_voltage,self.max_step_voltage))
        # Round the increment toward zero so voltage quantization cannot exceed
        # the requested step. Stop rather than silently accepting a coarse DAC.
        new=round(old+math.trunc(delta*1000)*.001,3)
        lower,upper=c.limits()
        if (not lower<=new<=upper or (self.max_total_voltage is not None
                and abs(new-self.initial_voltages[arm])>self.max_total_voltage+1e-9)):
            self.log('range_insufficient',arm=arm,slot=slot,requested_voltage=new,limits=[lower,upper])
            return None
        if new==old or self.stop_event.is_set() or self.pause_writes.is_set(): return None
        self.log('write_intent',arm=arm,old=old,new=new)
        if self.pause_writes.is_set() or self.stop_event.is_set(): return None
        remote.setVoltage(c.channel,new);remote.awaitOperation()
        read=float(remote.getVoltageSetpoints()[c.channel]);measured=float(remote.measureVoltages()[c.channel])
        if not all(math.isfinite(v) for v in (read,measured)) or abs(read-new)>.0015 or abs(measured-new)>.02:
            raise RuntimeError(arm+' write/readback failed; hardware state uncertain')
        self.voltages[arm]=read;self.suppress_until=max(self.suppress_until,self.latest+3)
        applied=(read-old)*c.slope_db_per_volt
        self.log('adjusted',arm=arm,voltage=read,measured=measured,applied_db=applied,slot=slot)
        return applied

    def process(self,get_z,*,enable=False):
        slots={}
        for f in self.cache.values(): slots.setdefault(f['slot'],[]).append(f)
        for slot in sorted(slots):
            if slot in self.done or slot>self.latest-2: continue
            f=slots[slot][0];reasons=self.quality(f,slots)
            stage=(slot-self.phase)%15 if self.phase is not None else None
            # Unknown phase may become identifiable using the next few seconds.
            if self.phase is None: continue
            self.done.add(slot)
            self.log('second',slot=slot,id=f['id'],FetchTime=f['FetchTime'],valid=not reasons,reasons=reasons,stage=stage,
                     no_compensation=stage==14,phase=self.phase)
            if reasons or stage!=14 or slot<=self.live_after or slot<=self.last_consumed: continue
            if self.latest-slot>10 or slot<=self.suppress_until: continue
            self.last_consumed=slot
            record=get_z(f['id'])
            if str(record['_id'])!=f['id'] or record['FetchTime']!=f['FetchTime']: raise RuntimeError('Z/index mismatch')
            try: z=self.decode_z(record)
            except (ValueError,KeyError,OSError) as e:
                self.log('invalid_z',slot=slot,reason=str(e));continue
            # A blocking read must not let a stale result drive a voltage change.
            if self.last_progress is not None and time.monotonic()-self.last_progress>10: continue
            self.log('sample',slot=slot,id=f['id'],FetchTime=f['FetchTime'],z=z)
            self.update(z,slot,enable=enable)

    def tick(self,*,enable=False):
        storage=self.worker().Storage
        latest=as_list(storage.latest('TFQKD_TDC',by='FetchTime',length=1,filter=INDEX_FILTER))
        if not latest: return
        latest_time=timestamp(latest[0]['FetchTime']);high=math.floor(latest_time)
        if self.latest is None:
            self.live_after=high;self.cursor=high-self.history_seconds
        if self.latest is None or high>self.latest: self.last_progress=time.monotonic()
        self.latest=high
        if time.monotonic()-self.last_progress>10:
            self.filters.clear();self.state='waiting_for_data';return
        self.state='controlling' if enable else 'observing'
        # FetchTime incremental cursor + 3s overlap handles late neighboring meta.
        # Fetch at most 60s each tick during bootstrap/backlog; then ~1s/tick.
        upper=min(self.cursor+60,latest_time+.000001)
        iso=lambda t:datetime.fromtimestamp(t,timezone.utc).isoformat()
        batch=as_list(storage.range('TFQKD_TDC',iso(self.cursor-3),iso(upper),by='FetchTime',limit=256,filter=META_FILTER))
        if len(batch)>=256: raise RuntimeError('Meta query truncated')
        self.ingest(batch);self.cursor=upper
        self.learn_phase()
        self.process(lambda identity:storage.get('TFQKD_TDC',identity,filter=Z_FILTER),enable=enable)

    def stop(self):
        self.stop_event.set()

    def status(self):
        return {'state':self.state,'cached_meta':len(self.cache),'phase':self.phase,'phase_info':self.phase_info,
                'targets_db':self.targets,'voltages':self.voltages,'latest_slot':self.latest,
                'enabled':self.enabled and not self.pause_writes.is_set()}

    def command(self, name, value=None):
        """Execute on the acquisition thread, never on the keyboard reader."""
        if name == 'observe':
            self.pause_writes.set()
            self.enabled=False
            self.state='observing'
            self.log('mode',mode='observe',policy='hold last voltage')
        elif name == 'implement':
            if self.enabled and not self.pause_writes.is_set(): return
            # Clear before arm(), so a concurrent o during RPC readback stays
            # latched. Re-entering implementation always checks actual voltages.
            self.pause_writes.clear()
            try:
                self.arm()
            except Exception as e:
                self.pause_writes.set();self.enabled=False
                self.log('command_error',command=name,reason=str(e))
                return
            if self.pause_writes.is_set() or self.stop_event.is_set(): return
            self.enabled=True;self.state='controlling'
            self.live_after=max(self.live_after,self.latest if self.latest is not None else -math.inf)
            self.log('mode',mode='implement',policy='next fresh valid no-compensation second')
        elif name == 'targets':
            if (not value or any(k not in ('Alice','Bob') or not math.isfinite(v) for k,v in value.items())):
                raise ValueError('Targets must contain finite Alice/Bob attenuation values')
            self.targets.update(value)
            for arm in value: self.target_variance_db[arm]=0.
            self.log('target_changed',targets_db=value,policy='next fresh valid no-compensation second')
        elif name == 'input_error':
            self.log('input_error',reason=value)

    def _commands(self, keys):
        if keys is None: return
        import queue
        while not keys.commands.empty():
            try: name,value=keys.commands.get_nowait()
            except queue.Empty: break
            try: self.command(name,value)
            except (ValueError,TypeError) as e: self.log('input_error',reason=str(e))

    def run(self,*,enable=False,rich_console=True,interactive=True,history_seconds=900,history_rows=8,console_width=120):
        if self.state!='idle': raise RuntimeError('Use a fresh controller for a new run')
        keys=None
        if rich_console:
            try:
                from AttenuationConsole import StabilizerConsole, TerminalCommands
            except ImportError as e:
                raise RuntimeError('Rich 控制台需要 rich：请用当前 Python 执行 python3 -m pip install rich；或使用 --plain') from e
            keys=TerminalCommands(self) if interactive else None
            self._dashboard=StabilizerConsole(self,keys,history_seconds=history_seconds,history_rows=history_rows,width=console_width)
        self.enabled=enable
        try:
            if keys is not None: keys.start()
            if self._dashboard is not None: self._dashboard.start()
            self.log('started',enabled=enable,max_meta=self.max_meta,target_db=self.targets)
            if enable: self.arm()
            while not self.stop_event.is_set():
                started=time.monotonic()
                self._commands(keys)
                if self.stop_event.is_set(): break
                self.tick(enable=self.enabled and not self.pause_writes.is_set())
                if self._dashboard is not None: self._dashboard.refresh()
                while not self.stop_event.is_set() and time.monotonic()-started<1:
                    self.stop_event.wait(min(.2,max(0,1-(time.monotonic()-started))))
                    self._commands(keys)
                    if self._dashboard is not None: self._dashboard.refresh()
        except KeyboardInterrupt: self.stop()
        except Exception as e:
            self.state='fault';self.log('fault',reason=str(e));raise
        finally:
            self.enabled=False
            self.pause_writes.set()
            if self.state!='fault': self.state='stopped'
            self.log('stopped',state=self.state,policy='hold last voltage',voltages=self.voltages)
            try:
                if self._dashboard is not None: self._dashboard.close()
            finally:
                if keys is not None: keys.close()
                self._dashboard=None


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--enable',action='store_true')
    p.add_argument('--alice-target-db',type=float)
    p.add_argument('--bob-target-db',type=float)
    p.add_argument('--endpoint',default='tcp://code.qpqi.group:1161')
    p.add_argument('--plain',action='store_true',help='JSON lines without Rich dashboard or keyboard commands')
    p.add_argument('--no-keys',action='store_true',help='Disable keyboard commands')
    p.add_argument('--history-seconds',type=int,default=900,help='Dashboard history window, default 900s')
    p.add_argument('--history-rows',type=int,default=8,help='Recent measurement rows on screen')
    p.add_argument('--console-width',type=int,default=120,help='Fixed dashboard width in columns, default 120')
    args=p.parse_args()
    targets={k:v for k,v in (('Alice',args.alice_target_db),('Bob',args.bob_target_db)) if v is not None}
    AttenuationStabilizer(endpoint=args.endpoint,target_db=targets).run(
        enable=args.enable,rich_console=not args.plain,interactive=not args.no_keys,
        history_seconds=args.history_seconds,history_rows=args.history_rows,console_width=args.console_width)


if __name__=='__main__': main()
