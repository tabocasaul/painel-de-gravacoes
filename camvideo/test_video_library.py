"""Only temporary sources and injected recycling; no user videos are touched."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import video_library as library


class VideoLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.videos = self.root / 'videos'
        self.area = self.root / 'area'
        self.videos.mkdir()
        self.area.mkdir()
        self.old = 'Original.MOV'
        self.source = self.videos / self.old
        self.source.write_bytes(b'original source bytes')

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def cache(self, fill):
        raw = self.area / ('raw-fill.i420' if fill else 'raw-fit.i420')
        raw.write_bytes(b'prepared original camera bytes')
        info = self.source.stat()
        metadata = dict(name=self.old, fill=fill, sourceSize=info.st_size,
            sourceMtime=info.st_mtime_ns, rawSize=raw.stat().st_size,
            rawPath=str(raw), sha256='original-digest')
        self.write(library.cache_metadata_path(self.area, self.source, fill), metadata)
        return metadata

    def rename(self, name='Renamed.MOV'):
        return library.rename_video(self.videos, self.area, self.old, name)

    def test_rename_preserves_source_and_both_prepared_variants_and_labels(self):
        before = self.source.stat()
        caches = [self.cache(False), self.cache(True)]
        self.write(self.area / 'prepared-video.json', caches[1])
        self.write(self.area / 'video-selecionado.json', {'name': self.old})
        self.write(self.area / 'camera-installed.json', {'s1': {'name': self.old, 'assetId': 'same'}})
        self.write(self.area / 'shared-cameras.json', {'p1': {'name': self.old, 'rawPath': caches[0]['rawPath'], 'disk': 'untouched'}})
        result = self.rename()
        self.assertEqual(result, {'oldName': self.old, 'name': 'Renamed.MOV'})
        target = self.videos / result['name']
        self.assertEqual((target.stat().st_size, target.stat().st_mtime_ns), (before.st_size, before.st_mtime_ns))
        self.assertFalse(self.source.exists())
        self.assertEqual(target.read_bytes(), b'original source bytes')
        for previous in caches:
            updated = json.loads(library.cache_metadata_path(self.area, target, previous['fill']).read_text())
            self.assertEqual(updated, dict(previous, name=result['name']))
            self.assertEqual(Path(previous['rawPath']).read_bytes(), b'prepared original camera bytes')
        self.assertEqual(json.loads((self.area / 'prepared-video.json').read_text()), dict(caches[1], name=result['name']))
        self.assertEqual(json.loads((self.area / 'camera-installed.json').read_text())['s1'], {'name': result['name'], 'assetId': 'same'})
        self.assertEqual(json.loads((self.area / 'shared-cameras.json').read_text())['p1']['disk'], 'untouched')
        self.assertEqual(library.resolve_name(self.videos, self.area, self.old), result['name'])

    def test_rename_unprepared_source_and_keep_original_extension(self):
        self.assertEqual(self.rename('Simple')['name'], 'Simple.MOV')
        self.assertFalse((self.area / 'frame-cache').exists())

    def test_legacy_prepared_metadata_without_cache_directory_is_preserved(self):
        raw = self.area / 'legacy.i420'
        raw.write_bytes(b'legacy prepared bytes')
        info = self.source.stat()
        metadata = dict(name=self.old, fill=False, sourceSize=info.st_size,
            sourceMtime=info.st_mtime_ns, rawSize=raw.stat().st_size, sha256='legacy')
        self.write(self.area / 'prepared-video.json', metadata)
        result = library.rename_video(self.videos, self.area, self.old, 'new.MOV', str(raw))
        cached = library.cache_metadata_path(self.area, self.videos / result['name'], False)
        self.assertEqual(json.loads(cached.read_text()), dict(metadata, name=result['name']))
        self.assertEqual(raw.read_bytes(), b'legacy prepared bytes')

    def test_case_only_rename_is_supported_without_overwrite(self):
        self.assertEqual(self.rename('original.mov')['name'], 'original.MOV')
        self.assertIn('original.MOV', os.listdir(self.videos))
        self.assertEqual(library.resolve_name(self.videos, self.area, self.old), 'original.MOV')

    def test_extension_changes_paths_reserved_and_invalid_names_are_rejected(self):
        for value in ('Changed.mp4', '../other.MOV', r'folder\other.MOV', 'C:other.MOV',
                      'CON.MOV', 'aux.mov', 'com1.mov', 'LPT².mov', 'NUL .MOV',
                      'bad?.MOV', 'bad\x00.MOV', 'name.MOV.', 'name.MOV ', '', None, 'x' * 256 + '.MOV'):
            with self.subTest(value=value), self.assertRaises((ValueError, UnicodeError)):
                self.rename(value)
            self.assertTrue(self.source.exists())

    def test_collision_is_case_insensitive_and_does_not_replace_other_file(self):
        other = self.videos / 'OTHER.MOV'
        other.write_bytes(b'other')
        with self.assertRaises(ValueError):
            self.rename('other.MOV')
        self.assertEqual(other.read_bytes(), b'other')
        self.assertTrue(self.source.exists())

    def test_source_paths_are_rejected_before_recycle(self):
        calls = []
        for name in ('../outside.MOV', r'..\outside.MOV', str(self.source), '', None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                library.delete_video(self.videos, name, calls.append)
        self.assertEqual(calls, [])

    def test_reparse_source_and_cache_subdirectory_are_rejected(self):
        self.cache(False)
        original = Path.lstat
        for redirected in (self.source, self.area / 'frame-cache'):
            def stat_path(path):
                if path == redirected:
                    return SimpleNamespace(st_mode=0o100644, st_file_attributes=0x400)
                return original(path)
            with self.subTest(path=redirected.name), patch.object(Path, 'lstat', stat_path):
                with self.assertRaisesRegex(ValueError, 'redirecionadas'):
                    self.rename()

    def test_configured_junction_roots_are_trusted_but_cache_uses_logical_path(self):
        metadata = self.cache(False)
        original = Path.lstat
        def roots_are_junctions(path):
            if path in {self.area, self.videos, self.root}:
                return SimpleNamespace(st_mode=0o040755, st_file_attributes=0x400)
            return original(path)
        with patch.object(Path, 'lstat', roots_are_junctions):
            result = self.rename()
            self.assertEqual(library.resolve_name(self.videos, self.area, self.old), result['name'])
        cached = library.cache_metadata_path(self.area, self.videos / result['name'], False)
        self.assertEqual(json.loads(cached.read_text()), dict(metadata, name=result['name']))

    def test_rename_aliases_survive_multiple_edits_and_rename_back(self):
        self.rename('Second.MOV')
        library.rename_video(self.videos, self.area, 'Second.MOV', 'Third.MOV')
        self.assertEqual(library.resolve_name(self.videos, self.area, self.old), 'Third.MOV')
        library.rename_video(self.videos, self.area, 'Third.MOV', self.old)
        self.assertEqual(library.resolve_name(self.videos, self.area, 'Second.MOV'), self.old)

    def test_failed_metadata_commit_rolls_back_source_labels_and_new_cache(self):
        self.cache(False)
        self.cache(True)
        selected = self.area / 'video-selecionado.json'
        self.write(selected, {'name': self.old})
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        real_replace = os.replace
        calls = 0
        def fail_once(source, target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('injected commit failure')
            return real_replace(source, target)
        with patch.object(library.os, 'replace', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'commit failure'):
                self.rename()
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(after, before)

    def test_failed_source_rename_leaves_all_metadata_untouched(self):
        self.cache(False)
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with patch.object(library.os, 'rename', side_effect=PermissionError('source in use')):
            with self.assertRaises(PermissionError):
                self.rename()
        self.assertEqual({str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)

    def test_recycle_moves_only_source_through_injected_adapter(self):
        raw = self.cache(False)['rawPath']
        calls = []
        fake_bin = self.root / 'fake-recycle-bin'
        fake_bin.mkdir()
        def fake_recycle(path):
            calls.append(path)
            os.rename(path, fake_bin / Path(path).name)
        self.assertEqual(library.delete_video(self.videos, self.old, fake_recycle), {'name': self.old, 'deleted': True})
        self.assertEqual(calls, [str(self.source)])
        self.assertEqual((fake_bin / self.old).read_bytes(), b'original source bytes')
        self.assertTrue(Path(raw).exists())
        self.assertTrue(any((self.area / 'frame-cache').glob('*.json')))

    def test_recycle_failure_or_noop_never_falls_back_to_permanent_delete(self):
        def fail(path):
            raise OSError('recycle unavailable')
        for adapter in (fail, lambda path: None):
            with self.subTest(adapter=adapter), self.assertRaises((OSError, RuntimeError)):
                library.delete_video(self.videos, self.old, adapter)
            self.assertEqual(self.source.read_bytes(), b'original source bytes')


if __name__ == '__main__':
    unittest.main()
