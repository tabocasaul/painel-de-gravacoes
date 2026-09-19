"""Move one file to the Windows Recycle Bin, with no permanent-delete fallback.

Flags: https://learn.microsoft.com/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags
Vtable: Microsoft WinSDK ShObjIdl_core.h, IFileOperation.
"""
import ctypes
import os
import stat
import sys
import uuid


FOFX_RECYCLEONDELETE = 0x00080000
FOFX_EARLYFAILURE = 0x00100000
FOFX_ADDUNDORECORD = 0x20000000
FOF_NOERRORUI = 0x0400
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_NO_CONNECTED_ELEMENTS = 0x2000
RECYCLE_FLAGS = (FOFX_RECYCLEONDELETE | FOFX_EARLYFAILURE | FOFX_ADDUNDORECORD
                 | FOF_NOERRORUI | FOF_SILENT | FOF_NOCONFIRMATION | FOF_NO_CONNECTED_ELEMENTS)


class GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16),
                ('Data3', ctypes.c_uint16), ('Data4', ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check(result):
    if result & 0x80000000:
        raise RuntimeError('O Windows não conseguiu mover o vídeo para a Lixeira '
                           f'(0x{result & 0xFFFFFFFF:08X}). Nenhuma exclusão definitiva será tentada.')


def _invoke(pointer, slot, result_type, argument_types=(), arguments=()):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    method = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[slot])
    return method(pointer, *arguments)


class _WindowsOperation:
    def __init__(self, path):
        self.operation = ctypes.c_void_p()
        self.item = ctypes.c_void_p()
        self.initialized = False
        self.ole = ctypes.WinDLL('ole32')
        shell = ctypes.WinDLL('shell32')
        self.ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.ole.CoInitializeEx.restype = ctypes.c_int32
        self.ole.CoUninitialize.argtypes = []
        self.ole.CoUninitialize.restype = None
        self.ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p,
                                            ctypes.c_uint32, ctypes.POINTER(GUID),
                                            ctypes.POINTER(ctypes.c_void_p)]
        self.ole.CoCreateInstance.restype = ctypes.c_int32
        shell.SHCreateItemFromParsingName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
                                                     ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        shell.SHCreateItemFromParsingName.restype = ctypes.c_int32
        try:
            _check(self.ole.CoInitializeEx(None, 2))  # Each HTTP worker owns its STA.
            self.initialized = True
            clsid = GUID.parse('3ad05575-8857-4850-9277-11b85bdb8e09')
            operation_id = GUID.parse('947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8')
            _check(self.ole.CoCreateInstance(ctypes.byref(clsid), None, 1,
                                           ctypes.byref(operation_id), ctypes.byref(self.operation)))
            item_id = GUID.parse('43826d1e-e718-42ee-bc55-a1e261c37bfe')
            _check(shell.SHCreateItemFromParsingName(path, None, ctypes.byref(item_id), ctypes.byref(self.item)))
        except BaseException:
            self.close()
            raise

    def set_flags(self, flags):
        _check(_invoke(self.operation, 5, ctypes.c_int32, (ctypes.c_uint32,), (flags,)))

    def queue_delete(self):
        _check(_invoke(self.operation, 18, ctypes.c_int32,
                       (ctypes.c_void_p, ctypes.c_void_p), (self.item, None)))

    def perform(self):
        _check(_invoke(self.operation, 21, ctypes.c_int32))

    def aborted(self):
        value = ctypes.c_int32()
        _check(_invoke(self.operation, 22, ctypes.c_int32,
                       (ctypes.POINTER(ctypes.c_int32),), (ctypes.byref(value),)))
        return bool(value.value)

    def close(self):
        for pointer in (self.item, self.operation):
            if pointer:
                _invoke(pointer, 2, ctypes.c_uint32)
                pointer.value = None
        if self.initialized:
            self.ole.CoUninitialize()
            self.initialized = False


def recycle_file(path, *, _factory=None):
    """Caller must already have validated the library boundary and operation lock."""
    path = os.fspath(path)
    if not os.path.isabs(path) or '\x00' in path:
        raise ValueError('Caminho de vídeo inválido.')
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or os.path.islink(path)
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        raise ValueError('Somente um arquivo de vídeo regular pode ser enviado à Lixeira.')
    if _factory is None:
        if os.name != 'nt' or tuple(sys.getwindowsversion()[:2]) < (6, 2):
            raise RuntimeError('A Lixeira segura precisa do Windows 8 ou posterior.')
        _factory = _WindowsOperation
    operation = _factory(path)
    try:
        operation.set_flags(RECYCLE_FLAGS)
        operation.queue_delete()
        operation.perform()
        if operation.aborted():
            raise RuntimeError('O envio à Lixeira foi cancelado ou não foi concluído.')
    finally:
        operation.close()
