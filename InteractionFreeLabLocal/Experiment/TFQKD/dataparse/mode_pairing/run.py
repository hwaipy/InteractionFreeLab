"""Editable simulation settings, no command-line arguments required."""
import json
from pathlib import Path
from model import Source, expected_counts, average_visibility, analytical_estimate


def main():
    source=Source(mu=.292,nu=.018,p_mu=.199,p_nu=.325)
    total_loss_db=76.5
    detector_efficiency=.70
    insertion_loss_db=1.91
    dark_probability=1e-9  # 10 Hz x 100 ps gate; change for measured background
    n_slots=1e14
    lmin,lmax=25,200000
    clock_hz=1.25e9
    quantum_duty=7/8
    linewidth_hz=100
    residual_drift_rad_s=4000
    eta=detector_efficiency*10**(-(total_loss_db/2+insertion_loss_db)/10)
    counts=expected_counts(source,source,eta,eta,dark_probability,n_slots,lmax,lmin)
    visibility=average_visibility(counts['p_click'],lmax,lmin,clock_hz,
                                  linewidth_hz=linewidth_hz,drift_rad_s=residual_drift_rad_s)
    counts=expected_counts(source,source,eta,eta,dark_probability,n_slots,lmax,lmin,visibility=visibility)
    result=analytical_estimate(counts,source,clock_hz=clock_hz*quantum_duty)
    # Expected synthetic counts are floating-point means. monte_carlo.simulate
    # generates integer realizations; never round tiny means before estimation.
    payload=dict(settings=dict(total_loss_db=total_loss_db,detector_efficiency=detector_efficiency,
        insertion_loss_db=insertion_loss_db,dark_probability=dark_probability,n_slots=n_slots,
        lmin=lmin,lmax=lmax,clock_hz=clock_hz,quantum_duty=quantum_duty,linewidth_hz=linewidth_hz,
        residual_drift_rad_s=residual_drift_rad_s,source=source.__dict__),
        counts={k:v.tolist() if hasattr(v,'tolist') else v for k,v in counts.items()},result=result,
        status='Research simulation; all-paper reproduction not yet passed')
    out=Path(__file__).parent/'results';out.mkdir(exist_ok=True)
    (out/'simulation.json').write_text(json.dumps(payload,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
