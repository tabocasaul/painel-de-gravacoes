import json
import builtins
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID
from types import SimpleNamespace

from interleaved_video_rotation import InterleavedVideoRotation


class InterleavedVideoRotationTests(unittest.TestCase):
    def test_configured_junction_alias_is_resolved_before_new_file_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            physical = root / 'physical-data' / 'rotation.json'
            physical.parent.mkdir()
            logical = root / 'configured-junction-chain' / 'rotation.json'
            self.assertFalse(logical.exists())
            self.assertFalse(physical.exists())
            with patch('interleaved_video_rotation.os.path.realpath', return_value=str(physical)) as resolve:
                rotation = InterleavedVideoRotation(logical)
                rotation.advance('Task', ['first.mov', 'second.mov'], 0)
            resolve.assert_called_once_with(os.path.abspath(logical))
            self.assertEqual(rotation.path, str(physical))
            self.assertTrue(physical.is_file())
            self.assertFalse(logical.parent.exists())
            self.assertEqual(InterleavedVideoRotation(physical).position('Task', ['first.mov', 'second.mov']), 1)

    def test_permission_failure_stops_after_one_create_attempt_and_preserves_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            videos = ['first.mov', 'second.mov', 'third.mov']
            rotation.advance('Task', videos, 0)
            previous = path.read_bytes()
            with patch('interleaved_video_rotation.open', create=True,
                       side_effect=PermissionError('injected permission failure')) as create:
                with self.assertRaisesRegex(RuntimeError, 'Sem permissão'):
                    rotation.advance('Task', videos, 1)
            create.assert_called_once()
            self.assertEqual(create.call_args.args[1], 'x')
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(rotation.position('Task', videos), 1)
            self.assertEqual(list(Path(directory).glob('.interleaved-videos-*.tmp')), [])

    def test_only_real_name_collisions_are_retried_and_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            videos = ['first.mov', 'second.mov']
            rotation.advance('Task', videos, 0)
            previous = path.read_bytes()
            collision = Path(directory) / '.interleaved-videos-collision.tmp'
            collision.write_bytes(b'belongs to a different operation')
            with patch('interleaved_video_rotation.uuid.uuid4', return_value=SimpleNamespace(hex='collision')) as names:
                with self.assertRaisesRegex(RuntimeError, 'três tentativas'):
                    rotation.advance('Task', videos, 1)
            self.assertEqual(names.call_count, 3)
            self.assertEqual(collision.read_bytes(), b'belongs to a different operation')
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(rotation.position('Task', videos), 1)

    def test_collision_then_unique_name_commits_and_keeps_other_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            collision = Path(directory) / '.interleaved-videos-collision.tmp'
            collision.write_bytes(b'keep this file')
            rotation = InterleavedVideoRotation(path)
            names = [SimpleNamespace(hex='collision'), SimpleNamespace(hex='available')]
            with patch('interleaved_video_rotation.uuid.uuid4', side_effect=names) as identifier:
                rotation.advance('Task', ['first.mov', 'second.mov'], 0)
            self.assertEqual(identifier.call_count, 2)
            self.assertEqual(collision.read_bytes(), b'keep this file')
            self.assertFalse((Path(directory) / '.interleaved-videos-available.tmp').exists())
            self.assertEqual(InterleavedVideoRotation(path).position('Task', ['first.mov', 'second.mov']), 1)

    def test_fsync_failure_does_not_publish_or_advance_and_closes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            videos = ['first.mov', 'second.mov']
            rotation.advance('Task', videos, 0)
            previous = path.read_bytes()
            opened = []
            def capture(path, mode, **kwargs):
                stream = builtins.open(path, mode, **kwargs)
                opened.append(stream)
                return stream
            with patch('interleaved_video_rotation.open', create=True, side_effect=capture), \
                    patch('interleaved_video_rotation.os.fsync', side_effect=OSError('injected fsync error')), \
                    patch('interleaved_video_rotation.os.replace') as replace:
                with self.assertRaises(RuntimeError):rotation.advance('Task', videos, 1)
                replace.assert_not_called()
            self.assertTrue(all(stream.closed for stream in opened))
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(rotation.position('Task', videos), 1)
            self.assertEqual(list(Path(directory).glob('.interleaved-videos-*.tmp')), [])

    def test_valid_complete_json_is_synced_before_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            order = []
            real_fsync, real_replace = os.fsync, os.replace
            def sync(descriptor):
                order.append('fsync')
                return real_fsync(descriptor)
            def replace(source, destination):
                self.assertEqual(order, ['fsync'])
                self.assertEqual(json.loads(Path(source).read_text(encoding='utf-8'))['version'], 1)
                self.assertEqual(Path(source).parent, path.parent)
                self.assertFalse(path.exists())
                order.append('replace')
                return real_replace(source, destination)
            with patch('interleaved_video_rotation.os.fsync', side_effect=sync), \
                    patch('interleaved_video_rotation.os.replace', side_effect=replace):
                rotation.advance('Task', ['first.mov', 'second.mov'], 0)
            self.assertEqual(order, ['fsync', 'replace'])
            self.assertEqual(InterleavedVideoRotation(path).position('Task', ['first.mov', 'second.mov']), 1)

    def test_new_task_starts_at_first_video_without_advancing_on_read(self):
        rotation = InterleavedVideoRotation()
        videos = ['primeiro.mov', 'segundo.mov']
        self.assertEqual(rotation.position('Lavar louça', videos), 0)
        self.assertEqual(rotation.position('Lavar louça', videos), 0)

    def test_confirmed_advances_follow_playlist_order_and_wrap(self):
        rotation = InterleavedVideoRotation()
        videos = ['z.mov', 'a.mov', 'm.mov']
        for expected in [0, 1, 2, 0, 1, 2, 0]:
            self.assertEqual(rotation.position('Jardim', videos), expected)
            rotation.advance('Jardim', videos, expected)

    def test_single_video_stays_at_zero_after_every_confirmation(self):
        rotation = InterleavedVideoRotation()
        for _ in range(5):
            self.assertEqual(rotation.position('Louça', ['unico.mov']), 0)
            rotation.advance('Louça', ['unico.mov'], 0)

    def test_more_than_four_videos_all_take_turns(self):
        rotation = InterleavedVideoRotation()
        videos = [f'video-{index}.mov' for index in range(7)]
        observed = []
        for _ in range(15):
            index = rotation.position('Organizar livros', videos)
            observed.append(videos[index])
            rotation.advance('Organizar livros', videos, index)
        self.assertEqual(observed, videos * 2 + videos[:1])

    def test_tasks_and_playlists_have_independent_positions(self):
        rotation = InterleavedVideoRotation()
        first = ['a.mov', 'b.mov', 'c.mov']
        second = ['d.mov', 'e.mov']
        rotation.advance('Ervas', first, 0)
        rotation.advance('Jardim', first, 0)
        rotation.advance('Jardim', first, 1)
        rotation.advance('Ervas', second, 0)
        self.assertEqual(rotation.position('Ervas', first), 1)
        self.assertEqual(rotation.position('Jardim', first), 2)
        self.assertEqual(rotation.position('Ervas', second), 1)
        self.assertEqual(rotation.position('Jardim', second), 0)

    def test_changed_playlist_starts_at_zero_and_known_playlist_resumes(self):
        rotation = InterleavedVideoRotation()
        original = ['a.mov', 'b.mov', 'c.mov']
        reordered = ['b.mov', 'a.mov', 'c.mov']
        extended = original + ['d.mov']
        rotation.advance('Ervas', original, 0)
        rotation.advance('Ervas', original, 1)
        self.assertEqual(rotation.position('Ervas', reordered), 0)
        rotation.advance('Ervas', reordered, 0)
        self.assertEqual(rotation.position('Ervas', extended), 0)
        self.assertEqual(rotation.position('Ervas', original), 2)
        self.assertEqual(rotation.position('Ervas', reordered), 1)

    def test_equivalent_task_names_share_position(self):
        rotation = InterleavedVideoRotation()
        videos = ['a.mov', 'b.mov', 'c.mov']
        rotation.advance('Colher Ervas', videos, 0)
        self.assertEqual(rotation.position('  CÓLHER   erva  ', videos), 1)
        rotation.advance('  CÓLHER   erva  ', videos, 1)
        self.assertEqual(rotation.position('Colher Ervas', videos), 2)

    def test_stale_confirmation_does_not_skip_a_video(self):
        rotation = InterleavedVideoRotation()
        videos = ['a.mov', 'b.mov', 'c.mov']
        rotation.advance('Ervas', videos, 0)
        with self.assertRaises(RuntimeError):
            rotation.advance('Ervas', videos, 0)
        self.assertEqual(rotation.position('Ervas', videos), 1)

    def test_new_instance_restores_all_saved_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            first = ['a.mov', 'b.mov', 'c.mov']
            second = ['d.mov', 'e.mov']
            rotation = InterleavedVideoRotation(path)
            rotation.advance('Ervas', first, 0)
            rotation.advance('Ervas', first, 1)
            rotation.advance('Ervas', second, 0)
            rotation.advance('Jardim', first, 0)
            self.assertIsInstance(json.loads(path.read_text(encoding='utf-8')), dict)
            restored = InterleavedVideoRotation(path)
            self.assertEqual(restored.position('Ervas', first), 2)
            self.assertEqual(restored.position('Ervas', second), 1)
            self.assertEqual(restored.position('Jardim', first), 1)
            self.assertEqual(restored.position('Jardim', second), 0)

    def test_memory_only_instances_do_not_share_state(self):
        videos = ['a.mov', 'b.mov']
        rotation = InterleavedVideoRotation(path=None)
        rotation.advance('Ervas', videos, 0)
        self.assertEqual(rotation.position('Ervas', videos), 1)
        self.assertEqual(InterleavedVideoRotation(path=None).position('Ervas', videos), 0)

    def test_replace_failure_preserves_memory_and_previous_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            videos = ['a.mov', 'b.mov', 'c.mov']
            rotation = InterleavedVideoRotation(path)
            rotation.advance('Ervas', videos, 0)
            previous_json = path.read_bytes()
            with patch('interleaved_video_rotation.os.replace',
                       side_effect=OSError('disk unavailable')) as replace:
                with self.assertRaises((OSError, RuntimeError)):
                    rotation.advance('Ervas', videos, 1)
                replace.assert_called_once()
            self.assertEqual(rotation.position('Ervas', videos), 1)
            self.assertEqual(path.read_bytes(), previous_json)
            self.assertEqual(InterleavedVideoRotation(path).position('Ervas', videos), 1)
            rotation.advance('Ervas', videos, 1)
            self.assertEqual(rotation.position('Ervas', videos), 2)
            self.assertEqual(InterleavedVideoRotation(path).position('Ervas', videos), 2)

    def test_invalid_persisted_file_is_rejected(self):
        for contents in ('{invalid json', '[]', 'null', '42'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'rotation.json'
                path.write_text(contents, encoding='utf-8')
                with self.assertRaises(RuntimeError):
                    InterleavedVideoRotation(path)
                self.assertEqual(path.read_text(encoding='utf-8'), contents)

    def test_begin_round_persists_expected_phones_without_advancing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            videos = ['a.mov', 'b.mov', 'c.mov']
            targets = {'Primeiro': ('serial-a', 5554), 'Segundo': ('serial-b', 5556)}
            rotation = InterleavedVideoRotation(path)
            self.assertIsNone(rotation.pending_round)
            rotation.begin_round('Ervas', videos, 0, targets)
            pending = dict(rotation.pending_round)
            self.assertEqual(UUID(hex=pending['id']).hex, pending['id'])
            self.assertTrue(pending['key'])
            self.assertEqual(pending['index'], 0)
            self.assertEqual(pending['count'], 3)
            self.assertEqual(set(pending['serials']), {'serial-a', 'serial-b'})
            self.assertEqual(rotation.position('Ervas', videos), 0)
            restored = InterleavedVideoRotation(path)
            self.assertEqual(restored.pending_round, pending)
            self.assertEqual(restored.position('Ervas', videos), 0)

    def test_restart_reconciles_all_receipts_once_and_persists_next_video(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            videos = ['a.mov', 'b.mov', 'c.mov']
            rotation = InterleavedVideoRotation(path)
            rotation.begin_round('Ervas', videos, 0,
                                 {'A': ('serial-a', 5554), 'B': ('serial-b', 5556)})
            round_id = rotation.pending_round['id']
            receipts = {
                'session-b': {'interleavedRound': round_id, 'serial': 'serial-b'},
                'session-a': {'interleavedRound': round_id, 'serial': 'serial-a'},
                'old-session': {'interleavedRound': 'old-round', 'serial': 'serial-a'},
            }
            restored = InterleavedVideoRotation(path)
            self.assertTrue(restored.reconcile(receipts))
            self.assertEqual(restored.position('Ervas', videos), 1)
            self.assertIsNone(restored.pending_round)
            self.assertFalse(restored.reconcile(receipts))
            again = InterleavedVideoRotation(path)
            self.assertIsNone(again.pending_round)
            self.assertEqual(again.position('Ervas', videos), 1)
            self.assertFalse(again.reconcile(receipts))
            self.assertEqual(again.position('Ervas', videos), 1)

    def test_incomplete_wrong_round_and_duplicate_receipts_do_not_advance(self):
        scenarios = ('none', 'partial', 'wrong_round', 'mixed_round', 'duplicate', 'outsider')
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'rotation.json'
                videos = ['a.mov', 'b.mov']
                rotation = InterleavedVideoRotation(path)
                rotation.begin_round('Ervas', videos, 0,
                                     {'A': ('serial-a', 5554), 'B': ('serial-b', 5556)})
                pending = dict(rotation.pending_round)
                own_id = pending['id']
                receipt_a = {'interleavedRound': own_id, 'serial': 'serial-a'}
                receipt_b = {'interleavedRound': own_id, 'serial': 'serial-b'}
                receipts = {
                    'none': {},
                    'partial': {'a': receipt_a},
                    'wrong_round': {
                        'a': dict(receipt_a, interleavedRound='unrelated-round'),
                        'b': dict(receipt_b, interleavedRound='unrelated-round'),
                    },
                    'mixed_round': {
                        'a': receipt_a,
                        'b': dict(receipt_b, interleavedRound='unrelated-round'),
                    },
                    'duplicate': {'a': receipt_a, 'a-copy': dict(receipt_a)},
                    'outsider': {'a': receipt_a, 'c': dict(receipt_b, serial='serial-c')},
                }[scenario]
                previous_json = path.read_bytes()
                self.assertFalse(rotation.reconcile(receipts))
                self.assertEqual(rotation.position('Ervas', videos), 0)
                self.assertEqual(rotation.pending_round, pending)
                self.assertEqual(path.read_bytes(), previous_json)
                self.assertEqual(InterleavedVideoRotation(path).pending_round, pending)

    def test_reconcile_without_pending_round_does_nothing(self):
        rotation = InterleavedVideoRotation()
        receipts = {'session': {'interleavedRound': 'unrelated-round', 'serial': 'serial-a'}}
        self.assertFalse(rotation.reconcile(receipts))
        self.assertIsNone(rotation.pending_round)
        self.assertEqual(rotation.position('Ervas', ['a.mov', 'b.mov']), 0)

    def test_reconcile_wraps_last_video_and_leaves_other_task_untouched(self):
        rotation = InterleavedVideoRotation()
        videos = ['a.mov', 'b.mov']
        rotation.advance('Ervas', videos, 0)
        rotation.advance('Jardim', videos, 0)
        rotation.begin_round('Ervas', videos, 1, {'A': ('serial-a', 5554)})
        round_id = rotation.pending_round['id']
        self.assertTrue(rotation.reconcile({
            'session': {'interleavedRound': round_id, 'serial': 'serial-a'},
        }))
        self.assertEqual(rotation.position('Ervas', videos), 0)
        self.assertEqual(rotation.position('Jardim', videos), 1)
        self.assertIsNone(rotation.pending_round)

    def test_normal_advance_clears_matching_pending_round(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            videos = ['a.mov', 'b.mov']
            rotation.begin_round('Colher Ervas', videos, 0, {'A': ('serial-a', 5554)})
            round_id = rotation.pending_round['id']
            rotation.advance('  CÓLHER  erva ', videos, 0)
            self.assertIsNone(rotation.pending_round)
            self.assertEqual(rotation.position('Colher Ervas', videos), 1)
            restored = InterleavedVideoRotation(path)
            self.assertIsNone(restored.pending_round)
            self.assertFalse(restored.reconcile({
                'session': {'interleavedRound': round_id, 'serial': 'serial-a'},
            }))
            self.assertEqual(restored.position('Colher Ervas', videos), 1)

    def test_advancing_unrelated_task_preserves_pending_round(self):
        rotation = InterleavedVideoRotation()
        videos = ['a.mov', 'b.mov']
        rotation.begin_round('Ervas', videos, 0, {'A': ('serial-a', 5554)})
        pending = dict(rotation.pending_round)
        rotation.advance('Jardim', videos, 0)
        self.assertEqual(rotation.pending_round, pending)
        self.assertEqual(rotation.position('Ervas', videos), 0)
        self.assertEqual(rotation.position('Jardim', videos), 1)

    def test_begin_round_write_failure_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            videos = ['a.mov', 'b.mov', 'c.mov']
            rotation.advance('Ervas', videos, 0)
            previous_json = path.read_bytes()
            with patch('interleaved_video_rotation.os.replace',
                       side_effect=OSError('disk unavailable')):
                with self.assertRaises(RuntimeError):
                    rotation.begin_round('Ervas', videos, 1, {'A': ('serial-a', 5554)})
            self.assertEqual(rotation.position('Ervas', videos), 1)
            self.assertIsNone(rotation.pending_round)
            self.assertEqual(path.read_bytes(), previous_json)
            self.assertIsNone(InterleavedVideoRotation(path).pending_round)

    def test_reconcile_write_failure_keeps_round_for_later_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.json'
            rotation = InterleavedVideoRotation(path)
            videos = ['a.mov', 'b.mov']
            rotation.begin_round('Ervas', videos, 0, {'A': ('serial-a', 5554)})
            pending = dict(rotation.pending_round)
            receipts = {'session': {'interleavedRound': pending['id'], 'serial': 'serial-a'}}
            previous_json = path.read_bytes()
            with patch('interleaved_video_rotation.os.replace',
                       side_effect=OSError('disk unavailable')):
                with self.assertRaises(RuntimeError):
                    rotation.reconcile(receipts)
            self.assertEqual(rotation.position('Ervas', videos), 0)
            self.assertEqual(rotation.pending_round, pending)
            self.assertEqual(path.read_bytes(), previous_json)
            restored = InterleavedVideoRotation(path)
            self.assertEqual(restored.pending_round, pending)
            self.assertTrue(restored.reconcile(receipts))
            self.assertEqual(restored.position('Ervas', videos), 1)
            self.assertIsNone(restored.pending_round)


if __name__ == '__main__':
    unittest.main()
