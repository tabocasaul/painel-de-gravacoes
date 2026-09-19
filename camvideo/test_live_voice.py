import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from voice_manager import VoiceManager
from live_voice import LiveVoice
from product_writer import ProductWriter, protect, validate_product

PRODUCT = dict(name='Produto de teste', features='Informações de teste fornecidas pelo usuário.', offer='')


class WriterTests(unittest.TestCase):
    def test_dpapi_roundtrip(self):
        import os
        if os.name != 'nt': self.skipTest('Windows only')
        secret = b'test-key-not-a-real-api-key'
        encoded = protect(secret)
        self.assertNotIn(secret, encoded)
        self.assertEqual(protect(encoded, decrypt=True), secret)

    def test_missing_product_is_rejected(self):
        for product in (None, {}, dict(name='Nome', features='', offer='')):
            with self.assertRaises(ValueError): validate_product(product)

    def test_api_payload_and_response(self):
        with tempfile.TemporaryDirectory() as folder:
            writer = ProductWriter(folder)
            text = ('Informação confirmada sobre o produto. ' * 36).strip()
            result = dict(status='completed', output=[dict(type='message',content=[dict(type='output_text',text=json.dumps({'text':text}))])], usage={'total_tokens':123})
            from io import BytesIO
            with patch.object(writer, 'key', return_value='test-secret'), patch('product_writer.urllib.request.urlopen') as send:
                send.return_value.__enter__.return_value = BytesIO(json.dumps(result).encode())
                script, usage = writer.write(PRODUCT)
                payload = json.loads(send.call_args.args[0].data)
                self.assertFalse(payload['store'])
                self.assertEqual(payload['text']['format']['type'], 'json_schema')
                self.assertIn(PRODUCT['name'], payload['input'])
                self.assertEqual(script, text)
                self.assertEqual(usage['total_tokens'], 123)
                send.return_value.__enter__.return_value = BytesIO(json.dumps(result).encode())
                writer.write(PRODUCT, stock={'remaining': 12})
                stock_payload = json.loads(send.call_args.args[0].data)
                self.assertEqual(json.loads(stock_payload['input'])['unidades_restantes_no_valor_promocional'], 12)
                with self.assertRaises(ValueError): writer.write(PRODUCT, stock={'remaining': 0})


