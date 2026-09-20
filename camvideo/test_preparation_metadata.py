import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from preparation_job import stage_preparation_metadata,PreparationCancelled

class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.token=Mock()
    def test_writes_physical_directory_and_preserves_old_record(self):
        old=self.root/'cache.json';old.write_text('old')
        with patch('os.path.realpath',return_value=str(self.root)):
            temp,dest=stage_preparation_metadata('/alias/cache.json',{'ready':True},self.token)
        self.assertEqual(dest,str(old));self.assertEqual(old.read_text(),'old')
        self.assertTrue(json.loads(Path(temp).read_text())['ready'])
    def test_permission_error_is_immediate(self):
        with patch('builtins.open',side_effect=PermissionError('blocked')) as opened:
            with self.assertRaises(PermissionError):stage_preparation_metadata(str(self.root/'cache.json'),{},self.token)
        self.assertEqual(opened.call_count,1)
    def test_collisions_are_bounded_and_do_not_remove_existing_file(self):
        existing=self.root/'.preparation-fixed.tmp';existing.write_text('keep')
        with patch('preparation_job.uuid.uuid4',return_value=Mock(hex='fixed')):
            with self.assertRaisesRegex(RuntimeError,'três'):stage_preparation_metadata(str(self.root/'cache.json'),{},self.token)
        self.assertEqual(existing.read_text(),'keep');self.assertEqual(self.token.check_cancel.call_count,3)
    def test_cancel_before_write_creates_nothing(self):
        self.token.check_cancel.side_effect=PreparationCancelled('cancel')
        with self.assertRaises(PreparationCancelled):stage_preparation_metadata(str(self.root/'cache.json'),{},self.token)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_cancel_during_write_removes_only_its_own_temporary(self):
        old=self.root/'cache.json';old.write_text('old')
        self.token.check_cancel.side_effect=[None,PreparationCancelled('cancel')]
        with self.assertRaises(PreparationCancelled):stage_preparation_metadata(str(old),{},self.token)
        self.assertEqual(list(self.root.iterdir()),[old]);self.assertEqual(old.read_text(),'old')

if __name__=='__main__':unittest.main()
