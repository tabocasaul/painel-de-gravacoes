"""Private media worker for DroidCam/OBS camera and VB-CABLE."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import ctypes


def main(request):
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import EDataFlow, ERole

    status, control = Path(request['status']), Path(request['control'])
    folder = Path(request['folder'])
    hidden = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}
    decoder = None
    original = {}
    cable_id = None
    stream = audio = camera = None
    audio_lock = threading.Lock()
    playing = False
    frames = 0
    parent_handle = None
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        parent_handle = kernel.OpenProcess(0x100000, False, request['parentPid'])
        if not parent_handle:
            raise RuntimeError('O painel que iniciou a conexão não está disponível.')

    def report(**value):
        temp = status.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        temp.replace(status)

    def close_decoder():
        nonlocal decoder
        if decoder:
            decoder.terminate()
            try:
                decoder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                decoder.kill()
                decoder.wait(timeout=5)
            decoder.stdout.close()
            decoder = None

    def new_decoder():
        close_decoder()
        return subprocess.Popen([request['ffmpeg'], '-hide_banner', '-loglevel', 'error',
            '-stream_loop', '-1', '-i', request['source'], '-an', '-vf',
            'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24',
            '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, **hidden)

    try:
        outputs = sd.query_devices()
        selected = next((i for i, d in enumerate(outputs) if
            sd.query_hostapis(d['hostapi'])['name'] + '|' + d['name'] == request['output']
            and d['max_output_channels'] >= 2), None)
        if selected is None:
            raise RuntimeError('CABLE Input não está disponível. Atualize as saídas de áudio.')
        microphones = [d for d in AudioUtilities.GetAllDevices() if
            'CABLE Output' in d.FriendlyName and AudioUtilities.GetEndpointDataFlow(d.id) == 'eCapture']
        if len(microphones) != 1:
            raise RuntimeError('Não foi encontrada uma única entrada CABLE Output.')
        # Fail before changing defaults when the virtual camera driver is missing.
        if request.get('backend') == 'droidcam':
            from droidcam_output import DroidCamCamera
            camera = DroidCamCamera(fps=24)
        else:
            import pyvirtualcam
            camera = pyvirtualcam.Camera(width=1280, height=720, fps=24, backend='obs')
        report(ready=False, stage='preparing', message='Preparando áudio do vídeo.')
        wav = folder / 'audio.wav'
        probe = Path(request['ffmpeg']).with_name('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
        result = subprocess.run([str(probe), '-v', 'error', '-select_streams', 'a',
                                 '-show_entries', 'stream=index', '-of', 'csv=p=0', request['source']],
                                capture_output=True, text=True, timeout=30, check=True, **hidden)
        if result.stdout.strip():
            subprocess.run([request['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-y', '-i',
                            request['source'], '-vn', '-ac', '2', '-ar', '48000', str(wav)],
                           check=True, timeout=150, **hidden)
            audio = sf.SoundFile(wav)
        roles = [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications]
        enumerator = AudioUtilities.GetDeviceEnumerator()
        original = {r.name: enumerator.GetDefaultAudioEndpoint(EDataFlow.eCapture.value, r.value).GetId() for r in roles}
        (folder / 'original-inputs.json').write_text(json.dumps(original), encoding='utf-8')
        cable_id = microphones[0].id
        AudioUtilities.SetDefaultDevice(cable_id, roles)

        def callback(outdata, count, time_info, flags):
            outdata.fill(0)
            with audio_lock:
                if not playing or audio is None:
                    return
                offset = 0
                while offset < count:
                    block = audio.read(count - offset, dtype='float32', always_2d=True)
                    if not len(block):
                        audio.seek(0)
                        if len(audio) == 0:
                            return
                        continue
                    outdata[offset:offset + len(block)] = block * request['volume']
                    offset += len(block)

        stream = sd.OutputStream(device=selected, samplerate=48000, channels=2, callback=callback)
        stream.start()
        decoder = new_decoder()
        length = 1280 * 720 * 3
        raw = decoder.stdout.read(length)
        if len(raw) != length:
            raise RuntimeError('FFmpeg não entregou o primeiro quadro.')
        frame = np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)
        generation = None
        last_report = 0
        while True:
            if parent_handle and kernel.WaitForSingleObject(parent_handle, 0) == 0:
                break
            try:
                command = json.loads(control.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                command = dict(mode='pause', generation=None)
            mode = command.get('mode', 'pause')
            if mode == 'stop':
                break
            if mode == 'play' and command.get('generation') != generation:
                with audio_lock:
                    playing = False
                    if audio:
                        audio.seek(0)
                decoder = new_decoder()
                frames = 0
                generation = command.get('generation')
            if mode == 'play':
                raw = decoder.stdout.read(length)
                if len(raw) != length:
                    raise RuntimeError('O decodificador de vídeo encerrou inesperadamente.')
                frame = np.frombuffer(raw, np.uint8).reshape(720, 1280, 3)
                frames += 1
            with audio_lock:
                playing = mode == 'play'
            camera.send(frame)
            camera.sleep_until_next_frame()
            if time.monotonic() - last_report > 1:
                report(ready=True, stage=mode, frames=frames, audioSent=playing and audio is not None,
                       message=('Enviando vídeo e áudio. Captação no TikTok ainda não confirmada.' if playing else
                                'Primeiro quadro preparado. Clique em Reproduzir do início.'))
                last_report = time.monotonic()
    except Exception as error:
        report(error=str(error), stage='error', ready=False)
        raise
    finally:
        if stream:
            stream.stop()
            stream.close()
        if audio:
            audio.close()
        close_decoder()
        if camera:
            camera.close()
        if parent_handle:
            kernel.CloseHandle(parent_handle)
        # Do not overwrite a device choice made by the user during the session.
        for name, identifier in original.items():
            role = getattr(ERole, name)
            try:
                current = AudioUtilities.GetDeviceEnumerator().GetDefaultAudioEndpoint(EDataFlow.eCapture.value, role.value).GetId()
                if current == cable_id:
                    AudioUtilities.SetDefaultDevice(identifier, [role])
            except Exception:
                pass


if __name__ == '__main__':
    main(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
