"""Exercise durable capture receipts with the real supervisor; Android is mocked."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from interleaved_video_rotation import InterleavedVideoRotation
from loop_supervisor import LoopSupervisor


class InterleavedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.area = self.folder.name
        self.history_path = Path(self.area) / 'history.json'
        self.rotation_path = Path(self.area) / 'rotation.json'
        self.videos = ['first.mov', 'second.mov']
        self.targets = {'p1': ('s1', 1), 'p2': ('s2', 2)}
        self.engine = Mock()
        self.engine.cancelar_sync = threading.Event()
        self.engine.lock_historico = threading.RLock()
        self.engine._ler_historico.side_effect = self.history
        self.engine._adb.return_value = SimpleNamespace(stdout='device')
        self.engine._detectar_tarefa_sessao.return_value = ('id', 'Task A')
        self.auto = Mock()
        self.auto.stop_after_round = threading.Event()
        self.rotation = InterleavedVideoRotation(self.rotation_path)
        self.rotation.begin_round('Task A', self.videos, 0, self.targets)
        self.supervisor = self.new_supervisor()
        self.supervisor.interleaved_round = self.rotation.pending_round

    def history(self):
        if not self.history_path.exists():
            return {}
        return json.loads(self.history_path.read_text(encoding='utf-8'))

    def new_supervisor(self):
        return LoopSupervisor(self.area, str(self.history_path), self.engine, self.auto, Mock())

    def checkpoint(self, supervisor, serial, session=True):
        supervisor.checkpoint(serial, phone=serial.replace('s', 'p'), task='Task A',
                              day='2026-09-19', before=[])
        if session:
            supervisor.checkpoint(serial, session='capture-'+serial)

    def test_restart_recovers_remaining_save_and_advances_exactly_once(self):
        self.checkpoint(self.supervisor, 's1')
        self.checkpoint(self.supervisor, 's2')
        self.supervisor.credit('s1', 120)
        before = InterleavedVideoRotation(self.rotation_path)
        self.assertFalse(before.reconcile(self.history()['supervisorSessions']))
        self.assertEqual(before.position('Task A', self.videos), 0)
        restarted = self.new_supervisor()
        with patch('loop_supervisor.confirmed_recording_seconds', return_value=120):
            restarted.recover()
        self.assertEqual(restarted.state()['pending'], {})
        ledger = self.history()['supervisorSessions']
        self.assertEqual({row['serial'] for row in ledger.values()}, {'s1', 's2'})
        self.assertEqual({row['interleavedRound'] for row in ledger.values()}, {self.rotation.pending_round['id']})
        reloaded = InterleavedVideoRotation(self.rotation_path)
        self.assertTrue(reloaded.reconcile(ledger))
        self.assertEqual(reloaded.position('Task A', self.videos), 1)
        self.assertFalse(InterleavedVideoRotation(self.rotation_path).reconcile(ledger))

    def test_recovery_without_second_capture_keeps_video_position(self):
        self.checkpoint(self.supervisor, 's1')
        self.checkpoint(self.supervisor, 's2', session=False)
        self.engine._pastas_gravacao.return_value = set()
        with patch('loop_supervisor.confirmed_recording_seconds', return_value=120):
            self.new_supervisor().recover()
        self.assertEqual(self.supervisor.state()['pending'], {})
        reloaded = InterleavedVideoRotation(self.rotation_path)
        self.assertFalse(reloaded.reconcile(self.history()['supervisorSessions']))
        self.assertEqual(reloaded.position('Task A', self.videos), 0)

    def test_failed_second_recovery_does_not_advance_until_both_receipts_exist(self):
        self.checkpoint(self.supervisor, 's1')
        self.checkpoint(self.supervisor, 's2')
        def connection(serial, *args, **kwargs):
            if serial == 's2':
                raise RuntimeError('Still disconnected')
            return SimpleNamespace(stdout='device')
        self.engine._adb.side_effect = connection
        with patch('loop_supervisor.confirmed_recording_seconds', return_value=120):
            with self.assertRaisesRegex(RuntimeError, 'disconnected'):
                self.new_supervisor().recover()
        pending = InterleavedVideoRotation(self.rotation_path)
        self.assertFalse(pending.reconcile(self.history()['supervisorSessions']))
        self.engine._adb.side_effect = None
        with patch('loop_supervisor.confirmed_recording_seconds', return_value=120):
            self.new_supervisor().recover()
        self.assertTrue(pending.reconcile(self.history()['supervisorSessions']))
        self.assertEqual(len(self.history()['supervisorSessions']), 2)

    def test_unrelated_phone_and_later_plain_capture_do_not_inherit_round(self):
        self.checkpoint(self.supervisor, 's3')
        self.assertNotIn('interleavedRound', self.supervisor.state()['pending']['s3'])
        self.checkpoint(self.supervisor, 's1')
        self.assertEqual(self.supervisor.state()['pending']['s1']['interleavedRound'], self.rotation.pending_round['id'])
        self.supervisor.interleaved_round = None
        original = self.supervisor.state()['pending']['s1']
        with self.assertRaisesRegex(RuntimeError, 'pendente'):
            self.checkpoint(self.supervisor, 's1')
        self.assertEqual(self.supervisor.state()['pending']['s1'], original)
        self.supervisor.clear('s1')
        self.checkpoint(self.supervisor, 's1')
        self.assertNotIn('interleavedRound', self.supervisor.state()['pending']['s1'])


if __name__ == '__main__':
    unittest.main()
