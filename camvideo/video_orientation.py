"""Lossless local rotation. Publish only fully verified copies."""
import json
import os
import shutil
import subprocess
import uuid


def rotate_copy(source, destination, degrees, ffmpeg, ffprobe, hidden=None):
    if type(degrees) is not int or degrees not in (-90, 90, 180):
        raise ValueError('Escolha direita, esquerda ou meia-volta.')
    if not ffmpeg or not ffprobe:
        raise ValueError('FFmpeg e FFprobe precisam estar instalados neste computador.')
    options = hidden or {}
    def probe(path):
        result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height:stream_side_data=rotation:format=duration',
            '-of', 'json', path], capture_output=True, text=True, timeout=30, **options)
        if result.returncode:
            raise ValueError('Não foi possível conferir a orientação do vídeo.')
        return json.loads(result.stdout)
    before = probe(source)
    stream = before['streams'][0]
    previous = next((float(s['rotation']) for s in stream.get('side_data_list', []) if 'rotation' in s), 0)
    rotation = (previous - degrees) % 360
    directory = os.path.realpath(os.path.dirname(destination))
    if shutil.disk_usage(directory).free < os.path.getsize(source) + 64*1024*1024:
        raise ValueError('Sem espaço para a cópia girada. Escolha outro disco em Armazenamento dos vídeos.')
    temporary = os.path.join(directory, '.rotation-' + uuid.uuid4().hex + '.tmp')
    try:
        result = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error',
            '-display_rotation:v:0', str(rotation), '-i', source,
            '-map', '0:v:0', '-map', '0:a?', '-c', 'copy', '-f', 'mov', '-n', temporary],
            capture_output=True, text=True, timeout=600, **options)
        if result.returncode:
            raise ValueError('Não foi possível girar este formato sem converter. O original foi preservado.')
        after = probe(temporary)
        actual = next((float(s['rotation']) for s in after['streams'][0].get('side_data_list', []) if 'rotation' in s), 0)
        if abs((actual-rotation+180) % 360-180) > 0.1 or abs(float(after['format']['duration'])-float(before['format']['duration'])) > 1:
            raise ValueError('A orientação não foi confirmada. O original foi preservado.')
        # Windows rename refuses to overwrite an existing destination.
        if os.path.exists(destination):
            raise ValueError('Já existe uma cópia com este nome. Tente novamente.')
        os.rename(temporary, destination)
        return {'name': os.path.basename(destination), 'rotated': True}
    finally:
        if os.path.isfile(temporary):
            os.remove(temporary)
