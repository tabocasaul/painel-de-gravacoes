import sys
import unittest
from unittest.mock import Mock, patch
from unicode_search import write_query, exact_text


class UnicodeTests(unittest.TestCase):
    def test_full_accented_text_is_written_and_connection_released(self):
        device = Mock()
        device.return_value.get_text.return_value = 'Lavar Louça na Pia'
        module = Mock(); module.connect.return_value = device
        with patch.dict(sys.modules, {'uiautomator2':module}):
            write_query('emulator-5582', 'Lavar Louça na Pia')
        device.return_value.set_text.assert_called_once_with('Lavar Louça na Pia', timeout=8)
        device.stop_uiautomator.assert_called_once()

    def test_missing_cedilla_is_not_accepted(self):
        self.assertNotEqual(exact_text('louça'), exact_text('louca'))
        device = Mock(); device.return_value.get_text.return_value = 'Lavar Louca na Pia'
        module = Mock(); module.connect.return_value = device
        with patch.dict(sys.modules, {'uiautomator2':module}), self.assertRaises(RuntimeError):
            write_query('emulator-5582', 'Lavar Louça na Pia')
        device.stop_uiautomator.assert_called_once()
