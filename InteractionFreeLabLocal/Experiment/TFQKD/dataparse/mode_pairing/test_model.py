import unittest
import numpy as np
from model import *
from monte_carlo import simulate
from papers import field2024,prl2023,prx2025
from decoy import estimate_prx2025


class ModelTests(unittest.TestCase):
    def test_pairing_limits(self):
        for p in [1e-8,.001,.5,1.]:
            self.assertAlmostEqual(pairing_rate(p,1),p*p/(1+p))
        self.assertAlmostEqual(pairing_rate(.01,100000),.005)
        self.assertEqual(pairing_rate(0,10),0)

    def test_pair_uniqueness_and_window(self):
        slots=np.array([1,2,3,5,7,20,24,30])
        pairs=pair_clicks(slots,4,2)
        np.testing.assert_array_equal(slots[pairs],[[3,5],[20,24]])
        self.assertEqual(len(np.unique(pairs)),pairs.size)

    def test_published_pair_rates(self):
        for d in prl2023():
            self.assertLess(abs(pairing_rate(d['p_click'],d['lmax'],63)/d['pair_rate']-1),.006)

    def test_chernoff(self):
        for x in [0,1,100,1e8]:
            lo,hi=inverse_chernoff(x)
            self.assertLessEqual(lo,x);self.assertGreaterEqual(hi,x)
            if x:
                for mean in [lo,hi]:
                    self.assertAlmostEqual(mean-x+x*np.log(x/mean),-np.log(5e-11),places=5)

    def test_zero_noise_x_floor(self):
        s=Source(.1,.01,.3,.2)
        r=expected_counts(s,s,1e-4,1e-4,0,1e12,1000)
        self.assertAlmostEqual(r['xe'][2,2]/r['x'][2,2],.25,places=4)
        self.assertLess(float(phase_visibility(1e-3,linewidth_hz=100)),float(phase_visibility(1e-6,linewidth_hz=100)))

    def test_theory_scaling(self):
        # Negligible dark counts: 100 km adds 20dB total loss.
        short=optimize_theory(200,1,dark=0)['keyrate']/optimize_theory(300,1,dark=0)['keyrate']
        long=optimize_theory(200,10**9,dark=0)['keyrate']/optimize_theory(300,10**9,dark=0)['keyrate']
        self.assertAlmostEqual(short,100,delta=.5)
        self.assertAlmostEqual(long,10,delta=.1)

    def test_monte_carlo_optics(self):
        s=Source(.4,.08,.3,.25);n=2_000_000
        expected=expected_counts(s,s,.1,.1,1e-7,n,100)
        sampled=simulate(s,s,.1,.1,1e-7,n,100)
        for label in ['z','x','xe']:
            self.assertTrue(np.all(abs(sampled[label]-expected[label]) < 6*np.sqrt(expected[label]+1)))
            self.assertTrue(np.issubdtype(sampled[label].dtype,np.integer))
        self.assertLess(abs(sampled['p_click']/expected['p_click']-1),.02)
        self.assertLess(abs(sampled['pair_rate']/expected['pair_rate']-1),.02)

    def test_field_key_accounting_only(self):
        for d in field2024():
            r=key_from_bounds(d['counts']['z'][1:,1:],d['counts']['ze'][1:,1:],d['published_single_z'],d['published_phase'],1.06,2e12,d['clock_hz'])
            self.assertLess(abs(r['key_bits']/d['published_bits']-1),.001)

    def test_prx_raw_counts_regression(self):
        # Regression for current estimator, not a claim of exact reproduction.
        for d in prx2025()[1:]:
            r=estimate_prx2025(d['counts'],d['source'])
            self.assertLess(abs(r['keyrate']/d['published_rate']-1),.05)

    def test_invalid_parameters(self):
        for args in [(-1,4,1),(.1,1,2),(1.1,4,1)]:
            with self.assertRaises(ValueError): pairing_rate(*args)
        with self.assertRaises(ValueError): Source(.1,.2,.2,.3)


if __name__=='__main__': unittest.main()
