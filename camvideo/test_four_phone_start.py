"""Exercise server boot/activation with a fake clock and no real Android calls."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from automation_queue import GIB, run_queue
from task_history import task_usage
import test_participant_selection as participant_fixture


class FourPhoneStartTests(unittest.TestCase):
    def setUp(self):
        self.fixture=participant_fixture.ServerSelectionTests()
        self.fixture.setUp()
        self.ns=self.fixture.ns
        self.now=0
        self.delays={f's{i}':0 for i in range(4)}
        self.started={}
        self.batches=[]
        self.queue_calls=[]
        self.state={}
        self.events=[]
        self.sleep_hook=lambda:None
        self.targets={f'p{i}':(f's{i}',i) for i in range(4)}
        self.options=dict(scope='selected',selectedSerials=[f's{i}' for i in range(4)],
            simultaneous=4,interleavedPlan=True,interleavedTasks=[dict(task='A',videos=['fixture.mov'])],
            autoNavigate=True,randomizePhones=False)
        self.ns['time']=SimpleNamespace(monotonic=lambda:self.now,sleep=self.sleep)
        self.ns['status']=self.status
        self.ns['start_phone']=Mock(side_effect=self.start)
        self.ns['task_usage']=task_usage
        self.fixture.e._ler_historico=Mock(return_value={'dias':{}})
        self.fixture.e._adb=Mock(return_value=SimpleNamespace(stdout='1',returncode=0))
        self.fixture.a.e=self.fixture.e
        self.fixture.a.mark=Mock()
        self.fixture.a.check_cancel=self.check_cancel
        self.fixture.a.update=self.update
        self.fixture.a._run_cycle=self.record
        self.ns['update']=self.update
        self.ns['snap']=lambda:self.state
        def queue(*args,**kwargs):
            self.queue_calls.append(kwargs)
            return run_queue(*args,available=lambda:20*GIB,**kwargs)
        self.ns['run_queue']=queue

    def check_cancel(self):
        if self.fixture.e.cancelar_sync.is_set():raise InterruptedError('cancelled in test')

    def update(self,**values):
        self.state.update(values)
        self.events.append(values)

    def sleep(self,seconds):
        self.now+=seconds
        self.sleep_hook()

    def status(self,serial):
        if serial not in self.started:return 'off'
        return 'online' if self.now-self.started[serial]>=self.delays.get(serial,0) else 'booting'

    def start(self,name,serial,port):
        self.started[serial]=self.now

    def record(self,batch,*args,**kwargs):
        self.batches.append((dict(batch),dict(kwargs),self.now))
        for name in batch:self.fixture.totals[name,'A']=7200
        self.fixture.a.snapshot=Mock(return_value={serial:dict(stage='Salvo') for serial,_ in batch.values()})

    def run_plan(self):return self.ns['sync'](self.options)

    def test_four_phones_including_one_thirty_second_boot_start_one_complete_batch(self):
        self.delays['s3']=30
        self.run_plan()
        self.assertEqual(self.ns['start_phone'].call_count,4)
        self.assertEqual(len(self.batches),1)
        batch,options,when=self.batches[0]
        self.assertEqual(batch,self.targets)
        self.assertTrue(options['require_all_ready'])
        self.assertTrue(options['tolerate_failures'])
        self.assertGreaterEqual(when-self.started['s3'],30)
        self.assertTrue(any(row.get('bootElapsed',0)>=30 for row in self.events))
        self.assertEqual(self.state['queueBootExpected'],4)
        self.assertEqual(self.state['queueBootReady'],4)
        self.assertEqual(self.state['queueFailed'],[])

    def test_timeout_of_fourth_phone_prevents_partial_recording(self):
        self.delays['s3']=1000
        with self.assertRaisesRegex(RuntimeError,'rodada não começou'):
            self.run_plan()
        self.assertEqual(self.batches,[])
        self.assertEqual(self.state['queueFailed'],['p3'])
        self.assertIn('6 minutos',self.state['queueErrors']['p3'])
        self.assertGreaterEqual(self.now-self.started['s3'],360)
        self.assertLess(self.now-self.started['s3'],362)
        self.assertFalse(self.state['bootWaiting'])
        self.assertFalse(self.state['queueActive'])

    def test_start_error_does_not_record_remaining_three_or_modify_installed_records(self):
        previous={serial:dict(row) for serial,row in self.fixture.installed.items()}
        def fail(name,serial,port):
            if serial=='s3':raise RuntimeError('not enough RAM for this phone')
            self.start(name,serial,port)
        self.ns['start_phone'].side_effect=fail
        with self.assertRaisesRegex(RuntimeError,'not enough RAM'):
            self.run_plan()
        self.assertEqual(self.batches,[])
        self.assertEqual(self.fixture.installed,previous)
        self.assertEqual(self.state['queueFailed'],['p3'])

    def test_cancel_during_slow_boot_stops_before_recording(self):
        self.delays['s0']=120
        self.sleep_hook=lambda:self.fixture.e.cancelar_sync.set() if self.now>=6 else None
        with self.assertRaises(InterruptedError):self.run_plan()
        self.assertEqual(self.batches,[])
        self.assertLess(self.now,10)
        self.assertFalse(self.state['bootWaiting'])

    def test_stop_after_round_during_boot_stops_without_starting_a_recording(self):
        self.delays['s0']=120
        self.sleep_hook=lambda:self.fixture.a.stop_after_round.set() if self.now>=6 else None
        with self.assertRaisesRegex(InterruptedError,'antes da gravação'):self.run_plan()
        self.assertEqual(self.batches,[])
        self.assertLess(self.now,10)
        self.assertFalse(self.fixture.e.cancelar_sync.is_set())

    def test_failed_source_activation_does_not_admit_three_to_queue(self):
        for serial in self.delays:self.fixture.installed[serial]['assetId']='previous'
        def install(targets,video,fill):
            for name,serial in targets:
                if serial=='s3':raise RuntimeError('source unavailable')
                self.fixture.installed[serial].update(assetId='cache:False',staged=True,mode='shared')
        self.ns['install_targets']=install
        with self.assertRaisesRegex(RuntimeError,'nem todos'):
            self.run_plan()
        self.assertEqual(self.queue_calls,[])
        self.assertEqual(self.batches,[])
        self.ns['start_phone'].assert_not_called()
        self.assertEqual(self.state['queueFailed'],['p3'])
        self.assertEqual(self.state['queueErrors']['p3'],'source unavailable')

    def test_old_queue_failure_is_cleared_on_new_successful_start(self):
        self.state.update(queueFailed=['previous'],queueErrors={'previous':'stale error'})
        self.run_plan()
        self.assertEqual(self.state['queueFailed'],[])
        self.assertEqual(self.state['queueErrors'],{})

    def test_phone_lost_after_boot_blocks_the_whole_group_before_recording(self):
        self.ns['status']=lambda serial:('off' if serial=='s0' and len(self.started)==4 else self.status(serial))
        with self.assertRaisesRegex(RuntimeError,'aguardando todos'):
            self.run_plan()
        self.assertEqual(self.batches,[])
        self.assertEqual(self.state['queueFailed'],['p0'])
        self.assertEqual(self.state['queueBootReady'],3)

    def test_one_offline_one_online_two_pending_offline_wait_for_recovery_then_start_four(self):
        pending={'s2':{'session':'saved-capture-2'},'s3':{'session':'saved-capture-3'}}
        self.fixture.supervisor.state.side_effect=lambda:{'pending':dict(pending)}
        self.started['s1']=-10
        self.delays['s2']=30
        self.delays['s3']=30
        recovered=[]
        def recover(serial):
            self.assertEqual(self.status(serial),'online')
            self.assertEqual(self.batches,[])
            recovered.append(serial)
            pending.pop(serial)
            return True
        self.fixture.supervisor.recover_quick.side_effect=recover
        self.run_plan()
        self.assertEqual(set(recovered),{'s2','s3'})
        self.assertEqual(pending,{})
        self.assertEqual(len(self.batches),1)
        self.assertEqual(self.batches[0][0],self.targets)
        self.assertEqual(len(self.started),4)
        calls=[call.args[1] for call in self.ns['start_phone'].call_args_list]
        self.assertEqual(calls.count('s2'),1)
        self.assertEqual(calls.count('s3'),1)
        self.assertTrue(any(row.get('bootWaiting') or row.get('admissionWaiting') for row in self.events))

    def test_unconfirmed_pending_captures_block_partial_group_and_keep_journal(self):
        pending={'s2':{'session':'unconfirmed-2'},'s3':{'session':'unconfirmed-3'}}
        original={serial:dict(entry) for serial,entry in pending.items()}
        self.fixture.supervisor.state.side_effect=lambda:{'pending':dict(pending)}
        self.fixture.supervisor.recover_quick.return_value=False
        self.started['s1']=-10
        with self.assertRaisesRegex(RuntimeError,'grupo completo em 6 minutos'):
            self.run_plan()
        self.assertEqual(self.batches,[])
        self.assertEqual(self.queue_calls,[])
        self.assertEqual(pending,original)
        self.assertEqual(set(self.started),{'s0','s1','s2','s3'})
        self.assertTrue(all(self.status(serial)=='online' for serial in self.started))
        self.fixture.supervisor.clear.assert_not_called()
        self.assertFalse(self.state['admissionWaiting'])
        self.assertGreaterEqual(self.now,360)

    def test_all_four_are_open_before_waiting_on_saved_uploads(self):
        pending={'s2':{'session':'saved-2'},'s3':{'session':'saved-3'}}
        self.fixture.supervisor.state.side_effect=lambda:{'pending':dict(pending)}
        self.started['s2']=-10
        self.started['s3']=-10
        checks=[]
        def recover(serial):
            checks.append(serial)
            self.assertTrue(all(self.status(item)=='online' for item in ('s0','s1','s2','s3')))
            self.assertEqual(self.batches,[])
            return False
        self.fixture.supervisor.recover_quick.side_effect=recover
        with self.assertRaisesRegex(RuntimeError,'grupo completo em 6 minutos'):
            self.run_plan()
        self.assertTrue(checks)
        self.assertEqual(self.batches,[])
        self.assertEqual(set(pending),{'s2','s3'})

    def test_pending_boot_failure_does_not_tap_record_or_clear_captures(self):
        pending={'s2':{'session':'saved-2'}}
        self.fixture.supervisor.state.side_effect=lambda:{'pending':dict(pending)}
        self.delays['s2']=1000
        with self.assertRaisesRegex(RuntimeError,'Android não terminou'):
            self.run_plan()
        self.assertEqual(self.batches,[])
        self.fixture.supervisor.clear.assert_not_called()

    def test_stop_after_while_waiting_for_pending_recovery_keeps_capture_journal(self):
        pending={'s2':{'session':'kept-2'},'s3':{'session':'kept-3'}}
        self.fixture.supervisor.state.side_effect=lambda:{'pending':dict(pending)}
        self.fixture.supervisor.recover_quick.return_value=False
        self.started.update({serial:-10 for serial in ('s0','s1','s2','s3')})
        self.sleep_hook=lambda:self.fixture.a.stop_after_round.set() if self.now>=6 else None
        with self.assertRaisesRegex(InterruptedError,'grupo completo'):
            self.run_plan()
        self.assertEqual(self.batches,[])
        self.assertEqual(set(pending),{'s2','s3'})
        self.assertLess(self.now,10)


if __name__=='__main__':unittest.main()
