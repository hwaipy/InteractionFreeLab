"""Pulse-level experiment simulator; integer statistics, reproducible seed."""
import numpy as np
from model import pair_clicks


def simulate(alice,bob,eta_a,eta_b,dark,n_slots,lmax,*,lmin=1,phases=16,
             clock_hz=1.25e9,linewidth_hz=0.,drift_rad_s=0.,seed=20261030):
    """Independent source choices -> BS -> threshold detectors -> greedy pairs.

    Gaussian phase increments model two equal Lorentzian linewidths. A single
    run draws a constant residual frequency drift with the requested standard
    deviation. No dead-time model; lmin is a postprocessing cut only.
    """
    if not isinstance(n_slots,int) or n_slots<=0 or phases<2 or phases%2:
        raise ValueError('positive integer n_slots and even phase count required')
    rng=np.random.default_rng(seed)
    ia=rng.choice(3,n_slots,p=alice.probabilities);ib=rng.choice(3,n_slots,p=bob.probabilities)
    pha=rng.integers(phases,size=n_slots);phb=rng.integers(phases,size=n_slots)
    residual=np.zeros(n_slots)
    if linewidth_hz:
        residual=np.cumsum(rng.normal(0,np.sqrt(4*np.pi*linewidth_hz/clock_hz),n_slots))
    if drift_rad_s: residual+=np.arange(n_slots)*rng.normal(0,drift_rad_s)/clock_hz
    a=alice.intensities[ia]*eta_a;b=bob.intensities[ib]*eta_b
    interference=np.sqrt(a*b)*np.cos(2*np.pi*(pha-phb)/phases+residual)
    left=rng.random(n_slots)<-np.expm1(np.log1p(-dark)-(a+b)/2-interference)
    right=rng.random(n_slots)<-np.expm1(np.log1p(-dark)-(a+b)/2+interference)
    slots=np.flatnonzero(left^right)
    pairs=pair_clicks(slots,lmax,lmin)
    z,ze,x,xe=(np.zeros((3,3),dtype=np.int64) for _ in range(4))
    for front,rear in slots[pairs]:
        a0,a1,b0,b1=ia[front],ia[rear],ib[front],ib[rear]
        def label(i,j):
            if i==j==0: return '0',0
            if i==0 or j==0: return 'Z',max(i,j)
            if i==j: return 'X',i
            return '-',0
        ba,i=label(a0,a1);bb,j=label(b0,b1)
        if ba in ('0','Z') and bb in ('0','Z'):
            z[i,j]+=1
            if i and j and (a0==0)==(b0==0): ze[i,j]+=1
        if ba in ('0','X') and bb in ('0','X'):
            if i and j:
                delta=int((pha[rear]-pha[front]-phb[rear]+phb[front])%phases)
                if delta not in (0,phases//2): continue
                x[i,j]+=1
                parity=int(left[front]!=left[rear])
                xe[i,j]+=parity != (delta==phases//2)
            else:
                x[i,j]+=1;xe[i,j]+=rng.integers(2)
    return dict(z=z,ze=ze,x=x,xe=xe,n_slots=n_slots,p_click=len(slots)/n_slots,
                pair_rate=len(pairs)/n_slots,clicks=len(slots),pairs=len(pairs),seed=seed)
