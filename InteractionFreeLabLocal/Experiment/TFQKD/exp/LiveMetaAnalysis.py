"""Incremental local analysis of committed TFQKD ZIP checkpoints.

No IFWorker, SSH, HTTP or device access. SQLite stores per-second sufficient
statistics and transactional aggregate deltas, so resuming never double counts.
python LiveMetaAnalysis.py --archive tdc_meta/run_20261031.zip
Use --once to process the current checkpoint and exit. Reports: <zip>.analysis/.
"""
import argparse
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from collections import Counter, defaultdict
from contextlib import nullcontext
from datetime import datetime, timezone, timedelta
import csv
import hashlib
import html
import io
import json
import lzma
from pathlib import Path
import signal
import sqlite3
import sys
import time
import zipfile
from urllib.parse import quote

import msgpack
import numpy as np

from AttenuationStabilizer import WaveformClassifier
from FetchTFQKDMeta import _CheckpointZipReader, save_json

ROOT = Path(__file__).resolve().parent
RHOS = [7**(i/13) for i in range(14)] + [None]
MODEL = {'num_photons':[.0303853,.482834,.494035], 'epsilon':1e-10, 'error_correction':1.16,
         'target_pulse_pairs':10**12, 'option':'yz', 'profile':'paper'}
TZ = timezone(timedelta(hours=8))


def metric(record, model):
    f = model.frame(record)
    f['costs'] = f['costs'].tolist() if f['costs'] is not None else None
    f['cohort'] = 'invalid'
    try:
        q = record['Data']['QKDQBER']; phase = int(q['PhaseThreshold'])
        with np.load(io.BytesIO(q['Intermediate']), allow_pickle=False) as z:
            m = json.loads(z['metadata'].tobytes().decode()); cfg = m['configuration']
            if (m['format_version'] != 1 or m['basis_order'] != ['O','X','Y','Z']
                    or m['algorithm'] != 'TFQKDQBER-frequency-zero-v1' or not 0 <= phase < 64
                    or cfg['TimeEachBlock'] != 10**12 or cfg['IntensityFrame'] <= 0
                    or 10**12 % cfg['IntensityFrame']):
                raise ValueError('Unsupported QBER configuration')
            frames = 10**12 // cfg['IntensityFrame']
            for key in ('pulseCounts','detectionStatistics'):
                if z[key].shape != (4,4,frames) or z[key].dtype.kind != 'u':
                    raise ValueError('Invalid sufficient-statistics array')
            h = z['phaseHistogram']
            if h.shape != (4,frames,64,2) or h.dtype.kind != 'u':
                raise ValueError('Invalid phase histogram')
            window = m['analysis_window']
            if window['end_exclusive_ps']-window['origin_ps'] != 10**12:
                raise ValueError('Incomplete analysis window')
            f['p'] = z['pulseCounts'].sum(axis=2,dtype=np.uint64).tolist()
            if not np.asarray(f['p'],dtype=np.uint64).sum():raise ValueError('No emitted signal pulses')
            f['d'] = z['detectionStatistics'].sum(axis=2,dtype=np.uint64).tolist()
            # ALL intensity frames are summed, with the stored phase threshold.
            f['e'] = h[:,:,:phase+1,:].sum(axis=(1,2),dtype=np.uint64).tolist()
            signature = {k:m[k] for k in ('algorithm','configuration','processing','random_numbers_sha256')}
            signature['phase_bin'] = phase
            f['cohort'] = hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:16]
            f['phase_bin'] = phase
            f['q'] = [f['e'][i][1]/sum(f['e'][i]) if sum(f['e'][i]) else None for i in (1,2,3)]
    except (KeyError,ValueError,TypeError,OSError) as e:
        f['reasons'].append('invalid_intermediate: '+str(e))
    return f


