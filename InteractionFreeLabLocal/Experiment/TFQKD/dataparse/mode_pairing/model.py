"""Mode pairing: explicit time-slot normalization, no SNS/AOPP substitution.

Sources and fidelity limits are documented in README.md and references.json.
"""
from dataclasses import dataclass
from math import exp, log, log1p, expm1, pi, sqrt
import numpy as np
from scipy.optimize import brentq, minimize_scalar
from scipy.special import i0e


def entropy(x):
    x = np.asarray(x, dtype=float)
    if np.any((x < 0) | (x > 1)):
        raise ValueError('entropy argument outside [0,1]')
    out = -np.where(x > 0, x * np.log2(np.maximum(x, 1e-300)), 0) - np.where(x < 1, (1-x)*np.log2(np.maximum(1-x, 1e-300)), 0)
    return float(out) if out.ndim == 0 else out


def pairing_rate(p, lmax, lmin=1):
    """Zeng Eq (4); Zhu 2023 Eq (B7) when lmin>1. Pairs per time slot.

    This is the i.i.d. Bernoulli renewal result, not a detector-dead-time model. See pair_clicks for the operational nearest-click algorithm.
    """
    if not 0 <= p <= 1 or lmin < 1 or lmax < lmin:
        raise ValueError('invalid click probability or pairing window')
    if p == 0: return 0.0
    if p == 1: return 0.5 if lmin == 1 else 0.0
    q = exp((lmin-1)*log1p(-p)) * -expm1((lmax-lmin+1)*log1p(-p))
    return p*q/(1+q)


def pair_clicks(slots, lmax, lmin=1):
    """Greedy adjacent successful clicks; too-close/too-far -> advance first.

    At lmin=1 this is Algorithm 1 of Zeng 2022. Each click used at most once.
    """
    slots = np.asarray(slots)
    if slots.ndim != 1 or np.any(np.diff(slots) <= 0) or lmin < 1 or lmax < lmin:
        raise ValueError('require increasing slots and a valid window')
    pairs, i = [], 0
    while i + 1 < len(slots):
        gap = slots[i+1] - slots[i]
        if lmin <= gap <= lmax:
            pairs.append((i, i+1)); i += 2
        else:
            i += 1
    return np.asarray(pairs, dtype=np.int64).reshape(-1, 2)


def phase_visibility(dt, linewidth_hz=0, drift_rad_s=0, slices=32):
    """PRX 2025 B10: raw equal-intensity X error = 1/2 - visibility/4."""
    if linewidth_hz < 0 or drift_rad_s < 0 or slices < 2:
        raise ValueError('invalid phase noise')
    dt = np.asarray(dt)
    if np.any(dt < 0): raise ValueError('negative interval')
    variance = 4*pi*linewidth_hz*dt + (drift_rad_s*dt)**2
    return np.sinc(2/slices)*np.exp(-variance/2)


def average_visibility(p, lmax, lmin=1, clock_hz=1.25e9, **noise):
    gaps = np.arange(lmin, lmax+1, dtype=float)
    weights = np.exp((gaps-lmin)*log1p(-p))
    return float(np.dot(weights, phase_visibility(gaps/clock_hz, **noise))/weights.sum())


def single_click(a, b, eta_a, eta_b, dark):
    """Phase-averaged exactly-one-detector probability; double clicks excluded."""
    if min(a, b, eta_a, eta_b, dark) < 0 or max(eta_a, eta_b, dark) > 1:
        raise ValueError('invalid optical parameters')
    total = a*eta_a+b*eta_b
    interference = sqrt(a*b*eta_a*eta_b)
    return float(2*(1-dark)*exp(-total/2+interference)*i0e(interference) - 2*(1-dark)**2*exp(-total))


def theory_rate(distance_km, mu, lmax, *, dark=1.2e-8, efficiency=.2,
                loss_db_km=.2, misalignment=.04, f_ec=1.15):
    """Original theory arXiv 2201.04300v2 D1-D15 / Fig 4.

    Uses the paper's low-click approximation D3/D5, deliberately distinct
    from the exact optical simulator below. Infinite decoys, asymptotic.
    """
    eta = efficiency * 10**(-distance_km*loss_db_km/20)
    c = np.array([2*dark, -expm1(-eta*mu)+2*dark*exp(-eta*mu),
                  -expm1(-2*eta*mu)+2*dark*exp(-2*eta*mu)])
    p = (c[0]+2*c[1]+c[2])/4
    z = (2*c[0]*c[2]+2*c[1]**2)/16
    ez = 2*c[0]*c[2]/(16*z)
    n = np.array([2*dark, 1-(1-2*dark)*(1-eta), 1-(1-2*dark)*(1-eta)**2])
    q11 = (mu*exp(-mu))**2*(2*n[0]*n[2]+2*n[1]**2)/(16*z)
    y11 = (1-dark)**2*(eta**2/2+(4*eta-3*eta**2)*dark+4*(1-eta)**2*dark**2)
    ex11 = np.clip(.5-(.5-misalignment)*(1-dark**2)*eta**2/(2*y11), 0, .5)
    rp = pairing_rate(p,lmax)
    signed = rp*z/p**2*(q11*(1-entropy(ex11))-f_ec*entropy(ez))
    return dict(keyrate=max(0.,signed), signed_keyrate=signed, p_click=p,
                pair_rate=rp, z_fraction=z/p**2, q11=q11, e_z=ez, e_phase=float(ex11), mu=mu)


