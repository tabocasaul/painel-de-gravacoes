"""Local companion: watch the owning panel only while the user enabled its loop."""
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request


def watch(path, pid, server):
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x100001,False,pid)  # SYNCHRONIZE | TERMINATE
    if not handle:return
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    missing_since=None
    try:
        while True:
            time.sleep(10)
            try:
                with open(path,encoding='utf-8') as f:state=json.load(f)
            except (OSError,ValueError):continue
            if state.get('ownerPid')!=pid:return
            if not state.get('enabled'):return
            dead=kernel.WaitForSingleObject(handle,0)==0
            if not dead:
                try:
                    with urllib.request.urlopen(state['url']+'api/health',timeout=8) as response:health=json.load(response)
                    missing_since=None
                    # Preparation, saves and ADB calls are bounded. No progress
                    # for 12 minutes indicates a stuck worker, not normal capture.
                    stalled=health.get('busy') and not health.get('waiting') and time.time()-health.get('lastProgress',time.time())>720
                    if not stalled:continue
                except Exception:
                    missing_since=missing_since or time.monotonic()
                    if time.monotonic()-missing_since<120:continue
                # Re-read stop intent immediately before terminating the owner.
                try:
                    with open(path,encoding='utf-8') as f:latest=json.load(f)
                except (OSError,ValueError):continue
                if not latest.get('enabled') or latest.get('ownerPid')!=pid:return
                kernel.TerminateProcess(handle,1)
                kernel.WaitForSingleObject(handle,15000)
            subprocess.Popen([sys.executable,server,'--no-open','--supervisor-resume'],
                             cwd=os.path.dirname(server),creationflags=0x08000000)
            return
    finally:kernel.CloseHandle(handle)


if __name__=='__main__':watch(sys.argv[1],int(sys.argv[2]),sys.argv[3])
