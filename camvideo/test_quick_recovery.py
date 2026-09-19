"""Short recovery passes exercise the real journal with Android mocked."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from loop_supervisor import LoopSupervisor


class QuickRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.history_path=Path(self.folder.name)/'history.json'
        self.engine=Mock()
        self.engine.lock_historico=threading.RLock()
        self.engine._ler_historico.side_effect=self.history
        self.auto=Mock()
        self.supervisor=LoopSupervisor(self.folder.name,str(self.history_path),self.engine,self.auto,Mock())
        self.supervisor.ensure_online=Mock()
        self.supervisor.interleaved_round={'id':'original-round','serials':['serial-a']}
        self.supervisor.checkpoint('serial-a',phone='Phone A',task='Colher Ervas',
                                   day='2026-09-19',before=[],session='capture-a_1')
        self.supervisor.interleaved_round={'id':'later-round','serials':['serial-a']}
        self.engine._adb.side_effect=self.adb
        self.engine._shell_root_bytes.return_value=b''
        self.xml='<hierarchy><node package="com.bakerdata.minute" text="Aguardando"/></hierarchy>'
        self.activity='ACTIVITY com.bakerdata.minute/.MainActivity\n mResumed=true'

    def history(self):
        return json.loads(self.history_path.read_text(encoding='utf-8')) if self.history_path.exists() else {}

    def adb(self, serial, *args, **kwargs):
        if args==('get-state',):return SimpleNamespace(stdout='device')
        if args==('shell','uiautomator','dump','--compressed','/dev/tty'):
            return SimpleNamespace(stdout='UI hierarchy:\n'+self.xml+'\nUI hierarchy dumped to: /dev/tty')
        if args==('shell','dumpsys','activity','top'):return SimpleNamespace(stdout=self.activity)
        if args==('shell','wm','size'):return SimpleNamespace(stdout='Physical size: 1080x1920')
        if args[:3]==('shell','input','tap'):return SimpleNamespace(stdout='')
        self.fail('Unexpected ADB command: '+repr(args))

    def raw(self, task='Colher Ervas', session='capture-a'):
        objects=[{'sessionId':session,'accepted':True,'status':'ended',
                  'taskId':'task-a','taskName':task},
                 {'sessionId':session,'id':'upload-a','durationMs':120000,'status':'done'}]
        return b'\x00'.join(json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode('utf-8')
                          for obj in objects)

    def taps(self):
        return [call for call in self.engine._adb.call_args_list if call.args[1:4]==('shell','input','tap')]

    def assert_no_long_recovery(self):
        self.supervisor.ensure_online.assert_not_called()
        self.auto.xml.assert_not_called()
        self.auto.save.assert_not_called()
        self.auto.launch_minute.assert_not_called()
        self.engine._detectar_tarefa_sessao.assert_not_called()
        self.engine._pastas_gravacao.assert_not_called()
        self.engine._tocar_botao_gravacao.assert_not_called()

    def test_confirmed_capture_credits_original_round_once(self):
        self.engine._shell_root_bytes.return_value=self.raw(task='  CÓLHER  erva ')
        self.assertTrue(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(self.supervisor.state()['pending'],{})
        receipt=self.history()['supervisorSessions']['capture-a_1']
        self.assertEqual(receipt['seconds'],120)
        self.assertEqual(receipt['interleavedRound'],'original-round')
        self.assertEqual(receipt['serial'],'serial-a')
        self.assertTrue(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(len(self.history()['supervisorSessions']),1)
        self.assert_no_long_recovery()
        self.assertFalse(self.taps())

    def test_unconfirmed_capture_preserves_journal_and_history(self):
        original=self.supervisor.state()
        self.assertFalse(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(self.supervisor.state(),original)
        self.assertEqual(self.history(),{})
        self.assert_no_long_recovery()

    def test_confirmed_capture_with_wrong_or_neighbour_task_is_not_credited(self):
        for raw in (self.raw(task='Jardim'),
                    self.raw().replace(b'"taskId":"task-a","taskName":"Colher Ervas"',b'"other":"field"')+
                    b'{"sessionId":"another-session","taskId":"task-a","taskName":"Colher Ervas"}'):
            with self.subTest(raw=raw):
                self.engine._shell_root_bytes.return_value=raw
                self.assertFalse(self.supervisor.recover_quick('serial-a'))
                self.assertIn('serial-a',self.supervisor.state()['pending'])
                self.assertEqual(self.history(),{})

    def test_offline_device_is_not_booted_or_cleared(self):
        for failure in ('offline',RuntimeError('disconnected'),subprocess.TimeoutExpired('adb',3)):
            with self.subTest(failure=failure):
                self.engine._adb.side_effect=failure if isinstance(failure,Exception) else None
                self.engine._adb.return_value=SimpleNamespace(stdout='offline')
                original=self.supervisor.state()
                self.assertFalse(self.supervisor.recover_quick('serial-a'))
                self.assertEqual(self.supervisor.state(),original)
                self.engine._shell_root_bytes.assert_not_called()
                self.assert_no_long_recovery()

    def test_deadline_limits_each_call_and_stops_on_timeout(self):
        clock=[0.0]
        timeouts=[]
        def adb(serial,*args,**kwargs):
            timeouts.append(kwargs['timeout'])
            if args==('get-state',):
                clock[0]+=1
                return SimpleNamespace(stdout='device')
            clock[0]+=kwargs['timeout']
            raise subprocess.TimeoutExpired('adb',kwargs['timeout'])
        def root(serial,command,**kwargs):
            timeouts.append(kwargs['timeout'])
            clock[0]+=1
            return b''
        self.engine._adb.side_effect=adb
        self.engine._shell_root_bytes.side_effect=root
        with patch('loop_supervisor.time.monotonic',side_effect=lambda:clock[0]):
            self.assertFalse(self.supervisor.recover_quick('serial-a',budget=2.5))
        self.assertEqual(timeouts,[2.5,1.5,.5])
        self.assertEqual(clock[0],2.5)
        self.assertIn('serial-a',self.supervisor.state()['pending'])
        self.assert_no_long_recovery()

    def test_zero_budget_does_not_touch_device(self):
        self.assertFalse(self.supervisor.recover_quick('serial-a',budget=0))
        self.engine._adb.assert_not_called()
        self.engine._shell_root_bytes.assert_not_called()

    def test_visible_review_gets_one_safe_tap_and_confirmed_credit(self):
        for resource in ('record-accept','minute-save'):
            with self.subTest(resource=resource):
                if not self.supervisor.state()['pending']:
                    self.supervisor.checkpoint('serial-a',phone='Phone A',task='Colher Ervas',
                                              day='2026-09-19',before=[],session='capture-a_1')
                self.engine._adb.reset_mock()
                self.xml=(f'<hierarchy><node package="com.bakerdata.minute" resource-id="{resource}" '
                          'clickable="true" enabled="true" bounds="[100,200][300,400]"/></hierarchy>')
                self.engine._shell_root_bytes.side_effect=[b'',self.raw()]
                self.assertTrue(self.supervisor.recover_quick('serial-a'))
                self.assertEqual(len(self.taps()),1)
                self.assertEqual(self.taps()[0].args[1:],('shell','input','tap','200','300'))
                self.assert_no_long_recovery()

    def test_save_dialog_tap_without_confirmation_keeps_pending(self):
        self.xml=('<hierarchy><node package="com.bakerdata.minute" text="Salvar este Minute?"/>'
                  '<node package="com.bakerdata.minute" text="Salvar" clickable="true" '
                  'bounds="[20,30][100,90]"/></hierarchy>')
        original=self.supervisor.state()
        self.assertFalse(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(len(self.taps()),1)
        self.assertEqual(self.supervisor.state(),original)

    def test_unrelated_app_or_invalid_review_bounds_never_tapped(self):
        for package,bounds in (('com.other.app','[20,30][100,90]'),
                               ('com.bakerdata.minute','[20,30][10,20]'),
                               ('com.bakerdata.minute','invalid')):
            with self.subTest(package=package,bounds=bounds):
                self.engine._adb.reset_mock()
                self.xml=(f'<hierarchy><node package="{package}" resource-id="record-accept" '
                          f'clickable="true" bounds="{bounds}"/></hierarchy>')
                self.assertFalse(self.supervisor.recover_quick('serial-a'))
                self.assertFalse(self.taps())
                self.assertIn('serial-a',self.supervisor.state()['pending'])

    def test_missing_session_uses_short_root_listing_and_keeps_round_id(self):
        self.supervisor.clear('serial-a')
        self.supervisor.interleaved_round={'id':'original-round','serials':['serial-a']}
        self.supervisor.checkpoint('serial-a',phone='Phone A',task='Colher Ervas',
                                   day='2026-09-19',before=['old'])
        self.engine._shell_root_bytes.side_effect=[b'/recordings/old\n/recordings/capture-a_1\n',self.raw()]
        self.assertTrue(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(self.history()['supervisorSessions']['capture-a_1']['interleavedRound'],'original-round')
        self.assertLessEqual(self.engine._shell_root_bytes.call_args_list[0].kwargs['timeout'],3)
        self.assert_no_long_recovery()

    def test_no_new_capture_clears_intent_but_ambiguous_list_preserves_it(self):
        self.supervisor.clear('serial-a')
        self.supervisor.checkpoint('serial-a',phone='Phone A',task='Colher Ervas',
                                   day='2026-09-19',before=['old'])
        self.engine._shell_root_bytes.return_value=b'/recordings/old\n/recordings/a\n/recordings/b\n'
        self.assertFalse(self.supervisor.recover_quick('serial-a'))
        self.assertIn('serial-a',self.supervisor.state()['pending'])
        self.engine._shell_root_bytes.return_value=b'/recordings/old\n'
        self.assertTrue(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(self.supervisor.state()['pending'],{})
        self.assertEqual(self.history(),{})

    def test_checkpoint_cannot_replace_pending_but_can_attach_session(self):
        original=self.supervisor.state()
        with self.assertRaisesRegex(RuntimeError,'pendente'):
            self.supervisor.checkpoint('serial-a',phone='Other phone',task='Jardim',session='new',before=['new'])
        self.assertEqual(self.supervisor.state(),original)
        self.supervisor.checkpoint('serial-a',session='capture-a_1')
        self.assertEqual(self.supervisor.state(),original)

    def test_growing_known_camera_is_stopped_only_once_across_passes(self):
        self.activity='ACTIVITY com.bakerdata.minute/.EgoCameraPreview\n mResumed=true'
        self.engine._shell_root_bytes.side_effect=[b'',b'100',b'200',b'']
        with patch('loop_supervisor.time.sleep'):
            self.assertFalse(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(len(self.taps()),1)
        self.assertEqual(self.taps()[0].args[1:],('shell','input','tap','540','1770'))
        self.assertTrue(self.supervisor.state()['pending']['serial-a']['quickStopRequested'])
        self.engine._shell_root_bytes.side_effect=None
        self.assertFalse(self.supervisor.recover_quick('serial-a'))
        self.assertEqual(len(self.taps()),1)
        self.assert_no_long_recovery()


if __name__=='__main__':
    unittest.main()
