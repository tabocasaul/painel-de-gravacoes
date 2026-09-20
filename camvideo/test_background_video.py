import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import types
import unittest
import io
import urllib.parse
from http.server import BaseHTTPRequestHandler

from background_video import BackgroundVideo
from video_storage import VideoStorage
from preparation_job import PreparationJob, run_conversion, stage_preparation_metadata


class BackgroundTests(unittest.TestCase):
    def test_background_upload_preserves_running_state_and_existing_file(self):
        tree = ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8'))
        handler = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'H')
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'clip.mp4').write_bytes(b'active source')
            running = {'busy': True, 'progress': 62, 'message': 'Gravando'}
            context = dict(BaseHTTPRequestHandler=BaseHTTPRequestHandler, os=os,
                           urllib=urllib, json=json, shutil=shutil, VIDEOS=folder,
                           P=types.SimpleNamespace(EXTS=('.mp4',)),
                           LOCK=threading.Lock(), UPLOAD_LOCK=threading.Lock(),
                           S=running, update=lambda **kw: running.update(kw))
            context['VIDEO_STORAGE']=VideoStorage(folder,folder)
            exec(compile(ast.Module(body=[handler], type_ignores=[]), '<handler>', 'exec'), context)
            instance = object.__new__(context['H'])
            instance.path = '/api/upload'
            instance.headers = {'X-Filename': 'clip.mp4', 'Content-Length': '3', 'X-Background': '1'}
            instance.rfile = io.BytesIO(b'new')
            responses = []
            instance.sendj = lambda body, status=200: responses.append((body, status))
            instance.do_POST()
            self.assertEqual(responses[-1][1], 200)
            self.assertEqual((Path(folder) / 'clip.mp4').read_bytes(), b'active source')
            self.assertEqual((Path(folder) / 'clip (2).mp4').read_bytes(), b'new')
            self.assertEqual(running, {'busy': True, 'progress': 62, 'message': 'Gravando'})
            self.assertFalse(context['UPLOAD_LOCK'].locked())

    def test_rejects_duplicate_job_and_keeps_errors_separate(self):
        gate = threading.Event()
        def prepare(*args, **kwargs):
            gate.wait(2)
            raise ValueError('conversion failed')
        worker = BackgroundVideo(prepare)
        worker.start('test.mp4')
        with self.assertRaises(ValueError):
            worker.start('other.mp4')
        gate.set()
        deadline = time.monotonic() + 3
        while worker.snapshot()['busy'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(worker.snapshot()['error'], 'conversion failed')
        self.assertFalse(worker.snapshot()['busy'])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
    def test_real_conversion_preserves_active_source_and_reuses_cache(self):
        tree = ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8'))
        wanted = {'prepare_video', '_prepare_video', 'cache_metadata_path', 'prepared_cache'}
        definitions = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted], type_ignores=[])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'clip.mp4'
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x64:rate=30', '-t', '0.2', '-y', str(source)], check=True, capture_output=True)
            active = Path(folder) / 'prepared-video.json'
            active.write_text('{"active":"unchanged"}')
            global_updates = []
            context = dict(os=os, time=time, hashlib=hashlib, json=json, shutil=shutil,
                           tempfile=tempfile,PreparationJob=PreparationJob,run_conversion=run_conversion,stage_preparation_metadata=stage_preparation_metadata,
                           subprocess=subprocess, VIDEOS=folder, AREA=folder, RAW_READY='',
                           PREPARATION_LOCK=threading.Lock(), hidden=lambda: {},
                           P=types.SimpleNamespace(achar=shutil.which),
                           video_meta=lambda path: {'duration': .2},
                           update=lambda **kw: global_updates.append(kw))
            context['VIDEO_STORAGE']=VideoStorage(folder,folder)
            context['video_source']=context['VIDEO_STORAGE'].source
            exec(compile(definitions, '<preparation>', 'exec'), context)
            events = []
            prepare = context['prepare_video']
            prepare('clip.mp4', False, notify=lambda **kw: events.append(kw), background=True)
            cache = context['prepared_cache'](str(source), False)
            self.assertGreater(cache['rawSize'], 0)
            self.assertEqual(cache['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(active.read_text(), '{"active":"unchanged"}')
            self.assertEqual(global_updates, [])
            prepare('clip.mp4', False, notify=lambda **kw: events.append(kw), background=True)
            self.assertEqual(cache['rawPath'], context['prepared_cache'](str(source), False)['rawPath'])
            self.assertEqual(events[-1]['stage'], 'Quadros prontos')


if __name__ == '__main__':
    unittest.main()
