"""A single cache-only preparation job, independent of camera automation."""
import threading
from preparation_job import PreparationTracker


class BackgroundVideo(PreparationTracker):
    def __init__(self, prepare):
        super().__init__('background')
        self.prepare = prepare

    def start(self, name, fill=False):
        job = super().start(name, fill)

        def work():
            try:
                self.prepare(name, fill, notify=job.notify, background=True, preparation=job)
                job.finish()
            except Exception as exc:
                job.finish(exc)

        threading.Thread(target=work, daemon=True).start()
        return job.snapshot()
