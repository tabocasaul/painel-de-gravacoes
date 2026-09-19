import http.client
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from panel_runtime import runtime_identity, find_running_backend


class RuntimeTests(unittest.TestCase):
    def test_backend_edit_changes_identity_but_ui_edit_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'voice_manager.py'
            source.write_text('version=1')
            before = runtime_identity(folder, folder)
            (Path(folder) / 'index.html').write_text('new interface')
            self.assertEqual(before, runtime_identity(folder, folder))
            source.write_text('version=2')
            self.assertNotEqual(before['revision'], runtime_identity(folder, folder)['revision'])

    def test_skips_old_server_and_reuses_current_version(self):
        identity = {'app': 'EmulationControl', 'revision': 'current', 'voiceApi': 1, 'root': 'project'}
        old, current = Mock(), Mock()
        old.getresponse.return_value.status = 404
        current.getresponse.return_value.status = 200
        current.getresponse.return_value.read.return_value = json.dumps(identity).encode()
        with patch('panel_runtime.http.client.HTTPConnection', side_effect=[old, current]):
            self.assertEqual(find_running_backend(8768, identity), 8769)
        old.close.assert_called_once()
        current.close.assert_called_once()

    def test_different_version_or_project_is_not_reused(self):
        expected = {'revision': 'current', 'root': 'project'}
        for identity in ({'revision': 'old', 'root': 'project'}, {'revision': 'current', 'root': 'other'}):
            connection = Mock()
            connection.getresponse.return_value.status = 200
            connection.getresponse.return_value.read.return_value = json.dumps(identity).encode()
            with patch('panel_runtime.http.client.HTTPConnection', return_value=connection):
                self.assertIsNone(find_running_backend(8768, expected, count=1))

    def test_closed_or_invalid_endpoints_do_not_block_launch(self):
        connection = Mock()
        connection.request.side_effect = ConnectionRefusedError()
        with patch('panel_runtime.http.client.HTTPConnection', return_value=connection):
            self.assertIsNone(find_running_backend(8768, {}, count=1))


if __name__ == '__main__':
    unittest.main()
