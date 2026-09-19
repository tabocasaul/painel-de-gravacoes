import unittest
from unittest.mock import Mock
from daily_plan import DAILY_PLAN, run_daily_plan, continuous_daily_plan


class DailyPlanTests(unittest.TestCase):
    def test_continuous_retries_preparation_and_honors_stop(self):
        stopped = [False]
        def run():
            if run_once.call_count == 1:
                raise RuntimeError('Gravação não iniciada: ADB nao respondeu')
            stopped[0] = True
        run_once = Mock(side_effect=run); pause=Mock()
        continuous_daily_plan(run_once,Mock(),lambda:stopped[0],pause,lambda:'2026-09-14',Mock())
        self.assertEqual(run_once.call_count,2)
        self.assertEqual(pause.call_count,30)

    def test_continuous_preserves_failed_capture(self):
        run=Mock(side_effect=RuntimeError('A rodada não foi totalmente salva.'))
        with self.assertRaises(RuntimeError):
            continuous_daily_plan(run,Mock(),lambda:False,Mock(),lambda:'2026-09-14',Mock())
        run.assert_called_once()

    def test_continuous_restarts_after_date_change(self):
        stopped=[False]; day=['2026-09-14']
        def run():
            if run_once.call_count == 2: stopped[0]=True
        run_once=Mock(side_effect=run)
        continuous_daily_plan(run_once,Mock(),lambda:stopped[0],lambda _:day.__setitem__(0,'2026-09-15'),lambda:day[0],Mock())
        self.assertEqual(run_once.call_count,2)

    def setUp(self):
        self.targets = {'p1': ('s1', 1), 'p2': ('s2', 2)}
        self.totals = {}
        self.events = []
        self.stop = False
        self.preflight = Mock()
        self.activate = lambda targets, video: self.events.append(('video', video, list(targets)))

    def record(self, targets, task):
        self.events.append(('task', task, list(targets)))
        for name in targets:
            self.totals[name, task] = 7200

    def run_plan(self, record=None):
        run_daily_plan(self.targets, lambda n,t: self.totals.get((n,t), 0),
                       self.preflight, self.activate, record or self.record,
                       Mock(), lambda: self.stop, Mock())

    def test_correct_sources_and_independent_daily_balances(self):
        self.totals['p1', DAILY_PLAN[0]['task']] = 7200
        self.run_plan()
        self.assertEqual([e[1] for e in self.events if e[0]=='video'],
                         ['Lavando louça .MOV', 'Arrancando ervas .mov', 'Arrancando ervas .mov'])
        self.assertEqual(self.events[1][2], ['p2'])
        self.assertEqual(self.events[3][2], ['p1', 'p2'])
        self.assertTrue(all(self.totals[n,r['task']]==7200 for n in self.targets for r in DAILY_PLAN))

    def test_missing_second_video_prevents_any_activation(self):
        self.preflight.side_effect = [None, ValueError('missing')]
        with self.assertRaises(ValueError): self.run_plan()
        self.assertEqual(self.events, [])

    def test_failed_recording_does_not_change_category(self):
        with self.assertRaises(RuntimeError):
            self.run_plan(Mock(side_effect=RuntimeError('capture failed')))
        self.assertEqual(len(self.events), 1)

    def test_incomplete_task_cannot_advance(self):
        with self.assertRaisesRegex(RuntimeError, 'saldo diário'):
            self.run_plan(Mock())
        self.assertEqual(len(self.events), 1)

    def test_stop_after_round_prevents_next_video(self):
        def record(targets, task):
            self.record(targets, task)
            self.stop = True
        self.run_plan(record)
        self.assertEqual(len(self.events), 2)

    def test_new_day_starts_all_categories_again(self):
        self.run_plan()
        self.events.clear()
        self.run_plan()
        self.assertEqual(self.events, [])
        self.totals.clear()
        self.run_plan()
        self.assertEqual(len(self.events), 6)
