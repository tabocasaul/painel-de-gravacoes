"""Attempt-scoped preparation state and cancellation of one owned converter."""
import queue
import subprocess
import threading
import time
import uuid


class PreparationCancelled(InterruptedError):
    pass


class PreparationJob:
    def __init__(self, name, kind='background', fill=False, cancellable=True):
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.state = dict(jobId=uuid.uuid4().hex, name=name, kind=kind, fill=bool(fill),
            startedAt=time.time_ns(),
            busy=True, canCancel=bool(cancellable), cancelRequested=False, progress=0,
            stage='Aguardando preparação', error='', status='running')

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def notify(self, **values):
        with self.lock:
            self.state.update(values)
            if self.cancel_event.is_set():
                self.state.update(stage='Cancelando preparação', status='cancelling')

    def check_cancel(self):
        if self.cancel_event.is_set():
            raise PreparationCancelled('Preparação cancelada. Você pode tentar novamente quando quiser.')

    def request_cancel(self):
        with self.lock:
            if not self.state['busy'] or not self.state['canCancel']:
                raise ValueError('Esta preparação já encerrou ou está concluindo a publicação dos quadros.')
            self.cancel_event.set()
            self.state.update(cancelRequested=True, status='cancelling', stage='Cancelando preparação')
            return True

    def commit(self, publish):
        """Accept cancellation up to this boundary; never report it after publish."""
        with self.lock:
            self.check_cancel()
            self.state.update(canCancel=False, stage='Concluindo preparação')
            return publish()

    def finish(self, error=None):
        with self.lock:
            cancelled = isinstance(error, PreparationCancelled)
            self.state.update(busy=False, canCancel=bool(error),
                status='cancelled' if cancelled else 'error' if error else 'completed',
                stage='Preparação cancelada' if cancelled else 'Falha na preparação' if error else 'Pronto para usar',
                error='' if cancelled or error is None else str(error))
            if error is None:
                self.state['progress'] = 100


class PreparationTracker:
    def __init__(self, kind):
        self.kind, self.lock, self.job = kind, threading.RLock(), None

    def start(self, name, fill=False):
        with self.lock:
            if self.job is not None and self.job.snapshot()['busy']:
                raise ValueError('Já existe um vídeo sendo preparado nesta modalidade.')
            self.job = PreparationJob(name, self.kind, fill)
            return self.job

    def snapshot(self):
        with self.lock:
            return self.job.snapshot() if self.job is not None else dict(jobId='', name='', kind=self.kind,
                startedAt=0,
                busy=False, canCancel=False, cancelRequested=False, progress=0,
                stage='Aguardando', error='', status='idle')

    def cancel(self, job_id, name=None):
        with self.lock:
            state = self.snapshot()
            if (not isinstance(job_id, str) or not job_id or job_id != state['jobId']
                    or (name is not None and name != state['name'])):
                raise ValueError('Esta tentativa de preparação não é mais a atual. Atualize o painel.')
            if not state['busy'] and state['status'] in {'error', 'cancelled'}:
                self.job = None
                return dict(jobId=job_id, kind=self.kind, cleared=True)
            self.job.request_cancel()
            return dict(jobId=job_id, kind=self.kind, cancelRequested=True)


def _stop_process(process, grace):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=grace)


def run_conversion(process, job, on_line, grace=1.0, poll_interval=.05):
    """Drain progress independently so a silent ffmpeg remains cancellable."""
    lines = queue.Queue()
    reader_done = threading.Event()
    def read_output():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            process.stdout.close()
            reader_done.set()
    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        while True:
            job.check_cancel()
            try:
                line = lines.get(timeout=poll_interval)
            except queue.Empty:
                if process.poll() is not None and reader_done.is_set():
                    break
            else:
                on_line(line)
        job.check_cancel()
        return process.wait(timeout=grace)
    finally:
        # A failed terminate/kill is not proof of exit. Keep this worker (and
        # its caller's preparation lock/busy state) until this exact child and
        # its output reader are gone. Each stop attempt has a short deadline.
        while True:
            problem = ''
            try:
                _stop_process(process, grace)
            except (OSError, subprocess.TimeoutExpired) as exc:
                problem = str(exc)
            try:
                exited = process.poll() is not None
            except OSError as exc:
                exited, problem = False, str(exc)
            reader.join(timeout=max(poll_interval, .01))
            if exited and not reader.is_alive():
                break
            job.notify(message='Aguardando o conversor encerrar antes de liberar uma nova preparação.',
                       error=problem)
            time.sleep(max(poll_interval, .01))
