import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from shared_camera import SharedCamera


class SharedCameraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.avd = self.root/'avds'/'MinutePlay9.avd'
        self.avd.mkdir(parents=True)
        (self.avd/'config.ini').write_text('hw.ramSize = 4096\nhw.sdCard = yes\n', encoding='utf-8')
        self.t = Mock()
        self.t.hidden.return_value = {}
        self.shared = SharedCamera(self.root, self.root, self.root/'avds', self.t, self.root)

    def test_binding_persists_without_copying_video(self):
        raw = self.root/'video.i420';raw.write_bytes(b'frame')
        disk = self.root/'overlay.qcow2';disk.write_bytes(b'overlay')
        record = {'rawPath': str(raw), 'disk': str(disk), 'assetId': 'video'}
        self.shared.bind('MinutePlay9', record)
        self.assertEqual(self.shared.arguments('MinutePlay9'), ['-sdcard', str(disk)])
        self.assertEqual(raw.read_bytes(), b'frame')
        config = (self.avd/'config.ini').read_text()
        self.assertIn('hw.ramSize = 2048', config)
        self.assertIn(str(disk), config)
        self.assertIn('4096', (self.avd/'config.ini.before-shared').read_text())

    def test_offline_install_does_not_boot_or_use_adb(self):
        raw = self.root/'video.i420'; raw.write_bytes(b'a'*4096)
        start = Mock()
        with patch.object(self.shared, 'make_disk', return_value=str(self.root/'disk')):
            self.shared.install('MinutePlay9', 's', 5570, raw, 'video.mov', 100,
                                'asset', start, lambda s: False)
        start.assert_not_called()
        self.t.run.assert_not_called()
        self.assertTrue(self.t.record.call_args.kwargs['staged'])
        self.assertFalse(self.t.record.call_args.kwargs['confirmed'])

    def test_pending_source_is_not_confirmed_if_verification_fails(self):
        self.t.snapshot.return_value = {'installedVideos': {'s': {
            'staged': True, 'assetId': 'asset'}}}
        with patch.object(self.shared, 'bindings', return_value={'avd': {'assetId':'asset','rawPath':'raw'}}), \
             patch.object(self.shared, 'wait_boot'), patch.object(self.shared, 'configure_guest'), \
             patch.object(self.shared, 'verify', side_effect=RuntimeError('wrong frames')):
            with self.assertRaises(RuntimeError): self.shared.activate_pending('avd', 's')
        self.t.record.assert_not_called()

    def test_missing_shared_source_blocks_launch(self):
        self.shared.bind('MinutePlay9', {'rawPath': str(self.root/'missing'), 'disk': str(self.root/'disk')})
        with self.assertRaises(RuntimeError): self.shared.arguments('MinutePlay9')

    def test_overlay_uses_read_only_backing_instead_of_file_copy(self):
        with patch('shared_camera.subprocess.run') as run:
            self.shared.make_disk('MinutePlay9', self.root/'video.i420', 'asset')
        args = run.call_args.args[0]
        self.assertIn('-b', args)
        self.assertEqual(args[args.index('-F')+1], 'raw')
        self.assertEqual(args[args.index('-f')+1], 'qcow2')

    def test_verify_rejects_wrong_camera_data(self):
        raw = self.root/'video.i420';raw.write_bytes(b'a'*12288)
        self.t.run.side_effect = ['', '12288', 'wronghash  -']
        with self.assertRaises(RuntimeError): self.shared.verify('s', raw)

    def test_verify_checks_three_separated_ranges(self):
        raw = self.root/'video.i420';raw.write_bytes(b'a'*4096+b'b'*4096+b'c'*4096)
        digests = [hashlib.sha256(c*4096).hexdigest()+'  -' for c in [b'a', b'b', b'c']]
        self.t.run.side_effect = ['', '12288']+digests
        self.shared.verify('s', raw)
        self.assertEqual(self.t.run.call_count, 5)

    def test_guest_configuration_is_flushed_to_disk(self):
        raw = self.root/'video.i420';raw.write_bytes(b'a'*4096)
        self.shared.configure_guest('s', raw)
        self.assertEqual(self.t.run.call_args.args, ('s', 'shell', 'sync'))
        script = self.t.run.call_args_list[-2].args[1]
        self.assertIn('chmod 755 /data/adb/modules/videocam/service.sh', script)


if __name__ == '__main__': unittest.main()
