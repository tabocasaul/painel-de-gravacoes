"""Install a pinned OmniVoice model; never download during live synthesis."""
import json
import os
from pathlib import Path
import shutil
import hashlib
import time
import urllib.request

REVISION = 'c5fdb5ccb189668d56333f77ba2629f4cd7535f4'
ROOT = Path(os.environ['LOCALAPPDATA']) / 'emulation-cam' / 'omnivoice-assets'
WEIGHTS = {'model.safetensors': '730839316de585f4c8298ec0e1712efc10fb19c6fa4e36eb741cb8d51ebcf6aa',
           'audio_tokenizer/model.safetensors': 'fe7c5e8785e0a05833e1bfc3e002ec7f55af21e306b2e7154a448c1f54ccfb0d'}

def download(name):
    path = ROOT / 'model' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return
    partial = path.with_suffix('.part')
    for attempt in range(5):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            request = urllib.request.Request(f'https://huggingface.co/k2-fsa/OmniVoice/resolve/{REVISION}/{name}',
                headers={'Range': f'bytes={offset}-'} if offset else {})
            print(f'Baixando {name}, a partir de {offset // 1048576} MB...', flush=True)
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status == 206:
                    if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise RuntimeError('Resposta parcial incompatível.')
                    mode = 'ab'
                else:
                    mode = 'wb'
                with partial.open(mode) as output:
                    while block := response.read(1024 * 1024):
                        output.write(block)
            if name in WEIGHTS:
                with partial.open('rb') as file:
                    if hashlib.file_digest(file, 'sha256').hexdigest() != WEIGHTS[name]:
                        partial.unlink()
                        raise RuntimeError('Checksum inválido: ' + name)
            partial.replace(path)
            print('Concluído: ' + name, flush=True)
            return
        except Exception as error:
            print(str(error), flush=True)
            if attempt == 4:
                raise
            time.sleep(2)

if __name__ == '__main__':
    ROOT.mkdir(parents=True, exist_ok=True)
    for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja',
                 'README.md', 'audio_tokenizer/config.json', 'audio_tokenizer/preprocessor_config.json',
                 'audio_tokenizer/LICENSE', *WEIGHTS):
        download(name)
    for name, expected in WEIGHTS.items():
        with (ROOT / 'model' / name).open('rb') as file:
            if hashlib.file_digest(file, 'sha256').hexdigest() != expected:
                raise RuntimeError('Peso inválido: ' + name)
    for extension in ('wav', 'json'):
        shutil.copyfile(Path(__file__).with_name('omnivoice-reference.' + extension),
                        ROOT / ('reference-female.' + extension))
    (ROOT / 'manifest.json').write_text(json.dumps(dict(model='k2-fsa/OmniVoice',
        revision=REVISION, license='CC-BY-NC', package='omnivoice==0.2.1')), encoding='utf-8')