def optimize_theory(distance_km, lmax, **kwargs):
    opt = minimize_scalar(lambda mu: -theory_rate(distance_km,mu,lmax,**kwargs)['signed_keyrate'],
                          bounds=(.001,1.5),method='bounded',options={'xatol':1e-10})
    return theory_rate(distance_km,float(opt.x),lmax,**kwargs)


@dataclass(frozen=True)
class Source:
    mu: float
    nu: float
    p_mu: float
    p_nu: float

    def __post_init__(self):
        if not 0 < self.nu < self.mu or min(self.p_mu,self.p_nu) <= 0 or self.p_mu+self.p_nu >= 1:
            raise ValueError('require 0<nu<mu and positive source probabilities including vacuum')

    @property
    def intensities(self): return np.array([0., self.nu, self.mu])
    @property
    def probabilities(self): return np.array([1-self.p_mu-self.p_nu,self.p_nu,self.p_mu])
    def pair_weights(self,basis):
        p = self.probabilities
        return np.array([p[0]**2,2*p[0]*p[1],2*p[0]*p[2]]) if basis=='Z' else p**2


def expected_counts(alice, bob, eta_a, eta_b, dark, n_slots, lmax, lmin=1,
                    phase_sift=1/8, visibility=1., phase_grid=128):
    """Stationary optical model -> 3x3 Z/X pair counts, order vacuum,nu,mu.

    Integrates independent absolute phase and detector parity in two slots.
    Visibility models residual relative-phase noise (weak-light approximation
    for its attenuation); visibility=1 uses exact threshold-detector parity.
    """
    if n_slots <= 0 or not 0 < phase_sift <= 1 or not 0 <= visibility <= 1:
        raise ValueError('invalid exposure, sifting or visibility')
    a,b = alice.intensities,bob.intensities
    pa,pb = alice.probabilities,bob.probabilities
    c = np.array([[single_click(x,y,eta_a,eta_b,dark) for y in b] for x in a])
    p = float(pa@c@pb)
    factor = n_slots*pairing_rate(p,lmax,lmin)/p**2
    z, ze, x, xe = (np.zeros((3,3)) for _ in range(4))
    theta = np.arange(phase_grid)*2*pi/phase_grid
    for i in range(3):
        for j in range(3):
            sa = [(0,0)] if i==0 else [(0,i),(i,0)]
            sb = [(0,0)] if j==0 else [(0,j),(j,0)]
            for a0,a1 in sa:
                for b0,b1 in sb:
                    w = pa[a0]*pa[a1]*pb[b0]*pb[b1]*c[a0,b0]*c[a1,b1]*factor
                    z[i,j] += w
                    if i and j and (a0==0)==(b0==0): ze[i,j] += w
            s = a[i]*eta_a+b[j]*eta_b
            t = sqrt(a[i]*b[j]*eta_a*eta_b)
            # R no-click minus double no-click = L-only, and vice versa.
            left = (1-dark)*np.exp(-s/2+t*np.cos(theta))-(1-dark)**2*exp(-s)
            right = (1-dark)*np.exp(-s/2-t*np.cos(theta))-(1-dark)**2*exp(-s)
            base = pa[i]**2*pb[j]**2*factor
            if i and j:
                # Same compensated relative phase in two paired pulses.
                gain = np.mean((left+right)**2)
                parity = np.mean((left-right)**2)
                x[i,j] = base*phase_sift*gain
                xe[i,j] = base*phase_sift*(gain-visibility*parity)/2
            else:
                x[i,j] = base*c[i,j]**2
                xe[i,j] = x[i,j]/2
    return dict(z=z,ze=ze,x=x,xe=xe,p_click=p,pair_rate=pairing_rate(p,lmax,lmin),n_slots=n_slots)


def inverse_chernoff(observed, epsilon=1e-10):
    """Bounds on expectation; tail probability epsilon/2 on each side."""
    x = float(observed)
    if x < 0 or not 0 < epsilon < 1: raise ValueError('invalid count/epsilon')
    beta = -log(epsilon/2)
    if x == 0: return 0., beta
    # Solve log(mean/x) to retain accuracy for counts close to zero.
    fun=lambda t: x*(expm1(t)-t)-beta
    lower_t=brentq(fun,-(beta/x+1),0,xtol=1e-14)
    upper_t=brentq(fun,0,log1p(beta/x)+2,xtol=1e-14)
    return x*exp(lower_t), x*exp(upper_t)



