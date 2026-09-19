import tempfile
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from automation_queue import GIB, run_queue
from interleaved_participants import InterleavedParticipants
from interleaved_plan import run_interleaved_plan
from interleaved_video_rotation import InterleavedVideoRotation


class ContinuationTests(unittest.TestCase):
    def test_failed_phone_does_not_replay_task_and_rejoins_next_available_group(self):
        for count in (2, 4):
            with self.subTest(count=count):
                targets = {f'p{i}': (f's{i}', i) for i in range(count)}
                pending, events, rows = {}, [], {}
                engine = SimpleNamespace(cancelar_sync=threading.Event())
                a = SimpleNamespace(e=engine, check_cancel=Mock(), stop_after_round=threading.Event(),
                                    update=Mock(), mark=Mock(), snapshot=lambda: rows)
                recoveries = []
                def recover(serial):
                    recoveries.append(serial)
                    if len(recoveries) == 1:
                        return False
                    pending.pop(serial)
                    return True
                participants = InterleavedParticipants(targets, lambda serial: 'online', Mock(),
                    lambda: pending, recover, Mock(), Mock())
                def cycle(batch, prepare, installed, task, *args, **kwargs):
                    self.assertTrue(kwargs['tolerate_failures'])
                    self.assertTrue(all(serial not in pending for serial, _ in batch.values()))
                    events.append((task, list(batch), set(pending)))
                    rows.clear()
                    rows.update({serial: dict(stage='Salvo') for serial, _ in batch.values()})
                    if len(events) == 1:
                        pending['s0'] = dict(session='preserved')
                        rows['s0'] = dict(stage='Erro', error='Connection lost')
                    if len(events) == 3:
                        a.stop_after_round.set()
                a._run_cycle = cycle
                installed = {serial: dict(confirmed=True, assetId='same') for serial, _ in targets.values()}
                def record(batch, task):
                    result = run_queue(a, batch, Mock(), installed, task, True, False, lambda serial: True,
                        Mock(), Mock(), lambda: 100*GIB, simultaneous=count, reset_controls=False,
                        tolerate_failures=True)
                    participants.failed(result['failed'], rows)
                    return result
                rotation = InterleavedVideoRotation()
                videos = ['a1.mov', 'a2.mov']
                activate = Mock()
                run_interleaved_plan([dict(task='A', videos=videos), dict(task='B', video='b.mov'),
                    dict(task='C', video='c.mov')], targets, lambda *args: 0, Mock(), activate, record,
                    Mock(), a.stop_after_round.is_set, Mock(), shuffle=lambda items: None, simultaneous=count,
                    rotation=rotation, continue_after_failure=True, admit=participants.admit, pause=Mock())
                self.assertEqual([event[0] for event in events], ['A', 'B', 'C'])
                self.assertEqual([call.args[1] for call in activate.call_args_list], ['a1.mov', 'b.mov', 'c.mov'])
                self.assertEqual(len(events[0][1]), count)
                self.assertNotIn('p0', events[1][1])
                self.assertEqual(events[1][2], {'s0'})
                self.assertEqual(len(events[2][1]), count)
                self.assertEqual(rotation.position('A', videos), 1)
                self.assertEqual(pending, {})

    def test_all_failed_waits_without_advancing_or_spinning(self):
        rotation, stop, pauses = InterleavedVideoRotation(), [False], []
        videos = ['a.mov', 'b.mov']
        def pause(seconds):
            pauses.append(seconds)
            stop[0] = True
        record = Mock(return_value=dict(saved=[], failed=['p']))
        run_interleaved_plan([dict(task='A', videos=videos)], {'p': ('s', 1)}, lambda *args: 0,
            Mock(), Mock(), record, Mock(), lambda: stop[0], Mock(), rotation=rotation,
            continue_after_failure=True, pause=pause)
        record.assert_called_once()
        self.assertEqual(pauses, [1])
        self.assertEqual(rotation.position('A', videos), 0)

    def test_no_available_phone_waits_and_never_activates_or_records(self):
        stop, activate, record = [False], Mock(), Mock()
        run_interleaved_plan([dict(task='A', video='a.mov')], {'p': ('s', 1)}, lambda *args: 0,
            Mock(), activate, record, Mock(), lambda: stop[0], Mock(), continue_after_failure=True,
            admit=lambda *args: {}, pause=lambda seconds: stop.__setitem__(0, True))
        activate.assert_not_called()
        record.assert_not_called()

    def test_partial_receipt_survives_restart_and_late_receipt_does_not_advance_twice(self):
        targets, videos = {'p1': ('s1', 1), 'p2': ('s2', 2)}, ['a.mov', 'b.mov']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            rotation.begin_round('A', videos, 0, targets, allow_partial=True)
            token = rotation.pending_round['id']
            ledger = {'saved1': dict(interleavedRound=token, serial='s1')}
            restarted = InterleavedVideoRotation(path)
            self.assertTrue(restarted.reconcile(ledger))
            self.assertEqual(restarted.position('A', videos), 1)
            ledger['saved2'] = dict(interleavedRound=token, serial='s2')
            self.assertFalse(InterleavedVideoRotation(path).reconcile(ledger))
            self.assertEqual(InterleavedVideoRotation(path).position('A', videos), 1)

    def test_manual_cancellation_and_legacy_round_still_require_every_receipt(self):
        targets, videos = {'p1': ('s1', 1), 'p2': ('s2', 2)}, ['a.mov', 'b.mov']
        for partial in (False, True):
            rotation = InterleavedVideoRotation()
            rotation.begin_round('A', videos, 0, targets, allow_partial=partial)
            rotation.require_all()
            token = rotation.pending_round['id']
            self.assertFalse(rotation.reconcile({'saved': dict(interleavedRound=token, serial='s1')}))
            self.assertEqual(rotation.position('A', videos), 0)


