"""Isolated local speech/audio worker. Heavy dependencies never enter the panel."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import subprocess
import time

AREA = Path(os.environ['LOCALAPPDATA']) / 'emulation-cam'
ASSETS = AREA / 'omnivoice-assets'
# These are speaking rates, not unsupported emotion instructions.
STYLES = {'natural': 1.0, 'acolhedora': 0.95, 'animada': 1.05}
REFERENCE_TEXT = 'Oi, gente! Que bom ter vocês aqui. Me conta de qual cidade você está assistindo!'
_MODEL = None
_PROMPT = None


def enter_voice_runtime():
    """Older live servers may still invoke this updated file with the old venv."""
    runtime = AREA / 'omnivoice-runtime'
    if Path(sys.prefix).resolve() == runtime.resolve():
        return
    python = runtime / 'Scripts' / 'python.exe'
    if not python.is_file():
        raise RuntimeError('Instale o OmniVoice com setup/INSTALAR-VOZ-LOCAL.ps1.')
    result = subprocess.run([str(python), str(Path(__file__).resolve()), *sys.argv[1:]],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)


def atomic_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def outputs():
    import sounddevice as sd
    apis = sd.query_hostapis()
    result = []
    for index, device in enumerate(sd.query_devices()):
        if device['max_output_channels'] < 1:
            continue
        api = apis[device['hostapi']]['name']
        # Prefer one stable Windows backend, avoiding duplicate MME/DirectSound devices.
        if sys.platform == 'win32' and api != 'Windows WASAPI':
            continue
        name = device['name']
        result.append(dict(key=api + '|' + name, index=index, name=name,
                           rate=int(device['default_samplerate']), channels=device['max_output_channels'],
                           virtual=any(x in name.lower() for x in ('cable input', 'cable in 16ch', 'voicemeeter input', 'voicemeeter aux input'))))
    return result


def generate(request):
    global _MODEL, _PROMPT
    # All model assets are installed explicitly; generation must also work offline.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import numpy as np
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(4)
    seed = request.get('seed', 42)
    torch.manual_seed(seed)
    np.random.seed(seed)
    started = time.monotonic()
    cached = _MODEL is not None
    if _MODEL is None:
        print('Carregando OmniVoice em ' + device, flush=True)
        _MODEL = OmniVoice.from_pretrained(str(ASSETS / 'model'), device_map=device,
            dtype=torch.float16 if device == 'cuda' else torch.float32,
            attn_implementation='sdpa', local_files_only=True)
    model = _MODEL
    print('Gerando fala feminina em português brasileiro...', flush=True)
    with torch.inference_mode():
        reference = ASSETS / 'reference-female.wav'
        if reference.is_file() and _PROMPT is None:
            _PROMPT = model.create_voice_clone_prompt(ref_audio=str(reference), ref_text=REFERENCE_TEXT)
        voice = dict(voice_clone_prompt=_PROMPT) if _PROMPT is not None else dict(instruct='female, young adult')
        if request.get('targetDuration'):
            voice['duration'] = request['targetDuration']
        wav = model.generate(request['text'], language='Portuguese',
                             speed=STYLES[request['style']], num_step=request.get('steps', 32),
                             audio_chunk_duration=15, audio_chunk_threshold=25, **voice)
    data = np.asarray(wav[0], dtype=np.float32).reshape(-1)
    rate = model.sampling_rate
    if not np.isfinite(data).all() or data.size < rate // 4:
        raise RuntimeError('O modelo produziu áudio inválido. Tente uma frase mais curta.')
    path = Path(request['wav'])
    if request.get('saleDemo'):
        # A short original two-tone bell, followed by the requested speech.
        timeline = np.arange(int(rate * .85), dtype=np.float32) / rate
        bell = np.zeros_like(timeline)
        for delay, frequency in ((0, 1318.51), (.16, 1760.0)):
            elapsed = np.maximum(timeline - delay, 0)
            envelope = (timeline >= delay) * np.minimum(elapsed / .005, 1) * np.exp(-elapsed * 7)
            bell += .18 * envelope * (np.sin(2 * np.pi * frequency * elapsed) +
                                     .25 * np.sin(2 * np.pi * frequency * 2.76 * elapsed))
        data = np.concatenate((bell, np.zeros(int(rate * .2), dtype=np.float32), data))
    partial = path.with_suffix('.partial.wav')
    sf.write(partial, data, rate, subtype='PCM_16')
    partial.replace(path)
    return dict(duration=round(data.size / rate, 2), seconds=round(time.monotonic() - started, 2), device=device,
                sampleRate=rate, referenceVoice=reference.is_file(), model='OmniVoice', voice='Feminina em português',
                cachedModel=cached, steps=request.get('steps', 32))


def play(request):
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    from scipy.signal import resample_poly
    selected = next((item for item in outputs() if item['key'] == request['output']), None)
    if not selected:
        raise RuntimeError('A saída de áudio foi desconectada. Atualize a lista e selecione novamente.')
    data, rate = sf.read(request['wav'], dtype='float32', always_2d=True)
    target = selected['rate']
    if rate != target:
        divisor = math.gcd(rate, target)
        data = resample_poly(data, target // divisor, rate // divisor).astype('float32')
    data *= request.get('volume', 0.8)
    # No change to Windows defaults. This process owns only this one audio stream.
    sd.play(data, samplerate=target, device=selected['index'], blocking=True)
    return dict(output=selected['name'])


def main():
    enter_voice_runtime()
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--outputs', action='store_true')
    parser.add_argument('--request')
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    if args.check:
        import importlib.util
        import importlib.metadata
        for module in ('torch', 'torchaudio', 'sounddevice', 'soundfile', 'transformers', 'omnivoice', 'librosa'):
            if importlib.util.find_spec(module) is None:
                raise RuntimeError('Biblioteca ausente: ' + module)
        if not (ASSETS / 'manifest.json').is_file():
            raise RuntimeError('Instale os arquivos do modelo.')
        for file in ('model/model.safetensors', 'model/config.json', 'model/tokenizer.json',
                     'model/tokenizer_config.json', 'model/audio_tokenizer/model.safetensors',
                     'model/audio_tokenizer/config.json', 'model/audio_tokenizer/preprocessor_config.json'):
            if not (ASSETS / file).is_file():
                raise RuntimeError('Arquivo ausente: ' + file)
        # Installation validation must not reserve GPU/RAM. Actual synthesis is
        # tested on the first generation and is reported separately per phrase.
        details = dict(torch=importlib.metadata.version('torch'), version=1, runtime='installed', modelValidated=False)
        atomic_json(ASSETS / 'ready.json', details)
        print(json.dumps(details))
    elif args.outputs:
        print(json.dumps(outputs(), ensure_ascii=False))
    elif args.serve:
        # stdin is a private parent-owned pipe. EOF releases model/GPU on exit.
        for line in sys.stdin:
            path = line.strip()
            if path:
                execute_request(path)
    elif args.request:
        execute_request(args.request)


def execute_request(path):
    request = json.loads(Path(path).read_text(encoding='utf-8'))
    try:
        result = generate(request) if request['kind'] == 'generate' else play(request)
        atomic_json(request['result'], dict(ok=True, **result))
    except Exception as error:
        message = str(error)
        if 'out of memory' in message.lower():
            message = 'Memória da GPU insuficiente. Libere memória e tente novamente.'
        atomic_json(request['result'], dict(ok=False, error=message[:800]))


if __name__ == '__main__':
    main()
