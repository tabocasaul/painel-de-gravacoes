import ctypes
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from windows_recycle import (recycle_file, RECYCLE_FLAGS, FOFX_RECYCLEONDELETE,
                             FOFX_EARLYFAILURE, FOF_NOERRORUI, GUID, _invoke, _check)


class RecycleTests(unittest.TestCase):
    def test_recycle_only_flags_and_lifecycle_without_touching_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'vídeo.MOV'
            path.write_bytes(b'preserved')
            operation = Mock()
            operation.aborted.return_value = False
            factory = Mock(return_value=operation)
            recycle_file(path, _factory=factory)
            factory.assert_called_once_with(str(path))
            operation.set_flags.assert_called_once_with(RECYCLE_FLAGS)
            self.assertTrue(RECYCLE_FLAGS & FOFX_RECYCLEONDELETE)
            self.assertTrue(RECYCLE_FLAGS & FOFX_EARLYFAILURE)
            self.assertTrue(RECYCLE_FLAGS & FOF_NOERRORUI)
            self.assertEqual([call[0] for call in operation.mock_calls],
                             ['set_flags', 'queue_delete', 'perform', 'aborted', 'close'])
            self.assertEqual(path.read_bytes(), b'preserved')

    def test_any_com_error_stops_without_fallback(self):
        for step in ('set_flags', 'queue_delete', 'perform', 'aborted'):
            with self.subTest(step=step), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'video.MOV'
                path.write_bytes(b'preserved')
                operation = Mock()
                getattr(operation, step).side_effect = RuntimeError('Cannot recycle')
                with self.assertRaisesRegex(RuntimeError, 'Cannot recycle'):
                    recycle_file(path, _factory=lambda _: operation)
                operation.close.assert_called_once()
                if step in ('set_flags', 'queue_delete'):
                    operation.perform.assert_not_called()
                self.assertEqual(path.read_bytes(), b'preserved')

    def test_abort_is_an_error_and_never_reports_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'video.MOV'
            path.write_bytes(b'preserved')
            operation = Mock()
            operation.aborted.return_value = True
            with self.assertRaisesRegex(RuntimeError, 'cancelado'):
                recycle_file(path, _factory=lambda _: operation)
            operation.close.assert_called_once()
            self.assertEqual(path.read_bytes(), b'preserved')

    def test_directory_and_relative_path_never_create_an_operation(self):
        factory = Mock()
        with tempfile.TemporaryDirectory() as folder:
            for path in (folder, 'relative.MOV'):
                with self.assertRaises(ValueError):
                    recycle_file(path, _factory=factory)
        factory.assert_not_called()

    def test_signed_and_unsigned_failed_hresult(self):
        for code in (-2147024891, 0x80070005):
            with self.assertRaisesRegex(RuntimeError, '80070005'):
                _check(code)
        _check(0)
        _check(1)

    def test_guid_layout_matches_windows_abi(self):
        self.assertEqual(ctypes.sizeof(GUID), 16)
        value = GUID.parse('3ad05575-8857-4850-9277-11b85bdb8e09')
        self.assertEqual(value.Data1, 0x3AD05575)
        self.assertEqual(value.Data2, 0x8857)
        self.assertEqual(value.Data3, 0x4850)
        self.assertEqual(bytes(value.Data4), bytes.fromhex('927711b85bdb8e09'))

    @unittest.skipUnless(hasattr(ctypes, 'WINFUNCTYPE'), 'Windows calling convention')
    def test_real_ctypes_vtable_dispatch_uses_correct_argument_width(self):
        seen = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_uint32)
        callback = callback_type(lambda this, flags: seen.append(flags) or 0)
        table = (ctypes.c_void_p * 23)()
        table[5] = ctypes.cast(callback, ctypes.c_void_p).value
        table_pointer = ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p))
        instance = ctypes.pointer(table_pointer)
        result = _invoke(ctypes.cast(instance, ctypes.c_void_p), 5, ctypes.c_int32,
                         (ctypes.c_uint32,), (RECYCLE_FLAGS,))
        self.assertEqual(result, 0)
        self.assertEqual(seen, [RECYCLE_FLAGS])


if __name__ == '__main__':
    unittest.main()
