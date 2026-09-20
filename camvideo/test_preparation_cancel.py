"""Cancel only fake conversions and temporary sources, never a real camera."""
import ast
from contextlib import contextmanager
import hashlib
from io import StringIO, BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from background_video import BackgroundVideo
from preparation_job import PreparationJob, PreparationTracker, PreparationCancelled, run_conversion, stage_preparation_metadata
from video_readiness import video_readiness
from video_storage import VideoStorage


class PreparationCancelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.area = Path(self.directory.name) / 'area'
        self.videos = Path(self.directory.name) / 'videos'
        self.area.mkdir();self.videos.mkdir()
        self.source = self.videos / 'clip.mp4'
        self.source.write_bytes(b'fake video source')
        self.active = self.area / 'active.i420'
        self.active.write_bytes(b'previous installed camera frames')
        self.existing_meta = self.area / 'prepared-video.json'
        self.existing_meta.write_text(json.dumps({'previous':'camera cache remains intact'}))
        self.foreground = PreparationTracker('foreground')
        self.states = {'busy':True, 'operation':'install'}
        self.processes = []
        self.hook = lambda values: None
        def notify(**values):
            self.states.update(values)
            self.hook(values)
        def popen(args, **kwargs):
            Path(args[-1]).write_bytes(b'new camera frames')
            process = SimpleNamespace(stdout=StringIO('out_time_us=100000\n'),
                poll=Mock(return_value=0), wait=Mock(return_value=0), terminate=Mock(), kill=Mock())
            self.processes.append(process)
            return process
        self.ns = dict(os=os, tempfile=tempfile, time=time, hashlib=hashlib, json=json, shutil=shutil,
            threading=threading, PreparationJob=PreparationJob, PreparationTracker=PreparationTracker,
            PreparationCancelled=PreparationCancelled, run_conversion=run_conversion,
            FOREGROUND_PREPARATION=self.foreground, PREPARATION_LOCK=threading.Lock(), LOCK=threading.Lock(),
            VIDEOS=str(self.videos), AREA=str(self.area), RAW_READY=str(self.active),
            P=SimpleNamespace(achar=Mock(return_value='fake-ffmpeg')), hidden=lambda:{},
            video_meta=Mock(return_value={'duration':.2}), update=notify, S=self.states,
            subprocess=SimpleNamespace(Popen=Mock(side_effect=popen),PIPE=subprocess.PIPE,BELOW_NORMAL_PRIORITY_CLASS=0),
            devices=Mock(side_effect=AssertionError('Cancellation must not touch ADB or phones')))
        self.ns['VIDEO_STORAGE']=VideoStorage(self.area,self.videos)
        self.ns['video_source']=self.ns['VIDEO_STORAGE'].source
        self.ns['stage_preparation_metadata']=stage_preparation_metadata
        tree = ast.parse(Path(__file__).with_name('modern_server.pyw').read_text(encoding='utf-8-sig'))
        names = {'prepare_video','_prepare_video','cache_metadata_path','prepared_cache','cancel_preparation','action','job','install_targets','preparation_state_for_video'}
        definitions = [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
        handler = next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='H')
        definitions.extend(node for node in handler.body if isinstance(node,ast.FunctionDef) and node.name=='do_POST')
        exec(compile(ast.Module(body=definitions,type_ignores=[]),'preparation-functions-only','exec'),self.ns)
        self.background = BackgroundVideo(self.ns['prepare_video'])
        self.ns['BACKGROUND_VIDEO'] = self.background

    def call(self, kind='foreground', name='clip.mp4'):
        tracker = self.foreground if kind=='foreground' else self.background
        return self.ns['cancel_preparation']({'kind':kind,'jobId':tracker.snapshot()['jobId'],'video':name})

    def wait_idle(self, tracker):
        deadline = time.monotonic() + 3
        while tracker.snapshot()['busy'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(tracker.snapshot()['busy'])

    def assert_old_files(self):
        self.assertEqual(self.source.read_bytes(),b'fake video source')
        self.assertEqual(self.active.read_bytes(),b'previous installed camera frames')
        self.assertEqual(json.loads(self.existing_meta.read_text()),{'previous':'camera cache remains intact'})
        self.assertFalse(list(self.area.rglob('*.partial')))
        self.assertFalse(list(self.area.rglob('.preparation-*.tmp')))

    def test_cancel_foreground_waiting_for_lock_never_starts_ffmpeg_and_releases_busy_after_cleanup(self):
        self.ns['PREPARATION_LOCK'].acquire()
        errors = []
        def prepare():
            try:self.ns['prepare_video']('clip.mp4',False,manual=True)
            except BaseException as exc:errors.append(exc)
        worker = threading.Thread(target=prepare);worker.start()
        deadline = time.monotonic()+2
        while not self.foreground.snapshot()['jobId'] and time.monotonic()<deadline:time.sleep(.01)
        try:
            self.assertTrue(self.call()['cancelRequested'])
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertIsInstance(errors[0],PreparationCancelled)
            self.ns['subprocess'].Popen.assert_not_called()
            self.assertEqual(self.foreground.snapshot()['status'],'cancelled')
            self.assertTrue(self.ns['PREPARATION_LOCK'].locked())
        finally:self.ns['PREPARATION_LOCK'].release()
        self.assert_old_files()

    def test_cancel_background_waiter_does_not_cancel_or_change_current_recording(self):
        self.states.update(busy=True,planActive=True,progress=62,message='Recording current task')
        before = dict(self.states)
        with self.ns['PREPARATION_LOCK']:
            started = self.background.start('clip.mp4')
            self.assertTrue(self.call('background')['cancelRequested'])
            self.wait_idle(self.background)
        self.assertEqual(self.states,before)
        self.assertEqual(self.background.snapshot()['jobId'],started['jobId'])
        self.assertEqual(self.background.snapshot()['status'],'cancelled')
        self.ns['subprocess'].Popen.assert_not_called()
        self.assert_old_files()

    def test_cancel_hashing_cleans_only_new_partial_and_next_manual_attempt_succeeds(self):
        def cancel_hash(values):
            if values.get('stage')=='Identificando vídeo':
                self.assertTrue(self.call()['cancelRequested'])
        self.hook = cancel_hash
        with self.assertRaises(PreparationCancelled):
            self.ns['prepare_video']('clip.mp4',False,manual=True)
        old_id = self.foreground.snapshot()['jobId']
        self.assert_old_files()
        self.assertEqual(list((self.area/'frame-cache').glob('*.i420')),[])
        self.hook = lambda values:None
        self.assertEqual(self.ns['prepare_video']('clip.mp4',False,manual=True),'clip.mp4')
        self.assertNotEqual(self.foreground.snapshot()['jobId'],old_id)
        self.assertEqual(self.foreground.snapshot()['status'],'completed')
        self.assertTrue(self.ns['prepared_cache'](str(self.source),False))

    def test_wrong_name_stale_id_and_foreground_during_plan_never_cancel_current_job(self):
        current = self.foreground.start('clip.mp4')
        for data in ({'kind':'foreground','jobId':'stale'},
                     {'kind':'foreground','jobId':current.snapshot()['jobId'],'video':'other.mp4'}):
            with self.assertRaises(ValueError):self.ns['cancel_preparation'](data)
        self.states['planActive'] = True
        with self.assertRaises(ValueError):self.call()
        self.assertFalse(current.cancel_event.is_set())
        self.ns['devices'].assert_not_called()

    def test_cache_reuse_closes_cancel_before_return_and_preserves_prepared_raw(self):
        self.ns['prepare_video']('clip.mp4',False,manual=True)
        raw = self.ns['prepared_cache'](str(self.source),False)['rawPath']
        self.ns['subprocess'].Popen.reset_mock()
        self.ns['prepare_video']('clip.mp4',False,manual=True)
        with self.assertRaises(ValueError):self.call()
        self.ns['subprocess'].Popen.assert_not_called()
        self.assertTrue(Path(raw).is_file())

    def test_cancel_at_publication_is_rejected_and_valid_cache_survives(self):
        actual = os.replace
        observed = []
        def replace(source, target):
            if str(target).endswith('.i420'):
                try:self.call()
                except ValueError:observed.append('rejected')
            return actual(source,target)
        with patch.object(os,'replace',side_effect=replace):
            self.ns['prepare_video']('clip.mp4',False,manual=True)
        self.assertEqual(observed,['rejected'])
        self.assertEqual(self.foreground.snapshot()['status'],'completed')
        self.assertTrue(self.ns['prepared_cache'](str(self.source),False))

    def test_terminal_space_failure_can_be_cleared_without_restart(self):

        with patch('video_storage.shutil.disk_usage',return_value=SimpleNamespace(free=0)), self.assertRaisesRegex(RuntimeError,'GiB'):
            self.ns['prepare_video']('clip.mp4',False,manual=True)
        self.states['busy'] = False
        failed = self.foreground.snapshot()
        self.assertEqual(failed['status'],'error')
        self.assertTrue(failed['canCancel'])
        self.assertTrue(self.call()['cleared'])
        self.assertEqual(self.foreground.snapshot()['status'],'idle')
        self.assertEqual(self.states['stage'],'Aguardando')
        self.ns['subprocess'].Popen.assert_not_called()

    def test_clearing_old_error_does_not_overwrite_new_operation_state(self):
        previous = self.foreground.start('clip.mp4')
        previous.finish(RuntimeError('old disk error'))
        self.states.update(busy=False,preparationJobId='newer-operation',stage='New result',message='Keep current result')
        before = dict(self.states)
        self.assertTrue(self.call()['cleared'])
        self.assertEqual(self.states,before)

    def test_cleanup_failure_is_an_error_not_a_successful_cancellation(self):
        self.hook = lambda values:self.call() if values.get('stage')=='Identificando vídeo' else None
        actual = os.remove
        def fail_partial(path):
            if str(path).endswith('.partial'):raise PermissionError('partial still in use')
            return actual(path)
        with patch.object(os,'remove',side_effect=fail_partial):
            with self.assertRaises(PermissionError):self.ns['prepare_video']('clip.mp4',False,manual=True)
        self.assertEqual(self.foreground.snapshot()['status'],'error')
        self.assertIn('still in use',self.foreground.snapshot()['error'])
        self.assertTrue(self.active.exists())

    def test_failed_kill_keeps_busy_and_preparation_lock_until_exact_child_exits(self):
        child_started, child_exit, kill_attempted = threading.Event(),threading.Event(),threading.Event()
        class StubbornOutput:
            closed=False
            def __iter__(self):return self
            def __next__(self):
                child_exit.wait(5)
                raise StopIteration
            def close(self):self.closed=True
        class StubbornProcess:
            stdout=StubbornOutput()
            def poll(self):return 0 if child_exit.is_set() else None
            def terminate(self):raise PermissionError('temporary terminate failure')
            def kill(self):kill_attempted.set()
            def wait(self,timeout=None):
                if not child_exit.is_set():raise subprocess.TimeoutExpired('fake-converter',timeout)
                return 0
        process=StubbornProcess()
        # First stop request cannot terminate; subsequent attempts reach kill,
        # which is intentionally ineffective until the test confirms exit.
        calls=0
        def terminate():
            nonlocal calls
            calls+=1
            if calls==1:raise PermissionError('temporary terminate failure')
        process.terminate=terminate
        def launch(args,**kwargs):
            Path(args[-1]).write_bytes(b'partially written frames')
            child_started.set()
            return process
        self.ns['subprocess'].Popen.side_effect=launch
        self.ns['run_conversion']=lambda process,job,on_line:run_conversion(process,job,on_line,grace=.01,poll_interval=.01)
        self.background.start('clip.mp4')
        foreground_errors=[]
        foreground_thread=None
        try:
            self.assertTrue(child_started.wait(2))
            self.call('background')
            self.assertTrue(kill_attempted.wait(2))
            self.assertTrue(self.background.snapshot()['busy'])
            self.assertTrue(self.ns['PREPARATION_LOCK'].locked())
            with self.assertRaises(ValueError):self.background.start('clip.mp4')
            def foreground_waiter():
                try:self.ns['prepare_video']('clip.mp4',False,manual=True)
                except BaseException as exc:foreground_errors.append(exc)
            foreground_thread=threading.Thread(target=foreground_waiter)
            foreground_thread.start()
            deadline=time.monotonic()+2
            while not self.foreground.snapshot()['jobId'] and time.monotonic()<deadline:time.sleep(.01)
            self.call('foreground')
            foreground_thread.join(2)
            self.assertFalse(foreground_thread.is_alive())
            self.assertIsInstance(foreground_errors[0],PreparationCancelled)
            self.assertEqual(self.ns['subprocess'].Popen.call_count,1)
            self.assertTrue(self.background.snapshot()['busy'])
        finally:
            child_exit.set()
            if foreground_thread is not None:foreground_thread.join(2)
            self.wait_idle(self.background)
        self.assertFalse(self.ns['PREPARATION_LOCK'].locked())
        self.assertTrue(process.stdout.closed)
        self.assertEqual(self.background.snapshot()['status'],'cancelled')
        self.assert_old_files()

    def test_manual_preparation_cancel_prevents_camera_activation(self):
        self.ns.update(phone_names=lambda:{},TRANSFERS=SimpleNamespace(reset=Mock(),mark=Mock(),
            snapshot=Mock(return_value={'installedVideos':{}})), SHARED=SimpleNamespace(install=Mock()))
        self.hook = lambda values:self.call() if values.get('stage')=='Identificando vídeo' else None
        with self.assertRaises(PreparationCancelled):
            self.ns['install_targets']([('phone','s1')],'clip.mp4',False,manual=True)
        self.ns['SHARED'].install.assert_not_called()
        self.assertNotEqual(self.states.get('stage'),'Ativando câmeras')

    def test_cancel_action_does_not_discover_devices_and_rejects_foreign_origin(self):
        job = self.foreground.start('clip.mp4')
        data = {'action':'cancel_preparation','kind':'foreground','jobId':job.snapshot()['jobId']}
        body=json.dumps(data).encode()
        handler=SimpleNamespace(path='/api/action',headers={'Content-Length':str(len(body)),
            'Host':'127.0.0.1:8770','Origin':'https://foreign.example'},rfile=BytesIO(body),sendj=Mock())
        self.ns['do_POST'](handler)
        self.assertEqual(handler.sendj.call_args.args[1],403)
        self.assertFalse(job.cancel_event.is_set())
        self.assertTrue(self.ns['action'](data)['cancelRequested'])
        self.ns['devices'].assert_not_called()

    def test_active_manual_preparation_wins_over_old_background_error_for_same_video(self):
        older = dict(name='clip.mp4',busy=False,error='old failure',startedAt=1)
        current = dict(name='clip.mp4',busy=True,error='',progress=52,startedAt=2)
        selected = self.ns['preparation_state_for_video']('clip.mp4',older,current)
        readiness = video_readiness('clip.mp4',None,None,[],{},selected)
        self.assertEqual(readiness['preparation']['state'],'preparing')
        self.assertEqual(readiness['preparation']['progress'],52)


if __name__ == '__main__':unittest.main()
