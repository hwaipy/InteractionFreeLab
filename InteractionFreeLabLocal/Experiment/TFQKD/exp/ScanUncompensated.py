"""Offline center-calibrated intensity-ratio postselection on no-comp meta.

python ScanUncompensated.py --archive tdc_meta/run_20261031B.zip
Uses the published valid/no-comp seconds from the archive's live analysis.
No network, no datablocks and no changes to the downloader or device outputs.
The 1e12 budget counts ORIGINAL emitted pulse pairs, including discarded frames.
"""
import argparse
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from collections import defaultdict
from datetime import datetime
import csv
import hashlib
import html
import io
import json
import lzma
from pathlib import Path
import sqlite3
import sys
import zipfile

import msgpack
import numpy as np

from FetchTFQKDMeta import _CheckpointZipReader,save_json

ROOT=Path(__file__).resolve().parent


def expected_center(sync_a,sync_b,counts_a,pulses_a,counts_b,pulses_b,vac_counts,vac_pulses,mu_z):
    """Monitor ratio at equal optical efficiency; remove actual arm imbalance."""
    bg=np.asarray(vac_counts)/np.asarray(vac_pulses)
    ya=np.asarray(counts_a)/np.asarray(pulses_a);yb=np.asarray(counts_b)/np.asarray(pulses_b)
    if np.any(bg>=ya) or np.any(bg>=yb) or np.any(ya>=1) or np.any(yb>=1):
        raise ValueError('Invalid background/single-arm yields for center calibration')
    ea=-np.log((1-ya)/(1-bg))/mu_z;eb=-np.log((1-yb)/(1-bg))/mu_z
    return np.asarray(sync_a)/np.asarray(sync_b)*eb/ea,ea,eb


def accumulate_grid(a,b,p,d,e,center,thresholds):
    """Strict center/rho < a/b < center*rho; last inf point retains ALL frames."""
    thresholds=np.asarray(thresholds,float)
    if (not np.isfinite(center) or center<=0 or thresholds[-1]!=np.inf
            or np.any(np.diff(thresholds)<=0) or thresholds[0]<1):
        raise ValueError('Require positive center, sorted rho>=1, and final infinity')
    imbalance=np.full(len(a),np.inf)
    good=(a>0)&(b>0)
    ratio=a[good]/b[good]/center
    imbalance[good]=np.maximum(ratio,1/ratio)
    labels=np.searchsorted(thresholds[:-1],imbalance,side='right')
    total=len(thresholds)
    def accumulate(array):
        flat=array.reshape(-1,len(a));rows=[]
        for values in flat:
            # Integers remain exactly representable for this data volume.
            if int(values.sum(dtype=np.uint64))>=2**53:raise ValueError('Counts exceed exact float64 binning range')
            bins=np.bincount(labels,weights=values.astype(float),minlength=total)
            rows.append(np.cumsum(bins,dtype=np.float64).astype(np.int64))
        return np.stack(rows,axis=1).reshape((total,)+array.shape[:-1])
    return accumulate(p),accumulate(d),accumulate(e),np.bincount(labels,minlength=total).cumsum(),imbalance


