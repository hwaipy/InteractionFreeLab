"""Re-run evidence checks and plots. All configuration is in main()."""
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).parent/'results'/'.matplotlib'))
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from model import *
from papers import prl2023,field2024,prx2025
from decoy import estimate,estimate_prx2025
from monte_carlo import simulate


def serial(value):
    if isinstance(value,np.ndarray): return value.tolist()
    if isinstance(value,np.generic): return value.item()
    raise TypeError(type(value).__name__)


def run(output,mc_slots=2_000_000):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report={'all_papers_reproduced':False,'rate_unit':'bits per simultaneous sending time slot',
            'theory_version':'2201.04300v2 Fig 4; journal corresponding figure is Fig 3',
            'checks':[],'unresolved':[
                'Theory: formulas and limiting scalings checked; original digitized curve data unavailable.',
                '2023: 202 km bound replay differs by ~12%; published rounded intermediate values do not explain it.',
                '2024: raw vacuum error constraints conflict with E_k0=M_k0/2 at stated Chernoff intervals.',
                '2024: random-bit vacuum diagnostic still does not reproduce phase-error upper bounds.',
                '2025: 101 km X(2mu,0) PDF text ambiguous (145543908); not silently corrected.',
                'Finite LP: cutoff convergence checked, photon-tail security bound not certified.',
                'Optical hardware: duty-cycle gaps, actual phase-tracking errors and detector dead time are not simulated.'
            ]}
    rows=report['checks']
    for d in prl2023():
        calc=key_from_bounds([d['z']],[d['ze']],d['single_z'],d['phase'],1.1,d['n_slots'],444.83e6)
        rows.append(dict(id=d['id'],level='published_bound_replay_only',calculated_bps=calc['bits_per_second'],published_bps=d['published_bps'],relative_error=calc['bits_per_second']/d['published_bps']-1,
                         pairing_calculated=pairing_rate(d['p_click'],d['lmax'],63),pairing_published=d['pair_rate']))
    for d in field2024():
        c=d['counts']
        replay=key_from_bounds(c['z'][1:,1:],c['ze'][1:,1:],d['published_single_z'],d['published_phase'],1.06,c['n_slots'],d['clock_hz'])
        entry=dict(id=d['id'],level='published_bound_replay_only',calculated_bps=replay['bits_per_second'],published_bps=d['published_bps'],relative_error=replay['bits_per_second']/d['published_bps']-1)
        try: entry['raw_lp']=estimate(c,d['alice'],d['bob'],clock_hz=d['clock_hz'])
        except RuntimeError as exc: entry['raw_lp_error']=str(exc)
        diagnostic=estimate(c,d['alice'],d['bob'],clock_hz=d['clock_hz'],vacuum_errors='random_bit')
        entry['random_bit_vacuum_diagnostic']=diagnostic
        entry['single_z_relative_error']=(np.array(diagnostic['single_z'])/d['published_single_z']-1).tolist()
        # Both throughput interpretations are retained; no fitted count factor.
        entry['optical_assumptions_comparison']=[]
        for efficiency_in_eta in [True,False]:
            for lmin in [1,63]:
                eta_a=d['eta_a']/(.72 if efficiency_in_eta else 1)
                eta_b=d['eta_b']/(.72 if efficiency_in_eta else 1)
                optical=expected_counts(d['alice'],d['bob'],eta_a,eta_b,36.5*800e-12,c['n_slots'],1000,lmin)
                entry['optical_assumptions_comparison'].append(dict(eta_includes_detector=efficiency_in_eta,lmin=lmin,gate_seconds=800e-12,
                    z_signal_ratio=optical['z'][2,2]/c['z'][2,2],x_signal_ratio=optical['x'][2,2]/c['x'][2,2]))
        rows.append(entry)
    for d in prx2025():
        entry=dict(id=d['id'],level='raw_count_estimation',published_bps=d['published_rate']*d['clock_hz'])
        if d['distance']==101:
            entry.update(level='blocked_transcription',reason='X(2mu,0) needs PDF visual verification')
        else:
            r=estimate_prx2025(d['counts'],d['source'],clock_hz=d['clock_hz'])
            entry.update(calculated_bps=r['bits_per_second'],relative_error=r['keyrate']/d['published_rate']-1,result=r)
            entry['cutoff_convergence']={str(k):estimate_prx2025(d['counts'],d['source'],clock_hz=d['clock_hz'],cutoff=k)['keyrate'] for k in [8,12,16]}
            entry['union_budget']=estimate_prx2025(d['counts'],d['source'],clock_hz=d['clock_hz'],budget='union')
        rows.append(entry)
    print('Experimental checks complete',flush=True)
    distances=np.arange(0.,501.,5.)
    curves={}
    fig,ax=plt.subplots(figsize=(8,5),layout='constrained')
    for l in [1,10,100,1000,10000,100000,1000000]:
        data=[optimize_theory(float(d),l) for d in distances]
        curves[str(l)]=data
        y=np.array([r['keyrate'] for r in data]);y[y<=0]=np.nan
        ax.semilogy(distances,y,label=f'L = {l:g}')
    eta=10**(-.2*distances/10)
    bound=-np.log2(1-np.minimum(eta,1-1e-12))
    ax.semilogy(distances,bound,'k--',label='PLOB (channel only)')
    ax.set(xlabel='Total fiber distance (km)',ylabel='Secret bits / sending time slot',ylim=(1e-12,1e-2),title='Zeng et al. 2022: equation-based reproduction')
    ax.legend(ncol=2,fontsize=8);ax.grid(alpha=.2)
    fig.savefig(output/'theory_curves.png',dpi=180);plt.close(fig)
    (output/'theory_curves.json').write_text(json.dumps(dict(distance_km=distances,curves=curves),default=serial,indent=2))
    fig,ax=plt.subplots(figsize=(9,4.5),layout='constrained')
    good=[r for r in rows if 'calculated_bps' in r]
    xx=np.arange(len(good))
    ax.bar(xx-.18,[r['published_bps'] for r in good],width=.36,label='Published')
    ax.bar(xx+.18,[r['calculated_bps'] for r in good],width=.36,label='Recalculated')
    ax.set_yscale('log');ax.set_xticks(xx,[r['id'].replace('_','\n') for r in good],fontsize=8)
    ax.set(ylabel='Secret bits / second',title='First 6: published-bound replay; last 2: raw-count estimation')
    ax.legend();ax.grid(axis='y',alpha=.2);fig.savefig(output/'experimental_checks.png',dpi=180);plt.close(fig)
    s=Source(.4,.08,.3,.25)
    expected=expected_counts(s,s,.1,.1,1e-7,mc_slots,100)
    sampled=simulate(s,s,.1,.1,1e-7,mc_slots,100)
    report['monte_carlo']={'expected':expected,'sampled':sampled}
    fig,ax=plt.subplots(figsize=(7,4),layout='constrained')
    times=np.geomspace(1e-8,1e-3,300)
    for lw in [100,1000,10000]:
        ax.semilogx(times*1e6,.5-.25*phase_visibility(times,linewidth_hz=lw,drift_rad_s=4000),label=f'{lw:g} Hz')
    ax.set(xlabel='Pair separation (microseconds)',ylabel='Raw X error rate',title='PRX 2025 B10: phase-noise model',ylim=(.24,.51))
    ax.legend();ax.grid(alpha=.2);fig.savefig(output/'phase_noise.png',dpi=180);plt.close(fig)
    (output/'validation.json').write_text(json.dumps(report,default=serial,indent=2),encoding='utf-8')
    for r in good: print(f"{r['id']}: {r['calculated_bps']:.6g} vs {r['published_bps']:.6g} bit/s ({r['relative_error']:+.2%}); {r['level']}")
    print('Full reproduction status: NOT YET PASSED; see validation.json')
    return report


def main():
    output=Path(__file__).parent/'results'
    mc_slots=2_000_000
    run(output,mc_slots)


if __name__=='__main__':main()
