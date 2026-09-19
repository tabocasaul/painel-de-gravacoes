import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from voice_manager import VoiceManager, write_json
from tiktok_live import TikTokLive


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = VoiceManager(self.temp.name, self.temp.name, lambda: {})
        self.memory = patch('voice_manager.check_generation_memory')
        self.memory.start()

    def tearDown(self):
        self.manager.close()
        self.memory.stop()
        self.temp.cleanup()

    def test_rejects_path_traversal_and_invalid_identifiers(self):
        for ident in ('../file', 'a' * 31, 'C:\\private.wav', None, 7):
            with self.assertRaises(ValueError):
                self.manager.clip_path(ident)

    def test_chatterbox_installation_does_not_mark_omnivoice_ready(self):
        old_assets = Path(self.temp.name) / 'voice-assets'
        old_assets.mkdir()
        (old_assets / 'ready.json').write_text('{}')
        self.manager.python.parent.mkdir(parents=True)
        self.manager.python.touch()
        self.assertFalse(self.manager.installed())
        new_assets = Path(self.temp.name) / 'omnivoice-assets'
        new_assets.mkdir()
        (new_assets / 'ready.json').write_text('{}')
        self.assertTrue(self.manager.installed())
        self.assertEqual(self.manager.snapshot()['model'], 'OmniVoice')

    def test_unfinished_audio_is_not_listed(self):
        ident = 'a' * 32
        self.manager.clip_path(ident).write_bytes(b'partial')
        self.assertEqual(self.manager.snapshot()['clips'], [])
        write_json(self.manager.clip_path(ident).with_suffix('.json'), {'id': ident, 'text': 'Oi'})
        self.assertEqual(len(self.manager.snapshot()['clips']), 1)

    def test_rejects_empty_long_or_invalid_prompts_before_spawning(self):
        with patch('voice_manager.subprocess.Popen') as spawn:
            for text in (' ', 'a' * 2401, None, []):
                with self.assertRaises(ValueError):
                    self.manager.generate(text)
            with self.assertRaises(ValueError):
                self.manager.generate('Oi', '../model')
            spawn.assert_not_called()

    def test_play_requires_real_clip_valid_volume_and_output(self):
        ident = 'b' * 32
        self.manager.clip_path(ident).write_bytes(b'wav')
        write_json(self.manager.clip_path(ident).with_suffix('.json'), {'id': ident})
        for volume in (-1, 2, float('nan'), float('inf'), 'loud'):
            with self.assertRaises(ValueError):
                self.manager.play(ident, 'headphones', volume)
        with self.assertRaisesRegex(ValueError, 'saída'):
            self.manager.play(ident, 'unplugged', 0.8)

    def test_busy_generation_rejects_second_request_and_cancel_cleans_partial(self):
        gate = threading.Event()
        proc = Mock()
        proc.poll.return_value = None
        proc.returncode = 1
        proc.wait.side_effect = lambda **kw: gate.wait(2)
        proc.terminate.side_effect = gate.set
        with patch.object(self.manager, 'installed', return_value=True), patch('voice_manager.subprocess.Popen', return_value=proc), patch.object(self.manager, 'terminate_worker', side_effect=lambda worker: worker.terminate()):
            ident = self.manager.generate('Oi, gente!')
            self.manager.clip_path(ident).write_bytes(b'partial')
            with self.assertRaisesRegex(ValueError, 'andamento'):
                self.manager.generate('Outra frase')
            self.manager.stop('generation')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and list(self.manager.folder.glob('*.request.json')):
                time.sleep(.01)
            self.assertFalse(self.manager.snapshot()['generation']['busy'])
            self.assertFalse(self.manager.clip_path(ident).exists())
            self.assertEqual(self.manager.snapshot()['clips'], [])

    def test_windows_cancel_targets_only_the_owned_worker_tree(self):
        proc = Mock(pid=4321)
        proc.poll.return_value = None
        with patch('voice_manager.os.name', 'nt'), patch('voice_manager.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.manager.terminate_worker(proc)
        self.assertEqual(run.call_args.args[0], ['taskkill.exe', '/PID', '4321', '/T', '/F'])
        self.assertNotIn('shell', run.call_args.kwargs)


class TikTokTests(unittest.TestCase):
    def setUp(self):
        self.adb = Mock()
        self.live = TikTokLive(self.adb, lambda: {'phone': ('emulator-5554', '5554')})

    def test_unknown_phone_never_reaches_adb(self):
        with self.assertRaises(ValueError):
            self.live.open('emulator-1234')
        self.adb.assert_not_called()

    def test_missing_tiktok_does_not_launch_anything(self):
        self.adb.side_effect = [subprocess.CompletedProcess([], 0, 'device\n'),
                               subprocess.CompletedProcess([], 1, ''), subprocess.CompletedProcess([], 1, ''),
                               subprocess.CompletedProcess([], 0, 'OK')]
        with self.assertRaisesRegex(ValueError, 'não instalado'):
            self.live.open('emulator-5554')
        self.assertFalse(any('monkey' in call.args for call in self.adb.call_args_list))

    def test_microphone_rejection_is_not_reported_as_success(self):
        self.adb.side_effect = [subprocess.CompletedProcess([], 0, 'device\n'), subprocess.CompletedProcess([], 0, 'KO: unknown')]
        with self.assertRaises(RuntimeError):
            self.live.microphone('emulator-5554', True)

    def test_open_only_launches_detected_package(self):
        self.adb.side_effect = [subprocess.CompletedProcess([], 0, 'device\n'),
                               subprocess.CompletedProcess([], 0, 'package:/data/app/tiktok.apk'),
                               subprocess.CompletedProcess([], 0, 'OK'), subprocess.CompletedProcess([], 0, 'Events injected: 1')]
        info = self.live.open('emulator-5554')
        self.assertFalse(info['liveVerified'])
        self.assertIn('com.zhiliaoapp.musically', self.adb.call_args.args)


if __name__ == '__main__':
    unittest.main()