def load_frames(archive,output,published=None,cache=None):
    analysis=Path(str(archive)+'.analysis')
    if published is None:published=json.loads((analysis/'summary.json').read_text())
    groups=[g for g in published['groups'] if g['rho'] is None and g['valid_seconds']>0]
    if len(groups)!=1:raise ValueError('Need exactly one QKD configuration with valid no-compensation data')
    group=groups[0]
    db=sqlite3.connect(f'file:{analysis/"analysis.sqlite"}?mode=ro',uri=True)
    try:
        db.execute('BEGIN')
        selected=list(db.execute('SELECT id,member,fetch FROM seconds WHERE valid=1 AND stage=14 AND cohort=? '
            'AND fetch>=? AND fetch<=? ORDER BY slot',(group['cohort'],group['first_FetchTime'],group['last_FetchTime'])))
    finally:db.close()
    if len(selected)!=group['valid_seconds']:raise ValueError('Published report/database mismatch; retry after report update')
    state_bytes=Path(str(archive)+'.state.xz').read_bytes()
    state=msgpack.unpackb(lzma.decompress(state_bytes),raw=False)
    (output/'source_checkpoint.state.xz').write_bytes(state_bytes)
    members=defaultdict(dict)
    for identity,member,fetch in selected:members[member][identity]=fetch
    arrays={'a':[],'b':[],'p':[],'d':[],'e':[]}
    blocks=[];seen=set();phase_bins=set()
    if cache is None:cache={}
    active=set()
    with _CheckpointZipReader(archive,state) as view,zipfile.ZipFile(view) as z:
        for member,identities in members.items():
            info=z.getinfo(member)
            token=(member,info.CRC,info.file_size,info.header_offset)
            active.add(token)
            if token in cache:
                for identity,fetch,phase,values,block in cache[token]:
                    if identity not in identities:continue
                    if identity in seen or fetch!=identities[identity]:raise ValueError('Cached archive identity mismatch')
                    seen.add(identity);phase_bins.add(phase)
                    for key,value in values.items():arrays[key].append(value)
                    blocks.append(block)
                continue
            decoded=[]
            records=msgpack.unpackb(lzma.decompress(z.read(member)),raw=False,strict_map_key=False)
            for r in records:
                identity=str(r['_id'])
                if identity not in identities:continue
                if identity in seen or r['FetchTime']!=identities[identity]:raise ValueError('Archive identity mismatch')
                seen.add(identity);q=r['Data']['QKDQBER'];phase=int(q['PhaseThreshold']);phase_bins.add(phase)
                with np.load(io.BytesIO(q['Intermediate']),allow_pickle=False) as data:
                    meta=json.loads(data['metadata'].tobytes().decode())
                    cfg=meta['configuration']
                    if cfg['IntensityFrame']!=10**9 or cfg['TimeEachBlock']!=10**12:
                        raise ValueError('Expected 1000 aligned 1ms QKD intensity frames')
                    signature={k:meta[k] for k in ('algorithm','configuration','processing','random_numbers_sha256')}
                    signature['phase_bin']=phase
                    cohort=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:16]
                    if cohort!=group['cohort']:raise ValueError('Intermediate cohort mismatch')
                    a=data['syncCountsAlice'].astype(float);b=data['syncCountsBob'].astype(float)
                    p=data['pulseCounts'];d=data['detectionStatistics']
                    e=data['phaseHistogram'][:,:,:phase+1,:].sum(axis=2,dtype=np.uint64).transpose(0,2,1)
                    if a.shape!=(1000,) or b.shape!=(1000,) or p.shape!=(4,4,1000) or d.shape!=p.shape:
                        raise ValueError('Invalid frame arrays')
                    values=dict(a=a,b=b,p=p,d=d,e=e)
                    for key,value in values.items():arrays[key].append(value)
                    block={'FetchTime':r['FetchTime'],'id':identity,'sync_a':float(a.sum()),'sync_b':float(b.sum()),
                        'count_a':int(d[3,0].sum()),'pulse_a':int(p[3,0].sum()),
                        'count_b':int(d[0,3].sum()),'pulse_b':int(p[0,3].sum()),
                        'vac_counts':int(d[0,0].sum()),'vac_pulses':int(p[0,0].sum())}
                    blocks.append(block);decoded.append((identity,r['FetchTime'],phase,values,block))
            # Cache only immutable one-second members. Revalidate CRC on every update.
            if len(decoded)==len(records):cache[token]=decoded
            if len(seen)%100==0:print('Loaded no-compensation seconds',len(seen),'/',len(selected),flush=True)
    if len(seen)!=len(selected) or len(phase_bins)!=1:raise ValueError('Missing selected seconds or mixed phase thresholds')
    for token in list(cache):
        if token not in active:del cache[token]
    arrays={k:np.concatenate(v,axis=-1) for k,v in arrays.items()}
    if int(arrays['p'].sum(dtype=np.uint64))!=group['observed_pulse_pairs']:
        raise ValueError('Pulse count disagrees with published no-compensation report')
    return published,group,arrays,blocks,next(iter(phase_bins))


