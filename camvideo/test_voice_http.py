import http.client
import importlib.machinery
import json
from pathlib import Path
import tempfile
import threading
import unittest

from voice_manager import VoiceManager, write_json

panel = importlib.machinery.SourceFileLoader('voice_http_panel', str(Path(__file__).with_name('modern_server.pyw'))).load_module()


class VoiceHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = panel.VOICE
        panel.VOICE = VoiceManager(self.temp.name, self.temp.name, lambda: {})
        self.server = panel.PanelServer(('127.0.0.1', 0), panel.H)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        panel.VOICE.close()
        panel.VOICE = self.previous
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, path, json.dumps(data) if data is not None else None,
                           {'Content-Type': 'application/json', **(headers or {})})
        response = connection.getresponse()
        code, body = response.status, response.read()
        connection.close()
        return code, body

    def test_cross_origin_generation_is_rejected(self):
        code, _ = self.request('POST', '/api/voice/action', {'action': 'generate', 'text': 'Oi'}, {'Origin': 'https://example.com'})
        self.assertEqual(code, 403)
        self.assertEqual(list(panel.VOICE.folder.iterdir()), [])

    def test_invalid_json_shape_returns_client_error(self):
        code, _ = self.request('POST', '/api/voice/action', ['generate'])
        self.assertEqual(code, 400)

    def test_audio_path_traversal_does_not_expose_files(self):
        code, _ = self.request('GET', '/api/voice/audio?id=../../private')
        self.assertEqual(code, 404)

    def test_unpublished_audio_is_not_served(self):
        ident = 'e' * 32
        path = panel.VOICE.clip_path(ident)
        path.write_bytes(b'partial')
        self.assertEqual(self.request('GET', '/api/voice/audio?id=' + ident)[0], 404)
        write_json(path.with_suffix('.json'), {'id': ident})
        self.assertEqual(self.request('GET', '/api/voice/audio?id=' + ident), (200, b'partial'))


if __name__ == '__main__':
    unittest.main()
