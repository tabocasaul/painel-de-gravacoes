"""Recording selection tests; the real server and emulators are never started."""
import ast
import os
from pathlib import Path
import threading
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import xml.etree.ElementTree as ET

from automation_queue import GIB, run_queue
from daily_plan import run_daily_plan
from interleaved_plan import run_interleaved_plan, validate_plan
from interleaved_video_rotation import InterleavedVideoRotation
from interleaved_participants import InterleavedParticipants
from participant_selection import recording_options, select_participants, validate_simultaneous


class ParticipantValidationTests(unittest.TestCase):
    def setUp(self):
        self.targets = {f'p{i}': (f's{i}', i) for i in range(9)}

    def test_positive_integer_quantity_has_no_upper_limit(self):
        for value in (None, 1, 4, 6, 99):
            self.assertEqual(validate_simultaneous(value), value)

    def test_invalid_quantities_are_rejected(self):
        for value in (0, -1, 1.5, 4.0, True, False, '4', [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_simultaneous(value)

    def test_subset_uses_serials_and_never_probes_unselected_phones(self):
        status = Mock(side_effect=AssertionError('No status query required'))
        selected = select_participants(self.targets,
            dict(scope='selected', selectedSerials=['s7', 's1']), status)
        self.assertEqual(selected, {'p1': ('s1', 1), 'p7': ('s7', 7)})
        renamed = {'new-name': ('s1', 1)}
        self.assertEqual(select_participants(renamed,
            dict(scope='selected', selectedSerials=['s1']), status), renamed)

    def test_invalid_selection_fails_before_any_status_query(self):
        status = Mock()
        for serials in (None, [], 's1', ['s1', 's1'], ['missing'], [None], ['']):
            with self.subTest(serials=serials), self.assertRaises(ValueError):
                select_participants(self.targets,
                    dict(scope='selected', selectedSerials=serials), status)
        status.assert_not_called()

    def test_all_and_online_scopes_remain_supported(self):
        self.assertEqual(select_participants(self.targets, dict(scope='all'), Mock()), self.targets)
        self.assertEqual(select_participants(self.targets, dict(scope='online'),
            lambda serial: 'online' if serial == 's2' else 'off'), {'p2': ('s2', 2)})

    def test_empty_or_unknown_scope_does_not_fall_back_to_all(self):
        for options in (dict(scope='online'), dict(scope='unknown')):
            with self.subTest(options=options), self.assertRaises(ValueError):
                select_participants(self.targets, options, lambda serial: 'off')

    def test_queue_respects_subset_and_quantities_one_four_and_over_five(self):
        selected = select_participants(self.targets,
            dict(scope='selected', selectedSerials=[f's{i}' for i in range(1, 8)]), Mock())
        for quantity in (1, 4, 6, 99):
            with self.subTest(quantity=quantity):
                active, batches, rows = {'s0', 's8'}, [], {}
                installed = {s: dict(confirmed=True, assetId='same') for s, _ in selected.values()}
                a = SimpleNamespace(e=SimpleNamespace(cancelar_sync=threading.Event()),
                    stop_after_round=threading.Event(), check_cancel=Mock(), update=Mock())
                def cycle(batch, *args, **kwargs):
                    batches.append(list(batch))
                    rows.update({s: dict(stage='Salvo') for s, _ in batch.values()})
                a._run_cycle, a.snapshot = cycle, lambda: rows
                boot = Mock(side_effect=lambda n, s, p: active.add(s))
                shutdown = Mock(side_effect=lambda s: active.remove(s))
                run_queue(a, selected, Mock(), installed, 'Task', True, False,
                    lambda s: s in active, boot, shutdown, lambda: GIB, simultaneous=quantity)
                self.assertEqual([name for batch in batches for name in batch], list(selected))
                self.assertEqual(len(batches[0]), min(quantity, len(selected)))
                self.assertTrue(all(len(batch) <= quantity for batch in batches))
                self.assertTrue({'s0', 's8'} <= active)
                self.assertTrue(all(c.args[0] not in {'s0', 's8'} for c in shutdown.call_args_list))

    def test_queue_and_interleaved_reject_invalid_quantities_before_callbacks(self):
        callback = Mock()
        for quantity in (0, -2, 1.5, True, False):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                run_queue(None, self.targets, callback, {}, 'Task', True, False,
                    callback, callback, callback, simultaneous=quantity)
            with self.subTest(interleaved=quantity), self.assertRaises(ValueError):
                run_interleaved_plan([dict(task='A', video='a.mov')], self.targets,
                    callback, callback, callback, callback, callback, callback, callback,
                    simultaneous=quantity)
        callback.assert_not_called()


class ServerSelectionTests(unittest.TestCase):
    def setUp(self):
        self.targets = {f'p{i}': (f's{i}', i) for i in range(9)}
        self.selected = {name: pair for name, pair in self.targets.items() if name in ('p1', 'p7')}
        self.options = dict(scope='selected', selectedSerials=['s1', 's7'], simultaneous=7,
                            taskName='A', autoNavigate=True, repeat=False)
        self.installed = {s: dict(confirmed=True, assetId='cache:False') for s, _ in self.targets.values()}
        self.totals = {}
        self.a = SimpleNamespace(usage_since=None, recovery=None, stop_after_round=threading.Event(),
            check_cancel=Mock(), update=Mock(), run=Mock(), snapshot=Mock(return_value={}),
            xml=Mock(return_value=ET.fromstring('<hierarchy><node resource-id="nav-index"/></hierarchy>')),
            task_usage=lambda name, task: self.totals.get((name, task), 0))
        self.e = SimpleNamespace(cancelar_sync=threading.Event(), _adb=Mock(),
            _camera_pronta=Mock(return_value=None), _hoje=lambda: '2026-09-19', _ler_historico=Mock())
        self.supervisor = Mock()
        self.supervisor.state.return_value = {'pending': {}}
        self.queue_state = dict(queueSaved=list(self.selected), queuePending=[])
        self.ns = dict(recording_options=recording_options, select_participants=select_participants,
            validate_plan=validate_plan, devices=lambda: self.targets, status=Mock(return_value='online'),
            os=SimpleNamespace(path=SimpleNamespace(join=os.path.join, basename=os.path.basename,
                                                    isfile=Mock(return_value=True))),
            AREA='unused', VIDEOS='unused', read_catalog=Mock(return_value={'tasks': ['A', 'B']}),
            resolve_name=lambda library, area, name: name,
            resolve_video_name=lambda name: name, video_source=lambda name: os.path.join('unused',name),
            AUTOMATION=self.a, E=self.e, update=Mock(), TRANSFERS=SimpleNamespace(
                snapshot=lambda: {'installedVideos': self.installed}),
            SHARED=SimpleNamespace(activate_pending=Mock()), start_phone=Mock(), wait_open=Mock(),
            open_minute=Mock(), time=SimpleNamespace(monotonic=lambda:0,sleep=lambda seconds:None), run_queue=Mock(),
            run_daily_plan=run_daily_plan, run_interleaved_plan=run_interleaved_plan,
            InterleavedVideoRotation=Mock(side_effect=lambda path: InterleavedVideoRotation()),
            InterleavedParticipants=InterleavedParticipants,
            snap=lambda: self.queue_state,
            continuous_daily_plan=lambda once, *args, **kwargs: once(),
            prepared_cache=Mock(return_value={'sha256': 'cache'}), install_targets=Mock(),
            wait_for_shutdown=Mock(), SUPERVISOR=self.supervisor, PORT=8768, FROZEN=True, WATCHDOG=None)
        source = ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8-sig'))
        names = {'preflight_plan_video', 'recording_request', 'sync', 'supervised_sync'}
        definitions = ast.Module(body=[node for node in source.body
            if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
        exec(compile(definitions, 'server-definitions-only', 'exec'), self.ns)

    def test_normal_queue_gets_only_chosen_targets_and_requested_quantity(self):
        self.ns['sync'](self.options)
        call = self.ns['run_queue'].call_args
        self.assertEqual(call.args[1], self.selected)
        self.assertEqual(call.kwargs['simultaneous'], 7)
        self.a.run.assert_not_called()

    def test_explicit_online_quantity_uses_queue_even_when_manage_ram_false(self):
        self.ns['sync'](dict(scope='online', autoNavigate=True, simultaneous=4,
                            manageRam=False, taskName='A'))
        self.assertEqual(self.ns['run_queue'].call_args.kwargs['simultaneous'], 4)
        self.a.run.assert_not_called()

    def test_daily_and_interleaved_preserve_subset_and_quantity(self):
        for kind in ('dailyPlan', 'interleavedPlan'):
            with self.subTest(kind=kind):
                self.totals.clear()
                self.ns['run_queue'].reset_mock()
                def record(automation, targets, prepare, installed, task, *args, **kwargs):
                    self.assertTrue(set(targets) <= set(self.selected))
                    self.assertEqual(kwargs['simultaneous'], 7)
                    for name in targets:
                        self.totals[name, task] = 7200
                self.ns['run_queue'].side_effect = record
                self.ns['sync'](dict(self.options, **{kind: True},
                    interleavedTasks=[dict(task='A', video='a.mov'), dict(task='B', video='b.mov')]))
                self.assertTrue(self.ns['run_queue'].called)
                self.assertEqual({name for name, task in self.totals}, set(self.selected))
                self.assertTrue(all(call.args[0] in {'s1', 's7'} for call in self.e._adb.call_args_list))

    def test_interleaved_over_five_records_full_requested_batch(self):
        batches, totals = [], {}
        def record(batch, task):
            batches.append(list(batch))
            for name in batch:
                totals[name, task] = 7200
        run_interleaved_plan([dict(task='A', video='a.mov')], self.targets,
            lambda name, task: totals.get((name, task), 0), Mock(), Mock(), record,
            Mock(), lambda: False, Mock(), shuffle=lambda values: None, simultaneous=7)
        self.assertEqual([len(batch) for batch in batches], [7, 2])

    def test_invalid_plan_quantity_fails_before_any_plan_or_phone_effects(self):
        for kind in ('dailyPlan', 'interleavedPlan'):
            for value in (0, 1.5, True):
                with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                    self.ns['supervised_sync'](dict(self.options, **{kind: True}, simultaneous=value))
        self.supervisor.begin.assert_not_called()
        self.ns['start_phone'].assert_not_called()
        self.ns['prepared_cache'].assert_not_called()

    def test_daily_video_activation_never_shuts_down_or_installs_unselected_phones(self):
        self.installed['s1']['assetId'] = 'previous-video'
        def install(targets, video, fill):
            self.assertEqual({serial for name, serial in targets}, {'s1', 's7'})
            for name, serial in targets:
                self.installed[serial]['assetId'] = 'cache:False'
        self.ns['install_targets'].side_effect = install
        def record(automation, targets, prepare, installed, task, *args, **kwargs):
            for name in targets:
                self.totals[name, task] = 7200
        self.ns['run_queue'].side_effect = record
        self.ns['sync'](dict(self.options, dailyPlan=True))
        self.ns['install_targets'].assert_called_once()
        self.assertEqual({call.args[0] for call in self.e._adb.call_args_list}, {'s1', 's7'})

    def test_invalid_participants_fail_before_supervisor_begin(self):
        for serials in ([], ['s1', 's1'], ['missing']):
            with self.subTest(serials=serials), self.assertRaises(ValueError):
                self.ns['supervised_sync'](dict(self.options, selectedSerials=serials))
        self.supervisor.begin.assert_not_called()
        self.ns['start_phone'].assert_not_called()

    def test_pending_unselected_phone_fails_before_supervisor_or_phone_changes(self):
        self.supervisor.state.return_value = {'pending': {'s0': {'session': 'pending'}}}
        with self.assertRaisesRegex(ValueError, 'fora dos participantes'):
            self.ns['supervised_sync'](self.options)
        self.supervisor.begin.assert_not_called()
        self.ns['status'].assert_not_called()
        self.e._adb.assert_not_called()

    def test_supervisor_reset_touches_only_selected_and_retains_options(self):
        self.supervisor.run.side_effect = lambda operation, reset: reset()
        self.ns['supervised_sync'](self.options)
        persisted = self.supervisor.begin.call_args.args[0]
        self.assertEqual(persisted['selectedSerials'], ['s1', 's7'])
        self.assertEqual(persisted['simultaneous'], 7)
        self.assertEqual({call.args[0] for call in self.e._adb.call_args_list}, {'s1', 's7'})
        self.ns['status'].reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'não pertence'):
            self.supervisor.ensure_online('s0')
        self.ns['status'].assert_not_called()
        self.ns['start_phone'].assert_not_called()

    def test_supervisor_preserves_online_snapshot_across_shutdown_and_resume(self):
        self.ns['status'].side_effect = lambda s: 'online' if s in {'s1', 's7'} else 'off'
        self.ns['supervised_sync'](dict(scope='online', simultaneous=4, taskName='A', resumePhones=['p7']))
        persisted = self.supervisor.begin.call_args.args[0]
        self.assertEqual(persisted['scope'], 'selected')
        self.assertEqual(persisted['selectedSerials'], ['s1', 's7'])
        self.assertEqual(persisted['resumePhones'], ['p7'])
        self.assertFalse(persisted['manageRam'])
        self.ns['status'].side_effect = lambda serial: 'off'
        self.ns['sync'](persisted)
        self.assertEqual(self.ns['run_queue'].call_args.args[1], self.selected)
        self.assertEqual(self.ns['run_queue'].call_args.kwargs['simultaneous'], 4)

    def test_ready_mode_runs_selected_online_cameras_without_boot(self):
        self.ns['sync'](dict(self.options, autoNavigate=False, simultaneous=None))
        targets, prepare = self.a.run.call_args.args[:2]
        self.assertEqual(targets, self.selected)
        for name, (serial, port) in targets.items():
            prepare(name, serial, port)
        self.ns['start_phone'].assert_not_called()
        self.ns['open_minute'].assert_not_called()
        self.ns['run_queue'].assert_not_called()

    def test_ready_offline_or_explicit_limit_fails_before_supervisor_begin(self):
        with self.assertRaisesRegex(ValueError, 'busca automática'):
            self.ns['supervised_sync'](dict(self.options, autoNavigate=False))
        self.ns['status'].return_value = 'off'
        with self.assertRaisesRegex(ValueError, 'somente celulares ligados'):
            self.ns['supervised_sync'](dict(self.options, autoNavigate=False, simultaneous=None))
        self.supervisor.begin.assert_not_called()
        self.ns['start_phone'].assert_not_called()

    def test_ready_phone_disconnect_during_preparation_does_not_boot_it(self):
        self.ns['sync'](dict(self.options, autoNavigate=False, simultaneous=None))
        prepare = self.a.run.call_args.args[1]
        self.ns['status'].return_value = 'off'
        with self.assertRaisesRegex(ValueError, 'deixe a câmera pronta'):
            prepare('p1', 's1', 1)
        self.ns['start_phone'].assert_not_called()
        self.ns['SHARED'].activate_pending.assert_not_called()

    def test_all_playlist_videos_are_preflighted_before_supervisor_can_recover(self):
        self.ns['os'].path.isfile.side_effect = lambda path: not path.endswith('last.mov')
        options = dict(self.options, interleavedPlan=True, interleavedTasks=[
            dict(task='A', videos=['a.mov', 'b.mov']), dict(task='B', videos=['c.mov', 'last.mov'])])
        with self.assertRaisesRegex(ValueError, 'last.mov'):
            self.ns['supervised_sync'](options)
        self.supervisor.begin.assert_not_called()
        self.supervisor.run.assert_not_called()
        self.ns['install_targets'].assert_not_called()
        self.e._adb.assert_not_called()

    def test_server_reloads_saved_playlist_cursor_when_next_run_starts(self):
        with tempfile.TemporaryDirectory() as folder:
            self.ns['AREA'] = folder
            self.ns['InterleavedVideoRotation'] = InterleavedVideoRotation
            options = dict(self.options, interleavedPlan=True,
                interleavedTasks=[dict(task='A', videos=['a.mov', 'b.mov', 'c.mov', 'd.mov'])])
            def record(*args, **kwargs):
                self.a.stop_after_round.set()
            self.ns['run_queue'].side_effect = record
            for expected in (1, 2):
                self.ns['update'].reset_mock()
                self.ns['sync'](options)
                states = [call.kwargs for call in self.ns['update'].call_args_list if 'planVideoIndex' in call.kwargs]
                self.assertEqual(len(states), 1)
                self.assertEqual(states[0]['planVideoIndex'], expected)
                self.assertEqual(states[0]['planVideoCount'], 4)

    def test_server_queue_return_without_saving_does_not_advance_playlist(self):
        rotation = InterleavedVideoRotation()
        self.ns['InterleavedVideoRotation'].return_value = rotation
        self.ns['InterleavedVideoRotation'].side_effect = None
        self.queue_state = dict(queueSaved=[], queuePending=list(self.selected))
        videos = ['a.mov', 'b.mov']
        options = dict(self.options, interleavedPlan=True, interleavedTasks=[dict(task='A', videos=videos)])
        self.ns['run_queue'].side_effect=lambda *args,**kwargs:self.a.stop_after_round.set()
        self.ns['sync'](options)
        self.assertEqual(rotation.position('A', videos), 0)

    def test_real_queue_cancel_after_all_saved_persists_next_video(self):
        self.exercise_cancelled_real_queue('saved')

    def test_real_queue_cancel_with_participant_pending_keeps_current_video(self):
        self.exercise_cancelled_real_queue('partial')

    def test_real_queue_cancel_before_save_keeps_current_video(self):
        self.exercise_cancelled_real_queue('unsaved')

    def exercise_cancelled_real_queue(self, outcome):
        with tempfile.TemporaryDirectory() as folder:
            self.ns['AREA'] = folder
            self.ns['InterleavedVideoRotation'] = InterleavedVideoRotation
            self.e._ler_historico.return_value = {'supervisorSessions': {}}
            self.a.e = self.e
            self.a.update = lambda **fields: self.queue_state.update(fields)
            self.ns['task_usage'] = lambda *args: 0
            self.ns['run_queue'] = lambda *args, **kwargs: run_queue(*args, available=lambda: int(1.5*GIB), **kwargs)
            def check_cancel():
                if self.e.cancelar_sync.is_set():
                    raise InterruptedError('User cancelled')
            self.a.check_cancel = check_cancel
            recorded = []
            def cycle(batch, *args, **kwargs):
                recorded.append(list(batch))
                self.e.cancelar_sync.set()
                if outcome == 'unsaved':
                    check_cancel()
                self.a.snapshot.return_value = {serial: dict(stage='Salvo') for serial, _ in batch.values()}
            self.a._run_cycle = cycle
            videos = ['a.mov', 'b.mov']
            options = dict(self.options, interleavedPlan=True, randomizePhones=False,
                interleavedTasks=[dict(task='A', videos=videos)])
            if outcome == 'partial':
                options['simultaneous'] = None
                self.ns['status'].side_effect = lambda serial: 'online' if serial == 's1' else 'off'
            with self.assertRaises(InterruptedError):
                self.ns['sync'](options)
            saved = InterleavedVideoRotation(Path(folder) / 'interleaved-video-rotation.json')
            self.assertEqual(saved.position('A', videos), 1 if outcome == 'saved' else 0)
            self.assertEqual(len(recorded), 1)
            if outcome == 'saved':
                self.assertIsNone(saved.pending_round)
                self.assertEqual(set(self.queue_state['queueSaved']), set(self.selected))
            else:
                self.assertIsNotNone(saved.pending_round)
                if outcome == 'partial':
                    self.assertTrue(self.queue_state['queuePending'])
                else:
                    self.assertFalse(self.queue_state['queueSaved'])

    def test_supervisor_recovers_known_capture_even_when_future_video_is_missing(self):
        self.supervisor.state.return_value = {'pending': {'s1': dict(session='capture')}}
        self.ns['os'].path.isfile.side_effect = lambda path: not path.endswith('missing.mov')
        recovered = Mock()
        def recover(serial):
            recovered()
            self.supervisor.state.return_value = {'pending': {}}
            return True
        self.supervisor.recover_quick.side_effect = recover
        options = dict(self.options, interleavedPlan=True,
            interleavedTasks=[dict(task='A', videos=['a.mov', 'missing.mov'])])
        with self.assertRaisesRegex(ValueError, 'missing.mov'):
            self.ns['supervised_sync'](options)
        recovered.assert_called_once()
        self.ns['run_queue'].assert_not_called()
        self.ns['install_targets'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
