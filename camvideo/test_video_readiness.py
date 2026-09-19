"""Temporary files only; no server initialization, preparation, or devices."""
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_readiness import video_readiness


class PreparationReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.source = self.area / 'source.MOV'
        self.source.write_bytes(b'original')
        self.raw = self.area / 'prepared.i420'
        self.raw.write_bytes(b'prepared frames')
        source = ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8-sig'))
        definitions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                       and node.name in {'prepared_cache', 'cache_metadata_path'}]
        self.ns = dict(os=os, hashlib=hashlib, json=json, AREA=str(self.area), RAW_READY=str(self.raw))
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'cache-only', 'exec'), self.ns)

    def metadata(self, fill=False):
        stat = self.source.stat()
        return dict(name=self.source.name, sourceSize=stat.st_size, sourceMtime=stat.st_mtime_ns,
                    fill=fill, sha256='identity', rawSize=self.raw.stat().st_size, rawPath=str(self.raw))

    def write(self, value, fill=False, legacy=False):
        path = self.area / 'prepared-video.json' if legacy else Path(self.ns['cache_metadata_path'](str(self.source), fill))
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def read(self, fill=False, read_only=True):
        return self.ns['prepared_cache'](str(self.source), fill, read_only=read_only)

    def test_status_read_does_not_create_cache_directory_or_write_legacy_migration(self):
        self.assertIsNone(self.read())
        self.assertFalse((self.area / 'frame-cache').exists())
        metadata = self.metadata()
        legacy = self.write(metadata, legacy=True)
        before = legacy.read_bytes(), legacy.stat().st_mtime_ns
        with patch('builtins.open', wraps=open) as opened:
            self.assertEqual(self.read(), metadata)
            self.assertTrue(all(call.args[1] == 'r' if len(call.args) > 1 else True for call in opened.call_args_list))
        self.assertFalse((self.area / 'frame-cache').exists())
        self.assertEqual((legacy.read_bytes(), legacy.stat().st_mtime_ns), before)

    def test_valid_cache_matches_existing_preflight_and_legacy_migration_still_works(self):
        metadata = self.metadata()
        self.write(metadata, legacy=True)
        self.assertEqual(self.read(), self.read(read_only=False))
        cached = Path(self.ns['cache_metadata_path'](str(self.source), False))
        self.assertEqual(json.loads(cached.read_text()), metadata)

    def test_old_filename_preview_or_changed_file_cannot_be_marked_prepared(self):
        metadata = self.metadata()
        for changes in ({'name':'old-name.MOV'}, {'sourceSize':999}, {'sourceMtime':1},
                        {'rawSize':999}, {'rawPath':str(self.area / 'missing.i420')}):
            with self.subTest(changes=changes):
                self.write(dict(metadata, **changes))
                self.assertIsNone(self.read())
                self.assertIsNone(self.read(read_only=False))

    def test_cropped_preparation_never_means_the_automation_variant_is_ready(self):
        self.write(self.metadata(True), fill=True)
        self.assertIsNone(self.read(False))
        self.assertIsNotNone(self.read(True))
        status = video_readiness(self.source.name, self.read(False), self.read(True), [], {}, {})
        self.assertEqual(status['preparation']['state'], 'missing')
        self.assertTrue(status['preparation']['croppedReady'])

    def test_damaged_metadata_and_partial_or_removed_raw_are_not_green(self):
        for value in ([], None, {}, {'rawPath':None}, dict(self.metadata(), rawPath=None)):
            with self.subTest(value=value):
                self.write(value)
                self.assertIsNone(self.read())
        self.write(self.metadata())
        self.raw.write_bytes(b'partial')
        self.assertIsNone(self.read())
        self.raw.unlink()
        self.assertIsNone(self.read())

    def test_reading_does_not_rehash_or_open_the_video_or_prepared_frames(self):
        self.write(self.metadata())
        actual_open = open
        def metadata_only(path, *args, **kwargs):
            self.assertNotIn(Path(path), (self.source, self.raw))
            return actual_open(path, *args, **kwargs)
        with patch('builtins.open', side_effect=metadata_only):
            self.assertIsNotNone(self.read())


class ReadinessTests(unittest.TestCase):
    def status(self, fit=None, crop=None, background=None, installed=None, phones=None):
        return video_readiness('video.MOV', fit, crop, phones or [], installed or {}, background or {})

    def test_state_tracks_cache_and_background_without_promising_ready_on_job_completion(self):
        self.assertEqual(self.status()['preparation']['state'], 'missing')
        working = {'name':'video.MOV','busy':True,'fill':False,'progress':40}
        self.assertEqual(self.status(background=working)['preparation']['state'], 'preparing')
        self.assertEqual(self.status(background=dict(working,fill=True))['preparation']['preparingCropped'], True)
        self.assertEqual(self.status(background=dict(working,name='another.MOV'))['preparation']['state'], 'missing')
        self.assertEqual(self.status(background=dict(working,busy=False,progress=100))['preparation']['state'], 'missing')
        self.assertEqual(self.status(background=dict(working,busy=False,error='failed'))['preparation']['state'], 'error')
        # A valid cache is still usable while another variant is being prepared.
        self.assertEqual(self.status(fit={'sha256':'same'},background=working)['preparation']['state'], 'ready')

    def test_camera_counts_use_registered_devices_and_content_id_not_filename(self):
        phones = [{'serial':f's{i}'} for i in range(13)]
        installed = {
            's0':{'name':'video.MOV','assetId':'stale:False','confirmed':True},
            's1':{'name':'video.MOV','assetId':'same:False','confirmed':True},
            's2':{'name':'another-name.MOV','assetId':'same:False','staged':True},
            'removed-device':{'assetId':'same:False','confirmed':True}}
        result = self.status(fit={'sha256':'same'}, installed=installed, phones=phones)['cameras']
        self.assertEqual(result, dict(total=13,confirmed=1,staged=1,allConfirmed=False,allAssigned=False))

    def test_staged_and_empty_devices_are_never_all_confirmed(self):
        self.assertFalse(self.status(fit={'sha256':'same'})['cameras']['allConfirmed'])
        phones = [{'serial':'s1'}]
        installed = {'s1':{'assetId':'same:False','staged':True}}
        result = self.status(fit={'sha256':'same'}, installed=installed, phones=phones)['cameras']
        self.assertTrue(result['allAssigned'])
        self.assertFalse(result['allConfirmed'])
        installed['s1']['confirmed'] = True
        result = self.status(fit={'sha256':'same'}, installed=installed, phones=phones)['cameras']
        self.assertTrue(result['allConfirmed'])
        self.assertEqual(result['staged'], 0)

    def test_missing_raw_preparation_cannot_reuse_stale_installation_as_green(self):
        result = self.status(phones=[{'serial':'s1'}], installed={'s1':{'assetId':'same:False','confirmed':True}})
        self.assertFalse(result['preparation']['ready'])
        self.assertFalse(result['cameras']['allConfirmed'])


if __name__ == '__main__':
    unittest.main()
