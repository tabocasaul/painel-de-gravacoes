"""Local destinations for new imports and frame caches. Never moves old files."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import threading
import uuid
from video_library import filename, aliases


class VideoStorage:
    def __init__(self, area, library):
        self.path = Path(os.path.realpath(area)) / 'video-storage.json'
        self.original = os.path.abspath(library)  # Preserve old cache signatures.
        self.lock = threading.RLock()
        self.data = {'uploadPath': self.original, 'cachePath': '', 'libraries': [self.original]}
        self.error = ''
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or not isinstance(value.get('libraries'), list)
                    or not all(isinstance(p, str) and os.path.isabs(p) for p in value['libraries'])
                    or not isinstance(value.get('uploadPath'), str) or not os.path.isabs(value['uploadPath'])
                    or not isinstance(value.get('cachePath'), str)
                    or (value['cachePath'] and not os.path.isabs(value['cachePath']))):
                raise ValueError('Formato inválido')
            self.data = value
            self.data['libraries'] = list(dict.fromkeys([self.original, *value['libraries'], value['uploadPath']]))
        except FileNotFoundError:
            pass
        except (ValueError, OSError, TypeError):
            self.error = 'Não foi possível ler as pastas salvas. Confira a configuração antes de importar.'

    def roots(self):
        with self.lock:
            return list(self.data['libraries'])

    def files(self):
        result = {}
        for root in self.roots():
            try:
                for name in os.listdir(root):
                    path = os.path.join(root, name)
                    if os.path.isfile(path):
                        result.setdefault(name.casefold(), (name, path))
            except OSError:
                continue
        return sorted(result.values(), key=lambda item: item[0].casefold())

    def source(self, name):
        name = filename(name)
        for actual, path in self.files():
            if actual.casefold() == name.casefold():
                return path
        return os.path.join(self.original, name)

    def resolve(self, area, name):
        name = filename(name)
        links, seen = aliases(area), set()
        while not os.path.isfile(self.source(name)) and name in links:
            if name in seen:
                raise ValueError('Referências de vídeos contêm um ciclo.')
            seen.add(name)
            name = links[name]
        return name

    @staticmethod
    def directory(value):
        if not isinstance(value, str) or not value.strip() or not os.path.isabs(value.strip()):
            raise ValueError('Informe uma pasta com caminho completo, como C:\\Gravacoes\\Videos.')
        value = value.strip()
        if os.name == 'nt' and (value.startswith(('\\\\', '//')) or len(os.path.splitdrive(value)[0]) != 2):
            raise ValueError('Escolha uma pasta em um disco local do computador.')
        path = os.path.realpath(value)
        if os.name == 'nt' and not os.path.isdir(os.path.splitdrive(path)[0] + '\\'):
            raise ValueError('O disco escolhido não está disponível.')
        os.makedirs(path, exist_ok=True)
        probe = Path(path) / ('.painel-write-' + uuid.uuid4().hex)
        try:
            with probe.open('xb') as stream:
                stream.write(b'ok')
        finally:
            probe.unlink(missing_ok=True)
        return path

    def configure(self, upload, cache):
        with self.lock:
            upload = self.directory(upload)
            cache = self.directory(cache) if cache else ''
            # Keep the exact spelling of existing roots for cache reuse.
            upload = next((p for p in self.roots() if os.path.normcase(os.path.realpath(p)) == os.path.normcase(upload)), upload)
            value = {'uploadPath': upload, 'cachePath': cache,
                     'libraries': list(dict.fromkeys([*self.roots(), upload]))}
            temp = self.path.with_name('.storage-' + uuid.uuid4().hex + '.tmp')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with temp.open('x', encoding='utf-8') as stream:
                    json.dump(value, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)
            self.data = value
            self.error = ''
            return self.snapshot()

    def upload_directory(self):
        with self.lock:
            if self.error:
                raise ValueError(self.error)
            path = self.data['uploadPath']
        if not os.path.isdir(path):
            raise ValueError('A pasta de importação não está disponível. Escolha outra no painel.')
        return path

    def upload_name(self, name, directory):
        name = filename(name)
        stem, ext = os.path.splitext(name)
        used = {n.casefold() for n, _ in self.files()}
        original, index = name, 2
        while name.casefold() in used or os.path.lexists(os.path.join(directory, name)) or os.path.lexists(os.path.join(directory, name) + '.uploading'):
            name = f'{stem} ({index}){ext}'
            index += 1
        return name

    def cache_directory(self, required, default, fallback):
        with self.lock:
            if self.error:
                raise ValueError(self.error)
            selected = self.data['cachePath']
        candidates = [selected] if selected else [default, fallback]
        checked = []
        for folder in candidates:
            real = os.path.realpath(folder)
            if real in checked:
                continue
            checked.append(real)
            os.makedirs(real, exist_ok=True)
            free = shutil.disk_usage(real).free
            if free >= required:
                return real
        available = '; '.join(f'{p}: {shutil.disk_usage(p).free / 1024**3:.1f} GiB livres' for p in checked)
        raise RuntimeError(f'Preparação precisa de {required / 1024**3:.1f} GiB. {available}. Escolha outra pasta em Armazenamento dos vídeos.')

    @staticmethod
    def info(path):
        if not path:
            return None
        real = os.path.realpath(path)
        try:
            free = shutil.disk_usage(real).free
        except OSError:
            free = None
        return {'path': path, 'realPath': real, 'freeBytes': free}

    def snapshot(self):
        with self.lock:
            data = dict(self.data)
        drives = []
        if os.name == 'nt':
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                root = chr(65 + i) + ':\\'
                if mask & (1 << i) and ctypes.windll.kernel32.GetDriveTypeW(root) in (2, 3):
                    item = self.info(root)
                    base = os.path.join(root, 'PainelGravacoes')
                    if os.path.splitdrive(os.path.expanduser('~'))[0].casefold() == root[:2].casefold():
                        base = os.path.join(os.path.expanduser('~'), 'Videos', 'PainelGravacoes')
                    item.update(uploadPath=os.path.join(base, 'Videos'), cachePath=os.path.join(base, 'Preparados'))
                    drives.append(item)
        return {'upload': self.info(data['uploadPath']), 'cache': self.info(data['cachePath']),
                'libraries': [self.info(p) for p in data['libraries']],
                'defaultCaches': [self.info(str(self.path.parent / 'frame-cache')), self.info(os.path.join(self.original, '.frame-cache'))],
                'drives': drives, 'error': self.error}
