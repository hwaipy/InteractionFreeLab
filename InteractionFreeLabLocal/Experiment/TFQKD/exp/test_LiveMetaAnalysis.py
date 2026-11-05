"""Offline archive/analysis regressions; no broker, SSH or hardware required."""
from datetime import datetime,timedelta,timezone
import hashlib
from contextlib import redirect_stdout,redirect_stderr
import io
import json
import lzma
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import zipfile

import msgpack
import numpy as np

from FetchTFQKDMeta import _direct_follow,_receive_follow,iter_metas,resolve_live_range,main
from LiveMetaAnalysis import LiveAnalysis,metric,infer_phase,RHOS


class LiveAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.archive=self.root/'test.zip'
        self.analysis=LiveAnalysis(self.archive)
        self.addCleanup(self.analysis.close)
        self.base=1793437200
        cfg={'TimeEachBlock':10**12,'IntensityFrame':10**12}
        m={'format_version':1,'algorithm':'TFQKDQBER-frequency-zero-v1','basis_order':['O','X','Y','Z'],
           'configuration':cfg,'processing':'test','random_numbers_sha256':'test',
           'analysis_window':{'origin_ps':0,'end_exclusive_ps':10**12}}
        p=np.full((4,4,1),1000000,dtype=np.uint32);d=np.full_like(p,1000)
        h=np.zeros((4,1,64,2),dtype=np.uint32);h[:,:,0,0]=100;h[:,:,0,1]=2
        b=io.BytesIO();np.savez_compressed(b,metadata=np.frombuffer(json.dumps(m).encode(),dtype=np.uint8),
            pulseCounts=p,detectionStatistics=d,phaseHistogram=h)
        self.intermediate=b.getvalue()

    def record(self,i,held=False,zero=False):
        slot=self.base+i;stage=slot%15;counts={}
        for idx,ch in enumerate(('4','5')):
            matrix=self.analysis.model.matrices[idx][0]
            v=np.maximum(1,np.rint(matrix[(15 if held else 0)*25+stage*25+12]*10000)).astype(int).tolist()
            if zero:v[50:56]=[0]*6
            counts[ch]=v
        return {'_id':str(slot),'FetchTime':datetime.fromtimestamp(slot,timezone.utc).isoformat(),
            'Data':{'Counter':{'2':2000000,'3':2000000},
                'ChannelMonitor':{'Configuration':{'Frequency':1000},'CountSections':counts},
                'QKDQBER':{'Intermediate':self.intermediate,'PhaseThreshold':7,'CountsZ':[0,0,0,0]}}}

    def write(self,rows):
        with zipfile.ZipFile(self.archive,'w',compression=zipfile.ZIP_STORED) as z:
            for i,r in enumerate(rows):
                z.writestr(f'{i:06d}.msgpack.xz',lzma.compress(msgpack.packb([r],use_bin_type=True),preset=1))

    def test_resume_idempotent_and_quality_unscreened_statistics(self):
        rows=[self.record(i,held=i==75,zero=i==60) for i in range(150)]
        self.write(rows)
        self.assertEqual(self.analysis.scan(),150)
        self.assertEqual(self.analysis.scan(),0)
        valid=self.analysis.db.execute('SELECT COUNT(*) FROM seconds WHERE valid=1').fetchone()[0]
        self.assertGreater(valid,100)
        self.assertEqual(sum(g['seconds'] for g in self.analysis.groups.values()),valid)
        for i in (60,75):
            self.assertEqual(self.analysis.db.execute('SELECT valid FROM seconds WHERE id=?',(str(self.base+i),)).fetchone()[0],0)
        self.assertEqual(len({s for (c,s),g in self.analysis.groups.items() if g['seconds']}),15)
        resumed=LiveAnalysis(self.archive)
        try:
            self.assertEqual(resumed.scan(),0)
            self.assertEqual(sum(g['seconds'] for g in resumed.groups.values()),valid)
        finally:resumed.close()
        for g in self.analysis.groups.values():
            if g['seconds']:
                self.assertEqual(g['p'][0][0],g['seconds']*1000000)
                self.assertEqual(g['e'][2][1],g['seconds']*2)

    def test_partial_tail_pending_and_archive_rollback_subtracts_aggregates(self):
        rows=[self.record(i) for i in range(160)];self.write(rows)
        self.analysis.scan()
        self.write(rows[:110]);self.analysis.scan()
        self.assertEqual(self.analysis.db.execute('SELECT COUNT(*) FROM seconds').fetchone()[0],110)
        valid=self.analysis.db.execute('SELECT COUNT(*) FROM seconds WHERE valid=1').fetchone()[0]
        self.assertEqual(sum(g['seconds'] for g in self.analysis.groups.values()),valid)
        self.assertGreater(valid,60)

    def test_local_report_scaling_and_files(self):
        self.write([self.record(i) for i in range(120)])
        self.analysis.scan()
        r=self.analysis.report(compute_rates=False)
        self.assertEqual(len(r['groups']),15)
        self.assertEqual(len(r['paired_groups']),7)
        for i,g in enumerate(r['paired_groups']):
            self.assertEqual(g['rho'],(RHOS[2*i]+RHOS[2*i+1])/2)
            expected=sum(r['groups'][j]['observed_pulse_pairs'] for j in (2*i,2*i+1))
            self.assertEqual(g['observed_pulse_pairs'],expected)
            self.assertAlmostEqual(g['scale_factor']*expected/10**12,1.)
        for g in r['groups']:
            self.assertAlmostEqual(g['scale_factor']*g['observed_pulse_pairs']/10**12,1.)
            self.assertAlmostEqual(g['y_mean'],2/102)
            self.assertIsNone(g['finite_keyrate_1e12'])
        for name in ('index.html','summary.json','by_rho.csv','seconds.csv'):
            self.assertTrue((self.analysis.output/name).exists())

    def test_paired_rate_recalculates_from_summed_counts_not_mean_rates(self):
        def group(value):
            return {'seconds':value,'phase_bin':7,
                    'p':np.full((4,4),value*1000000).tolist(),
                    'd':np.full((4,4),value*1000).tolist(),
                    'e':np.full((4,2),value*10).tolist()}
        self.analysis.groups={('test',0):group(2),('test',1):group(3),('test',14):group(100)}
        cal=Mock(return_value={'keyrate':.123,'key_bits':42.,'details':{'status':'estimated'}})
        import sys
        with patch.dict(sys.modules,{'universal_sns':SimpleNamespace(calKeyRate=cal)}):
            paired=self.analysis.paired_rates()
        self.assertEqual(cal.call_count,2)  # one scaled calculation, one actual
        np.testing.assert_array_equal(cal.call_args_list[0].args[0]['pulses'],np.full((4,4),5000000))
        np.testing.assert_array_equal(cal.call_args_list[0].args[0]['detections'],np.full((4,4),5000))
        np.testing.assert_array_equal(cal.call_args_list[0].args[0]['errors'],np.full((4,2),50))
        self.assertEqual(paired[0]['valid_seconds'],5)
        self.assertEqual(paired[0]['finite_keyrate_1e12'],.123)
        self.assertEqual(paired[0]['rho'],(RHOS[0]+RHOS[1])/2)
        self.assertTrue(all(g['rate_status']=='incomplete_pair' for g in paired[1:]))

    def test_direct_archive_does_not_start_ssh_and_preserves_original(self):
        record=self.record(0);payload=lzma.compress(msgpack.packb([record],use_bin_type=True))
        begin=record['FetchTime'];end=(datetime.fromisoformat(begin)+timedelta(seconds=1)).isoformat()
        manifest={'begin':begin,'requested_end':end,'windows':0,'files':0,'records':0,'compressed_bytes':0,'state':'following','mode':'follow'}
        with zipfile.ZipFile(self.archive,'w'):pass
        packets=iter([({'kind':'chunk','index':0,'begin':begin,'end':end,'records':1,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()},payload),
                      ({'kind':'done','windows':1,'end':end},b'')])
        with patch('FetchTFQKDMeta.subprocess.Popen') as popen:
            _receive_follow(self.archive,manifest,packets=packets)
            popen.assert_not_called()
        saved=list(iter_metas(self.archive))
        self.assertEqual(saved,[record])

    def test_direct_source_projection_and_exact_bounds(self):
        record=self.record(0);start=record['FetchTime'];stop=(datetime.fromisoformat(start)+timedelta(seconds=1)).isoformat()
        worker=Mock();worker.Storage.latest.return_value={'FetchTime':start,'_id':record['_id']}
        worker.Storage.range.return_value=[record]
        packets=list(_direct_follow(start,0,1,0,end=stop,worker=worker))
        self.assertEqual([p[0]['kind'] for p in packets],['chunk','done'])
        self.assertEqual(worker.Storage.latest.call_args.kwargs['filter'],{'_id':1,'FetchTime':1})
        # Full archive queries intentionally have no lossy projection.
        self.assertNotIn('filter',worker.Storage.range.call_args.kwargs)

    def saved_range(self):
        saved={'begin':'2026-10-31T17:00:00+08:00','requested_end':'2026-11-02T06:00:00+08:00',
               'downloaded_through':'2026-10-31T21:01:18+08:00'}
        Path(str(self.archive)+'.state.xz').write_bytes(lzma.compress(msgpack.packb({'manifest':saved},use_bin_type=True)))
        return saved

    def test_resume_keeps_saved_bounds_despite_changed_code_defaults(self):
        saved=self.saved_range()
        begin,end,actual=resolve_live_range(self.archive,default_begin='2026-10-31 22:00:00',default_end='2026-11-03 06:00:00')
        self.assertEqual((begin,end),(saved['begin'],saved['requested_end']))
        self.assertEqual(actual,saved)
        with self.assertRaisesRegex(ValueError,'--output'):
            resolve_live_range(self.archive,begin='2026-10-31 22:00:00')
        self.assertEqual(resolve_live_range(self.root/'new.zip',default_begin='2026-10-31 22:00:00'),
                         ('2026-10-31 22:00:00',None,None))

    def test_cli_validates_before_starting_analysis(self):
        self.saved_range()
        with patch('FetchTFQKDMeta.subprocess.Popen') as popen,patch('FetchTFQKDMeta.follow_download') as follow:
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
                main(['--output',str(self.archive),'--begin','2026-10-31 22:00:00'])
            self.assertEqual(error.exception.code,2)
            popen.assert_not_called();follow.assert_not_called()
            with redirect_stdout(io.StringIO()):main(['--output',str(self.archive)])
            self.assertEqual(follow.call_args.args[1],'2026-10-31T17:00:00+08:00')
            self.assertTrue(callable(follow.call_args.kwargs['on_ready']))
            # Analysis waits until the real downloader has acquired its lock
            # and validated the archive, not merely until CLI parsing finishes.
            popen.assert_not_called()


if __name__=='__main__':unittest.main()
