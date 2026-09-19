"""Exercise real recording workers and barriers without starting any device."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from automation import Automation


class ParallelRecordingFailureTests(unittest.TestCase):
    def check_isolated_failure(self, count, tolerate=False, fail_stage='capture', require_all_ready=False, hold_last=False):
        engine = Mock()
        engine.cancelar_sync = threading.Event()
        engine._camera_pronta.return_value = 900
        engine._uso_tarefa.return_value = 0
        engine._ler_geracao.return_value = 4
        engine._detectar_tarefa_sessao.side_effect = lambda serial, *_: (
            ('wrong-task', 'Outra tarefa') if serial == 's0' and fail_stage == 'task'
            else ('task-id', 'Cozinhar'))
        engine._shell_root.return_value.stdout = '4096'
        automation = Automation(engine, Mock())
        automation.rotate_left = Mock()
        automation.navigate = Mock()
        def wait_recording(serial, *_):
            if serial == 's0' and fail_stage == 'countdown':
                raise RuntimeError('Falha isolada na contagem')
            return serial + '_session'
        automation.wait_recording = Mock(side_effect=wait_recording)
        automation.save = Mock()
        failed = threading.Event()
        all_playing = threading.Event()
        playing = set()
        timeline = []
        timeline_lock = threading.Lock()
        real_mark = automation.mark

        def control(serial, command, generation):
            if command == 'play':
                with timeline_lock:
                    playing.add(serial)
                    if len(playing) == (count if fail_stage == 'capture' else count - 1):
                        all_playing.set()

        engine._escrever_controle.side_effect = control

        def mark(serial, **fields):
            real_mark(serial, **fields)
            stage = fields.get('stage', '')
            if stage.startswith('Erro'):
                with timeline_lock:
                    timeline.append(('failed', serial))
                failed.set()
            elif stage == 'Salvo':
                with timeline_lock:
                    timeline.append(('saved', serial))

        automation.mark = mark

        def foreground(serial):
            # Fail during capture, after all devices have actually received play.
            if not all_playing.wait(2):
                raise AssertionError('The group did not start together')
            if serial == 's0':
                return False
            if not failed.wait(2):
                raise AssertionError('The failing worker did not finish independently')
            return True

        automation.minute_foreground = Mock(side_effect=foreground)
        thread_clock = threading.local()

        def monotonic():
            value = getattr(thread_clock, 'value', -61) + 61
            thread_clock.value = value
            return value

        targets = {f'phone{i}': (f's{i}', str(i)) for i in range(count)}
        installed = {serial: {'confirmed': True, 'assetId': 'same-video'}
                     for serial, _ in targets.values()}
        allow_last=threading.Event()
        last_entered=threading.Event()
        arrived=set()
        first_taps=[]
        def before_recording(serial):
            with timeline_lock:arrived.add(serial)
            if serial==f's{count-1}' and hold_last:
                last_entered.set()
                if not allow_last.wait(2):raise RuntimeError('Test gate timed out')
            return []
        engine._pastas_gravacao.side_effect=before_recording
        def tap(serial):
            with timeline_lock:first_taps.append((serial,set(arrived)))
        engine._tocar_botao_gravacao.side_effect=tap
        real_monotonic = time.monotonic
        with patch('synchronized_recording_start.time', SimpleNamespace(monotonic=real_monotonic)), \
             patch('automation.time.monotonic', side_effect=monotonic), \
             patch('automation.stop_deadline', side_effect=lambda play, *_: play + 183):
            if hold_last:
                errors=[]
                def run():
                    try:
                        automation._run_cycle(targets, Mock(), installed, 'Cozinhar', True,
                                              tolerate_failures=tolerate,require_all_ready=require_all_ready)
                    except BaseException as exc:errors.append(exc)
                thread=threading.Thread(target=run,daemon=True)
                thread.start()
                try:
                    self.assertTrue(last_entered.wait(1))
                    engine._tocar_botao_gravacao.assert_not_called()
                    self.assertFalse(playing)
                finally:
                    allow_last.set()
                    thread.join(4)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors,[])
            else:
                automation._run_cycle(targets, Mock(), installed, 'Cozinhar', True,
                                      tolerate_failures=tolerate,require_all_ready=require_all_ready)

        self.assertFalse(engine.cancelar_sync.is_set())
        rows = automation.snapshot()
        expected_error = {'capture': 'saiu da câmera', 'countdown': 'Falha isolada',
                          'task': 'Tarefa aberta diferente'}[fail_stage]
        self.assertIn(expected_error, rows['s0']['error'])
        self.assertEqual(timeline[0], ('failed', 's0'))
        self.assertEqual({serial for kind, serial in timeline if kind == 'saved'},
                         {f's{i}' for i in range(1, count)})
        self.assertEqual(automation.save.call_count, count - 1)
        self.assertEqual(engine._somar_uso_tarefa.call_count, count - 1)
        self.assertTrue(all(rows[f's{i}']['stage'] == 'Salvo' for i in range(1, count)))
        played = [call.args[0] for call in engine._escrever_controle.call_args_list
                  if call.args[1] == 'play']
        self.assertEqual(set(played), {f's{i}' for i in range(0 if fail_stage == 'capture' else 1, count)})
        self.assertTrue(first_taps)
        self.assertEqual(first_taps[0][1],{f's{i}' for i in range(count)})

    def test_one_failure_does_not_stop_the_other_recording(self):
        self.check_isolated_failure(2)

    def test_one_of_four_fails_and_the_other_three_finish_and_save(self):
        self.check_isolated_failure(4)

    def test_interleaved_group_survives_failure_during_capture(self):
        for count in (2, 4):
            with self.subTest(phones=count):
                self.check_isolated_failure(count, tolerate=True)

    def test_interleaved_group_survives_failure_during_countdown(self):
        for count in (2, 4):
            with self.subTest(phones=count):
                self.check_isolated_failure(count, tolerate=True, fail_stage='countdown')

    def test_interleaved_group_survives_wrong_task_on_one_device(self):
        for count in (2, 4):
            with self.subTest(phones=count):
                self.check_isolated_failure(count, tolerate=True, fail_stage='task')

    def test_strict_four_wait_before_first_tap_and_save_after_one_capture_fails(self):
        self.check_isolated_failure(4,tolerate=True,require_all_ready=True,hold_last=True)

    def test_strict_group_saves_others_after_countdown_or_task_failure(self):
        for fail_stage in ('countdown','task'):
            with self.subTest(fail_stage=fail_stage):
                self.check_isolated_failure(4,tolerate=True,fail_stage=fail_stage,require_all_ready=True)

    def test_strict_preparation_failure_never_starts_the_other_three(self):
        engine=Mock()
        engine.cancelar_sync=threading.Event()
        engine._camera_pronta.return_value=900
        engine._uso_tarefa.return_value=0
        engine._ler_geracao.return_value=4
        automation=Automation(engine,Mock())
        automation.rotate_left=Mock()
        automation.navigate=Mock()
        targets={f'phone{i}':(f's{i}',str(i)) for i in range(4)}
        installed={serial:{'confirmed':True,'assetId':'same-video'} for serial,_ in targets.values()}
        def prepare(name,serial,port):
            if serial=='s3':raise RuntimeError('Câmera ainda indisponível')
        with self.assertRaisesRegex(RuntimeError,'Gravação não iniciada.*Câmera ainda indisponível'):
            automation._run_cycle(targets,prepare,installed,'Cozinhar',
                                  tolerate_failures=True,require_all_ready=True)
        engine._tocar_botao_gravacao.assert_not_called()
        engine._pastas_gravacao.assert_not_called()
        self.assertFalse(any(call.args[1]=='play' for call in engine._escrever_controle.call_args_list))
        self.assertEqual(sum(row['stage']=='Pronto' for row in automation.snapshot().values()),3)


if __name__ == '__main__':
    unittest.main()
