import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock
from minute_catalog import collect_catalog, read_catalog


class CatalogTests(unittest.TestCase):
    def test_collects_deduplicates_and_saves_only_after_end(self):
        a=Mock();a.e._camera_pronta.return_value=None
        one=ET.fromstring('<hierarchy><node resource-id="task-card-a" content-desc="Louça, tarefa" bounds="[0,0][100,100]"/></hierarchy>')
        two=ET.fromstring('<hierarchy><node resource-id="task-card-b" content-desc="Jardim, tarefa" bounds="[0,0][100,100]"/></hierarchy>')
        a.xml.side_effect=[one,two,two,two]
        with tempfile.TemporaryDirectory() as folder:
            path=str(pathlib.Path(folder)/'catalog.json')
            collect_catalog(a,'s',path,Mock())
            self.assertEqual(read_catalog(path)['tasks'],['Jardim','Louça'])
        a.navigate.assert_not_called()

    def test_camera_blocks_catalog_without_leaving_capture(self):
        a=Mock();a.e._camera_pronta.return_value=1800
        with self.assertRaises(RuntimeError):collect_catalog(a,'s','unused',Mock())
        a.launch_minute.assert_not_called()

    def test_failed_read_keeps_existing_catalog(self):
        a=Mock();a.e._camera_pronta.return_value=None;a.xml.side_effect=RuntimeError('ADB offline')
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'catalog.json';path.write_text('{"tasks":["existing"]}')
            with self.assertRaises(RuntimeError):collect_catalog(a,'s',str(path),Mock())
            self.assertEqual(read_catalog(str(path))['tasks'],['existing'])