def run(archive,output=None,center_override=None,*,published=None,cache=None):
    archive=Path(archive).resolve();output=Path(output or str(archive)+'.analysis/postselection')
    output.mkdir(parents=True,exist_ok=True)
    published,source,arrays,blocks,phase=load_frames(archive,output,published,cache)
    save_json(output/'source_live_summary.json',published)
    model=published['model'];mu=model['num_photons'][2]
    keys=('sync_a','sync_b','count_a','pulse_a','count_b','pulse_b','vac_counts','vac_pulses')
    values=np.asarray([[r[k] for k in keys] for r in blocks]);totals=values.sum(axis=0)
    center,eta_a,eta_b=expected_center(*totals,mu)
    center=float(center);eta_a=float(eta_a);eta_b=float(eta_b)
    rng=np.random.default_rng(20261101)
    bootstrap=values[rng.integers(0,len(values),size=(1000,len(values)))].sum(axis=1)
    boot_center,_,_=expected_center(*(bootstrap[:,i] for i in range(8)),mu)
    ci=np.quantile(boot_center,[.025,.975]).tolist()
    used=center if center_override is None else float(center_override)
    print('Expected balanced monitor ratio A/B:',center,'95% bootstrap interval',ci,
          '| raw mean ratio:',totals[0]/totals[1],'| signal efficiency A/B:',eta_a/eta_b,flush=True)
    # Include the experimental compensation rho grid plus a denser local scan.
    finite=sorted(set([1.,1.01,1.02,1.05]+[round(1+i*.05,8) for i in range(1,21)]
        +[round(2+i*.1,8) for i in range(1,11)]+[round(3+i*.25,8) for i in range(1,17)]
        +[8.,10.,15.,20.,50.]+[7**(i/13) for i in range(14)]))
    thresholds=finite+[np.inf]
    p,d,e,frame_counts,imbalance=accumulate_grid(arrays['a'],arrays['b'],arrays['p'],arrays['d'],arrays['e'],used,thresholds)
    n_original=int(p[-1].sum());target=model['target_pulse_pairs'];scale=target/n_original
    sys.path.insert(0,str(ROOT.parent/'dataparse/keyrate'))
    from universal_sns import calKeyRate
    results=[]
    for i,rho in enumerate(thresholds):
        kept=int(p[i].sum());fraction=kept/n_original
        row={'rho':float(rho) if np.isfinite(rho) else None,'center_ratio':used,
             'retained_frames':int(frame_counts[i]),'total_frames':len(imbalance),
             'frame_retention':int(frame_counts[i])/len(imbalance),'original_pulse_pairs':n_original,
             'retained_pulse_pairs':kept,'pulse_retention':fraction,'scale_factor_original':scale,
             'original_pulse_pairs_scaled':target,'retained_pulse_pairs_scaled':kept*scale,
             'keyrate_per_original_pulse':0.,'keyrate_per_retained_pulse':0.,'key_bits_1e12_original':0.,'status':'no_frames'}
        for index,label in ((1,'x'),(2,'y'),(3,'z1')):
            total=int(e[i,index].sum());row[label+'_error']=int(e[i,index,1])/total if total else None
        if kept:
            try:
                result=calKeyRate({'pulses':p[i],'detections':d[i],'errors':e[i]},
                    num_photons=model['num_photons'],phaseSeletcedRatio=(phase+1)/64,strict=True,scale=scale,
                    option=model['option'],profile=model['profile'],epsilon=model['epsilon'],error_correction=model['error_correction'])
                row.update(keyrate_per_original_pulse=result['key_bits']/target,
                    keyrate_per_retained_pulse=result['keyrate'],key_bits_1e12_original=result['key_bits'],
                    status=result['details']['status'])
            except (ValueError,ArithmeticError) as error:
                row.update(keyrate_per_original_pulse=None,keyrate_per_retained_pulse=None,
                           key_bits_1e12_original=None,status='error: '+str(error))
        results.append(row)
    if not np.isclose(results[-1]['keyrate_per_original_pulse'],source['finite_keyrate_1e12'],atol=1e-15,rtol=1e-8):
        raise ValueError('Unfiltered baseline does not reproduce published keyrate')
    summary={'updated_at':datetime.now().astimezone().isoformat(),'archive':str(archive),'model':model,
        'source_report_updated_at':published['updated_at'],'cohort':source['cohort'],
        'valid_no_compensation_seconds':len(blocks),'first':blocks[0]['FetchTime'],'last':blocks[-1]['FetchTime'],
        'original_pulse_pairs':n_original,'scale_factor_original':scale,'estimated_center_ratio':center,
        'center_ratio_used':used,'center_95_ci':ci,'raw_monitor_mean_ratio':float(totals[0]/totals[1]),
        'signal_eta_a':eta_a,'signal_eta_b':eta_b,'mean_signal_efficiency_ratio':eta_a/eta_b,
        'selection':'1ms QKDIntermediate frames; center/rho < syncAlice/syncBob < center*rho; no absolute count cut; infinity keeps all frames',
        'center_method':'center=(sum syncAlice / sum syncBob) * (etaBob / etaAlice), eta from unsifted Z10/Z01 minus vacuum background',
        'normalization':'Same ORIGINAL 1e12 emitted pulse pairs for every threshold; discarded frames still count in the denominator',
        'calibration_note':'Center inferred from this unsifted dataset, not an independent detector-gain calibration; conditional model estimates.',
        'best':max((r for r in results if r['keyrate_per_original_pulse'] is not None),key=lambda r:r['keyrate_per_original_pulse']),
        'results':results}
    save_json(output/'summary.json',summary);save_json(output/'selected_seconds.json',blocks)
    with (output/'thresholds.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    plots(output,summary,published,arrays,blocks)
    page=['<!doctype html><meta charset="utf-8"><title>No-compensation postselection</title>',
          '<style>body{font:16px system-ui;margin:25px}td,th{padding:6px;border:1px solid #ddd}table{border-collapse:collapse}img{max-width:100%}</style>',
          '<h2>不补偿数据：强度比筛选</h2>',
          f'<p>{html.escape(summary["first"])} ～ {html.escape(summary["last"])}，{len(blocks)}个有效秒；中心比 A/B={used:.6f}。</p>',
          '<p>所有阈值使用相同的原始发送脉冲预算10¹²；丢弃的数据仍计入发送成本。中心由未筛选Z统计校准，为离线模型估计。</p>',
          '<p><a href="thresholds.csv">完整阈值CSV</a> · <a href="summary.json">完整结果JSON</a></p>',
          '<img src="comparison_14.png"><img src="comparison_7.png">',
          '<img src="postselection.png"><img src="center_calibration.png">',
          '<table><tr><th>rho</th><th>脉冲保留率</th><th>Y误码</th><th>原始量扩展倍数</th><th>成码率/原始脉冲</th></tr>']
    for r in results:
        page.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in
            [('不筛选' if r['rho'] is None else f'{r["rho"]:.4g}'),f'{r["pulse_retention"]:.3%}',
             '—' if r['y_error'] is None else f'{r["y_error"]:.3%}',f'{scale:.5f}×',
             '—' if r['keyrate_per_original_pulse'] is None else f'{r["keyrate_per_original_pulse"]:.6g}'])+'</tr>')
    page.append('</table>');(output/'index.html').write_text('\n'.join(page),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2),flush=True)
    print('OUTPUT',output,flush=True)
    return summary


