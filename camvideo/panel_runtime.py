"""Find a running copy of this backend without reusing an outdated server."""
import hashlib
import http.client
import json
import os
from pathlib import Path

APP_VERSION = '2.3.43'

BACKEND_FILES = ('preparation_job.py', 'video_readiness.py', 'windows_recycle.py', 'video_library.py', 'synchronized_recording_start.py', 'interleaved_participants.py', 'interleaved_video_rotation.py', 'participant_selection.py', 'daily_plan.py', 'background_video.py', 'modern_server.pyw', 'painel.pyw', 'automation.py', 'automation_queue.py', 'task_history.py', 'unicode_search.py', 'camera_transfer.py',
                 'shared_camera.py', 'mirror.py', 'storage.py', 'voice_manager.py',
                 'voice_worker.py', 'tiktok_live.py', 'tiktok_video.py', 'tiktok_video_worker.py', 'droidcam_output.py', 'panel_runtime.py', 'product_writer.py', 'live_voice.py')


def runtime_identity(resources, owner, executable=None):
    digest = hashlib.sha256()
    for name in BACKEND_FILES + ('interleaved_plan.py', 'minute_catalog.py', 'loop_supervisor.py', 'panel_watchdog.py'):
        path = Path(resources) / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    if executable:
        stat = Path(executable).stat()
        digest.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode())
    return {'app': 'EmulationControl', 'revision': digest.hexdigest(),
            'root': os.path.normcase(os.path.realpath(owner)), 'voiceApi': 1, 'appVersion': APP_VERSION}


def find_running_backend(first_port, expected, count=32):
    for port in range(first_port, first_port + count):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=.75)
        try:
            connection.request('GET', '/api/version')
            response = connection.getresponse()
            if response.status == 200:
                body = response.read(8193)
                if len(body) <= 8192 and json.loads(body) == expected:
                    return port
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            connection.close()
    return None
