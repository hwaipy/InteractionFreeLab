"""Offline regressions for phase discovery, incremental reads and actuator bounds."""
from datetime import datetime, timezone
import io
import json
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from AttenuationStabilizer import (AttenuationStabilizer, INDEX_FILTER, META_FILTER,
                                  Z_FILTER, default_actuators)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


class StabilizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c=AttenuationStabilizer(output_dir=self.tmp.name)
        self.c.log=Mock()

    def test_voltage_step_cannot_exceed_point_one_volt(self):
        self.assertEqual(self.c.max_step_voltage,.1)
        capped=AttenuationStabilizer(max_step_voltage=1,output_dir=self.tmp.name)
        self.assertEqual(capped.max_step_voltage,.1)
        small=AttenuationStabilizer(max_step_voltage=.03,output_dir=self.tmp.name)
        self.assertEqual(small.max_step_voltage,.03)

    def test_default_target_fixed_at_30_db(self):
        self.assertEqual(self.c.targets,{'Alice':30.,'Bob':30.})
        overridden=AttenuationStabilizer(target_db={'Alice':29.},output_dir=self.tmp.name)
        self.assertEqual(overridden.targets,{'Alice':29.,'Bob':30.})

    def frames(self, start=100, end=190, phase=7):
        c=self.c
        for t in range(start,end+1):
            costs=np.ones((4,15))
            costs[0,(t-phase)%15]=.01
            c.cache[str(t)]={'id':str(t),'slot':t,'FetchTime':iso(t),'reasons':[],
                            'zeros':{'4':(0,0,0),'5':(0,0,0)},'costs':costs,
                            'counter':{'2':100,'3':100}}

    def test_phase_learned_without_fixed_wall_clock_offset(self):
        self.frames()
        self.c.learn_phase()
        self.assertEqual(self.c.phase,7)
        self.assertGreaterEqual(self.c.phase_info['supported_cycles'],3)

    def test_ambiguous_sequence_does_not_lock_phase(self):
        self.frames()
        for f in self.c.cache.values(): f['costs'][:]=.01
        self.c.learn_phase()
        self.assertIsNone(self.c.phase)

    def test_history_cannot_drive_writes_and_new_sample_exactly_once(self):
        c=self.c;self.frames();c.learn_phase();c.latest=190;c.live_after=180
        getter=Mock(return_value={'_id':'186','FetchTime':iso(186)})
        c.decode_z=Mock(return_value={'test':'z'});c.update=Mock()
        c.process(getter,enable=True);c.process(getter,enable=True)
        getter.assert_called_once_with('186')
        c.update.assert_called_once_with({'test':'z'},186,enable=True)

    def test_idle_and_cross_second_outage_invalid(self):
        c=self.c;self.frames();c.learn_phase()
        slots={f['slot']:[f] for f in c.cache.values()}
        f=slots[186][0];f['costs'][0,14]=1;f['costs'][1,14]=.01
        self.assertIn('gen1_waiting_or_constant',c.quality(f,slots))
        slots[185][0]['zeros']['4']=(3,0,3);f['zeros']['4']=(3,3,0)
        self.assertIn('cross_second_sync_zero_ch4',c.quality(f,slots))
        f['counter']['2']=1
        self.assertIn('detector_major_drop_ch2',c.quality(f,slots))

    def test_cache_bound_and_seen_id_not_refitted(self):
        c=self.c;c.max_meta=100
        c.model.frame=Mock(side_effect=lambda r:{'id':r['_id'],'slot':r['t']})
        records=[{'_id':str(t),'FetchTime':iso(t),'t':t} for t in range(200)]
        c.ingest(records)
        self.assertEqual(len(c.cache),100)
        c.ingest(records[-5:])
        self.assertEqual(c.model.frame.call_count,200)

    def test_correct_minimal_storage_filters_and_incremental_cursor(self):
        c=self.c;store=Mock();c._worker=Mock(Storage=store)
        store.latest.return_value={'_id':'last','FetchTime':iso(1000)}
        store.range.return_value=[]
        c.tick();self.assertEqual(c.cursor,760)
        c.tick();self.assertEqual(c.cursor,820)
        self.assertEqual(store.latest.call_args.kwargs['filter'],INDEX_FILTER)
        self.assertEqual(store.range.call_args.kwargs['filter'],META_FILTER)
        self.assertNotIn('Data.QKDQBER.Intermediate',META_FILTER)
        self.assertEqual(Z_FILTER,{'_id':1,'FetchTime':1,'Data.QKDQBER.Intermediate':1})
        store.get.assert_not_called()

    def test_given_slopes_and_bounded_positive_correction(self):
        c=self.c;c.latest=200
        expected={'Alice':6.436228748966406,'Bob':2.90778112829884}
        for arm,cfg in default_actuators().items():
            self.assertAlmostEqual(cfg.slope_db_per_volt,expected[arm])
            self.assertIsNone(cfg.min_voltage)
            self.assertIsNone(cfg.max_voltage)
            self.assertIsNone(c.max_total_voltage)
            voltage=[3.09 if arm=='Alice' else 2.59]
            remote=Mock()
            remote.getOutputStatuses.return_value=[True]*3
            remote.getVoltageSetpoints.side_effect=lambda:[0,0,voltage[0]]
            remote.measureVoltages.side_effect=lambda:[0,0,voltage[0]]
            remote.setVoltage.side_effect=lambda ch,v:voltage.__setitem__(0,v)
            c._worker=Mock(**{cfg.service:remote})
            c.voltages[arm]=c.initial_voltages[arm]=voltage[0]
            applied=c.adjust(arm,.02,186)
            self.assertGreater(applied,0);self.assertLessEqual(applied,.02+1e-10)
            remote.setVoltage.assert_called_once()
            c.voltages[arm]=voltage[0]=cfg.limits()[1]
            remote.setVoltage.reset_mock()
            self.assertIsNone(c.adjust(arm,.02,201))
            remote.setVoltage.assert_not_called()

    def test_unscreened_z_decode_and_background_subtraction(self):
        cfg={'TimeEachBlock':10**12,'IntensityFrame':10**9}
        m={'format_version':1,'basis_order':['O','X','Y','Z'],
           'algorithm':'TFQKDQBER-frequency-zero-v1','configuration':cfg,'processing':'test',
           'random_numbers_sha256':'test','analysis_window':{'origin_ps':0,'end_exclusive_ps':10**12}}
        p=np.full((4,4,1000),1000,dtype=np.uint32);d=np.zeros_like(p)
        d[3,0]=2;d[0,3]=3
        b=io.BytesIO();np.savez_compressed(b,metadata=np.frombuffer(json.dumps(m).encode(),dtype=np.uint8),
                                        pulseCounts=p,detectionStatistics=d)
        z=self.c.decode_z({'Data':{'QKDQBER':{'Intermediate':b.getvalue(),'CountsZ':[0,0,0,0]}}})
        self.assertEqual(z['Alice']['counts'],2000)
        self.assertEqual(z['Bob']['counts'],3000)
        self.assertAlmostEqual(z['Alice']['efficiency'],-np.log(1-.002)/.494035)

    def test_stop_prevents_voltage_write_and_isolated_jump_ignored(self):
        c=self.c;c.targets={'Alice':26.0};c.adjust=Mock(return_value=0)
        def sample(e):return {'Alice':{'efficiency':e,'variance':1e-12}}
        stable=10**(-25.85/10)
        for _ in range(3):c.update(sample(stable),100,enable=True)
        c.adjust.assert_called_once()
        c.adjust.reset_mock();c.update(sample(.001),115,enable=True)
        c.adjust.assert_not_called()
        c.stop();c.update(sample(stable),130,enable=True)
        c.adjust.assert_not_called()

    def test_far_target_uses_first_valid_second_and_fast_voltage_cap(self):
        c=self.c;c.targets={'Bob':26.0};c.adjust=Mock(return_value=0)
        eta=10**(-25.4/10)
        c.update({'Bob':{'efficiency':eta,'variance':eta*eta/5000}},100,enable=True)
        self.assertEqual(c.filters['Bob']['phase'],'fast')
        c.adjust.assert_called_once()
        self.assertGreater(c.adjust.call_args.args[1],c.max_step_db)
        self.assertLessEqual(abs(c.adjust.call_args.args[1]/c.actuators['Bob'].slope_db_per_volt),.1+1e-12)

    def test_fast_to_hold_hysteresis(self):
        c=self.c;c.targets={'Bob':26.0};c.adjust=Mock(return_value=0)
        for db,phase in ((25.70,'fast'),(25.82,'fast'),(25.92,'hold'),(25.82,'hold')):
            eta=10**(-db/10)
            c.update({'Bob':{'efficiency':eta,'variance':1e-14}},100,enable=False)
            self.assertEqual(c.filters['Bob']['phase'],phase)

    def test_fast_closed_loop_tolerates_coarse_slopes(self):
        for arm in ('Alice','Bob'):
            for response_factor in (.8,1.,1.2):
                c=AttenuationStabilizer(output_dir=self.tmp.name,target_db={arm:26.})
                c.log=Mock();actual=[25.4];steps=[]
                slope=c.actuators[arm].slope_db_per_volt
                def adjust(name,db,slot):
                    dv=np.trunc(np.clip(db/slope,-.1,.1)*1000)*.001
                    steps.append(float(dv));predicted=float(dv*slope)
                    actual[0]+=predicted*response_factor
                    return predicted
                c.adjust=adjust
                for i in range(3):
                    eta=10**(-actual[0]/10)
                    c.update({arm:{'efficiency':eta,'variance':eta*eta/5000}},100+15*i,enable=True)
                # Hold averages beyond the single-second statistical floor.
                self.assertLess(abs(actual[0]-26.),.15)
                self.assertEqual(c.filters[arm]['phase'],'hold')
                self.assertTrue(all(abs(v)<=.1 for v in steps))

    def test_recorded_bob_response_not_rejected_by_rough_slope(self):
        c=self.c;c.targets={'Bob':30.};c.adjust=Mock(return_value=.290778112829884)
        def sample(db):
            eta=10**(-db/10)
            return {'Bob':{'efficiency':eta,'variance':eta*eta/3000}}
        c.update(sample(27.624623),100,enable=True)
        c.update(sample(28.569949),115,enable=True)
        # Actual response ~0.945dB after a predicted 0.291dB step. This was
        # formerly rejected forever before reaching fast acquisition.
        self.assertEqual(c.adjust.call_count,2)
        self.assertTrue(any(call.args[0]=='response_checked' for call in c.log.call_args_list))
        self.assertFalse(any(call.args[0]=='isolated_z_jump' for call in c.log.call_args_list))

    def test_sustained_new_level_reacquires_instead_of_freezing(self):
        c=self.c;c.targets={'Bob':30.};c.adjust=Mock(return_value=0)
        def sample(eta):return {'Bob':{'efficiency':eta,'variance':eta*eta/4000}}
        for slot in (100,115,130):c.update(sample(.002),slot,enable=False)
        for slot in (145,160):c.update(sample(.0014),slot,enable=True)
        c.adjust.assert_not_called()
        c.update(sample(.0014),175,enable=True)
        c.adjust.assert_called_once()
        self.assertTrue(any(call.args[0]=='jump_reacquired' for call in c.log.call_args_list))
        self.assertEqual(c.filters['Bob']['phase'],'fast')

    def test_single_spike_is_not_reacquired_as_new_level(self):
        c=self.c;c.targets={'Bob':30.}
        def sample(eta):return {'Bob':{'efficiency':eta,'variance':eta*eta/4000}}
        c.update(sample(.002),100)
        c.update(sample(.0014),115)
        c.update(sample(.002),130)
        self.assertFalse(c.filters['Bob']['jumps'])
        self.assertFalse(any(call.args[0]=='jump_reacquired' for call in c.log.call_args_list))


if __name__=='__main__':unittest.main()
