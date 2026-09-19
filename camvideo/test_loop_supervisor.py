import json
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import Mock
from loop_supervisor import LoopSupervisor, credit_history


class SupervisorTests(unittest.TestCase):
    def test_atomic_credit_once_and_original_day(self):
        history={'dias':{'2026-09-13':{'p':{'old':{'nome':'Louça','segundos':6500}}}}}
        entry=dict(session='id',day='2026-09-13',phone='p',task='Louça')
        self.assertTrue(credit_history(history,entry,1200))
        self.assertFalse(credit_history(history,entry,1200))
        self.assertEqual(sum(v['segundos'] for v in history['dias']['2026-09-13']['p'].values()),7200)
        self.assertNotIn('2026-09-14',history['dias'])

    def test_invalid_duration_never_credits(self):
        for value in (float('nan'),0,-1,1800):
            with self.assertRaises(ValueError):credit_history({},dict(session='id',day='d',phone='p',task='t'),value)

    def setup(self,folder):
        engine=Mock();engine.cancelar_sync=threading.Event();engine.lock_historico=threading.Lock()
        auto=Mock();auto.stop_after_round=threading.Event()
        return LoopSupervisor(folder,str(pathlib.Path(folder)/'history.json'),engine,auto,Mock())

    def test_run_intent_and_pending_survive_reload_and_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            s=self.setup(folder);s.begin({'dailyPlan':True},'http://127.0.0.1:1234/')
            s.checkpoint('serial',session='id',task='t',phone='p',day='2026-09-13')
            other=self.setup(folder);self.assertEqual(other.state()['pending']['serial']['session'],'id')
            other.stop();self.assertFalse(other.state()['enabled']);self.assertIn('serial',other.state()['pending'])

    def test_pending_capture_prevents_idle_reset_and_stop_interrupts_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            s=self.setup(folder);s.begin({},'url');s.checkpoint('serial',session='id')
            s.recover=Mock(side_effect=RuntimeError('pending upload'));reset=Mock()
            def stop_wait(_):s.stop();return False
            s.e.cancelar_sync=Mock();s.e.cancelar_sync.is_set.return_value=False;s.e.cancelar_sync.wait.side_effect=stop_wait
            s.run(Mock(),reset);reset.assert_not_called();self.assertIn('serial',s.state()['pending'])

    def test_history_marker_prevents_double_credit_after_interrupted_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            s=self.setup(folder);s.checkpoint('s',session='id',task='t',phone='p',day='2026-09-13')
            history={};credit_history(history,s.state()['pending']['s'],100)
            s.e._ler_historico.return_value=history
            s.credit('s',100)
            self.assertFalse(s.state()['pending'])
            self.assertEqual(history['supervisorSessions']['id']['seconds'],100)

    def test_disconnected_phone_never_clears_capture_intent(self):
        with tempfile.TemporaryDirectory() as folder:
            s=self.setup(folder);s.checkpoint('s',before=[])
            s.e._adb.side_effect=RuntimeError('offline')
            with self.assertRaises(RuntimeError):s.recover()
            self.assertIn('s',s.state()['pending'])