def plots(output,summary,published,arrays,blocks):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=[r for r in summary['results'] if r['rho'] is not None and r['rho']<=7]
    for key,count in (('groups',14),('paired_groups',7)):
        comp=sorted((g for g in published.get(key,[]) if g['cohort']==summary['cohort']
                     and g['rho'] is not None and g['finite_keyrate_1e12'] is not None),key=lambda g:g['rho'])
        fig,ax=plt.subplots(figsize=(11,5.5),layout='constrained')
        ax.plot([g['rho'] for g in comp],[g['finite_keyrate_1e12'] for g in comp],'o-',lw=2,
                label=f'Compensation ({count} '+('individual rho)' if count==14 else 'pooled rho pairs)'))
        ax.plot([r['rho'] for r in rows],[r['keyrate_per_original_pulse'] for r in rows],'.-',lw=2,
                label='No compensation + intensity-ratio postselection')
        ax.set(xlabel='rho (arithmetic mean for pooled compensation pairs)' if count==7 else 'rho',
               ylabel='Secret bits / ORIGINAL emitted pulse pair',xlim=(1,7),ylim=(0,None))
        ax.ticklabel_format(axis='y',style='sci',scilimits=(0,0));ax.grid(alpha=.25);ax.legend()
        ax.set_title(f'Both methods: N=10¹² original pulse pairs; discarded pulses count as cost\n'
                     f'Updated {published["updated_at"]} | selection center A/B={summary["center_ratio_used"]:.5f}',fontsize=10)
        name=f'comparison_{count}'
        for ext in ('png','pdf'):
            temp=output/(name+'.tmp.'+ext);fig.savefig(temp,dpi=170);temp.replace(output/(name+'.'+ext))
        plt.close(fig)
    fig,axes=plt.subplots(3,1,figsize=(12,11),sharex=True,layout='constrained')
    axes[0].plot([r['rho'] for r in rows],[r['keyrate_per_original_pulse'] for r in rows],'.-',label='No comp. + postselection')
    comp=[g for g in published['groups'] if g['cohort']==summary['cohort'] and g['rho'] is not None]
    axes[0].plot([g['rho'] for g in comp],[g['finite_keyrate_1e12'] for g in comp],'o--',alpha=.7,label='Gen2 compensation, same archive')
    axes[0].set(ylabel='Secret bits / ORIGINAL pulse pair',ylim=(0,None));axes[0].legend();axes[0].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
    axes[1].plot([r['rho'] for r in rows],[r['pulse_retention']*100 for r in rows],'.-',color='tab:green')
    axes[1].set(ylabel='Retained signal pulses (%)',ylim=(0,100))
    axes[2].plot([r['rho'] for r in rows],[r['y_error']*100 if r['y_error'] is not None else np.nan for r in rows],'.-',color='tab:red')
    axes[2].set(ylabel='Pooled Y QBER (%)',xlabel='Intensity-ratio threshold rho')
    for ax in axes:ax.grid(alpha=.25)
    fig.suptitle(f'No-compensation postselection | calibrated center A/B={summary["center_ratio_used"]:.5f}\n'
                 f'Original pulse budget 10¹² | scale={summary["scale_factor_original"]:.4f}× | {len(blocks)} accepted seconds')
    fig.savefig(output/'postselection.png',dpi=170);fig.savefig(output/'postselection.pdf');plt.close(fig)
    per_center,_,_=expected_center(*(np.asarray([b[k] for b in blocks]) for k in
        ('sync_a','sync_b','count_a','pulse_a','count_b','pulse_b','vac_counts','vac_pulses')),summary['model']['num_photons'][2])
    t=[datetime.fromisoformat(b['FetchTime']) for b in blocks]
    fig,ax=plt.subplots(figsize=(12,4),layout='constrained')
    ax.plot(t,per_center,'.',ms=3,alpha=.4,label='Per-second gain-ratio estimate')
    ax.axhline(summary['center_ratio_used'],color='crimson',label='Calibrated center')
    ax.set(ylabel='Expected syncAlice / syncBob at equal efficiency',xlabel='FetchTime (UTC+08:00)')
    ax.grid(alpha=.25);ax.legend();fig.savefig(output/'center_calibration.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--center-ratio',type=float,help='Explicitly override the calibrated expected A/B ratio')
    args=parser.parse_args();run(args.archive,args.output,args.center_ratio)
