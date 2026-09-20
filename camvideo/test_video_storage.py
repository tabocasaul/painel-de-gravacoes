import ast
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import urllib.parse
from http.server import BaseHTTPRequestHandler
from video_storage import VideoStorage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.area=self.root/'area';self.area.mkdir()
        self.old=self.root/'old';self.old.mkdir()
        self.new=self.root/'new';self.cache=self.root/'prepared'
        self.storage=VideoStorage(self.area,self.old)

    def test_new_destinations_persist_and_keep_old_videos(self):
        original=self.old/'old.mp4';original.write_bytes(b'original')
        self.storage.configure(str(self.new),str(self.cache))
        (self.new/'new.mp4').write_bytes(b'new')
        restored=VideoStorage(self.area,self.old)
        self.assertEqual(restored.source('old.mp4'),str(original))
        self.assertEqual(restored.source('new.mp4'),str(self.new/'new.mp4'))
        self.assertEqual(original.read_bytes(),b'original')
        self.assertEqual(restored.data['cachePath'],str(self.cache))

    def test_duplicate_import_names_are_unique_across_folders(self):
        (self.old/'clip.mp4').write_bytes(b'playing')
        self.storage.configure(str(self.new),'')
        (self.new/'clip (2).mp4.uploading').write_bytes(b'pending')
        self.assertEqual(self.storage.upload_name('CLIP.mp4',str(self.new)),'CLIP (3).mp4')

    def test_changing_destination_twice_preserves_all_libraries(self):
        self.storage.configure(str(self.new),'');(self.new/'a.mp4').write_bytes(b'a')
        other=self.root/'other';self.storage.configure(str(other),str(self.cache))
        self.assertEqual(self.storage.source('a.mp4'),str(self.new/'a.mp4'))

    def test_failed_save_keeps_previous_configuration(self):
        before=dict(self.storage.data)
        with patch('video_storage.os.replace',side_effect=PermissionError('blocked')):
            with self.assertRaises(PermissionError):self.storage.configure(str(self.new),str(self.cache))
        self.assertEqual(self.storage.data,before)
        self.assertFalse(self.storage.path.exists())

    def test_invalid_filename_cannot_escape_library(self):
        for name in ('../secret','..\\secret','C:\\secret',''):
            with self.assertRaises(ValueError):self.storage.source(name)

    def test_selected_cache_does_not_fall_back_silently(self):
        self.storage.configure(str(self.new),str(self.cache))
        with patch('video_storage.shutil.disk_usage',return_value=types.SimpleNamespace(free=5)):
            with self.assertRaisesRegex(RuntimeError,'Armazenamento dos vídeos'):
                self.storage.cache_directory(100,str(self.area/'frame-cache'),str(self.old/'.frame-cache'))

    def test_new_cache_does_not_move_or_delete_old_frames(self):
        old=self.area/'frame-cache';old.mkdir();raw=old/'current.i420';raw.write_bytes(b'playing')
        self.storage.configure(str(self.new),str(self.cache))
        self.assertEqual(self.storage.cache_directory(1,str(old),str(self.old/'.frame-cache')),str(self.cache))
        self.assertEqual(raw.read_bytes(),b'playing')

    def test_renamed_video_alias_resolves_across_libraries(self):
        self.storage.configure(str(self.new),'');(self.new/'renamed.mp4').write_bytes(b'new')
        (self.area/'video-library-aliases.json').write_text(json.dumps({'old.mp4':'renamed.mp4'}))
        self.assertEqual(self.storage.resolve(str(self.area),'old.mp4'),'renamed.mp4')

    def test_malformed_saved_configuration_blocks_new_upload(self):
        self.storage.path.write_text('{}')
        broken=VideoStorage(self.area,self.old)
        with self.assertRaises(ValueError):broken.upload_directory()

    def configure_action(self):
        tree=ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='configure_video_storage')
        context=dict(UPLOAD_LOCK=threading.Lock(),PREPARATION_LOCK=threading.Lock(),LIBRARY_LOCK=threading.RLock(),
                     LOCK=threading.Lock(),S={'busy':True,'planActive':True},VIDEO_STORAGE=self.storage,META_CACHE={},
                     BACKGROUND_VIDEO=types.SimpleNamespace(snapshot=lambda:{'busy':False}),
                     FOREGROUND_PREPARATION=types.SimpleNamespace(snapshot=lambda:{'busy':False}))
        exec(compile(ast.Module(body=[function],type_ignores=[]),'<configure>','exec'),context)
        return context

    def test_cannot_switch_destination_during_upload_or_preparation(self):
        context=self.configure_action()
        for lock in ('UPLOAD_LOCK','PREPARATION_LOCK'):
            with context[lock],self.assertRaises(ValueError):
                context['configure_video_storage']({'uploadPath':str(self.new),'cachePath':str(self.cache)})
            self.assertFalse(self.storage.path.exists())

    def test_idle_file_operations_allow_setting_next_destination_during_recording(self):
        context=self.configure_action()
        result=context['configure_video_storage']({'uploadPath':str(self.new),'cachePath':str(self.cache)})
        self.assertEqual(context['S'],{'busy':True,'planActive':True})
        self.assertEqual(result['videoStorage']['cache']['realPath'],str(self.cache))

    def test_http_upload_uses_selected_folder_preserves_active_video_and_state(self):
        (self.old/'clip.mp4').write_bytes(b'playing')
        self.storage.configure(str(self.new),str(self.cache))
        tree=ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8'))
        handler=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='H')
        state={'busy':True,'progress':59,'message':'Gravando'}
        context=dict(BaseHTTPRequestHandler=BaseHTTPRequestHandler,os=os,urllib=urllib,json=json,shutil=shutil,
                     VIDEOS=str(self.old),VIDEO_STORAGE=self.storage,P=types.SimpleNamespace(EXTS=('.mp4',)),
                     LOCK=threading.Lock(),UPLOAD_LOCK=threading.Lock(),S=state,update=lambda **kw:state.update(kw))
        exec(compile(ast.Module(body=[handler],type_ignores=[]),'<handler>','exec'),context)
        request=object.__new__(context['H']);request.path='/api/upload'
        request.headers={'X-Filename':'clip.mp4','Content-Length':'3','X-Background':'1'}
        request.rfile=io.BytesIO(b'new');responses=[]
        request.sendj=lambda body,status=200:responses.append((body,status))
        request.do_POST()
        self.assertEqual(responses[-1][1],200)
        self.assertEqual((self.new/'clip (2).mp4').read_bytes(),b'new')
        self.assertEqual((self.old/'clip.mp4').read_bytes(),b'playing')
        self.assertEqual(state,{'busy':True,'progress':59,'message':'Gravando'})
        self.assertFalse(context['UPLOAD_LOCK'].locked())


if __name__=='__main__':unittest.main()
