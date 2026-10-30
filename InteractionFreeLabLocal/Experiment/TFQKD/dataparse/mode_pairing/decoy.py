"""Photon-number linear programming, following field-test 2024 A6-A9.

Numerical reproduction estimator: truncation convergence must be checked.
This implementation does not claim a composable tail/security proof.
"""
import numpy as np
from scipy.special import gammaln
from scipy.optimize import linprog
from model import inverse_chernoff, key_from_bounds


def posterior(source,basis,cutoff):
    ints=source.intensities*(2 if basis=='X' else 1)
    weights=source.pair_weights(basis)
    k=np.arange(cutoff+1)
    poisson=np.exp(-ints[:,None]+k*np.log(np.maximum(ints[:,None],1e-300))-gammaln(k+1))
    poisson[0,1:]=0
    joint=weights[:,None]*poisson
    return joint/joint.sum(axis=0)


def estimate(counts,alice,bob,*,cutoff=12,phase_sift=1/8,epsilon=1e-10,
             f_ec=1.06,clock_hz=1.,key_settings='all',finite=True,vacuum_errors='observed'):
    """LP reproduces published posterior-count formulation, not gain<=1 LP.

    X vacuum rows remain unsifted, matching the paper's recorded statistics.
    Report diagnostics explicitly so normalization and convergence are visible.
    """
    m=(cutoff+1)**2; idx=cutoff+2
    n11={}; solutions={}; matrices={}
    def cb(values,scale):
        return np.array([inverse_chernoff(v,epsilon) if finite else (v,v) for v in values]).T/scale
    for basis,label in [('Z','z'),('X','x')]:
        pa=posterior(alice,basis,cutoff); pb=posterior(bob,basis,cutoff)
        mat=np.einsum('ik,jl->ijkl',pa,pb).reshape(9,m)
        if basis=='X':
            mat.reshape(3,3,m)[1:,1:]*=phase_sift
            mat /= mat.sum(axis=0)
        matrices[basis]=mat
        values=np.asarray(counts[label]).ravel(); scale=values.sum()
        lo,hi=cb(values,scale)
        aa=np.vstack([mat,-mat,np.ones(m)])
        bb=np.r_[hi,-lo,1.]
        obj=np.zeros(m);obj[idx]=1
        opt=linprog(obj,A_ub=aa,b_ub=bb,bounds=(0,None),method='highs',options={'dual_feasibility_tolerance':1e-9,'primal_feasibility_tolerance':1e-9})
        if not opt.success: raise RuntimeError(f'{basis} decoy LP failed: {opt.message}')
        n11[basis]=opt.fun*scale
        solutions[basis]=(aa,bb,scale)
    mat=matrices['X'];aa,bb,scale=solutions['X']
    errors=np.asarray(counts['xe']).copy()
    if vacuum_errors=='random_bit':
        errors[0,:]=counts['x'][0,:]/2
        errors[:,0]=counts['x'][:,0]/2
    elif vacuum_errors!='observed':
        raise ValueError('vacuum_errors must be observed or random_bit')
    lo,hi=cb(errors.ravel(),scale)
    # Joint variables photon counts and photon error counts.
    ab=np.block([[aa,np.zeros_like(aa)],[np.zeros((9,m)),mat],[np.zeros((9,m)),-mat],[-np.eye(m),np.eye(m)]])
    rhs=np.r_[bb,hi,-lo,np.zeros(m)]
    ab=np.vstack([ab,np.r_[np.zeros(m),np.ones(m)]])
    rhs=np.r_[rhs,errors.sum()/scale]
    eq=[]
    for i in range(cutoff+1):
        for j in range(cutoff+1):
            if i==0 or j==0:
                r=np.zeros(2*m);r[i*(cutoff+1)+j]=-.5;r[m+i*(cutoff+1)+j]=1;eq.append(r)
    obj=np.zeros(2*m);obj[m+idx]=-1
    opt=linprog(obj,A_ub=ab,b_ub=rhs,A_eq=eq,b_eq=np.zeros(len(eq)),bounds=(0,None),method='highs',options={'dual_feasibility_tolerance':1e-9,'primal_feasibility_tolerance':1e-9})
    if not opt.success: raise RuntimeError(f'X errors LP failed: {opt.message}')
    ex=-opt.fun*scale
    phase=min(.5,ex/n11['X']) if n11['X']>0 else .5
    selected=matrices['Z'][:,idx].reshape(3,3)*n11['Z']
    sl=np.s_[1:,1:] if key_settings=='all' else np.s_[2:3,2:3]
    out=key_from_bounds(counts['z'][sl],counts['ze'][sl],selected[sl],phase,f_ec,counts['n_slots'],clock_hz)
    out.update(single_z=selected[sl].tolist(),single_x=n11['X'],error_single_x=ex,cutoff=cutoff,
               estimator='posterior_LP_2024',finite=finite,vacuum_errors=vacuum_errors,security_status='numerical reproduction; photon-tail proof not certified')
    return out


def estimate_prx2025(counts,source,*,epsilon=1e-10,clock_hz=1.,cutoff=12,budget='per_bound'):
    """PRX C1-C9 with LP decoys + direct Chernoff + random sampling.

    per_bound follows published individual-bound epsilon convention; union
    splits a total epsilon across bounds. Neither certifies truncated LP tails.
    """
    from model import direct_chernoff, phase_bound
    if budget not in ('per_bound','union'): raise ValueError('unknown epsilon budget')
    eps=epsilon if budget=='per_bound' else epsilon/58
    out=estimate(counts,source,source,epsilon=eps,clock_hz=clock_hz,
                 key_settings='signal',cutoff=cutoff)
    nz=direct_chernoff(np.sum(out['single_z']),eps)[0]
    nx=direct_chernoff(out['single_x'],eps)[0]
    ex=direct_chernoff(out['error_single_x'],eps)[1]
    phase=phase_bound(ex/nx if nx else .5,nx,nz,eps)
    result=key_from_bounds([counts['z'][2,2]],[counts['ze'][2,2]],nz,phase,1.06,counts['n_slots'],clock_hz)
    result.update(single_z=nz,single_x=nx,error_single_x=ex,estimator='PRX_LP_with_direct_and_sampling',
                  budget=budget,cutoff=cutoff,security_status=out['security_status'])
    return result
