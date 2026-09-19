import threading
import time
import unittest
from unittest.mock import Mock

from synchronized_recording_start import RecordingStartGroup


class RecordingStartGroupTests(unittest.TestCase):
    def start_workers(self, serials, operation):
        errors=[]
        threads=[]
        def run(serial):
            try:operation(serial)
            except BaseException as exc:errors.append(exc)
        for serial in serials:
            thread=threading.Thread(target=run,args=(serial,),daemon=True)
            thread.start()
            threads.append(thread)
        return threads,errors

    def join_workers(self, threads, errors):
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive(),'A recording barrier did not terminate')
        self.assertEqual(errors,[])

    def test_two_and_four_phones_wait_for_last_active_phone_at_both_phases(self):
        for count in (2,4):
            with self.subTest(count=count):
                serials=[f's{index}' for index in range(count)]
                group=RecordingStartGroup(serials,Mock())
                last=serials[-1]
                allow_last=[threading.Event(),threading.Event()]
                entered={phase:{serial:threading.Event() for serial in serials} for phase in (0,1)}
                finished={phase:{serial:threading.Event() for serial in serials} for phase in (0,1)}
                def worker(serial):
                    for phase in (0,1):
                        if serial==last:
                            if not allow_last[phase].wait(1):raise RuntimeError('Test gate timed out')
                        entered[phase][serial].set()
                        group.wait(serial,phase,timeout=1)
                        finished[phase][serial].set()
                threads,errors=self.start_workers(serials,worker)
                try:
                    for phase in (0,1):
                        for serial in serials[:-1]:
                            self.assertTrue(entered[phase][serial].wait(1))
                            self.assertFalse(finished[phase][serial].is_set())
                        allow_last[phase].set()
                        for event in finished[phase].values():self.assertTrue(event.wait(1))
                finally:
                    for gate in allow_last:gate.set()
                self.join_workers(threads,errors)

    def test_drop_before_first_phase_keeps_two_and_four_phone_groups_working(self):
        for count in (2,4):
            with self.subTest(count=count):
                serials=[f's{index}' for index in range(count)]
                group=RecordingStartGroup(serials,Mock())
                group.drop(serials[-1])
                completed=[]
                def worker(serial):
                    group.wait(serial,0,timeout=1)
                    group.wait(serial,1,timeout=1)
                    completed.append(serial)
                threads,errors=self.start_workers(serials[:-1],worker)
                self.join_workers(threads,errors)
                self.assertEqual(set(completed),set(serials[:-1]))
                self.assertEqual(group.active(),set(serials[:-1]))

    def test_drop_after_first_phase_releases_healthy_second_phase_waiters(self):
        for count in (2,4):
            with self.subTest(count=count):
                serials=[f's{index}' for index in range(count)]
                group=RecordingStartGroup(serials,Mock())
                failing=serials[-1]
                allow_drop=threading.Event()
                entered_second={serial:threading.Event() for serial in serials[:-1]}
                completed={serial:threading.Event() for serial in serials[:-1]}
                def worker(serial):
                    group.wait(serial,0,timeout=1)
                    if serial==failing:
                        if not allow_drop.wait(1):raise RuntimeError('Test gate timed out')
                        group.drop(serial)
                        return
                    entered_second[serial].set()
                    group.wait(serial,1,timeout=1)
                    completed[serial].set()
                threads,errors=self.start_workers(serials,worker)
                try:
                    for serial in serials[:-1]:
                        self.assertTrue(entered_second[serial].wait(1))
                        self.assertFalse(completed[serial].is_set())
                    allow_drop.set()
                finally:
                    allow_drop.set()
                self.join_workers(threads,errors)
                self.assertTrue(all(event.is_set() for event in completed.values()))

    def test_drop_while_waiting_first_phase_notifies_all_healthy_phones(self):
        group=RecordingStartGroup(['a','b','failed'],Mock())
        entered={serial:threading.Event() for serial in ('a','b')}
        completed={serial:threading.Event() for serial in ('a','b')}
        def worker(serial):
            entered[serial].set()
            group.wait(serial,0,timeout=1)
            completed[serial].set()
        threads,errors=self.start_workers(['a','b'],worker)
        for serial in ('a','b'):
            self.assertTrue(entered[serial].wait(1))
            self.assertFalse(completed[serial].is_set())
        group.drop('failed')
        self.join_workers(threads,errors)
        self.assertTrue(all(event.is_set() for event in completed.values()))

    def test_timeout_keeps_ready_phone_and_rejects_missing_phone_when_late(self):
        group=RecordingStartGroup(['a','b'],Mock())
        started=time.monotonic()
        group.wait('a',0,timeout=.03)
        self.assertLess(time.monotonic()-started,.5)
        self.assertEqual(group.active(),{'a'})
        group.wait('a',1,timeout=.03)
        with self.assertRaisesRegex(RuntimeError,'removido'):
            group.wait('b',0,timeout=.03)
        with self.assertRaisesRegex(RuntimeError,'removido'):
            group.wait('b',1,timeout=.03)

    def test_second_phase_timeout_releases_three_ready_phones_and_rejects_fourth(self):
        group=RecordingStartGroup(['a','b','c','late'],Mock())
        ready={serial:threading.Event() for serial in ('a','b','c')}
        completed={serial:threading.Event() for serial in ('a','b','c')}
        def worker(serial):
            ready[serial].set()
            group.wait(serial,1,timeout=.15)
            completed[serial].set()
        threads,errors=self.start_workers(['a','b','c'],worker)
        for event in ready.values():self.assertTrue(event.wait(1))
        self.join_workers(threads,errors)
        self.assertTrue(all(event.is_set() for event in completed.values()))
        self.assertEqual(group.active(),{'a','b','c'})
        with self.assertRaisesRegex(RuntimeError,'removido'):
            group.wait('late',1,timeout=.1)
        self.assertEqual(group.active(),{'a','b','c'})

    def test_manual_cancel_propagates_promptly_to_waiting_threads(self):
        cancelled=threading.Event()
        entered=threading.Event()
        finished=threading.Event()
        errors=[]
        def check_cancel():
            entered.set()
            if cancelled.is_set():raise InterruptedError('Cancelado')
        group=RecordingStartGroup(['a','absent'],check_cancel)
        def worker():
            try:group.wait('a',0,timeout=3)
            except BaseException as exc:errors.append(exc)
            finally:finished.set()
        thread=threading.Thread(target=worker,daemon=True)
        thread.start()
        self.assertTrue(entered.wait(1))
        cancelled.set()
        self.assertTrue(finished.wait(.8),'Cancellation was not checked within the polling interval')
        thread.join(1)
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],InterruptedError)

    def test_active_returns_copy_and_duplicate_drop_is_harmless(self):
        group=RecordingStartGroup(['a','b'],Mock())
        snapshot=group.active()
        snapshot.clear()
        self.assertEqual(group.active(),{'a','b'})
        group.drop('a')
        group.drop('a')
        with self.assertRaisesRegex(RuntimeError,'removido'):
            group.wait('a',0,timeout=0)
        self.assertEqual(group.active(),{'b'})

    def test_invalid_phase_and_unbounded_timeout_are_rejected(self):
        group=RecordingStartGroup(['a'],Mock())
        with self.assertRaises(ValueError):group.wait('a',2)
        for timeout in (float('inf'),float('nan'),-1):
            with self.subTest(timeout=timeout),self.assertRaises(ValueError):
                group.wait('a',0,timeout=timeout)

    def test_strict_four_wait_for_last_phone_at_both_phases(self):
        serials=['a','b','c','last']
        group=RecordingStartGroup(serials,Mock(),allow_partial=False)
        gates=[threading.Event(),threading.Event()]
        waiting={phase:threading.Event() for phase in (0,1)}
        released={phase:[] for phase in (0,1)}
        lock=threading.Lock()
        def worker(serial):
            for phase in (0,1):
                if serial=='last':
                    waiting[phase].set()
                    if not gates[phase].wait(2):raise RuntimeError('Test gate timed out')
                group.wait(serial,phase,timeout=360)
                with lock:released[phase].append(serial)
        threads,errors=self.start_workers(serials,worker)
        try:
            for phase in (0,1):
                self.assertTrue(waiting[phase].wait(1))
                with lock:self.assertEqual(released[phase],[])
                self.assertEqual(group.active(),set(serials))
                gates[phase].set()
        finally:
            for gate in gates:gate.set()
        self.join_workers(threads,errors)
        for phase in (0,1):self.assertEqual(set(released[phase]),set(serials))

    def test_strict_drop_before_first_release_prevents_every_start(self):
        for drop_first in (False,True):
            with self.subTest(drop_first=drop_first):
                group=RecordingStartGroup(['a','b','c','failed'],Mock(),allow_partial=False)
                entered={serial:threading.Event() for serial in ('a','b','c')}
                started=[]
                if drop_first:group.drop('failed')
                def worker(serial):
                    entered[serial].set()
                    group.wait(serial,0,timeout=360)
                    started.append(serial)
                threads,errors=self.start_workers(['a','b','c'],worker)
                for event in entered.values():self.assertTrue(event.wait(1))
                if not drop_first:group.drop('failed')
                for thread in threads:
                    thread.join(1)
                    self.assertFalse(thread.is_alive())
                self.assertEqual(started,[])
                self.assertEqual(len(errors),3)
                self.assertTrue(all('Gravação não iniciada' in str(error) for error in errors))
                with self.assertRaisesRegex(RuntimeError,'Gravação não iniciada'):
                    group.wait('failed',0,timeout=0)

    def test_strict_first_phase_timeout_fails_waiters_and_late_phone(self):
        group=RecordingStartGroup(['a','b','c','late'],Mock(),allow_partial=False)
        started=[]
        def worker(serial):
            group.wait(serial,0,timeout=.05)
            started.append(serial)
        threads,errors=self.start_workers(['a','b','c'],worker)
        for thread in threads:
            thread.join(1)
            self.assertFalse(thread.is_alive())
        self.assertEqual(started,[])
        self.assertEqual(len(errors),3)
        self.assertTrue(all('dentro do prazo' in str(error) for error in errors))
        with self.assertRaisesRegex(RuntimeError,'dentro do prazo'):
            group.wait('late',0,timeout=0)

    def test_strict_group_keeps_started_captures_after_drop_or_second_phase_timeout(self):
        for failure in ('drop','timeout'):
            with self.subTest(failure=failure):
                group=RecordingStartGroup(['a','b','c','failed'],Mock(),allow_partial=False)
                completed=[]
                def worker(serial):
                    group.wait(serial,0,timeout=1)
                    if serial=='failed':
                        if failure=='drop':group.drop(serial)
                        return
                    group.wait(serial,1,timeout=.05)
                    completed.append(serial)
                threads,errors=self.start_workers(['a','b','c','failed'],worker)
                self.join_workers(threads,errors)
                self.assertEqual(set(completed),{'a','b','c'})
                self.assertEqual(group.active(),{'a','b','c'})

    def test_strict_six_minute_wait_observes_cancel_promptly(self):
        cancelled=threading.Event()
        entered=threading.Event()
        def check_cancel():
            entered.set()
            if cancelled.is_set():raise InterruptedError('Cancelado')
        group=RecordingStartGroup(['a','absent'],check_cancel,allow_partial=False)
        threads,errors=self.start_workers(['a'],lambda serial:group.wait(serial,0,timeout=360))
        self.assertTrue(entered.wait(1))
        cancelled.set()
        threads[0].join(.8)
        self.assertFalse(threads[0].is_alive())
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],InterruptedError)


if __name__=='__main__':
    unittest.main()
