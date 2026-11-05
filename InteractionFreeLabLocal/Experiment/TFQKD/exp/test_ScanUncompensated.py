"""Offline checks of center calibration and strict ratio selection."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from ScanUncompensated import expected_center,accumulate_grid,plots


class PostselectionTests(unittest.TestCase):
    def test_both_comparisons_have_two_curves_and_original_budget(self):
        import matplotlib
        matplotlib.use('Agg')
        from matplotlib.figure import Figure
        summary={'results':[{'rho':r,'keyrate_per_original_pulse':r*1e-7,
                            'keyrate_per_retained_pulse':99.,'pulse_retention':.4,'y_error':.02}
                           for r in (1.,2.,7.)],
                 'cohort':'c','center_ratio_used':1.,'scale_factor_original':10.,
                 'model':{'num_photons':[.03,.48,.49]}}
        def groups(n):
            return [{'cohort':'c','rho':1+i*6/(n-1),'finite_keyrate_1e12':2e-6} for i in range(n)]
        published={'groups':groups(14),'paired_groups':groups(7),'updated_at':'test'}
        blocks=[dict(FetchTime='2026-11-01T01:00:00+08:00',sync_a=100,sync_b=100,
                     count_a=100,pulse_a=100000,count_b=100,pulse_b=100000,vac_counts=0,vac_pulses=100000)]
        captured={};original=Figure.savefig
        def save(fig,path,*args,**kwargs):
            if Path(path).name.startswith('comparison_'):
                captured[Path(path).name]=[(line.get_xdata(),line.get_ydata()) for line in fig.axes[0].lines]
            return original(fig,path,*args,**kwargs)
        with tempfile.TemporaryDirectory() as directory,patch.object(Figure,'savefig',save):
            plots(Path(directory),summary,published,{},blocks)
            for count in (14,7):
                curves=captured[f'comparison_{count}.tmp.png']
                self.assertEqual(len(curves),2)
                self.assertEqual(len(curves[0][0]),count)
                np.testing.assert_allclose(curves[1][1],[1e-7,2e-7,7e-7])
                self.assertTrue((Path(directory)/f'comparison_{count}.png').exists())

    def test_center_corrects_real_link_imbalance_not_just_monitor_mean(self):
        mu=.494035;n=10**8;ea=.001;eb=.002
        center,a,b=expected_center(400,1000,-np.expm1(-mu*ea)*n,n,
                                  -np.expm1(-mu*eb)*n,n,0,n,mu)
        self.assertAlmostEqual(float(a),ea)
        self.assertAlmostEqual(float(b),eb)
        self.assertAlmostEqual(float(center),.8)
        self.assertNotAlmostEqual(float(center),.4)

    def test_strict_center_band_and_infinity_keeps_zero_monitor_frames(self):
        a=np.asarray([50.,100.,0.,50.]);b=np.asarray([100.,100.,0.,0.])
        p=np.ones((4,4,4),dtype=np.uint32)
        d=np.zeros_like(p);e=np.zeros((4,2,4),dtype=np.uint64)
        pp,dd,ee,n,_=accumulate_grid(a,b,p,d,e,.5,[1.,1.2,2.,np.inf])
        self.assertEqual(n.tolist(),[0,1,1,4])
        self.assertEqual(pp[:,0,0].tolist(),[0,1,1,4])
        self.assertEqual(int(pp[-1].sum()),int(p.sum()))

    def test_bin_sums_match_independent_boolean_selection(self):
        rng=np.random.default_rng(42);a=rng.integers(1,100,1000).astype(float);b=rng.integers(1,100,1000).astype(float)
        p=rng.integers(0,1000,(4,4,1000),dtype=np.uint32)
        d=rng.integers(0,10,(4,4,1000),dtype=np.uint32);e=rng.integers(0,5,(4,2,1000),dtype=np.uint32)
        thresholds=[1.,1.2,1.5,3.,np.inf];c=.63
        pp,dd,ee,n,_=accumulate_grid(a,b,p,d,e,c,thresholds)
        for i,t in enumerate(thresholds):
            mask=np.ones(1000,dtype=bool) if np.isinf(t) else (a/b>c/t)&(a/b<c*t)
            np.testing.assert_array_equal(pp[i],p[...,mask].sum(axis=-1))
            np.testing.assert_array_equal(dd[i],d[...,mask].sum(axis=-1))
            np.testing.assert_array_equal(ee[i],e[...,mask].sum(axis=-1))


if __name__=='__main__':unittest.main()
