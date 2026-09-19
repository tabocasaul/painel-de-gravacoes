"""Copy offline AVDs without discarding encrypted user data or login keys."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

DEFAULT_STORAGE_GIB = 128
SDK = Path(os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk"))


def configure(directory, name, gib=DEFAULT_STORAGE_GIB):
    path = Path(directory) / "config.ini"
    text = path.read_text(encoding="utf-8-sig")
    for key, value in {"disk.dataPartition.size": f"{gib}G", "avd.id": name,
                       "avd.name": name, "fastboot.forceColdBoot": "yes",
                       "fastboot.forceFastBoot": "no", "hw.ramSize": "2048"}.items():
        pattern = rf"(?m)^{re.escape(key)}\s*=.*$"
        text = re.sub(pattern, f"{key} = {value}", text) if re.search(pattern, text) else text + f"\n{key} = {value}\n"
    path.write_text(text, encoding="utf-8")


def clone_offline(source, destination, progress=lambda *a: None, gib=DEFAULT_STORAGE_GIB):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise RuntimeError(f"Destino ja existe: {destination}")
    if not (source / "config.ini").is_file():
        raise RuntimeError("Origem nao encontrada")
    if list(source.glob("*.lock")):
        # A zero-byte multiinstance.lock persists even after shutdown; the caller
        # must additionally verify ADB/process state before copying a live AVD.
        if any(p.is_dir() for p in source.glob("*.lock")):
            raise RuntimeError("Desligue o emulador de origem antes de copiar")
    files = []
    for root, dirs, names in os.walk(source):
        dirs[:] = [d for d in dirs if d not in {"snapshots", "tmpAdbCmds"} and not d.endswith(".lock")]
        for name in names:
            if name.endswith(".lock") or name in {"hardware-qemu.ini", "emu-launch-params.txt", "userdata-expansion-attempt.qcow2"}:
                continue
            path = Path(root) / name
            files.append(path)
    total = sum(p.stat().st_size for p in files)
    if shutil.disk_usage(destination.parent).free < total + 2 * 1024**3:
        raise RuntimeError("Espaco insuficiente no PC para copiar o celular")
    done = 0
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        with path.open("rb") as src, target.open("wb") as dst:
            while chunk := src.read(8 * 1024**2):
                dst.write(chunk)
                done += len(chunk)
                progress(done, total)
    # Both layers must grow together. Changing only config.ini can cause the
    # emulator to regenerate its overlay and lose the existing app sessions.
    for name in ("userdata-qemu.img", "userdata-qemu.img.qcow2"):
        path = destination / name
        if path.exists():
            subprocess.run([str(SDK / "emulator/qemu-img.exe"), "resize", str(path), f"{gib}G"], check=True, capture_output=True)
    configure(destination, destination.stem, gib)
    return total


def finish_resize(serial, progress=lambda message: None, gib=DEFAULT_STORAGE_GIB):
    adb=str(SDK / 'platform-tools/adb.exe')
    def run(*args, script=None):
        result=subprocess.run([adb,'-s',serial]+list(args),input=script,
                              capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=90,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:raise RuntimeError((result.stderr or result.stdout).strip())
        return result.stdout.strip()
    def root(script):return run('shell','su',script='set -e\n'+script+'\n')
    def boot():
        end=time.monotonic()+420
        while time.monotonic()<end:
            try:
                if run('shell','getprop','sys.boot_completed')=='1':return
            except (RuntimeError,subprocess.TimeoutExpired):pass
            time.sleep(2)
        raise RuntimeError('Android nao concluiu o boot')
    boot()
    device=next(line.split()[0] for line in root('cat /proc/mounts').splitlines() if line.split()[1]=='/data')
    if not re.fullmatch(r'/dev/block/dm-\d+',device):
        raise RuntimeError('Particao de dados inesperada: '+device)
    features=root('tune2fs -l '+device)
    if 'resize_inode' in features:
        progress('Preparando o sistema de arquivos')
        # The stock AVD resize inode has invalid backup-GDT reservations above
        # 10 GiB. Remove that feature and reboot before online growth; the kernel
        # then uses meta_bg. The original offline AVD remains untouched.
        root('tune2fs -O ^resize_inode '+device+'\ntune2fs -E force_fsck '+device)
        run('reboot');time.sleep(5);boot()
        device=next(line.split()[0] for line in root('cat /proc/mounts').splitlines() if line.split()[1]=='/data')
    progress('Ampliando o armazenamento do Android')
    root('resize2fs '+device+'\ntune2fs -c 0 '+device)
    fields=run('shell','df','-k','/data').splitlines()[-1].split()
    size=int(fields[1])*1024
    if size<gib*1024**3*.95:raise RuntimeError('O Android nao confirmou a capacidade ampliada')
    return {'total':size,'free':int(fields[3])*1024}
