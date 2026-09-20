import unittest
from collections import Counter
from unittest.mock import Mock, patch
from automation import Automation


class AtRecordingBoundary(Exception):
    pass


class TaskSearchRetryTests(unittest.TestCase):
    def setUp(self):
        self.engine=Mock()
        self.engine.cancelar_sync.is_set.return_value=False
        self.engine.cancelar_sync.wait.return_value=False
        self.engine._ler_geracao.return_value=1
        self.engine._camera_pronta.return_value=120
        self.engine._uso_tarefa.return_value=0
        self.a=Automation(self.engine,Mock())
        self.a.rotate_left=Mock()
        self.a.navigate=Mock(side_effect=self.navigate)
        self.calls=Counter()
        self.targets={f'p{i}':(f's{i}',str(i)) for i in range(4)}
        self.installed={s:{'confirmed':True,'assetId':'same','name':'fixture.mov'} for s,_ in self.targets.values()}
        self.failures=1
        self.failure='A lista do Minute não está visível; rolagem interrompida'

    def navigate(self,serial,task):
        self.calls[serial]+=1
        if serial=='s0' and self.calls[serial]<=self.failures:
            raise RuntimeError(self.failure)

    def run_cycle(self):
        with patch('automation.RecordingStartGroup',side_effect=AtRecordingBoundary):
            self.a._run_cycle(self.targets,Mock(),self.installed,'Tarefa',True,require_all_ready=True,tolerate_failures=True)

    def test_retry_revisits_all_four_before_record_boundary(self):
        with self.assertRaises(AtRecordingBoundary):self.run_cycle()
        self.assertEqual(dict(self.calls),{f's{i}':2 for i in range(4)})
        self.assertTrue(all(row['stage']=='Pronto' for row in self.a.snapshot().values()))
        self.engine._tocar_botao_gravacao.assert_not_called()

    def test_persistent_failure_stops_after_three_attempts(self):
        self.failures=99
        with self.assertRaisesRegex(RuntimeError,'Gravação não iniciada'):self.run_cycle()
        self.assertEqual(dict(self.calls),{f's{i}':3 for i in range(4)})
        self.engine._tocar_botao_gravacao.assert_not_called()

    def test_pending_review_is_not_retried(self):
        self.failure='Há uma gravação na tela de revisão; salve ou descarte antes de iniciar outra'
        with self.assertRaisesRegex(RuntimeError,'tela de revisão'):self.run_cycle()
        self.assertEqual(dict(self.calls),{f's{i}':1 for i in range(4)})

    def test_cancel_during_delay_prevents_retry(self):
        def cancel(_):
            self.engine.cancelar_sync.is_set.return_value=True
            return True
        self.engine.cancelar_sync.wait.side_effect=cancel
        with self.assertRaises(InterruptedError):self.run_cycle()
        self.assertEqual(dict(self.calls),{f's{i}':1 for i in range(4)})
        self.engine._tocar_botao_gravacao.assert_not_called()

if __name__=='__main__':unittest.main()
