import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from interleaved_participants import InterleavedParticipants


class AdmissionReservationTests(unittest.TestCase):
    def test_requested_boots_keep_slots_while_adb_is_still_absent(self):
        source = Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8')
        node = next(node for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.FunctionDef) and node.name == 'start_for_admission')
        targets = {f'phone-{n}': (f'serial-{n}', 5500+n) for n in range(6)}
        pending = {'serial-4': {'session': 'saved-4'}, 'serial-5': {'session': 'saved-5'}}
        now = [0]
        start = Mock()
        status = lambda serial: 'off'
        namespace = dict(time=SimpleNamespace(monotonic=lambda: now[0]), admission_starts={},
                         targets=targets, status=status, options={'simultaneous': 4},
                         start_interleaved=start)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<start_for_admission>', 'exec'), namespace)
        participants = InterleavedParticipants(targets, status, namespace['start_for_admission'],
                                              lambda: pending, lambda serial: False,
                                              lambda: None, lambda **fields: None)
        first = participants.admit(targets, 4, 1)
        self.assertEqual(len(first), 2)
        self.assertEqual(start.call_count, 2)
        now[0] = 2
        second = participants.admit(targets, 4, 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(start.call_count, 2)
        self.assertEqual(set(participants.deferred), {'phone-4', 'phone-5'})
        self.assertLessEqual(len(second) + start.call_count, 4)


if __name__ == '__main__':
    unittest.main()
