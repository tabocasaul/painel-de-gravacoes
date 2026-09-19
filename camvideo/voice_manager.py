"""Persistent phrase library and isolated generation/playback jobs."""
import atexit
import ctypes
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

STYLES = {'natural', 'acolhedora', 'animada'}


def check_generation_memory():
    if os.name != 'nt':
        return
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(field, ctypes.c_ulonglong) for field in
            ('total', 'available', 'pageTotal', 'pageAvailable', 'virtualTotal', 'virtualAvailable', 'extended')]
    memory = MemoryStatus()
    memory.length = ctypes.sizeof(memory)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        gib = 1024 ** 3
        if memory.available < 3.5 * gib or memory.pageAvailable < 6 * gib:
            raise ValueError(f'Memória insuficiente para gerar voz: {memory.available/gib:.1f} GB de RAM livres. '
                             'Feche emuladores ociosos ou outros aplicativos e tente novamente. '
                             'A reprodução de falas já salvas continua disponível.')


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


class VoiceManager:
    def __init__(self, area, resources, hidden):
        self.area = Path(area)
        self.folder = self.area / 'voices'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.python = self.area / 'omnivoice-runtime' / 'Scripts' / 'python.exe'
        self.worker = Path(resources) / 'voice_worker.py'
        self.hidden = hidden
        self.lock = threading.RLock()
        self.jobs = {'generation': None, 'playback': None}
        self.states = {'generation': {'busy': False, 'message': 'Escreva uma frase para gerar a voz.'},
                       'playback': {'busy': False, 'message': 'Nenhuma fala em reprodução.'}}
        self.output_devices = []
        self.output_error = ''
        self.scanning = False
        self.engines = {'generation': None, 'playback': None}
        atexit.register(self.close)

    def installed(self):
        return self.python.is_file() and (self.area / 'omnivoice-assets' / 'ready.json').is_file()

    def clip_path(self, ident):
        if not isinstance(ident, str) or not re.fullmatch('[0-9a-f]{32}', ident):
            raise ValueError('Fala inválida.')
        return self.folder / (ident + '.wav')

    def snapshot(self):
        with self.lock:
            clips = []
            for file in self.folder.glob('*.json'):
                if not re.fullmatch('[0-9a-f]{32}', file.stem):
                    continue
                item = read_json(file, {})
                if isinstance(item, dict) and item.get('id') == file.stem and self.clip_path(file.stem).is_file():
                    clips.append(item)
            return dict(installed=self.installed(), model='OmniVoice', voice='Feminina em português',
                        clips=sorted(clips, key=lambda item: item.get('created', 0), reverse=True),
                        outputs=list(self.output_devices), outputError=self.output_error, scanning=self.scanning,
                        generation=dict(self.states['generation']), playback=dict(self.states['playback']),
                        engineLoaded=self.engines['generation'] is not None and self.engines['generation'].poll() is None)

    def refresh_outputs(self):
        with self.lock:
            if self.scanning:
                return
            if not self.installed():
                raise ValueError('A instalação da voz local ainda não foi concluída.')
            self.scanning = True
        def scan():
            try:
                result = subprocess.run([str(self.python), str(self.worker), '--outputs'], capture_output=True,
                                        text=True, encoding='utf-8', timeout=30, env=self.environment(), **self.hidden())
                if result.returncode:
                    raise RuntimeError('Não foi possível listar as saídas de áudio. Confira os dispositivos do Windows.')
                rows = json.loads(result.stdout)
                with self.lock:
                    self.output_devices = rows
                    self.output_error = ''
            except Exception as error:
                with self.lock:
                    self.output_devices = []
                    self.output_error = str(error)
            finally:
                with self.lock:
                    self.scanning = False
        threading.Thread(target=scan, daemon=True).start()

    def environment(self):
        return dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', HF_HUB_DISABLE_TELEMETRY='1')

    def sale_demo(self):
        import secrets
        name = secrets.choice(('Ana Gabriela', 'Mariana', 'Juliana', 'Camila', 'Beatriz'))
        text = ('Simulação de venda. Este é um teste com nome fictício. '
                f'{name} comprou neste exemplo. Obrigada pela confiança, {name}! '
                'Fim da simulação.')
        return self.generate(text, sale_demo=True)

    def generate(self, text, style='natural', steps=32, target_duration=None, seed=42, sale_demo=False):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2400:
            raise ValueError('Escreva um texto de 1 a 2400 caracteres.')
        if not isinstance(style, str) or style not in STYLES:
            raise ValueError('Estilo de voz inválido.')
        if steps not in (16, 32):
            raise ValueError('Qualidade inválida.')
        if target_duration not in (None, 60):
            raise ValueError('Duração inválida.')
        with self.lock:
            if self.engines['generation'] is None or self.engines['generation'].poll() is not None:
                check_generation_memory()
        ident = uuid.uuid4().hex
        meta = dict(id=ident, text=text.strip(), style=style, created=time.time(), model='OmniVoice',
                    voice='Feminina em português', url='/api/voice/audio?id=' + ident)
        self.start('generation', dict(kind='generate', text=text.strip(), style=style, wav=str(self.clip_path(ident)),
                     steps=steps, targetDuration=target_duration, seed=seed, saleDemo=sale_demo), meta)
        return ident

    def play(self, ident, output, volume=0.8):
        path = self.clip_path(ident)
        if not path.is_file() or not path.with_suffix('.json').is_file():
            raise ValueError('Fala não encontrada. Gere o áudio primeiro.')
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= 1:
            raise ValueError('Volume deve estar entre 0 e 1.')
        with self.lock:
            if not any(row['key'] == output for row in self.output_devices):
                raise ValueError('Selecione uma saída de áudio disponível.')
        self.start('playback', dict(kind='play', wav=str(path), output=output, volume=volume), {'id': ident})

    def start(self, channel, request, meta):
        with self.lock:
            if not self.installed():
                raise ValueError('Instale a voz local antes de gerar ou reproduzir falas.')
            if self.jobs[channel] is not None:
                raise ValueError('Já existe uma operação de voz em andamento. Aguarde ou pare a operação.')
            job_id = uuid.uuid4().hex
            request_path = self.folder / (job_id + '.request.json')
            result_path = self.folder / (job_id + '.result.json')
            log_path = self.folder / (job_id + '.log')
            request['result'] = str(result_path)
            write_json(request_path, request)
            proc = self.engines[channel]
            if proc is None or proc.poll() is not None:
                with log_path.open('wb') as log:
                    proc = subprocess.Popen([str(self.python), str(self.worker), '--serve'],
                                            stdin=subprocess.PIPE, stdout=log, stderr=log, env=self.environment(), **self.hidden())
                self.engines[channel] = proc
            try:
                proc.stdin.write((str(request_path) + '\n').encode('utf-8'))
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self.engines[channel] = None
                self.terminate_worker(proc)
                request_path.unlink(missing_ok=True)
                raise ValueError('O motor de voz encerrou. Tente novamente.')
            job = dict(process=proc, cancelled=False, meta=meta)
            self.jobs[channel] = job
            self.states[channel] = dict(busy=True, id=meta['id'], started=time.time(),
                message='Gerando voz no PC. O primeiro uso pode demorar alguns minutos.' if channel == 'generation' else 'Enviando fala à saída selecionada...')
        def watch():
            timeout = False
            try:
                deadline = time.monotonic() + (900 if channel == 'generation' else 180)
                while not result_path.exists() and proc.poll() is None and not job['cancelled']:
                    if time.monotonic() >= deadline:
                        timeout = True
                        self.terminate_worker(proc)
                        break
                    time.sleep(.08)
                result = read_json(result_path, {})
                with self.lock:
                    if job['cancelled']:
                        state = dict(busy=False, message='Geração cancelada.' if channel == 'generation' else 'Reprodução interrompida.')
                    elif timeout:
                        state = dict(busy=False, error=True, message='A operação excedeu o tempo limite. Tente uma frase mais curta.')
                    elif not result.get('ok'):
                        state = dict(busy=False, error=True, message=result.get('error') or 'A voz não concluiu a operação. Consulte o log em ' + str(log_path))
                    else:
                        if channel == 'generation':
                            write_json(self.clip_path(meta['id']).with_suffix('.json'), dict(meta, **{k: v for k, v in result.items() if k != 'ok'}))
                        state = dict(busy=False, id=meta['id'], message='Fala pronta. Ouça a prévia antes de usar.' if channel == 'generation' else 'Fala enviada à saída selecionada.')
                    self.states[channel] = state
            except Exception as error:
                with self.lock:
                    self.states[channel] = dict(busy=False, error=True, message=str(error))
            finally:
                with self.lock:
                    self.jobs[channel] = None
                request_path.unlink(missing_ok=True)
                result_path.unlink(missing_ok=True)
                if channel == 'generation' and not self.clip_path(meta['id']).with_suffix('.json').exists():
                    self.clip_path(meta['id']).unlink(missing_ok=True)
                    self.clip_path(meta['id']).with_suffix('.partial.wav').unlink(missing_ok=True)
        threading.Thread(target=watch, daemon=True).start()

    def stop(self, channel):
        if channel not in self.jobs:
            raise ValueError('Operação inválida.')
        with self.lock:
            job = self.jobs[channel]
            if job is not None:
                job['cancelled'] = True
                if job['process'].poll() is None:
                    self.terminate_worker(job['process'])
                    job['process'].wait(timeout=15)
                if job['process'].stdin:
                    job['process'].stdin.close()
                self.engines[channel] = None

    def terminate_worker(self, proc):
        # Windows venv python.exe is a launcher: stopping only it leaves the
        # actual inference process alive, retaining GPU/RAM and playing audio.
        if proc.poll() is not None:
            return
        if os.name == 'nt':
            result = subprocess.run(['taskkill.exe', '/PID', str(proc.pid), '/T', '/F'],
                                    capture_output=True, timeout=15, **self.hidden())
            if result.returncode and proc.poll() is None:
                raise RuntimeError('Não foi possível interromper o processo de voz.')
        else:
            proc.terminate()

    def close(self):
        for channel in self.jobs:
            self.stop(channel)
        self.unload()

    def unload(self):
        with self.lock:
            if any(self.jobs.values()):
                return
            for channel, proc in self.engines.items():
                if proc is not None:
                    # Graceful EOF: no forced process termination for idle workers.
                    proc.stdin.close()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: self.terminate_worker(proc)
                self.engines[channel] = None
