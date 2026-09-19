"""Isolated server functions: no initialization, server socket, or ADB calls."""
import ast
from contextlib import contextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from video_library import rename_video, source_path, resolve_name


class LibraryServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name) / 'area'
        self.videos = Path(self.temp.name) / 'videos'
        self.area.mkdir()
        self.videos.mkdir()
        (self.videos / 'old.MOV').write_bytes(b'fake source')
        self.background = SimpleNamespace(snapshot=Mock(return_value={'busy': False}), start=Mock())
        self.ns = dict(os=os, threading=threading, json=json, LOCK=threading.Lock(),
            S={'busy': False}, PREPARATION_LOCK=threading.Lock(), UPLOAD_LOCK=threading.Lock(),
            LIBRARY_LOCK=threading.RLock(), LIBRARY_READERS=0,contextmanager=contextmanager,
            PROXY_LOCK=threading.Lock(), PROXY_JOBS=set(), META_CACHE={},
            TRANSFERS=SimpleNamespace(lock=threading.RLock()), SHARED=SimpleNamespace(lock=threading.RLock()),
            BACKGROUND_VIDEO=self.background, SUPERVISOR=SimpleNamespace(state=Mock(return_value={'enabled':False,'pending':{}})),
            TIKTOK_VIDEO=SimpleNamespace(snapshot=Mock(return_value={'active':False,'busy':False})),
            LIVE_VOICE=SimpleNamespace(snapshot=Mock(return_value={'active':False})),
            P=SimpleNamespace(EXTS=('.mov','.mp4')), VIDEOS=str(self.videos), AREA=str(self.area), RAW_READY='unused',
            source_path=source_path, resolve_name=resolve_name, rename_video=rename_video, delete_video=Mock(),
            devices=Mock(side_effect=AssertionError('Video edits must not touch phones')))
        source = ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8-sig'))
        names = {'action','edit_video_library','start_background_video','preflight_plan_video','library_read'}
        body = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
        handler = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'H')
        body.extend(node for node in handler.body if isinstance(node, ast.FunctionDef) and node.name == 'do_POST')
        exec(compile(ast.Module(body=body,type_ignores=[]), 'server-only-functions', 'exec'), self.ns)

    def rename(self):
        return self.ns['action']({'action':'rename_video','video':'old.MOV','name':'new.MOV'})

    def test_action_is_synchronous_and_never_discovers_or_changes_phones(self):
        self.assertEqual(self.rename(), {'oldName':'old.MOV','name':'new.MOV'})
        self.assertFalse((self.videos / 'old.MOV').exists())
        self.ns['devices'].assert_not_called()
        self.assertFalse(self.ns['S']['busy'])

    def test_busy_background_supervisor_pending_live_and_proxy_reject_before_edit(self):
        changes = [lambda:self.ns['S'].update(busy=True),
            lambda:setattr(self.background.snapshot, 'return_value', {'busy':True}),
            lambda:setattr(self.ns['SUPERVISOR'].state, 'return_value', {'enabled':True}),
            lambda:setattr(self.ns['SUPERVISOR'].state, 'return_value', {'pending':{'s1':{}}}),
            lambda:setattr(self.ns['TIKTOK_VIDEO'].snapshot, 'return_value', {'active':True}),
            lambda:setattr(self.ns['LIVE_VOICE'].snapshot, 'return_value', {'active':True}),
            lambda:self.ns['PROXY_JOBS'].add('preview')]
        for change in changes:
            self.ns['S'].clear()
            self.background.snapshot.return_value = {'busy':False}
            self.ns['SUPERVISOR'].state.return_value = {}
            self.ns['TIKTOK_VIDEO'].snapshot.return_value = {}
            self.ns['LIVE_VOICE'].snapshot.return_value = {}
            self.ns['PROXY_JOBS'].clear()
            change()
            with self.assertRaises(ValueError):
                self.rename()
            self.assertTrue((self.videos / 'old.MOV').exists())

    def test_preparation_and_background_upload_mutex_block_mutation(self):
        for name in ('PREPARATION_LOCK','UPLOAD_LOCK','PROXY_LOCK'):
            with self.subTest(name=name), self.ns[name]:
                with self.assertRaises(ValueError):
                    self.rename()
            self.assertTrue((self.videos / 'old.MOV').exists())
        self.rename()

    def test_slow_preview_allows_parallel_library_reads_but_refuses_edits(self):
        entered, finish, listed = threading.Event(), threading.Event(), threading.Event()
        def slow_stream():
            with self.ns['library_read']():
                entered.set()
                finish.wait(3)
        def list_sources():
            with self.ns['library_read']():
                self.assertIn('old.MOV', os.listdir(self.videos))
                listed.set()
        stream = threading.Thread(target=slow_stream)
        stream.start()
        try:
            self.assertTrue(entered.wait(3))
            reader = threading.Thread(target=list_sources)
            reader.start()
            reader.join(1)
            self.assertTrue(listed.is_set(), 'State/library polling must not wait for the stream')
            self.assertFalse(reader.is_alive())
            with self.assertRaisesRegex(ValueError, 'leitura'):
                self.rename()
        finally:
            finish.set()
            stream.join(3)
        self.assertEqual(self.ns['LIBRARY_READERS'], 0)
        self.rename()

    def test_reader_exception_releases_registration(self):
        with self.assertRaises(RuntimeError):
            with self.ns['library_read']():
                raise RuntimeError('disconnected browser')
        self.assertEqual(self.ns['LIBRARY_READERS'], 0)
        self.rename()

    def test_background_start_cannot_claim_old_name_during_transaction(self):
        entered, finish = threading.Event(), threading.Event()
        actual = self.ns['rename_video']
        def held(*args):
            entered.set()
            self.assertTrue(finish.wait(3))
            return actual(*args)
        self.ns['rename_video'] = held
        errors = []
        def run():
            try:self.rename()
            except BaseException as exc:errors.append(exc)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(entered.wait(3))
            with self.assertRaises(ValueError):
                self.ns['start_background_video']('old.MOV', False)
            self.background.start.assert_not_called()
            with self.assertRaises(ValueError):
                self.rename()
        finally:
            finish.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_failure_releases_every_mutex_and_busy_flag(self):
        self.ns['rename_video'] = Mock(side_effect=OSError('injected'))
        with self.assertRaises(OSError):self.rename()
        self.assertFalse(self.ns['S']['busy'])
        for name in ('PREPARATION_LOCK','UPLOAD_LOCK','PROXY_LOCK'):
            self.assertTrue(self.ns[name].acquire(blocking=False))
            self.ns[name].release()

    def test_daily_old_name_preflight_reuses_renamed_cache(self):
        self.rename()
        self.ns['prepared_cache'] = Mock(return_value={'sha256':'prepared'})
        self.assertEqual(self.ns['preflight_plan_video']('old.MOV'), {'sha256':'prepared'})
        self.ns['prepared_cache'].assert_called_once_with(str(self.videos / 'new.MOV'), False)

    def test_http_returns_completed_result_with_200_and_legacy_job_with_202(self):
        for result, expected in (({'oldName':'old.MOV','name':'new.MOV'},200), (None,202)):
            self.ns['action'] = Mock(return_value=result)
            body = json.dumps({'action':'rename_video','video':'old.MOV','name':'new.MOV'}).encode()
            handler = SimpleNamespace(path='/api/action', headers={'Content-Length':str(len(body))},
                rfile=BytesIO(body), sendj=Mock())
            self.ns['do_POST'](handler)
            self.assertEqual(handler.sendj.call_args.args, ({'ok':True,**(result or {})},expected))

    def test_library_http_rejects_foreign_origin_and_wrong_route_before_action(self):
        for route, origin in (('/api/action','https://foreign.example'), ('/unrelated',None)):
            self.ns['action'] = Mock()
            body = json.dumps({'action':'delete_video','video':'old.MOV'}).encode()
            headers = {'Content-Length':str(len(body)), 'Host':'127.0.0.1:8768'}
            if origin:headers['Origin'] = origin
            handler = SimpleNamespace(path=route, headers=headers,rfile=BytesIO(body),sendj=Mock())
            self.ns['do_POST'](handler)
            self.assertEqual(handler.sendj.call_args.args[1],403)
            self.ns['action'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