def infer_phase(frames):
    good = [f for f in frames if not f['reasons'] and f['costs'] is not None]
    if len(good) < 45: return None
    counts = Counter(f['slot'] for f in good)
    good = [f for f in good if counts[f['slot']] == 1]
    if len(good) < 45: return None
    slots = np.asarray([f['slot'] for f in good],dtype=np.int64)
    costs = np.asarray([f['costs'] for f in good]).min(axis=1)
    indices = (slots[:,None]-np.arange(15)) % 15
    scores = np.median(np.take_along_axis(costs,indices,axis=1),axis=0)
    order = np.argsort(scores); phase = int(order[0])
    cycles = Counter((int(t)-phase)//15 for t in slots)
    if scores[phase]>.25 or scores[order[1]]-scores[phase]<.002 or sum(n>=12 for n in cycles.values())<3:
        return None
    return phase


def classify(f, window, phase):
    reasons = list(f['reasons']); slot=f['slot']
    by_slot = defaultdict(list)
    for r in window: by_slot[r['slot']].append(r)
    if len(by_slot[slot]) != 1: reasons.append('duplicate_wall_second')
    for ch in ('4','5'):
        cur = f['zeros'].get(ch)
        if cur is None: continue
        for adjacent, left, right in ((slot-1,2,1),(slot+1,1,2)):
            if len(by_slot.get(adjacent,[])) != 1:
                reasons.append('missing_or_duplicate_neighbor'); continue
            other = by_slot[adjacent][0]['zeros'].get(ch)
            a,b = (other[left],cur[right]) if other else (0,0)
            if a and b and a+b>=5: reasons.append('cross_second_zero_ch'+ch)
    if phase is None: return None, sorted(set(reasons+['sequence_not_confirmed']))
    stage = (slot-phase)%15
    if f['costs'] is not None:
        c = np.asarray(f['costs']); assigned=float(c[:,stage].min()); free=float(c.min())
        if assigned>.25 or assigned>max(free+.12,4*free): reasons.append('waveform_mismatch')
        if c[0,stage]-assigned>max(.04,.5*c[0,stage]): reasons.append('gen1_waiting_or_constant')
        # Counter 2/3 detects a stopped/majorly reduced signal detector, comparing
        # only equal rho stages. Sync CH4/5 1ms arrays detect optical interruptions.
        peers = [r for r in window if r['slot']<slot and not r['reasons'] and (r['slot']-phase)%15==stage]
        for ch in ('2','3'):
            counts = [r['counter'][ch] for r in peers if ch in r['counter']]
            if len(counts)>=3 and f['counter'].get(ch,0)<.2*float(np.median(counts)):
                reasons.append('detector_major_drop_ch'+ch)
    return stage, sorted(set(reasons))


class LiveAnalysis:
    def __init__(self, archive, output=None, waveform=None):
        self.archive = Path(archive).resolve()
        self.output = Path(output or str(self.archive)+'.analysis')
        self.output.mkdir(parents=True,exist_ok=True)
        self.waveform = Path(waveform or ROOT/'CountsTransmission100us.json')
        self.model = WaveformClassifier(self.waveform)
        self.db = sqlite3.connect(self.output/'analysis.sqlite')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE IF NOT EXISTS members(name TEXT PRIMARY KEY, ordinal INTEGER, token TEXT);
          CREATE TABLE IF NOT EXISTS seconds(id TEXT PRIMARY KEY,member TEXT,slot INTEGER,fetch TEXT,
            body TEXT,cohort TEXT,stage INTEGER,valid INTEGER,reasons TEXT,qx REAL,qy REAL,qz1 REAL);
          CREATE INDEX IF NOT EXISTS seconds_slot ON seconds(slot);
          CREATE INDEX IF NOT EXISTS seconds_group ON seconds(cohort,stage,valid);
          CREATE TABLE IF NOT EXISTS aggregates(cohort TEXT,stage INTEGER,body TEXT,PRIMARY KEY(cohort,stage));
        ''')
        config = json.dumps({'archive':str(self.archive),'waveform_sha256':hashlib.sha256(self.waveform.read_bytes()).hexdigest(),
                             'algorithm_version':1,'model':MODEL},sort_keys=True)
        saved = self.db.execute("SELECT value FROM settings WHERE key='config'").fetchone()
        if saved and saved[0]!=config: raise ValueError('Analysis settings changed; use a new analysis output directory')
        self.db.execute("INSERT OR IGNORE INTO settings VALUES('config',?)",(config,));self.db.commit()
        self.groups = {(c,s):json.loads(b) for c,s,b in self.db.execute('SELECT cohort,stage,body FROM aggregates')}
        self.changed = set();self.snapshot = {};self.archive_members = 0

    def close(self): self.db.close()

    def _aggregate(self,f,stage,sign):
        key=(f['cohort'],stage)
        g=self.groups.setdefault(key,{'seconds':0,'phase_bin':f['phase_bin'],
            'p':np.zeros((4,4),dtype=np.int64).tolist(),'d':np.zeros((4,4),dtype=np.int64).tolist(),
            'e':np.zeros((4,2),dtype=np.int64).tolist(),'q_n':[0,0,0],'q_sum':[0.,0.,0.],'q_sq':[0.,0.,0.]})
        g['seconds']+=sign
        for k in ('p','d','e'):g[k]=(np.asarray(g[k],dtype=np.int64)+sign*np.asarray(f[k],dtype=np.int64)).tolist()
        for i,q in enumerate(f['q']):
            if q is not None:
                g['q_n'][i]+=sign;g['q_sum'][i]+=sign*q;g['q_sq'][i]+=sign*q*q
        if g['seconds']<0:raise ValueError('Negative aggregate count')
        self.changed.add(key)

    def _flush(self):
        for c,s in self.changed:
            self.db.execute('INSERT OR REPLACE INTO aggregates VALUES(?,?,?)',(c,s,json.dumps(self.groups[c,s])))
        self.changed.clear()

    def _rollback(self,ordinal):
        names=[r[0] for r in self.db.execute('SELECT name FROM members WHERE ordinal>=?',(ordinal,))]
        for name in names:
            for body,stage in self.db.execute('SELECT body,stage FROM seconds WHERE member=? AND valid=1',(name,)):
                self._aggregate(json.loads(body),stage,-1)
            self.db.execute('DELETE FROM seconds WHERE member=?',(name,))
            self.db.execute('DELETE FROM members WHERE name=?',(name,))
        high=self.db.execute('SELECT MAX(slot) FROM seconds').fetchone()[0]
        if high is not None:
            affected=list(self.db.execute('SELECT id,body,stage,valid FROM seconds WHERE slot>=?',(high-90,)))
            for identity,body,stage,valid in affected:
                if valid:self._aggregate(json.loads(body),stage,-1)
                self.db.execute('UPDATE seconds SET valid=NULL,stage=NULL,reasons=NULL WHERE id=?',(identity,))
        self._flush()

    def analyze_pending(self,final=False):
        high=self.db.execute('SELECT MAX(slot) FROM seconds').fetchone()[0]
        if high is None:return
        cutoff=high if final else high-45
        pending=self.db.execute('SELECT id,body FROM seconds WHERE valid IS NULL AND slot<=? ORDER BY slot LIMIT 256',(cutoff,)).fetchall()
        while pending:
            low=json.loads(pending[0][1])['slot'];last=json.loads(pending[-1][1])['slot']
            window=[json.loads(r[0]) for r in self.db.execute('SELECT body FROM seconds WHERE slot BETWEEN ? AND ? ORDER BY slot',(low-90,last+45))]
            for identity,body in pending:
                f=json.loads(body);slot=f['slot']
                neighborhood=[r for r in window if slot-45<=r['slot']<=slot+45]
                # At a completed run boundary use available past context as well.
                if final and slot>high-45:neighborhood=[r for r in window if slot-90<=r['slot']<=slot+45]
                phase=infer_phase(neighborhood)
                stage,reasons=classify(f,window,phase)
                valid=not reasons
                self.db.execute('UPDATE seconds SET stage=?,valid=?,reasons=? WHERE id=?',
                                (stage,int(valid),json.dumps(reasons),identity))
                if valid:self._aggregate(f,stage,1)
            self._flush();self.db.commit()
            pending=self.db.execute('SELECT id,body FROM seconds WHERE valid IS NULL AND slot<=? ORDER BY slot LIMIT 256',(cutoff,)).fetchall()

    def scan(self,progress=None,should_stop=None):
        """Read immutable committed ZIP data only; never lock or edit the writer."""
        state_path=Path(str(self.archive)+'.state.xz')
        state=msgpack.unpackb(lzma.decompress(state_path.read_bytes()),raw=False) if state_path.exists() else None
        self.snapshot={k:state['manifest'].get(k) for k in ('state','downloaded_through','records')} if state else {'state':'complete'}
        if state:self.snapshot['checkpoint_time']=state['checkpoint_time']
        view=_CheckpointZipReader(self.archive,state) if state else None
        context=view if view is not None else nullcontext()
        new=0
        with context:
            with zipfile.ZipFile(view or self.archive) as z:
                infos=z.infolist();self.archive_members=len(infos)
                previous=list(self.db.execute('SELECT name,ordinal,token FROM members ORDER BY ordinal'))
                mismatch=None
                for name,ordinal,token in previous:
                    if ordinal>=len(infos) or name!=infos[ordinal].filename or token!=self.token(infos[ordinal]):
                        mismatch=ordinal;break
                if mismatch is not None:self._rollback(mismatch);self.db.commit()
                processed=self.db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
                for ordinal in range(processed,len(infos)):
                    if should_stop is not None and should_stop():break
                    info=infos[ordinal];payload=z.read(info)  # verifies ZIP CRC
                    rows=msgpack.unpackb(lzma.decompress(payload),raw=False,strict_map_key=False)
                    with self.db:
                        for record in rows:
                            f=metric(record,self.model)
                            if self.db.execute('SELECT 1 FROM seconds WHERE id=?',(f['id'],)).fetchone():
                                raise ValueError('Duplicate meta identity in archive: '+f['id'])
                            q=f.get('q',[None,None,None])
                            self.db.execute('INSERT INTO seconds VALUES(?,?,?,?,?,?,NULL,NULL,NULL,?,?,?)',
                                (f['id'],info.filename,f['slot'],f['FetchTime'],json.dumps(f),f['cohort'],*q))
                        self.db.execute('INSERT INTO members VALUES(?,?,?)',(info.filename,ordinal,self.token(info)))
                    new+=len(rows)
                    if ordinal%128==127:
                        self.analyze_pending()
                        if progress:progress(ordinal+1,len(infos))
                self.analyze_pending(final=self.snapshot.get('state')=='complete')
        return new

    @staticmethod
    def token(info):return f'{info.CRC}:{info.file_size}:{info.header_offset}'

    def report(self,compute_rates=True):
        sys.path.insert(0,str(ROOT.parent/'dataparse/keyrate'))
        from universal_sns import calKeyRate
        results=[]
        cohorts=sorted({c for (c,s),g in self.groups.items() if g['seconds']})
        for cohort,stage in ((c,s) for c in cohorts for s in range(15)):
            g=self.groups.get((cohort,stage))
            if g is None or not g['seconds']:
                g={'seconds':0,'p':np.zeros((4,4),dtype=np.int64),'e':np.zeros((4,2),dtype=np.int64),
                   'q_n':[0,0,0],'q_sum':[0.,0.,0.],'q_sq':[0.,0.,0.]}
            n=int(np.asarray(g['p'],dtype=np.int64).sum());scale=MODEL['target_pulse_pairs']/n if n else None
            row={'cohort':cohort,'class':stage+1,'rho':RHOS[stage],'valid_seconds':g['seconds'],
                 'observed_pulse_pairs':n,'target_pulse_pairs':MODEL['target_pulse_pairs'],'scale_factor':scale}
            first,last=self.db.execute('SELECT MIN(fetch),MAX(fetch) FROM seconds WHERE cohort=? AND stage=? AND valid=1',(cohort,stage)).fetchone()
            row.update(first_FetchTime=first,last_FetchTime=last)
            for i,label in enumerate(('x','y','z1')):
                count=g['q_n'][i];mean=g['q_sum'][i]/count if count else None
                row[label+'_mean']=mean
                row[label+'_sd']=math_sqrt(max(0,(g['q_sq'][i]-g['q_sum'][i]**2/count)/(count-1))) if count>1 else None
                total=sum(g['e'][i+1]);row[label+'_pooled']=g['e'][i+1][1]/total if total else None
            for label in ('finite_keyrate_1e12','finite_key_bits_1e12','actual_keyrate','actual_key_bits'):row[label]=None
            row['rate_status']='not_computed'
            if not n:row['rate_status']='no_data'
            if compute_rates and n:
                try:
                    stat={key:np.asarray(g[k],dtype=np.int64) for key,k in (('pulses','p'),('detections','d'),('errors','e'))}
                    kw=dict(num_photons=MODEL['num_photons'],phaseSeletcedRatio=(g['phase_bin']+1)/64,
                            strict=True,option=MODEL['option'],profile=MODEL['profile'],epsilon=MODEL['epsilon'],
                            error_correction=MODEL['error_correction'])
                    result=calKeyRate(stat,scale=scale,**kw);actual=calKeyRate(stat,scale=1,**kw)
                    row.update(finite_keyrate_1e12=result['keyrate'],finite_key_bits_1e12=result['key_bits'],
                               actual_keyrate=actual['keyrate'],actual_key_bits=actual['key_bits'],
                               rate_status=result['details']['status'])
                except (ValueError,ArithmeticError) as e:
                    row['rate_status']='error: '+str(e)  # never disguise errors as zero key
            results.append(row)
        counts=dict(self.db.execute('SELECT COALESCE(valid,-1),COUNT(*) FROM seconds GROUP BY valid'))
        report={'updated_at':datetime.now(TZ).isoformat(),'archive':str(self.archive),'snapshot':self.snapshot,
            'records':sum(counts.values()),'valid':counts.get(1,0),'invalid':counts.get(0,0),'pending':counts.get(-1,0),
            'model':MODEL,'selection':'Whole-second quality only; NO intensity-frame or QBER cuts. Latest ~45s pending cycle confirmation.',
            'groups':results,'paired_groups':self.paired_rates(compute_rates)}
        report['processed_members']=self.db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
        report['archive_members']=self.archive_members
        report['analyzed_FetchTime']=self.db.execute('SELECT MAX(fetch) FROM seconds').fetchone()[0]
        temp=self.output/'by_rho.csv.tmp'
        with temp.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(results[0]) if results else ['cohort','class','rho','valid_seconds','scale_factor','finite_keyrate_1e12'])
            w.writeheader();w.writerows(results)
        temp.replace(self.output/'by_rho.csv')
        paired=report['paired_groups'];temp=self.output/'by_rho_pairs.csv.tmp'
        with temp.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(paired[0]) if paired else ['cohort','rho','finite_keyrate_1e12'])
            w.writeheader();w.writerows(paired)
        temp.replace(self.output/'by_rho_pairs.csv')
        self.export_seconds()
        if compute_rates and any(g['rho'] is None and g['valid_seconds'] for g in results):
            from ScanUncompensated import run as scan_postselection
            try:
                if not hasattr(self,'postselection_cache'):self.postselection_cache={}
                selection=scan_postselection(self.archive,self.output/'postselection',
                    published=report,cache=self.postselection_cache)
                report['postselection']={'status':'updated','updated_at':selection['updated_at'],
                    'center_ratio':selection['center_ratio_used'],'source_report_updated_at':report['updated_at']}
            except (ValueError,ArithmeticError,OSError,zipfile.BadZipFile) as error:
                # A missing/temporarily inconsistent selection must not stop downloading
                # or disguise an old selection curve as a current comparison.
                report['postselection']={'status':'error','message':str(error)}
                print('Postselection update deferred:',error,flush=True)
        self.plots(report)
        self.html(report)
        save_json(self.output/'summary.json',report)
        return report

    def paired_rates(self,compute_rates=True):
        """Pool adjacent compensation stages, never average their keyrates."""
        sys.path.insert(0,str(ROOT.parent/'dataparse/keyrate'))
        from universal_sns import calKeyRate
        results=[]
        cohorts=sorted({c for (c,s),g in self.groups.items() if g['seconds']})
        for cohort in cohorts:
            for first in range(0,14,2):
                stages=(first,first+1)
                pair=[self.groups.get((cohort,s)) for s in stages]
                available=[g for g in pair if g is not None and g['seconds']]
                arrays={k:sum((np.asarray(g[k],dtype=np.int64) for g in available),
                             np.zeros(shape,dtype=np.int64))
                        for k,shape in (('p',(4,4)),('d',(4,4)),('e',(4,2)))}
                n=int(arrays['p'].sum());scale=MODEL['target_pulse_pairs']/n if n else None
                row={'cohort':cohort,'class_first':first+1,'class_second':first+2,
                     'rho_first':RHOS[first],'rho_second':RHOS[first+1],
                     'rho':(RHOS[first]+RHOS[first+1])/2,
                     'valid_seconds':sum(g['seconds'] for g in available),
                     'observed_pulse_pairs':n,'target_pulse_pairs':MODEL['target_pulse_pairs'],
                     'scale_factor':scale,'finite_keyrate_1e12':None,'finite_key_bits_1e12':None,
                     'actual_keyrate':None,'actual_key_bits':None,'rate_status':'not_computed'}
                for i,label in ((1,'x'),(2,'y'),(3,'z1')):
                    total=int(arrays['e'][i].sum())
                    row[label+'_pooled']=int(arrays['e'][i,1])/total if total else None
                if len(available)!=2 or not n:
                    row['rate_status']='incomplete_pair'
                elif len({g['phase_bin'] for g in available})!=1:
                    row['rate_status']='error: incompatible phase thresholds'
                elif compute_rates:
                    try:
                        statistic={key:arrays[k] for key,k in (('pulses','p'),('detections','d'),('errors','e'))}
                        kw=dict(num_photons=MODEL['num_photons'],phaseSeletcedRatio=(available[0]['phase_bin']+1)/64,
                            strict=True,option=MODEL['option'],profile=MODEL['profile'],epsilon=MODEL['epsilon'],
                            error_correction=MODEL['error_correction'])
                        scaled=calKeyRate(statistic,scale=scale,**kw);actual=calKeyRate(statistic,scale=1,**kw)
                        row.update(finite_keyrate_1e12=scaled['keyrate'],finite_key_bits_1e12=scaled['key_bits'],
                            actual_keyrate=actual['keyrate'],actual_key_bits=actual['key_bits'],
                            rate_status=scaled['details']['status'])
                    except (ValueError,ArithmeticError) as e:
                        row['rate_status']='error: '+str(e)
                results.append(row)
        return results

    def export_seconds(self):
        temp=self.output/'seconds.csv.tmp'
        with temp.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(['id','FetchTime','cohort','class','rho','valid','reasons','qber_x','qber_y','phase_error_z1'])
            for identity,fetch,cohort,stage,valid,reasons,x,y,z in self.db.execute('SELECT id,fetch,cohort,stage,valid,reasons,qx,qy,qz1 FROM seconds ORDER BY slot'):
                w.writerow([identity,fetch,cohort,stage+1 if stage is not None else '',RHOS[stage] if stage is not None else '',
                            'pending' if valid is None else bool(valid),reasons,x,y,z])
        temp.replace(self.output/'seconds.csv')

    def plots(self,report):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        # Separate cohorts rather than silently pooling changed QKD settings.
        for cohort in sorted({g['cohort'] for g in report['groups']}):
            groups=[g for g in report['groups'] if g['cohort']==cohort]
            rng=np.random.default_rng(42)
            fig,axes=plt.subplots(3,1,figsize=(14,10),sharex=True,layout='constrained')
            for ax,key,title in zip(axes,('qx','qy','qz1'),('X QBER','Y QBER','Z1 phase error')):
                for g in groups:
                    values=np.asarray([r[0] for r in self.db.execute(f'SELECT {key} FROM seconds WHERE cohort=? AND stage=? AND valid=1 AND {key} IS NOT NULL',(cohort,g['class']-1))])
                    if len(values):
                        ax.scatter(g['class']+rng.uniform(-.15,.15,len(values)),values*100,s=4,alpha=.25,rasterized=True)
                        ax.errorbar(g['class'],values.mean()*100,yerr=values.std(ddof=1)*100 if len(values)>1 else 0,fmt='D',color='crimson',capsize=3)
                ax.set_ylabel(title+' (%)');ax.set_ylim(bottom=0);ax.grid(alpha=.2)
            axes[-1].set_xticks(range(1,16),[f'{r:.3g}' if r is not None else 'No comp.' for r in RHOS])
            axes[-1].set_xlabel('Compensation threshold rho (15 classes)')
            fig.suptitle(f'All accepted seconds | mean ± sample SD | no intensity filtering\n'
                         f'Updated {report["updated_at"]} | {cohort}',fontsize=12)
            self.save_figure(fig,'qber_'+cohort);plt.close(fig)
            fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
            rows=[g for g in groups if g['rho'] is not None and g['finite_keyrate_1e12'] is not None]
            ax.plot([g['rho'] for g in rows],[g['finite_keyrate_1e12'] for g in rows],'o-',label='Extrapolated to 10¹² pulse pairs')
            ax.plot([g['rho'] for g in rows],[g['actual_keyrate'] for g in rows],'s--',label='Actual accumulated data')
            for g in groups:
                if g['rho'] is None and g['finite_keyrate_1e12'] is not None:
                    ax.axhline(g['finite_keyrate_1e12'],ls=':',color='gray',label='No compensation, 10¹²')
            ax.set(xlabel='rho',ylabel='Estimated secret bits / signal pulse pair',ylim=(0,None));ax.grid(alpha=.2);ax.legend()
            ax.set_title(f'Updated {report["updated_at"]} | {cohort}',fontsize=10)
            self.save_figure(fig,'keyrate_'+cohort);plt.close(fig)
            paired=[g for g in report.get('paired_groups',[]) if g['cohort']==cohort and g['finite_keyrate_1e12'] is not None]
            fig,ax=plt.subplots(figsize=(11,5.5),layout='constrained')
            ax.plot([g['rho'] for g in paired],[g['finite_keyrate_1e12'] for g in paired],'o-',lw=2,
                    label='Two adjacent rho stages pooled, N=10¹²')
            for g in groups:
                if g['rho'] is None and g['finite_keyrate_1e12'] is not None:
                    ax.axhline(g['finite_keyrate_1e12'],ls=':',color='gray',label='No compensation, N=10¹²')
            ax.set(xlabel='Arithmetic mean rho of each adjacent pair',ylabel='Estimated secret bits / signal pulse pair',ylim=(0,None))
            if paired:ax.set_xticks([g['rho'] for g in paired],[f'{g["rho"]:.3f}' for g in paired])
            ax.ticklabel_format(axis='y',style='sci',scilimits=(0,0));ax.grid(alpha=.25);ax.legend()
            ax.set_title(f'Raw statistics combined BEFORE finite-key calculation\nUpdated {report["updated_at"]} | {cohort}',fontsize=11)
            self.save_figure(fig,'keyrate_pairs_'+cohort);plt.close(fig)

    def save_figure(self,fig,name):
        temporary=self.output/(name+'.tmp.png');fig.savefig(temporary,dpi=140);temporary.replace(self.output/(name+'.png'))

    def html(self,report):
        def fmt(value,percent=False):
            return '—' if value is None else (f'{value*100:.3f}%' if percent else f'{value:.5g}')
        body=['<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="15">',
              '<title>TFQKD live meta analysis</title><style>body{font:15px system-ui;margin:25px;background:#fafafa;color:#222}table{border-collapse:collapse;background:white}td,th{padding:7px 12px;border:1px solid #ddd;text-align:right}img{max-width:100%;background:white}small{color:#666}</style>',
              '<h2>TFQKD 持续分析</h2>',f'<p>更新 {report["updated_at"]} · 已解析 {report["records"]:,} 条meta · 有效 {report["valid"]:,} · 无效 {report["invalid"]:,} · 待确认 {report["pending"]:,}</p>',
              f'<p>解析到 {html.escape(str(report.get("analyzed_FetchTime")))} · ZIP进度 {report["processed_members"]:,}/{report["archive_members"]:,} 条目</p>',
              '<p>不做强度筛选或QBER筛选；最近约45秒等待周期上下文确认。原始ZIP不删除、不修改。不同QKD配置分开统计。</p>',
              '<p>成码率为 Universal SNS yz/AOPP 模型估计，ε=10⁻¹⁰，fEC=1.16；10¹² 指每个 rho 的发送脉冲对数。倍数&lt;1表示缩减到10¹²；均值±SD中的SD为样本标准差。</p>',
              '<p><a href="by_rho.csv">下载汇总CSV</a> · <a href="by_rho_pairs.csv">相邻rho两两合并CSV</a> · <a href="seconds.csv">下载逐秒判定CSV</a> · <a href="summary.json">完整结果JSON</a></p>']
        for cohort in sorted({g['cohort'] for g in report['groups']}):
            selection=report.get('postselection',{})
            if selection.get('status')=='updated':
                body.append('<h3>补偿与不补偿后筛选：同一原始10¹²脉冲预算</h3>'
                            '<p>14个独立rho，以及相邻rho两两合并后的7个点。两条曲线都包含被丢弃脉冲的发送成本；'
                            '筛选中心随当前有效不补偿数据重新校准。合并点先合并计数再计算成码率。</p>')
                for count in (14,7):
                    body.append(f'<img src="postselection/comparison_{count}.png?v={quote(report["updated_at"],safe="")}">')
                body.append('<p><a href="postselection/index.html">筛选详情、阈值表和中心标定</a></p>')
            elif selection.get('status')=='error':
                body.append('<p>本轮筛选对比未更新：'+html.escape(selection['message'])+'</p>')
            body.append('<h3>配置 '+cohort+'</h3><table><tr><th>rho</th><th>有效秒</th><th>X均值±SD</th><th>Y均值±SD</th><th>Z1均值±SD</th><th>实际发送脉冲对</th><th>扩展倍数</th><th>成码率 @10¹²</th><th>实际量成码率</th><th>状态</th></tr>')
            for g in report['groups']:
                if g['cohort']!=cohort:continue
                values=[fmt(g['rho']) if g['rho'] is not None else '不补偿',str(g['valid_seconds'])]
                values += [fmt(g[k+'_mean'],True)+' ± '+fmt(g[k+'_sd'],True) for k in ('x','y','z1')]
                values += [f'{g["observed_pulse_pairs"]:,}',fmt(g['scale_factor'])+'×' if g['scale_factor'] is not None else '—',fmt(g['finite_keyrate_1e12']),fmt(g['actual_keyrate']),g['rate_status']]
                body.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in values)+'</tr>')
            body.append('</table>')
            paired=[g for g in report.get('paired_groups',[]) if g['cohort']==cohort]
            if paired:
                body.append('<h4>相邻补偿rho两两合并</h4><p>配对(1,2)、(3,4)…(13,14)。先合并发送/探测/错误计数，再扩展到10¹²重新计算；rho为算术平均。不补偿不参与配对。</p>')
                body.append('<table><tr><th>原rho范围</th><th>平均rho</th><th>有效秒</th><th>实际脉冲对</th><th>扩展倍数</th><th>成码率@10¹²</th></tr>')
                for g in paired:
                    values=[f'{g["rho_first"]:.4g} + {g["rho_second"]:.4g}',f'{g["rho"]:.5f}',str(g['valid_seconds']),
                            f'{g["observed_pulse_pairs"]:,}',fmt(g['scale_factor'])+'×',fmt(g['finite_keyrate_1e12'])]
                    body.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in values)+'</tr>')
                body.append('</table>')
            for name in ('qber_','keyrate_','keyrate_pairs_'):
                body.append(f'<img src="{name}{cohort}.png?v={quote(report["updated_at"],safe="")}">')
        if not report['groups']:body.append('<p>正在追赶归档或等待足够的完整补偿周期。</p>')
        temp=self.output/'index.html.tmp';temp.write_text('\n'.join(body),encoding='utf-8');temp.replace(self.output/'index.html')


def math_sqrt(value):return float(np.sqrt(value))


def paired_snapshot(archive,output=None):
    """Render from a read-only SQLite snapshot without taking the live writer's lock."""
    archive=Path(archive).resolve();source=Path(str(archive)+'.analysis')
    obj=LiveAnalysis.__new__(LiveAnalysis)
    obj.archive=archive;obj.output=Path(output or source/'paired_rho')
    obj.output.mkdir(parents=True,exist_ok=True)
    obj.db=sqlite3.connect(f'file:{source/"analysis.sqlite"}?mode=ro',uri=True)
    try:
        obj.db.execute('BEGIN')
        obj.groups={(c,s):json.loads(b) for c,s,b in obj.db.execute('SELECT cohort,stage,body FROM aggregates')}
        state=msgpack.unpackb(lzma.decompress(Path(str(archive)+'.state.xz').read_bytes()),raw=False)
        obj.snapshot={k:state['manifest'].get(k) for k in ('state','downloaded_through','records')}
        obj.snapshot['checkpoint_time']=state['checkpoint_time']
        obj.archive_members=state['manifest']['files']
        report=obj.report()
        print('Paired-rho snapshot:',obj.output/'index.html',flush=True)
        return report
    finally:obj.db.close()


def show_summary(report):
    from rich.console import Console
    from rich.table import Table
    c=Console();c.print(f"[bold]Meta分析[/bold] {report['updated_at']} | 有效 {report['valid']:,} / 无效 {report['invalid']:,} / 待确认 {report['pending']:,}")
    table=Table('配置','rho','秒','Y均值±SD','实际脉冲对','扩展×','成码率@10¹²')
    for g in report['groups']:
        q='—' if g['y_mean'] is None else f"{g['y_mean']*100:.3f} ± {(g['y_sd'] or 0)*100:.3f}%"
        table.add_row(g['cohort'][:6],f"{g['rho']:.3g}" if g['rho'] is not None else '不补偿',str(g['valid_seconds']),q,
                      f"{g['observed_pulse_pairs']:.4g}",f"{g['scale_factor']:.3f}" if g['scale_factor'] is not None else '—',
                      '—' if g['finite_keyrate_1e12'] is None else f"{g['finite_keyrate_1e12']:.4g}")
    c.print(table)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--paired-only',action='store_true',help='Read-only snapshot with adjacent rho pairs; leaves live analysis running')
    parser.add_argument('--interval',type=float,default=30)
    parser.add_argument('--parent-pid',type=int,help='Stop the analysis companion when its downloader exits')
    args=parser.parse_args()
    if args.interval<=0:parser.error('--interval must be positive')
    if args.paired_only:
        paired_snapshot(args.archive,args.output)
        return
    out=Path(args.output or str(args.archive.resolve())+'.analysis');out.mkdir(parents=True,exist_ok=True)
    import fcntl
    with (out/'analysis.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:parser.error('An analyzer is already running for this output')
        analyzer=LiveAnalysis(args.archive,out)
        stopped=False
        def stop(*_):
            nonlocal stopped
            stopped=True
        def should_stop():
            if args.parent_pid:
                try:os.kill(args.parent_pid,0)
                except ProcessLookupError:stop()
            return stopped
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGINT,stop)
        first=True
        try:
            while not should_stop():
                if not args.archive.exists():
                    if args.once:raise FileNotFoundError(args.archive)
                    time.sleep(min(1,args.interval));continue
                before=(dict(analyzer.snapshot),analyzer.archive_members)
                new=analyzer.scan(lambda n,total:print(f'分析归档 {n:,}/{total:,}',flush=True),should_stop=should_stop)
                if new or first or before!=(analyzer.snapshot,analyzer.archive_members) or not (out/'summary.json').exists():
                    report=analyzer.report();show_summary(report)
                    print('Report:',(out/'index.html').resolve(),flush=True)
                    first=False
                if args.once:break
                deadline=time.monotonic()+args.interval
                while not should_stop() and time.monotonic()<deadline:time.sleep(.2)
        finally:
            try:
                processed=analyzer.db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
                if stopped and args.archive.exists() and analyzer.archive_members-processed<=256:
                    # The downloader publishes its final ZIP checkpoint before
                    # stopping this companion. Drain a small final tail as well.
                    analyzer.scan();analyzer.report()
            finally:analyzer.close()


if __name__=='__main__':main()