class AdmissionTests(unittest.TestCase):
    def make_manager(self, count=7):
        targets = {f'p{i}': (f's{i}', i) for i in range(count)}
        states = {serial: 'off' for serial, _ in targets.values()}
        pending = {'s0': dict(session='keep')}
        start = Mock(side_effect=lambda name, serial, port: states.__setitem__(serial, 'booting'))
        recover = Mock(return_value=False)
        release = Mock(side_effect=lambda serial: states.__setitem__(serial, 'off'))
        manager = InterleavedParticipants(targets, lambda serial: states[serial], start,
            lambda: pending, recover, Mock(), Mock(), release)
        return targets, states, pending, start, recover, release, manager

    def test_pending_online_reserves_slot_and_keeps_its_capture(self):
        targets, states, pending, start, recover, release, manager = self.make_manager()
        states.update({f's{i}': 'online' for i in range(4)})
        admitted = manager.admit(targets, 4, 1)
        self.assertEqual(len(admitted), 3)
        self.assertNotIn('p0', admitted)
        self.assertIn('s0', pending)
        start.assert_not_called()
        release.assert_not_called()

    def test_offline_failed_phone_starts_without_waiting_and_rejoins_next_opportunity(self):
        targets, states, pending, start, recover, release, manager = self.make_manager(4)
        states.update({f's{i}': 'online' for i in range(1, 4)})
        admitted = manager.admit(targets, 4, 1)
        start.assert_called_once_with('p0', 's0', 0)
        self.assertEqual(len(admitted), 3)
        self.assertEqual(states['s0'], 'booting')
        self.assertIn('s0', pending)
        states['s0'] = 'online'
        recover.side_effect = lambda serial: pending.pop(serial) is not None
        admitted = manager.admit(targets, 4, 2)
        self.assertEqual(len(admitted), 4)
        self.assertNotIn('p0', manager.deferred)

    def test_full_group_releases_one_saved_slot_before_starting_failed_phone(self):
        targets, states, pending, start, recover, release, manager = self.make_manager(5)
        states.update({f's{i}': 'online' for i in range(1, 5)})
        peak = [4]
        def start_phone(name, serial, port):
            self.assertLess(sum(state != 'off' for state in states.values()), 4)
            states[serial] = 'booting'
            peak.append(sum(state != 'off' for state in states.values()))
        start.side_effect = start_phone
        admitted = manager.admit(targets, 4, 1)
        release.assert_called_once_with('s4')
        start.assert_called_once_with('p0', 's0', 0)
        self.assertEqual(len(admitted), 3)
        self.assertEqual(max(peak), 4)
        self.assertIn('s0', pending)

    def test_unreleasable_phone_is_protected_and_no_fifth_phone_starts(self):
        targets, states, pending, start, recover, release, manager = self.make_manager(5)
        states.update({f's{i}': 'online' for i in range(1, 5)})
        release.side_effect = RuntimeError('Not confirmed saved')
        admitted = manager.admit(targets, 4, 1)
        start.assert_not_called()
        self.assertIn('p4', manager.deferred)
        self.assertLessEqual(len(admitted), 3)
        self.assertIn('s0', pending)

    def test_recovery_true_without_clearing_journal_never_admits_phone(self):
        targets, states, pending, start, recover, release, manager = self.make_manager(2)
        states.update(s0='online', s1='online')
        recover.return_value = True
        self.assertNotIn('p0', manager.admit(targets, 2, 1))
        self.assertIn('s0', pending)


if __name__ == '__main__':
    unittest.main()
