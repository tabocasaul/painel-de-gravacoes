"""One immutable I420 file on the PC; tiny per-AVD SD disk overlays."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import threading
import time


class SharedCamera:
    def __init__(self, area, sdk, avd_home, transfers, resources):
        self.area = Path(area)
        self.sdk, self.avd_home = Path(sdk), Path(avd_home)
        self.transfers = transfers
        self.resources = Path(resources)
        self.path = self.area/'shared-cameras.json'
        self.lock = threading.RLock()

    def bindings(self):
        with self.lock:
            try: return json.loads(self.path.read_text(encoding='utf-8'))
            except (OSError, ValueError): return {}

    def bind(self, avd, record):
        with self.lock:
            data = self.bindings()
            data[avd] = record
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, self.path)
            config = self.avd_home/(avd+'.avd')/'config.ini'
            backup = config.with_name('config.ini.before-shared')
            if not backup.exists(): shutil.copy2(config, backup)
            content = config.read_text(encoding='utf-8-sig')
            for key, value in {'hw.sdCard': 'yes', 'hw.sdCard.path': record['disk'], 'hw.ramSize': '2048'}.items():
                pattern = rf'(?m)^{re.escape(key)}\s*=.*$'
                line = f'{key} = {value}'
                content = re.sub(pattern, lambda match: line, content) if re.search(pattern, content) else content+'\n'+line+'\n'
            config.write_text(content, encoding='utf-8')

    def arguments(self, avd):
        record = self.bindings().get(avd)
        if not record:
            return []
        if not Path(record['rawPath']).is_file() or not Path(record['disk']).is_file():
            raise RuntimeError('O arquivo compartilhado da câmera não está no PC. Selecione o vídeo novamente.')
        return ['-sdcard', record['disk']]

    def make_disk(self, avd, raw_path, asset_id):
        directory = self.area/'shared-disks'/avd
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(asset_id.encode()).hexdigest()[:24]
        disk = directory/(key+'.qcow2')
        if not disk.exists():
            subprocess.run([str(self.sdk/'emulator/qemu-img.exe'), 'create', '-f', 'qcow2', '-F', 'raw',
                            '-b', str(Path(raw_path).resolve()), str(disk)], check=True,
                           capture_output=True, timeout=30, **self.transfers.hidden())
        return str(disk)

    def configure_guest(self, serial, raw_path):
        t = self.transfers
        total = os.path.getsize(raw_path)
        with open(raw_path, 'rb') as f: digest = hashlib.sha256(f.read(4096)).hexdigest()
        remote = '/data/adb/modules/videocam'
        t.run(serial, 'push', str(self.resources/'shared-camera.sh'), '/data/local/tmp/shared-camera.sh')
        script = f'''test -d {remote}
cp /data/local/tmp/shared-camera.sh {remote}/shared-camera.sh
chmod 755 {remote}/shared-camera.sh
printf '%s %s\\n' {total} {digest} > {remote}/shared-camera.conf
test -f {remote}/system/vendor/etc/config/emu_camera_video.i420 || touch {remote}/system/vendor/etc/config/emu_camera_video.i420
test -f {remote}/service.sh.before-shared || cp {remote}/service.sh {remote}/service.sh.before-shared
printf '%s\\n' '#!/system/bin/sh' 'magiskpolicy --live "allow hal_camera_default system_file file {{ getattr open read map }}"' 'for ATTEMPT in 1 2 3 4 5 6 7 8 9 10; do' '/system/bin/sh {remote}/shared-camera.sh && break' 'sleep 1' 'done' > {remote}/service.sh
chmod 755 {remote}/service.sh
'''
        t.run(serial, script, root=True)
        # Emulator 'emu kill' is abrupt; persist guest page-cache writes first.
        t.run(serial, 'shell', 'sync', timeout=90)

    def verify(self, serial, raw_path):
        t = self.transfers
        target = '/vendor/etc/config/emu_camera_video.i420'
        size = os.path.getsize(raw_path)
        t.run(serial, '/system/bin/sh /data/adb/modules/videocam/shared-camera.sh', root=True)
        actual = int(t.run(serial, f'blockdev --getsize64 {target}', root=True))
        if actual != size:
            raise RuntimeError('Tamanho do disco da câmera diferente do vídeo')
        # Check separated ranges through the actual camera path, not its metadata.
        with open(raw_path, 'rb') as source:
            for offset in (0, (size//2//4096)*4096, ((size-4096)//4096)*4096):
                source.seek(offset)
                expected = hashlib.sha256(source.read(4096)).hexdigest()
                actual = t.run(serial, f'dd if={target} bs=4096 skip={offset//4096} count=1 2>/dev/null | sha256sum', root=True).split()[0]
                if actual != expected:
                    raise RuntimeError('Os quadros lidos pela câmera não correspondem ao vídeo')

    def install(self, avd, serial, port, raw_path, name, source_size, asset_id, start, online):
        t = self.transfers
        total = os.path.getsize(raw_path)
        t.mark(serial, stage='Vinculando vídeo compartilhado', total=total, bytes=0, percent=5, mode='shared')
        # The image is a few KiB of metadata, never a copy of the frame file.
        disk = self.make_disk(avd, raw_path, asset_id)
        was_online = online(serial)
        record = {'rawPath': str(Path(raw_path).resolve()), 'disk': disk, 'assetId': asset_id,
                  'name': name, 'bytes': total}
        if not was_online:
            self.bind(avd, record)
            t.record(serial, name, total, source_size, asset_id, confirmed=False, mode='shared', staged=True)
            t.mark(serial, stage='Fonte pronta — validar ao abrir', bytes=total, percent=100, error='')
            return
        self.configure_guest(serial, raw_path)
        t.record(serial, name, total, source_size, asset_id, confirmed=False, mode='shared')
        if was_online:
            t.mark(serial, stage='Reiniciando com a fonte compartilhada', percent=35)
            t.run(serial, 'shell', 'sync', timeout=90)
            t.run(serial, 'emu', 'kill')
            self.wait_closed(avd)
            self.bind(avd, record)
            start(avd, serial, port)
            self.wait_boot(serial)
        t.mark(serial, stage='Conferindo os quadros da câmera', percent=85)
        self.verify(serial, raw_path)
        t.record(serial, name, total, source_size, asset_id, mode='shared')
        t.mark(serial, stage='Concluido', bytes=total, percent=100, error='')

    def activate_pending(self, avd, serial):
        """Validate the staged disk before allowing this phone to record."""
        with self.lock:
            item = self.transfers.snapshot()['installedVideos'].get(serial, {})
            if not item.get('staged'):
                return
            binding = self.bindings().get(avd, {})
            if binding.get('assetId') != item.get('assetId'):
                raise RuntimeError('Fonte pendente não corresponde ao disco do celular.')
            raw = binding['rawPath']
            self.transfers.mark(serial, stage='Validando fonte ao abrir', percent=85)
            self.wait_boot(serial)
            self.configure_guest(serial, raw)
            self.verify(serial, raw)
            self.transfers.record(serial, item['name'], item['bytes'], item['sourceBytes'],
                                  item['assetId'], mode='shared')
            self.transfers.mark(serial, stage='Concluido', percent=100, error='')

    def wait_boot(self, serial):
        end = time.monotonic()+240
        while time.monotonic() < end:
            try:
                if self.transfers.run(serial, 'shell', 'getprop', 'sys.boot_completed', timeout=5) == '1': return
            except (RuntimeError, subprocess.TimeoutExpired): pass
            time.sleep(2)
        raise RuntimeError('Android não concluiu o boot em 4 minutos')

    def wait_closed(self, avd):
        # ADB disappears before QEMU releases userdata and its instance lock.
        lock = self.avd_home/(avd+'.avd')/'hardware-qemu.ini.lock'
        end = time.monotonic()+45
        while lock.exists() and time.monotonic()<end:
            time.sleep(.5)
        if lock.exists(): raise RuntimeError('O emulador ainda está encerrando; aguarde e tente novamente')
        time.sleep(1)
