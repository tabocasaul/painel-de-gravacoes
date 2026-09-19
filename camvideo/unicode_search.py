"""Write the complete Minute query through Android accessibility, not ADB keycodes."""
import os
from pathlib import Path
import sys
import unicodedata


def exact_text(text):
    return unicodedata.normalize('NFC', text or '').strip().casefold()


def write_query(serial, text):
    runtime = Path(os.environ.get('LOCALAPPDATA', '')) / 'emulation-cam' / 'automation-runtime'
    if str(runtime) not in sys.path:
        sys.path.append(str(runtime))
    try:
        import uiautomator2 as u2
    except ImportError as exc:
        raise RuntimeError('Instale a busca com acentos: setup/INSTALAR-BUSCA-UNICODE.ps1') from exc
    device = u2.connect(serial)
    try:
        field = device(packageName='com.bakerdata.minute', resourceId='home-search-input')
        field.set_text(text, timeout=8)
        actual = field.get_text(timeout=8) or ''
        if not text and actual == 'Buscar tarefas':
            actual = ''
        if exact_text(actual) != exact_text(text):
            raise RuntimeError('O Minute não confirmou o nome completo com os acentos informados.')
    finally:
        # Release UiAutomation so the existing XML/navigation commands can connect.
        device.stop_uiautomator()
