"""Download pinned official PT-BR inference code, weights and demo voice."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

SPACE = 'ResembleAI/Chatterbox-Multilingual-TTS-pt-br'
SPACE_REV = '9e515821e826e207cd617a0fdd0223899ed108ea'
MODEL = 'ResembleAI/Chatterbox-Multilingual-pt-br'
MODEL_REV = 'b3952f18bc2eaa72b9bd7c17d2c4653bcad4770d'
BASE_REV = '5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18'
REFERENCE = 'https://storage.googleapis.com/chatterbox-demo-samples/mtl-v3-single-language-prompts/pt-br/pt_br_f2.wav'
ROOT = Path(os.environ['LOCALAPPDATA']) / 'emulation-cam' / 'voice-assets'


def download(url, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size:
        return
    partial = destination.with_name(destination.name + '.part')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as response, partial.open('wb') as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            partial.replace(destination)
            print('Baixado:', destination.name, flush=True)
            return
        except Exception as error:
            if attempt == 3:
                raise
            print(f'Nova tentativa para {destination.name}: {error}', flush=True)
            time.sleep(2 * (attempt + 1))


def main():
    url = f'https://huggingface.co/api/spaces/{SPACE}/tree/{SPACE_REV}?recursive=true&limit=1000'
    with urllib.request.urlopen(url, timeout=60) as response:
        entries = json.load(response)
    code = [(f'https://huggingface.co/spaces/{SPACE}/resolve/{SPACE_REV}/{entry["path"]}', ROOT / 'source' / entry['path'])
            for entry in entries if entry['type'] == 'file' and entry['path'].startswith('chatterbox/')]
    if not code:
        raise RuntimeError('O código oficial de inferência não foi encontrado.')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda item: download(*item), code))
    for name in ('t3_pt_br.safetensors', 's3gen_v3.pt'):
        download(f'https://huggingface.co/{MODEL}/resolve/{MODEL_REV}/{name}', ROOT / 'model' / name)
    for name in ('ve.pt', 'grapheme_mtl_merged_expanded_v1.json'):
        download(f'https://huggingface.co/ResembleAI/chatterbox/resolve/{BASE_REV}/{name}', ROOT / 'model' / name)
    download(REFERENCE, ROOT / 'reference-female.wav')
    expected = {'t3_pt_br.safetensors': '074aaf65255eb9cb960288f7cc72e09d3b5008f6e0b14868c0d4e5b0bd7cbb6c',
                's3gen_v3.pt': 'f7abce4b196dae2d08d9296cbebc6521b046079577643b42a19a03499d08721e'}
    for name, digest in expected.items():
        with (ROOT / 'model' / name).open('rb') as model_file:
            checksum = hashlib.file_digest(model_file, 'sha256').hexdigest()
        if checksum != digest:
            raise RuntimeError(f'Checksum inválido em {name}. Remova esse arquivo e execute a instalação novamente.')
    (ROOT / 'manifest.json').write_text(json.dumps(dict(model=MODEL, revision=MODEL_REV, sourceRevision=SPACE_REV,
        baseRevision=BASE_REV, reference=REFERENCE), indent=2), encoding='utf-8')
    print('Arquivos da voz local prontos.', flush=True)


if __name__ == '__main__':
    main()
