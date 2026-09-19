"""Exercise cancellation with harmless owned Python children, never videos or ADB."""
import io
import os
import subprocess
import sys
import threading
import time
import unittest

from preparation_job import PreparationCancelled, PreparationJob, run_conversion


class PreparationProcessTests(unittest.TestCase):
    def child(self, code):
        process = subprocess.Popen([sys.executable, '-u', '-c', code],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        def cleanup():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if process.stdout and not process.stdout.closed:
                process.stdout.close()
        self.addCleanup(cleanup)
        return process

    def test_cancel_silent_process_is_prompt_and_does_not_stop_another_process(self):
        other = self.child('import time; time.sleep(30)')
        process = self.child('import time; time.sleep(30)')
        job = PreparationJob('silent-test.MOV', kind='background')
        timer = threading.Timer(.15, job.request_cancel)
        self.addCleanup(timer.cancel)
        timer.start()
        started = time.monotonic()
        with self.assertRaises(PreparationCancelled):
            run_conversion(process, job, lambda line: None, grace=.5, poll_interval=.02)
        self.assertLess(time.monotonic() - started, 3)
        self.assertIsNotNone(process.poll())
        self.assertIsNone(other.poll())
        self.assertTrue(process.stdout.closed)
        timer.join(1)

    def test_normal_completion_delivers_buffered_final_progress_and_closes_stdout(self):
        process = self.child("print('out_time_us=100000'); print('progress=end')")
        lines = []
        job = PreparationJob('complete-test.MOV', kind='background')
        self.assertEqual(run_conversion(process, job, lines.append, grace=.5, poll_interval=.02), 0)
        self.assertEqual([line.strip() for line in lines], ['out_time_us=100000','progress=end'])
        self.assertTrue(process.stdout.closed)

    def test_cancellation_requested_before_monitoring_still_terminates_owned_child(self):
        process = self.child('import time; time.sleep(30)')
        job = PreparationJob('cancel-before-monitor.MOV', kind='background')
        job.request_cancel()
        with self.assertRaises(PreparationCancelled):
            run_conversion(process, job, lambda line: None, grace=.5, poll_interval=.02)
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdout.closed)

    def test_unresponsive_process_uses_bounded_kill_after_terminate(self):
        class UnresponsiveProcess:
            def __init__(self):
                self.stdout = io.StringIO('')
                self.calls = []
                self.returncode = None
            def poll(self):
                return self.returncode
            def terminate(self):
                self.calls.append('terminate')
            def kill(self):
                self.calls.append('kill')
                self.returncode = -9
            def wait(self, timeout=None):
                self.calls.append(('wait',timeout))
                if self.returncode is None:
                    raise subprocess.TimeoutExpired('test-only fake process', timeout)
                return self.returncode
        process = UnresponsiveProcess()
        job = PreparationJob('fake-only.MOV', kind='foreground')
        job.request_cancel()
        with self.assertRaises(PreparationCancelled):
            run_conversion(process,job,lambda line:None,grace=.01,poll_interval=.01)
        self.assertIn('terminate',process.calls)
        self.assertIn('kill',process.calls)
        self.assertLess(process.calls.index('terminate'),process.calls.index('kill'))
        self.assertTrue(all(call[1] is not None and call[1] <= .1 for call in process.calls if isinstance(call,tuple)))
        self.assertTrue(process.stdout.closed)


if __name__ == '__main__':
    unittest.main()
