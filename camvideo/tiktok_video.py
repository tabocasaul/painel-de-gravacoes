"""Dedicated TikTok video transport. Never participates in Minute batches."""
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def library_video(library, name):
    root = Path(library).resolve()
    if not isinstance(name, str) or not name or '/' in name or '\\' in name:
        raise ValueError('Selecione um vídeo da biblioteca.')
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError('Vídeo não encontrado na biblioteca.')
    return path


def camera_source(listing):
    for name, backend in [('DroidCam Video', 'droidcam'), ('OBS Virtual Camera', 'obs')]:
        match = re.search(r"Camera '" + re.escape(name) + r"'.*?'(webcam\d+)'", listing, re.I)
        if match:
            return match[1], backend
    raise ValueError('O emulador não enumerou uma câmera compatível. Instale o driver DroidCam Video com setup/INSTALAR-TIKTOK-CAMERA.ps1. DroidCam Source 3 é a versão antiga e não serve. Nenhum celular foi reiniciado.')


class TikTokVideo:
    def __init__(self, adb, area, avd_home, library, resources, find, hidden):
        self.adb, self.hidden, self.find = adb, hidden, find
        self.area, self.library = Path(area), Path(library)
        self.avd_home, self.resources = Path(avd_home), Path(resources)
        self.emulator = Path(adb).parent.parent / 'emulator' / 'emulator.exe'
        self.python = self.area / 'omnivoice-runtime' / 'Scripts' / 'python.exe'
        self.lock = threading.RLock()
        self.proc = None
        self.cancel = threading.Event()
        self.state = dict(busy=False, active=False, message='Selecione o vídeo e conecte o TikTok Atual.',
                          stage='idle', video='', imageConfirmed=False, audioConfirmed=False)
        self.control_path = self.status_path = None
        self.discovery_time, self.discovery = 0, []

    def run_adb(self, serial, *args, timeout=15):
        return subprocess.run([str(self.adb), '-s', serial, *args], capture_output=True,
                              text=True, timeout=timeout, **self.hidden())

    def phones(self):
        with self.lock:
            if time.monotonic() - self.discovery_time < 3:
                return list(self.discovery)
            rows = []
            result = subprocess.run([str(self.adb), 'devices'], capture_output=True,
                                    text=True, timeout=8, **self.hidden())
            for serial in re.findall(r'^(emulator-\d+)\s+device$', result.stdout, re.M):
                name = self.run_adb(serial, 'emu', 'avd', 'name', timeout=5).stdout.splitlines()
                if name and name[0].strip() == 'TikTokAtual':
                    rows.append(dict(name='TikTok Atual', avd='TikTokAtual', serial=serial, status='online'))
            self.discovery_time, self.discovery = time.monotonic(), rows
            return list(rows)

    def validate(self, serial):
        if not re.fullmatch(r'emulator-\d+', str(serial)):
            raise ValueError('Selecione o TikTok Atual ligado.')
        result = self.run_adb(serial, 'emu', 'avd', 'name')
        if result.returncode or not result.stdout.splitlines() or result.stdout.splitlines()[0].strip() != 'TikTokAtual':
            raise ValueError('Esta conexão aceita apenas TikTokAtual; não altera celulares Minute.')

    def snapshot(self):
        with self.lock:
            value = dict(self.state)
            if self.status_path and self.status_path.exists():
                try:
                    worker = json.loads(self.status_path.read_text(encoding='utf-8'))
                    if worker.get('error'):
                        value.update(stage='error', message=worker['error'], active=False)
                    elif not value['busy'] and value['active']:
                        value.update({k: worker[k] for k in ('stage', 'message', 'frames', 'audioSent') if k in worker})
                except (OSError, ValueError):
                    pass
            if self.proc and self.proc.poll() is not None:
                value['active'] = False
            return value

    def start(self, serial, name, output, volume=.8):
        source = library_video(self.library, name)
        if not isinstance(output, str) or 'CABLE Input' not in output:
            raise ValueError('Selecione CABLE Input como saída de áudio do vídeo.')
        volume = float(volume)
        if not 0 <= volume <= 1:
            raise ValueError('Volume inválido.')
        with self.lock:
            if self.state['busy'] or (self.proc and self.proc.poll() is None):
                raise ValueError('Pare a conexão atual antes de trocar o vídeo.')
            self.validate(serial)
            cams = subprocess.run([str(self.emulator), '-webcam-list'], capture_output=True,
                                  text=True, timeout=20, **self.hidden())
            camera, backend = camera_source(cams.stdout)
            if not self.python.is_file():
                raise ValueError('Instale o ambiente de voz e setup/INSTALAR-TIKTOK-VIDEO.ps1.')
            ffmpeg = self.find('ffmpeg')
            if not ffmpeg:
                raise ValueError('FFmpeg não encontrado.')
            self.cancel.clear()
            self.status_path = None
            self.state.update(busy=True, active=False, stage='preparing', video=name, serial=serial,
                              message='Preparando vídeo e áudio; o TikTok Atual será reiniciado.',
                              imageConfirmed=False, audioConfirmed=False)
            threading.Thread(target=self._start, args=(serial, source, output, volume, camera, ffmpeg, backend), daemon=True).start()

    def _start(self, serial, source, output, volume, camera, ffmpeg, backend):
        try:
            folder = self.area / 'tiktok-video' / uuid.uuid4().hex
            folder.mkdir(parents=True)
            self.control_path, self.status_path = folder / 'control.json', folder / 'status.json'
            request = dict(source=str(source), output=output, volume=volume, ffmpeg=ffmpeg, parentPid=os.getpid(), backend=backend,
                           control=str(self.control_path), status=str(self.status_path), folder=str(folder))
            write_json(folder / 'request.json', request)
            write_json(self.control_path, dict(mode='pause', generation=0))
            with (folder / 'worker.log').open('wb') as log:
                self.proc = subprocess.Popen([str(self.python), str(self.resources / 'tiktok_video_worker.py'),
                                              str(folder / 'request.json')], stdout=log, stderr=log, **self.hidden())
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if self.cancel.is_set():
                    raise RuntimeError('Conexão cancelada.')
                if self.proc.poll() is not None:
                    raise RuntimeError(self.snapshot().get('message') or 'Motor de vídeo encerrou; confira worker.log.')
                if self.status_path.exists():
                    state = json.loads(self.status_path.read_text())
                    if state.get('error'):
                        raise RuntimeError(state['error'])
                    if state.get('ready'):
                        break
                time.sleep(.25)
            else:
                raise RuntimeError('Preparação excedeu 3 minutos.')
            # Recheck identity immediately before restarting; serials can be reused.
            self.validate(serial)
            if self.cancel.is_set():
                raise RuntimeError('Conexão cancelada.')
            self.run_adb(serial, 'shell', 'sync', timeout=60)
            result = self.run_adb(serial, 'emu', 'kill')
            if result.returncode or 'OK' not in result.stdout:
                raise RuntimeError('Não foi possível reiniciar o TikTok Atual.')
            time.sleep(2)
            port = serial.split('-')[1]
            with (folder / 'emulator.log').open('wb') as log:
                subprocess.Popen([str(self.emulator), '-avd', 'TikTokAtual', '-port', port,
                    '-no-snapshot-load', '-no-snapshot-save', '-camera-back', camera,
                    '-camera-front', camera, '-allow-host-audio'], stdout=log, stderr=log,
                    cwd=str(self.emulator.parent), **self.hidden())
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if self.cancel.is_set():
                    raise RuntimeError('Conexão cancelada.')
                result = self.run_adb(serial, 'shell', 'getprop', 'sys.boot_completed', timeout=5)
                if result.stdout.strip() == '1':
                    break
                time.sleep(2)
            else:
                raise RuntimeError('TikTok Atual não terminou de iniciar.')
            self.validate(serial)
            self.run_adb(serial, 'emu', 'avd', 'hostmicon', 'on')
            self.run_adb(serial, 'shell', 'am', 'start', '-n',
                         'com.zhiliaoapp.musically/com.ss.android.ugc.aweme.splash.SplashActivity')
            self.state.update(active=True, stage='pause', message='Conectado e pausado. Abra a câmera do TikTok e clique em Reproduzir do início.')
        except Exception as error:
            if self.control_path:
                write_json(self.control_path, dict(mode='stop', generation=0))
            self.state.update(active=False, stage='error', message=str(error))
        finally:
            self.state['busy'] = False

    def control(self, mode):
        if mode not in ('play', 'pause', 'stop'):
            raise ValueError('Controle inválido.')
        with self.lock:
            if mode == 'stop':
                self.cancel.set()
            elif self.state['busy'] or not self.proc or self.proc.poll() is not None:
                raise ValueError('Conecte o vídeo e aguarde o emulador iniciar.')
            if self.control_path:
                write_json(self.control_path, dict(mode=mode, generation=time.time_ns()))
            if mode == 'stop':
                self.state.update(active=False, stage='stopped', message='Conexão encerrada; entrada original de áudio será restaurada.')
