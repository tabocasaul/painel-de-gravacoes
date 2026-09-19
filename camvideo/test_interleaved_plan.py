import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock
from interleaved_plan import validate_plan, run_interleaved_plan
from interleaved_video_rotation import InterleavedVideoRotation


class InterleavedTests(unittest.TestCase):
    def test_alternates_saved_pairs_with_correct_video_and_daily_limits(self):
        rows=[dict(task=t,video=t+'.mov') for t in ('Louça','Ervas','Jardim')]
        targets={str(i):(str(i),i) for i in range(3)}
        totals={}; events=[]
        def record(pair,task):
            events.append(('save',task,list(pair)))
            for n in pair: totals[n,task]=totals.get((n,task),0)+1800
        run_interleaved_plan(rows,targets,lambda n,t:totals.get((n,t),0),Mock(),
            lambda pair,v:events.append(('video',v,list(pair))),record,Mock(),lambda:False,Mock(),shuffle=lambda rows:None)
        self.assertEqual(len(totals),9)
        self.assertTrue(all(v==7200 for v in totals.values()))
        saved=[e for e in events if e[0]=='save']
        self.assertEqual([e[1] for e in saved[:6]],['Louça','Ervas','Jardim']*2)
        for i in range(0,len(events),2):
            self.assertEqual(events[i][1],events[i+1][1]+'.mov')
            self.assertEqual(events[i][2],events[i+1][2])
            self.assertLessEqual(len(events[i][2]),2)

    def test_no_source_switch_after_save_failure(self):
        activate=Mock()
        with self.assertRaises(RuntimeError):
            run_interleaved_plan([dict(task='A',video='a.mov'),dict(task='B',video='b.mov')],
                {'p':('s',1)},lambda n,t:0,Mock(),activate,Mock(side_effect=RuntimeError('save failed')),
                Mock(),lambda:False,Mock())
        activate.assert_called_once()

    def test_validates_duplicates_and_paths_before_start(self):
        for rows in ([],[dict(task='A',video='../a.mov')],
                     [dict(task='A',video='a.mov'),dict(task='a',video='b.mov')]):
            with self.assertRaises(ValueError): validate_plan(rows)

    def test_stop_after_save_prevents_switch(self):
        stopped=[False]; activate=Mock()
        run_interleaved_plan([dict(task='A',video='a.mov'),dict(task='B',video='b.mov')],
            {'p':('s',1)},lambda n,t:0,Mock(),activate,lambda *args:stopped.__setitem__(0,True),
            Mock(),lambda:stopped[0],Mock())
        activate.assert_called_once()

    def test_missing_video_aborts_before_activation(self):
        activate=Mock()
        with self.assertRaises(ValueError):
            run_interleaved_plan([dict(task='A',video='a.mov')],{'p':('s',1)},lambda n,t:0,
                Mock(side_effect=ValueError('missing')),activate,Mock(),Mock(),lambda:False,Mock())
        activate.assert_not_called()

    def test_fixed_five_randomizes_tied_phones_and_runs_together(self):
        totals={}; batches=[]
        targets={str(i):(str(i),i) for i in range(7)}
        def record(batch,task):
            batches.append(list(batch))
            for name in batch: totals[name,task]=7200
        run_interleaved_plan([dict(task='A',video='a.mov')],targets,
            lambda n,t:totals.get((n,t),0),Mock(),Mock(),record,Mock(),lambda:False,Mock(),
            shuffle=lambda rows:rows.reverse(),simultaneous=5)
        self.assertEqual(batches,[['6','5','4','3','2'],['1','0']])

    def test_legacy_single_source_and_ordered_lists_normalize_together(self):
        rows = [dict(task='A', video='one.mov'),
                dict(task='B', videos=[f'video{i}.mov' for i in range(7)])]
        self.assertEqual(validate_plan(rows), [dict(task='A', videos=['one.mov']), rows[1]])

    def test_invalid_lists_and_any_invalid_filename_fail_before_preflight(self):
        bad_lists = (None, [], 'a.mov', [None], [3], [''], ['good.mov', '../bad.mov'],
                     ['a/b.mov'], ['a\\b.mov'], ['C:bad.mov'], ['a.mov:stream'],
                     ['.'], ['..'], ['a\x00.mov'], ['a?.mov'])
        callback = Mock()
        for videos in bad_lists:
            with self.subTest(videos=videos), self.assertRaises(ValueError):
                run_interleaved_plan([dict(task='A', videos=videos)], {'p': ('s', 1)},
                    callback, callback, callback, callback, callback, callback, callback)
        callback.assert_not_called()

    def test_each_task_rotates_its_own_list_in_order_and_wraps(self):
        rows = [dict(task='A', videos=['a1.mov', 'a2.mov', 'a3.mov']),
                dict(task='B', videos=['b1.mov', 'b2.mov']), dict(task='C', videos=['c.mov'])]
        totals, states, events = {}, [], []
        def record(pair, task):
            totals[task] = totals.get(task, 0) + 1800
        def update(**fields):
            if 'planVideo' in fields:
                states.append(fields)
        run_interleaved_plan(rows, {'p': ('s', 1)}, lambda name, task: totals.get(task, 0),
            Mock(), lambda pair, video: events.append(video), record, Mock(), lambda: False,
            update, shuffle=lambda items: None)
        self.assertEqual(events, ['a1.mov', 'b1.mov', 'c.mov', 'a2.mov', 'b2.mov', 'c.mov',
                                  'a3.mov', 'b1.mov', 'c.mov', 'a1.mov', 'b2.mov', 'c.mov'])
        self.assertEqual([s['planVideoIndex'] for s in states if s['planTask'] == 'A'], [1, 2, 3, 1])
        self.assertEqual([s['planVideoCount'] for s in states if s['planTask'] == 'B'], [2] * 4)

    def test_task_shuffle_does_not_shuffle_sources_inside_playlists(self):
        rows = [dict(task='A', videos=['a1.mov', 'a2.mov']), dict(task='B', videos=['b1.mov', 'b2.mov'])]
        totals, events = {}, []
        def record(pair, task):
            totals[task] = totals.get(task, 0) + 3600
        run_interleaved_plan(rows, {'p': ('s', 1)}, lambda name, task: totals.get(task, 0),
            Mock(), lambda pair, video: events.append(video), record, Mock(), lambda: False,
            Mock(), shuffle=lambda items: items.reverse())
        self.assertEqual(events, ['b1.mov', 'a1.mov', 'b2.mov', 'a2.mov'])

    def test_all_playlist_sources_are_checked_before_first_activation(self):
        rows = [dict(task='A', videos=['a.mov', 'shared.mov']),
                dict(task='B', videos=['shared.mov', 'last.mov'])]
        checked, activated = [], Mock()
        def preflight(video):
            checked.append(video)
            if video == 'last.mov':
                raise ValueError('Missing last video')
        with self.assertRaisesRegex(ValueError, 'Missing last'):
            run_interleaved_plan(rows, {'p': ('s', 1)}, lambda *args: 0, preflight,
                activated, Mock(), Mock(), lambda: False, Mock())
        self.assertEqual(checked, ['a.mov', 'shared.mov', 'last.mov'])
        activated.assert_not_called()

    def test_preparation_and_save_failures_retry_current_video_after_restart(self):
        videos = ['a1.mov', 'a2.mov', 'a3.mov']
        for failing_stage in ('activate', 'record'):
            with self.subTest(stage=failing_stage), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'rotation.json'
                rotation = InterleavedVideoRotation(path)
                events, saves = [], [0]
                def activate(pair, video):
                    events.append(video)
                    if failing_stage == 'activate' and len(events) == 2:
                        raise RuntimeError('Preparation failed')
                def record(pair, task):
                    saves[0] += 1
                    if failing_stage == 'record' and saves[0] == 2:
                        raise RuntimeError('Save failed')
                with self.assertRaises(RuntimeError):
                    run_interleaved_plan([dict(task='A', videos=videos)], {'p': ('s', 1)},
                        lambda *args: 0, Mock(), activate, record, Mock(), lambda: False, Mock(), rotation=rotation)
                self.assertEqual(events, ['a1.mov', 'a2.mov'])
                reloaded = InterleavedVideoRotation(path)
                self.assertEqual(reloaded.position('A', videos), 1)
                stop = [False]
                run_interleaved_plan([dict(task='A', videos=videos)], {'p': ('s', 1)},
                    lambda *args: 0, Mock(), lambda pair, video: events.append(video),
                    lambda *args: stop.__setitem__(0, True), Mock(), lambda: stop[0], Mock(), rotation=reloaded)
                self.assertEqual(events[-1], 'a2.mov')
                self.assertEqual(InterleavedVideoRotation(path).position('A', videos), 2)

    def test_explicit_unsaved_result_never_advances_even_when_stopping(self):
        videos = ['a1.mov', 'a2.mov']
        rotation, stop = InterleavedVideoRotation(), [False]
        def record(*args):
            stop[0] = True
            return False
        run_interleaved_plan([dict(task='A', videos=videos)], {'p': ('s', 1)}, lambda *args: 0,
            Mock(), Mock(), record, Mock(), lambda: stop[0], Mock(), rotation=rotation)
        self.assertEqual(rotation.position('A', videos), 0)

    def test_successful_final_round_advances_before_honoring_stop(self):
        videos = ['a1.mov', 'a2.mov']
        rotation, stop = InterleavedVideoRotation(), [False]
        run_interleaved_plan([dict(task='A', videos=videos)], {'p': ('s', 1)}, lambda *args: 0,
            Mock(), Mock(), lambda *args: stop.__setitem__(0, True), Mock(), lambda: stop[0], Mock(), rotation=rotation)
        self.assertEqual(rotation.position('A', videos), 1)