def direct_chernoff(mean, epsilon=1e-10):
    mean = max(0.,float(mean)); beta=-log(epsilon/2)
    if mean == 0: return 0.,0.
    fun=lambda x: x*log(x/mean)-x+mean-beta if x else mean-beta
    lo=brentq(fun,0,mean) if mean>beta else 0.
    hi=mean+sqrt(2*mean*beta)+2*beta
    while fun(hi)<0: hi*=2
    return lo,brentq(fun,mean,hi)


def phase_bound(error, nx, nz, epsilon=1e-10):
    """PRX 2025 C7-C9 random-sampling bound (positive-error domain)."""
    if nx<=0 or nz<=0 or error>=.5: return .5
    # At zero errors use a conservative hypergeometric no-error bound.
    if error<=0: return min(.5,-expm1(log(epsilon)/nx))
    q=nx/(nx+nz)
    pref=.5*log((nx+nz)/(error*(1-error)*nx*nz))
    def fun(theta):
        xi=entropy(error+(1-q)*theta)-q*entropy(error)-(1-q)*entropy(error+theta)
        return pref-(nx+nz)*xi*log(2)-log(epsilon)
    if fun(.5-error)>=0: return .5
    return error+brentq(fun,0,.5-error)


def key_from_bounds(z_counts,z_errors,single_z,phase,f_ec,n_slots,clock_hz=1.):
    z=np.asarray(z_counts,float); e=np.asarray(z_errors,float)
    if n_slots<=0 or np.any(e<0) or np.any(e>z) or np.any(np.asarray(single_z)<0):
        raise ValueError('invalid statistics')
    ec=float(np.sum(f_ec*z*entropy(np.divide(e,z,out=np.zeros_like(e),where=z>0))))
    privacy=float(np.sum(single_z))*(1-entropy(min(.5,max(0.,phase))))
    bits=max(0.,privacy-ec)
    return dict(key_bits=bits,keyrate=bits/n_slots,bits_per_second=bits/n_slots*clock_hz,
                privacy_bits=privacy,ec_bits=ec,e_phase=phase)


def analytical_estimate(counts,source,phase_sift=1/8,epsilon=1e-10,
                        f_ec=1.06,clock_hz=1.,finite=True):
    """Symmetric three-intensity estimator, PRX 2025 C1-C9.

    No fitted rate parameters. epsilon is allocated across 54 inverse tails,
    3 direct intervals and random sampling by a conservative union bound.
    """
    eps=epsilon/58
    mu,nu=source.mu,source.nu
    bounds={}
    weights={}
    for label,basis in [('z','Z'),('x','X'),('xe','X')]:
        w=np.outer(source.pair_weights(basis),source.pair_weights(basis))
        if basis=='X': w[1:,1:] *= phase_sift
        weights[label]=w
        obs=np.asarray(counts[label],float)
        bounds[label]=np.array([[inverse_chernoff(v,eps) if finite else (v,v) for v in row] for row in obs])/w[:,:,None]
    def lower_y(label,u,v):
        q=bounds[label]
        weak=q[1,1,0]*exp(2*v)+q[0,0,0]-exp(v)*(q[1,0,1]+q[0,1,1])
        strong=q[2,2,1]*exp(2*u)+q[0,0,1]-exp(u)*(q[2,0,0]+q[0,2,0])
        return max(0.,(u**3*weak-v**3*strong)/(u*u*v*v*(u-v)))
    yz=lower_y('z',mu,nu); yx=lower_y('x',2*mu,2*nu)
    q=bounds['xe']; v=2*nu
    ey=max(0.,(exp(2*v)*q[1,1,1]+q[0,0,1]-exp(v)*(q[0,1,0]+q[1,0,0]))/v**2)
    nz=yz*weights['z'][2,2]*(mu*exp(-mu))**2
    # All phase-sifted nonvacuum X intensity settings contribute to X sample.
    photons=source.intensities*2
    p1=photons*np.exp(-photons)
    x_factor=float(np.sum(weights['x']*np.outer(p1,p1)))
    nx=yx*x_factor; ex=ey*x_factor
    if finite:
        nz=direct_chernoff(nz,eps)[0]; nx=direct_chernoff(nx,eps)[0]; ex=direct_chernoff(ex,eps)[1]
    phase=min(.5,ex/nx) if nx>0 else .5
    if finite: phase=phase_bound(phase,nx,nz,eps)
    out=key_from_bounds([counts['z'][2,2]],[counts['ze'][2,2]],nz,phase,f_ec,counts['n_slots'],clock_hz)
    out.update(single_z=nz,single_x=nx,error_single_x=ex,estimator='symmetric_analytical',finite=finite)
    return out
