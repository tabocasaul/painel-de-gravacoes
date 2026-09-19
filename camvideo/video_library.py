"""Local source-file edits. Prepared camera files are never moved or deleted."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


def filename(value):
    if (not isinstance(value, str) or not value or value in {'.', '..'}
            or len(value.encode('utf-16-le')) // 2 > 255
            or value[-1] in ' .'
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in value)):
        raise ValueError('Informe somente um nome de arquivo válido, sem pastas.')
    stem = value.split('.')[0].rstrip(' ').upper()
    if re.fullmatch(r'CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]', stem):
        raise ValueError('Esse nome é reservado pelo Windows.')
    return value


def _plain_path(path, missing=False, root=None):
    """Trust the configured root, rejecting redirects anywhere beneath it.

    The installed application deliberately uses Junctions for its configured
    VIDEOS/AREA roots. Keep their logical spelling (cache keys depend on it),
    while verifying their physical root before inspecting child components.
    """
    path = Path(os.path.abspath(path))
    if root is None:
        parts = (*reversed(path.parents), path)
    else:
        root = Path(os.path.abspath(root))
        if not root.resolve(strict=True).is_dir():
            raise ValueError('A pasta configurada da biblioteca não está disponível.')
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError('O arquivo não pertence à pasta configurada.') from exc
        parts = [root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)]
    for part in parts:
        try:
            info = part.lstat()
        except FileNotFoundError:
            if missing and part == path:
                return path
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Links e pastas redirecionadas não podem ser alterados pela biblioteca.')
    return path


def source_path(library, name):
    name = filename(name)
    directory = _plain_path(library, root=library)
    source = _plain_path(directory / name, root=library)
    if source.parent != directory or not source.is_file():
        raise ValueError('Vídeo não encontrado na biblioteca.')
    return source


def _json(path, missing=None, root=None):
    try:
        path = _plain_path(path, missing=True, root=root)
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return missing


def aliases(area):
    data = _json(Path(area) / 'video-library-aliases.json', {}, root=area)
    if not isinstance(data, dict):
        raise ValueError('As referências da biblioteca estão inválidas.')
    for old, new in data.items():
        filename(old)
        filename(new)
    return data


def resolve_name(library, area, name):
    """Old saved plans keep working after a source is renamed."""
    name = filename(name)
    links = aliases(area)
    seen = set()
    actual_names = set(os.listdir(library))
    while name not in actual_names and name in links:
        if name in seen:
            raise ValueError('As referências da biblioteca contêm um ciclo.')
        seen.add(name)
        name = links[name]
    return name


def cache_metadata_path(area, source, fill, source_stat=None):
    source_stat = source_stat or os.stat(source)
    signature = f'{os.path.abspath(source)}:{source_stat.st_mtime_ns}:{source_stat.st_size}:{bool(fill)}'
    return Path(area) / 'frame-cache' / (hashlib.sha256(signature.encode()).hexdigest() + '.json')


def _encoded(data):
    return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')


def _stage(path, content, root=None):
    _plain_path(path.parent, root=root)
    _plain_path(path, missing=True, root=root)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.library-edit-', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    return temporary


def _reference_updates(area, old, new):
    updates = {}
    for leaf in ('video-selecionado.json', 'camera-installed.json', 'shared-cameras.json'):
        path = Path(area) / leaf
        data = _json(path, root=area)
        if data is None:
            continue
        if not isinstance(data, dict):
            raise ValueError('Um registro da biblioteca está inválido: ' + leaf)
        records = [data] if leaf == 'video-selecionado.json' else list(data.values())
        changed = False
        for record in records:
            if isinstance(record, dict) and record.get('name') == old:
                record['name'] = new
                changed = True
        if changed:
            updates[path] = _encoded(data)
    return updates


def rename_video(library, area, old_name, new_name, default_raw=None):
    source = source_path(library, old_name)
    new_name = filename(new_name)
    extension = source.suffix
    proposed_extension = Path(new_name).suffix
    if not proposed_extension:
        new_name += extension
    elif proposed_extension.casefold() != extension.casefold():
        raise ValueError('Mantenha a extensão original do vídeo: ' + extension)
    else:
        new_name = new_name[:-len(proposed_extension)] + extension
    filename(new_name)
    target = source.parent / new_name
    if old_name == new_name:
        return {'oldName': old_name, 'name': new_name}
    for entry in source.parent.iterdir():
        if entry.name.casefold() == new_name.casefold() and entry.name != old_name:
            raise ValueError('Já existe um arquivo com esse nome na biblioteca.')
    _plain_path(target, missing=True, root=library)
    original_stat = source.stat()
    updates = _reference_updates(area, old_name, new_name)
    links = aliases(area)
    # Flatten existing aliases so rename A->B->A cannot create a cycle.
    links = {old: (new_name if resolve_name(library, area, old) == old_name else value)
             for old, value in links.items() if old != new_name}
    links[old_name] = new_name
    updates[Path(area) / 'video-library-aliases.json'] = _encoded(links)
    shared_meta_path = Path(area) / 'prepared-video.json'
    shared_meta = _json(shared_meta_path, root=area)
    for fill in (False, True):
        metadata_path = cache_metadata_path(area, source, fill, original_stat)
        metadata = _json(metadata_path, root=area)
        if metadata is None:
            metadata = shared_meta
        if not isinstance(metadata, dict) or metadata.get('name') != old_name or metadata.get('fill') != fill:
            continue
        if (metadata.get('sourceSize') != original_stat.st_size
                or metadata.get('sourceMtime') != original_stat.st_mtime_ns):
            continue
        raw = metadata.get('rawPath', default_raw)
        if not raw or not os.path.isfile(raw) or metadata.get('rawSize') != os.path.getsize(raw):
            continue
        renamed = dict(metadata, name=new_name)
        updates[cache_metadata_path(area, target, fill, original_stat)] = _encoded(renamed)
    if isinstance(shared_meta, dict) and shared_meta.get('name') == old_name:
        updates[shared_meta_path] = _encoded(dict(shared_meta, name=new_name))
    cache_directory = Path(area) / 'frame-cache'
    if any(path.parent == cache_directory for path in updates):
        # A legacy installation may only have prepared-video.json. Its valid
        # metadata gets a normal cache entry without preparing the raw again.
        _plain_path(cache_directory, missing=True, root=area)
        cache_directory.mkdir(exist_ok=True)
        _plain_path(cache_directory, root=area)
    staged, backups, applied = {}, {}, []
    renamed = False
    try:
        for path, content in updates.items():
            _plain_path(path, missing=True, root=area)
            backups[path] = path.read_bytes() if path.exists() else None
            staged[path] = _stage(path, content, root=area)
        # On Windows rename refuses to replace another file even if an external
        # program creates it after the case-insensitive collision check.
        os.rename(source, target)
        renamed = True
        for path, temporary in staged.items():
            os.replace(temporary, path)
            applied.append(path)
    except BaseException as error:
        failures = []
        for path in reversed(applied):
            try:
                if backups[path] is None:
                    path.unlink(missing_ok=True)
                else:
                    rollback = _stage(path, backups[path], root=area)
                    try:
                        os.replace(rollback, path)
                    finally:
                        rollback.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(exc)
        if renamed:
            try:
                os.rename(target, source)
            except OSError as exc:
                failures.append(exc)
        if failures:
            raise RuntimeError('Não foi possível concluir nem restaurar toda a renomeação. Confira a biblioteca antes de continuar.') from error
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
    return {'oldName': old_name, 'name': new_name}


def delete_video(library, name, recycle=None):
    source = source_path(library, name)
    if recycle is None:
        from windows_recycle import recycle_file
        recycle = recycle_file
    recycle(str(source))
    if source.exists():
        raise RuntimeError('O Windows não confirmou o envio do vídeo à Lixeira.')
    return {'name': name, 'deleted': True}