FAKE_WORKER = '''import json, pathlib, sys, time
for line in sys.stdin:
    request = json.loads(pathlib.Path(line.strip()).read_text(encoding="utf-8"))
    if request['kind'] == 'generate':
        pathlib.Path(request['wav']).write_bytes(b'fake-test-audio')
        result = dict(ok=True,duration=60,seconds=.01)
    else:
        time.sleep(.2)
        result = dict(ok=True)
    path=pathlib.Path(request['result']); temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(result)); temp.replace(path)
'''


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.voice = VoiceManager(self.temp.name, self.temp.name, lambda: {})
        self.voice.python = Path(sys.executable)
        self.voice.worker.write_text(FAKE_WORKER, encoding='utf-8')
        self.ready = patch.object(self.voice, 'installed', return_value=True); self.ready.start()
        self.memory = patch('voice_manager.check_generation_memory'); self.memory.start()
        self.voice.output_devices = [dict(key='fake-output')]

    def tearDown(self):
        self.voice.close()
        self.ready.stop(); self.memory.stop()
        time.sleep(.1)
        self.temp.cleanup()

    def wait_idle(self):
        deadline = time.monotonic()+5
        while self.voice.jobs['generation'] and time.monotonic()<deadline: time.sleep(.02)
        self.assertIsNone(self.voice.jobs['generation'])

    def test_two_requests_reuse_same_worker(self):
        self.voice.generate('Primeira fala.'); self.wait_idle()
        first = self.voice.engines['generation']
        self.voice.generate('Segunda fala.'); self.wait_idle()
        self.assertIs(self.voice.engines['generation'], first)
        self.assertIsNone(first.poll())
        self.voice.unload(); first.wait(timeout=5)

    def test_continuous_prefetch_and_stop(self):
        writer = ProductWriter(self.temp.name)
        with patch.object(writer, 'configured', return_value=True), patch.object(writer, 'write', return_value=('Texto do produto.', {'total_tokens':10})):
            live = LiveVoice(self.voice, writer)
            live.start(PRODUCT, 'fake-output', minutes=15)
            deadline=time.monotonic()+8
            while live.snapshot()['played']<2 and time.monotonic()<deadline: time.sleep(.03)
            self.assertGreaterEqual(live.snapshot()['generated'], 3)
            self.assertGreaterEqual(live.snapshot()['played'], 2)
            live.stop(); live.thread.join(timeout=5)
            self.assertFalse(live.snapshot()['active'])
            count=live.snapshot()['requests']; time.sleep(.1)
            self.assertEqual(live.snapshot()['requests'],count)
            deadline=time.monotonic()+3
            while any(self.voice.jobs.values()) and time.monotonic()<deadline: time.sleep(.02)

    def test_prepare_does_not_play(self):
        writer=ProductWriter(self.temp.name)
        with patch.object(writer,'configured',return_value=True), patch.object(writer,'write',return_value=('Amostra.',{})):
            live=LiveVoice(self.voice,writer)
            live.start(PRODUCT,continuous=False)
            live.thread.join(timeout=5)
            self.assertFalse(live.snapshot()['active'])
            self.assertEqual(live.snapshot()['generated'],1)
            self.assertEqual(live.snapshot()['played'],0)
            self.assertIsNone(self.voice.engines['playback'])

    def test_real_sale_once_and_no_spontaneous_sales(self):
        writer = ProductWriter(self.temp.name)
        with patch.object(writer, 'configured', return_value=True), patch.object(writer, 'write', return_value=('Produto.', {})):
            live = LiveVoice(self.voice, writer)
            with self.assertRaises(ValueError): live.configure_sales(90, 30)
            with self.assertRaises(ValueError): live.add_sale('P1', True)
            live.configure_sales(10, 10)
            live.start(PRODUCT, 'fake-output', minutes=15)
            try:
                with self.assertRaises(ValueError): live.add_sale('P1', False)
                live.add_sale('P1', True)
                with self.assertRaises(ValueError): live.add_sale('P1', True)
                # Move just this test's timer forward; actual UI enforces >= 10 seconds.
                with live.lock: live.sale_due = time.monotonic() - 1
                deadline = time.monotonic() + 8
                while live.snapshot()['sales']['announced'] < 1 and time.monotonic() < deadline: time.sleep(.03)
                self.assertEqual(live.snapshot()['sales']['announced'], 1)
                time.sleep(.5)
                self.assertEqual(live.snapshot()['sales']['announced'], 1)
                clips = self.voice.snapshot()['clips']
                self.assertEqual(sum('vou usar o nome fictício' in c['text'] for c in clips), 1)
            finally:
                live.stop(); live.thread.join(timeout=5)
            self.assertEqual(live.snapshot()['sales']['queued'], 0)

    def test_batch_real_names_atomic_validation_and_append(self):
        live = LiveVoice(self.voice, ProductWriter(self.temp.name))
        live.state.update(active=True, continuous=True)
        try:
            result = live.add_sales([dict(order='A1', name='Ana'), dict(order='A2', name='Gabriel')], True)
            self.assertEqual(result['added'], 2)
            self.assertIn('Ana, obrigada', live.sales[0])
            self.assertNotIn('fictício', live.sales[0])
            for entries in ([dict(order='A3', name='Clara'), dict(order='A2', name='Gabriel')],
                            [dict(order='A3', name='Clara'), dict(order='A4', name='')]):
                with self.assertRaises(ValueError): live.add_sales(entries, True)
                self.assertEqual(len(live.sales), 2)
                self.assertNotIn('A3', live.sale_orders)
            live.add_sales([dict(order='A3', name='Clara')], True)
            self.assertEqual(len(live.sales), 3)
        finally:
            live.state['active'] = False

    def test_stock_updates_discard_old_prefetch_and_zero_stops(self):
        writer = ProductWriter(self.temp.name)
        calls = []
        played_texts = []
        original_play = self.voice.play
        def record_play(ident, output, volume):
            played_texts.append(json.loads(self.voice.clip_path(ident).with_suffix('.json').read_text())['text'])
            return original_play(ident, output, volume)
        self.voice.play = record_play
        def script(product, previous=(), stock=None):
            calls.append(stock['remaining'] if stock else None)
            return (f'Estoque informado: {calls[-1]}.', {})
        with patch.object(writer, 'configured', return_value=True), patch.object(writer, 'write', side_effect=script):
            live = LiveVoice(self.voice, writer)
            for invalid in (-1, 1.5, True, '5'):
                with self.assertRaises(ValueError): live.update_stock(PRODUCT['name'], invalid)
            live.update_stock(PRODUCT['name'], 12)
            live.start(PRODUCT, 'fake-output', minutes=15)
            try:
                deadline = time.monotonic() + 5
                while live.snapshot()['generated'] < 2 and time.monotonic() < deadline: time.sleep(.03)
                with live.lock:
                    live.update_stock(PRODUCT['name'], 3)
                    played_texts.clear()
                deadline = time.monotonic() + 5
                while not played_texts and time.monotonic() < deadline: time.sleep(.03)
                self.assertIn(12, calls)
                self.assertIn(3, calls)
                self.assertTrue(played_texts)
                self.assertTrue(all('Estoque informado: 3.' == text for text in played_texts))
                live.update_stock(PRODUCT['name'], 0)
                live.thread.join(timeout=5)
                self.assertFalse(live.snapshot()['active'])
                with self.assertRaises(ValueError): live.start(PRODUCT, 'fake-output', minutes=15)
            finally:
                live.stop(); live.thread.join(timeout=5)


if __name__ == '__main__': unittest.main()
