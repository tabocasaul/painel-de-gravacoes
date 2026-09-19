import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import voice_worker


class VoiceRuntimeTests(unittest.TestCase):
    def test_old_environment_forwards_arguments_output_and_exit_status(self):
        with tempfile.TemporaryDirectory() as folder:
            area = Path(folder)
            python = area / 'omnivoice-runtime' / 'Scripts' / 'python.exe'
            python.parent.mkdir(parents=True)
            python.touch()
            output = io.TextIOWrapper(io.BytesIO())
            errors = io.TextIOWrapper(io.BytesIO())
            with patch.object(voice_worker, 'AREA', area), patch('voice_worker.sys.prefix', folder), \
                 patch('voice_worker.sys.argv', ['voice_worker.py', '--outputs']), \
                 patch('voice_worker.sys.stdout', output), patch('voice_worker.sys.stderr', errors), \
                 patch('voice_worker.subprocess.run', return_value=subprocess.CompletedProcess([], 7, b'[]', b'failure')) as run:
                with self.assertRaises(SystemExit) as stopped:
                    voice_worker.enter_voice_runtime()
                self.assertEqual(stopped.exception.code, 7)
                self.assertEqual(run.call_args.args[0][0], str(python))
                self.assertEqual(run.call_args.args[0][-1], '--outputs')
                self.assertEqual(output.buffer.getvalue(), b'[]')
                self.assertEqual(errors.buffer.getvalue(), b'failure')

    def test_correct_environment_does_not_spawn_recursively(self):
        with patch('voice_worker.sys.prefix', str(voice_worker.AREA / 'omnivoice-runtime')), \
             patch('voice_worker.subprocess.run') as run:
            voice_worker.enter_voice_runtime()
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
