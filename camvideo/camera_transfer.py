"""Byte progress and durable, per-device camera installation records."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import threading
import time

REMOTE = "/data/adb/modules/videocam/system/vendor/etc/config"
TEMP = "/data/local/tmp/emu_camera_video.i420.partial"
CHUNK = TEMP + ".chunk"
CHECKPOINT = TEMP + ".resume"
BLOCK_BYTES = 128 * 1024**2


class Transfers:
    def __init__(self, adb, area, hidden):
        self.adb, self.area, self.hidden = adb, Path(area), hidden
        self.lock = threading.RLock()
        self.rows = {}
        self.path = self.area / "camera-installed.json"
        try:
            self.installed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.installed = {}

    def run(self, serial, *args, root=False, timeout=30):
        cmd = [self.adb, "-s", serial]
        if root:
            result = subprocess.run(cmd + ["shell", "su"], input="set -e\n" + args[0] + "\n",
                                    capture_output=True, text=True,encoding="utf-8",errors="replace", timeout=timeout, **self.hidden())
        else:
            result = subprocess.run(cmd + list(args), capture_output=True, text=True,encoding="utf-8",errors="replace",
                                    timeout=timeout, **self.hidden())
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or f"ADB falhou ({result.returncode})")
        return result.stdout.strip()

    def snapshot(self):
        with self.lock:
            try:self.installed=json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError,ValueError):pass
            return {"transfers": {s: dict(r) for s, r in self.rows.items()},
                    "installedVideos": {s: dict(r) for s, r in self.installed.items()}}

    def reset(self, targets, name):
        with self.lock:
            self.rows = {s: {"name": n, "video": name, "stage": "Aguardando", "bytes": 0,
                             "total": 0, "percent": 0, "error": ""} for n, s in targets}

    def mark(self, serial, **values):
        with self.lock:
            self.rows.setdefault(serial, {}).update(values)

    def record(self, serial, name, total, source_size, asset_id="", confirmed=True, mode="local", staged=False):
        with self.lock:
            self.installed[serial] = {"name": name, "bytes": total, "sourceBytes": source_size,
                                      "installedAt": time.time(), "assetId":asset_id, "confirmed":confirmed, "mode":mode, "staged":staged}
            self.area.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.installed, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.path)

    def send(self, serial, path, name, source_size, asset_id=""):
        total = os.path.getsize(path)
        self.mark(serial, stage="Enviando", total=total, bytes=0, percent=0)
        self.area.mkdir(parents=True, exist_ok=True)
        logpath = self.area / f"transfer-{serial}.log"
        self.send_blocks(serial,path,asset_id,logpath)
        if int(self.run(serial, "shell", "stat", "-c", "%s", TEMP)) != total:
            raise RuntimeError("O arquivo recebido esta incompleto")
        self.mark(serial, stage="Instalando", bytes=total, percent=100)
        self.run(serial, f"test -d {REMOTE}\n"
                 f"chown 0:0 {TEMP}\nchcon u:object_r:system_file:s0 {TEMP}\nchmod 644 {TEMP}\n"
                 f"mv -f {TEMP} {REMOTE}/emu_camera_video.i420\n"
                 f"printf '%s\\n' 'play 0' > {REMOTE}/emu_camera_control.txt\n"
                 f"chown 0:0 {REMOTE}/emu_camera_control.txt\n"
                 f"chcon u:object_r:system_file:s0 {REMOTE}/emu_camera_control.txt\n"
                 f"chmod 644 {REMOTE}/emu_camera_control.txt\nrm -f {CHECKPOINT} {CHUNK}", root=True)
        self.record(serial,name,total,source_size,asset_id,confirmed=False)
        self.mark(serial, stage="Reiniciando")
        self.run(serial, "reboot")
        end = time.monotonic() + 360
        while time.monotonic() < end:
            try:
                if self.run(serial, "shell", "getprop", "sys.boot_completed", timeout=10) == "1":
                    installed = int(self.run(serial, "shell", "stat", "-c", "%s", "/vendor/etc/config/emu_camera_video.i420"))
                    if installed == total:
                        self.record(serial, name, total, source_size,asset_id)
                        self.mark(serial, stage="Concluido", percent=100)
                        return
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                pass
            time.sleep(2)
        raise RuntimeError("Arquivo instalado, mas o Android nao confirmou a camera apos reiniciar")

    @staticmethod
    def resume_key(path,asset_id):
        return hashlib.sha256((asset_id+":"+str(os.path.getsize(path))).encode()).hexdigest()

    def checkpoint(self,serial,key,total):
        try:
            fields=self.run(serial,"shell","cat",CHECKPOINT).split()
            offset=int(fields[1])
            actual=int(self.run(serial,"shell","stat","-c","%s",TEMP))
            if fields[0]==key and 0<=offset<=total and actual>=offset:return offset
        except (RuntimeError,ValueError,IndexError):pass
        return 0

    def send_blocks(self,serial,path,asset_id,logpath):
        total=os.path.getsize(path);key=self.resume_key(path,asset_id)
        offset=self.checkpoint(serial,key,total)
        self.run(serial,f"touch {TEMP}\ntruncate -s {offset} {TEMP}",root=True)
        local_chunk=self.area/f"chunk-{serial}.bin"
        try:
            with open(path,"rb") as source:
                source.seek(offset)
                while offset<total:
                    data=source.read(min(BLOCK_BYTES,total-offset))
                    if not data:raise RuntimeError("Arquivo preparado foi interrompido")
                    local_chunk.write_bytes(data)
                    digest=hashlib.sha256(data).hexdigest();length=len(data)
                    del data
                    for attempt in range(1,6):
                        try:
                            self.run(serial,"shell","rm","-f",CHUNK)
                            self.push_block(serial,str(local_chunk),offset,total,logpath)
                            received_hash=self.run(serial,"shell","sha256sum",CHUNK,timeout=90).split()[0]
                            if received_hash!=digest:raise RuntimeError("Bloco recebido com dados divergentes")
                            # Roll back an incomplete append to the last durable
                            # checkpoint before retrying, preventing duplication.
                            end=offset+length
                            self.run(serial,f"truncate -s {offset} {TEMP}\ncat {CHUNK} >> {TEMP}\n"
                                     f"test $(stat -c %s {TEMP}) -eq {end}\n"
                                     f"printf '%s %s\\n' {key} {end} > {CHECKPOINT}.tmp\n"
                                     f"mv -f {CHECKPOINT}.tmp {CHECKPOINT}",root=True,timeout=120)
                            offset=end
                            self.mark(serial,stage="Enviando",bytes=offset,percent=min(99,offset*100//total),error="")
                            break
                        except (RuntimeError,subprocess.TimeoutExpired) as exc:
                            self.mark(serial,stage="Retomando envio",error=f"Tentativa {attempt}/5: {exc}")
                            if attempt==5:raise
                            time.sleep(attempt*2)
        finally:
            local_chunk.unlink(missing_ok=True)

    def push_block(self,serial,path,offset,total,logpath):
        # Poll the receiver: percentages reflect bytes actually received by ADB,
        # including when adb suppresses its own progress on redirected stdout.
        with logpath.open("wb") as log:
            process = subprocess.Popen([self.adb, "-s", serial, "push", path, CHUNK],
                                       stdout=log, stderr=subprocess.STDOUT, **self.hidden())
            last_bytes, last_change = 0, time.monotonic()
            started=last_change
            try:
                while process.poll() is None:
                    try:
                        received = min(total, offset+int(self.run(serial, "shell", "stat", "-c", "%s", CHUNK, timeout=10)))
                        if received > last_bytes:
                            last_bytes, last_change = received, time.monotonic()
                        speed=(received-offset)/max(1,time.monotonic()-started)
                        self.mark(serial, bytes=received, percent=min(99, received * 100 // total),
                                  speed=speed,eta=(total-received)/speed if speed else None)
                    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                        pass
                    if time.monotonic() - last_change > 180:
                        raise RuntimeError("Envio sem avancar por 3 minutos; confira a conexao e o espaco")
                    time.sleep(0.8)
            except BaseException:
                process.kill()
                process.wait()
                raise
        if process.returncode:
            raise RuntimeError(logpath.read_text(encoding="utf-8", errors="replace")[-2000:])
