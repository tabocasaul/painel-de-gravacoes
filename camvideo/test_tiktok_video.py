import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tiktok_video import TikTokVideo, library_video, camera_source
from droidcam_output import consumer_size
import struct


class TikTokTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'clip.mp4').write_bytes(b'test')
        self.transport = TikTokVideo('sdk/platform-tools/adb.exe', self.root,
                                    self.root, self.root, self.root, lambda _: 'ffmpeg', lambda: {})

    def tearDown(self):
        self.tmp.cleanup()

    def test_library_blocks_traversal_and_missing_files(self):
        for name in ('../secret.mp4', '..\\secret.mp4', '/clip.mp4', 'missing.mp4', None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                library_video(self.root, name)
        self.assertEqual(library_video(self.root, 'clip.mp4'), self.root / 'clip.mp4')

    def test_identity_rejects_minute_and_empty_adb_response(self):
        for text in ('MinutePlay9\nOK', ''):
            with patch.object(self.transport, 'run_adb', return_value=subprocess.CompletedProcess([], 0, text, '')):
                with self.assertRaises(ValueError):
                    self.transport.validate('emulator-5554')

    def test_missing_camera_does_not_restart_or_start_worker(self):
        with patch.object(self.transport, 'validate'), patch('tiktok_video.subprocess.run',
                return_value=subprocess.CompletedProcess([], 0, "Camera 'DroidCam' 'webcam0'", '')), \
                patch('tiktok_video.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'não enumerou'):
                self.transport.start('emulator-5554', 'clip.mp4', 'Windows WASAPI|CABLE Input')
            spawn.assert_not_called()
            self.assertFalse(self.transport.snapshot()['busy'])

    def test_play_requires_active_connection(self):
        with self.assertRaises(ValueError):
            self.transport.control('play')

    def test_prefers_media_foundation_driver_and_rejects_classic(self):
        listing = "Camera 'OBS Virtual Camera' 'webcam0'\nCamera 'DroidCam Source 3' 'webcam1'\nCamera 'DroidCam Video' 'webcam2'"
        self.assertEqual(camera_source(listing), ('webcam2', 'droidcam'))
        with self.assertRaises(ValueError):
            camera_source("Camera 'DroidCam Source 3' 'webcam0'")

    def test_consumer_dimensions_require_valid_header(self):
        values = [1, 0x02020101, 1280 ^ 720 ^ 333333, 1280, 720, 333333, 0]
        self.assertEqual(consumer_size(struct.pack('<7i', *values)), (1280, 720))
        values[2] = 0
        self.assertIsNone(consumer_size(struct.pack('<7i', *values)))

    def test_never_claims_capture_without_verification(self):
        status = self.transport.snapshot()
        self.assertFalse(status['imageConfirmed'])
        self.assertFalse(status['audioConfirmed'])


if __name__ == '__main__':
    unittest.main()
