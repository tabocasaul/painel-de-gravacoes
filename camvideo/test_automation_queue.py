import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from automation_queue import run_queue, additional_capacity, GIB, capacity_snapshot, wait_for_shutdown


class QueueTests(unittest.TestCase):
    def test_slow_shutdown_waits_for_three_confirmed_absences(self):
        now = [0]
        present = SimpleNamespace(returncode=0, stdout='List of devices attached\ns1\tdevice\n')
        absent = SimpleNamespace(returncode=0, stdout='List of devices attached\n')
        adb = Mock(side_effect=[present]*90 + [absent, present, absent, absent, absent])
        with patch('automation_queue.time.monotonic', side_effect=lambda: now[0]), patch('automation_queue.time.sleep', side_effect=lambda n: now.__setitem__(0, now[0]+n)):
            wait_for_shutdown('s1', adb, Mock())
        self.assertGreater(now[0], 120)
        self.assertEqual(adb.call_count, 95)
        self.assertTrue(all(c.args == ('s1', 'devices') for c in adb.call_args_list))

    def test_adb_failure_does_not_confirm_shutdown(self):
        now = [0]
        adb = Mock(return_value=SimpleNamespace(returncode=1, stdout=''))
        with patch('automation_queue.time.monotonic', side_effect=lambda: now[0]), patch('automation_queue.time.sleep', side_effect=lambda n: now.__setitem__(0, now[0]+n)):
            with self.assertRaisesRegex(RuntimeError, 'não confirmou'):
                wait_for_shutdown('s1', adb, Mock(), timeout=10)

    def test_random_order_visits_every_eligible_phone_once(self):
        a, targets, installed, active, calls, boot, shutdown, memory = self.setup_queue()
        with patch('automation_queue.random.shuffle', side_effect=lambda items: items.reverse()) as shuffle:
            run_queue(a, targets, Mock(), installed, 'task', True, False,
                      lambda s: s in active, boot, shutdown, memory,
                      usage=lambda n: 7200 if n == 'p0' else 0, randomize=True)
        self.assertEqual([n for batch in calls for n in batch], ['p4', 'p3', 'p2', 'p1'])
        shuffle.assert_called_once()

    def test_live_capacity_changes_when_memory_is_freed(self):
        with patch('automation_queue.memory_info', return_value={'freeBytes':3*GIB,'totalBytes':16*GIB}):
            self.assertEqual(capacity_snapshot(7,2)['additional'],0)
        with patch('automation_queue.memory_info', return_value={'freeBytes':9*GIB,'totalBytes':16*GIB}):
            self.assertEqual(capacity_snapshot(7,2)['additional'],2)
            self.assertEqual(capacity_snapshot(3,2)['estimatedTotal'],3)
    def test_higher_usage_online_phone_yields_to_lower_usage(self):
        data = self.setup_queue()
        a, targets, installed, active, calls, boot, shutdown, memory = data
        active.add('s0')
        used = lambda n: 7200 if n == 'p0' else 0
        run_queue(a, targets, Mock(), installed, 'task', True, False,
                  lambda s: s in active, boot, shutdown, memory, used)
        self.assertEqual(calls, [['p1', 'p2'], ['p3', 'p4']])
        self.assertEqual(shutdown.call_args_list[0].args, ('s0',))

    def test_everyone_at_limit_finishes_without_boot(self):
        a, targets, installed, active, calls, boot, shutdown, memory = self.setup_queue()
        run_queue(a, targets, Mock(), {}, 'task', True, True,
                  lambda s: s in active, boot, shutdown, memory, lambda n:7200)
        self.assertFalse(active)
        self.assertFalse(calls)

    def test_repeat_rotates_all_phones_across_cycles_until_daily_limit(self):
        a, targets, installed, active, calls, boot, shutdown, memory = self.setup_queue()
        totals = {name: 0 for name in targets}
        original = a._run_cycle
        def save_cycle(batch, *args, **kwargs):
            original(batch, *args, **kwargs)
            for name in batch:
                totals[name] += 3600
        a._run_cycle = save_cycle
        run_queue(a, targets, Mock(), installed, 'task', True, True,
                  lambda s: s in active, boot, shutdown, memory,
                  lambda name: totals[name])
        for name in targets:
            self.assertEqual(sum(name in batch for batch in calls), 2)
            self.assertEqual(totals[name], 7200)
        self.assertTrue(all(len(batch) <= 2 for batch in calls))
        self.assertEqual(a.update.call_args.kwargs['loopActive'], False)

    def setup_queue(self, failure=False):
        targets = {f'p{i}': (f's{i}', i) for i in range(5)}
        installed = {s: dict(confirmed=True, assetId='same') for s, _ in targets.values()}
        active, calls, rows = set(), [], {}
        a = SimpleNamespace(e=SimpleNamespace(cancelar_sync=threading.Event()),
                            stop_after_round=threading.Event(), update=Mock())
        def check():
            if a.e.cancelar_sync.is_set(): raise InterruptedError()
        a.check_cancel = check
        def cycle(batch, *args, **kwargs):
            calls.append(list(batch))
            rows.clear()
            rows.update({s: {'stage': 'Error' if failure else 'Salvo'} for s, _ in batch.values()})
        a._run_cycle = cycle
        a.snapshot = lambda: rows
        def boot(n, s, p): active.add(s)
        shutdown = Mock(side_effect=lambda s: active.remove(s))
        memory = lambda: (9 - len(active)*3)*GIB
        return a, targets, installed, active, calls, boot, shutdown, memory

    def execute(self, data):
        a, targets, installed, active, calls, boot, shutdown, memory = data
        run_queue(a, targets, Mock(), installed, 'Lavar Louça na Pia', True, False,
                  lambda s: s in active, boot, shutdown, memory)

    def test_capacity_scales_with_available_memory(self):
        self.assertEqual(additional_capacity(2*GIB), 0)
        self.assertEqual(additional_capacity(9*GIB), 2)
        self.assertEqual(additional_capacity(27*GIB), 8)

    def test_fixed_pair_ignores_conservative_auto_capacity_and_rotates(self):
        a, targets, installed, active, calls, boot, shutdown, _ = self.setup_queue()
        memory = lambda: (6 - len(active)*2)*GIB
        run_queue(a, targets, Mock(), installed, 'task', True, False,
                  lambda s: s in active, boot, shutdown, memory, simultaneous=2)
        self.assertEqual(calls, [['p0', 'p1'], ['p2', 'p3'], ['p4']])

    def test_fixed_pair_starts_even_below_memory_estimate(self):
        a, targets, installed, active, calls, boot, shutdown, _ = self.setup_queue()
        run_queue(a, targets, Mock(), installed, 'task', True, False,
                  lambda s: s in active, boot, shutdown, lambda: GIB // 2, simultaneous=2)
        self.assertEqual(calls, [['p0', 'p1'], ['p2', 'p3'], ['p4']])

    def test_fixed_five_starts_one_synchronized_batch(self):
        a, targets, installed, active, calls, boot, shutdown, _ = self.setup_queue()
        run_queue(a, targets, Mock(), installed, 'task', True, False,
                  lambda s: s in active, boot, shutdown, lambda: GIB, simultaneous=5)
        self.assertEqual(calls, [['p0', 'p1', 'p2', 'p3', 'p4']])

    def test_auto_keeps_three_phone_limit_when_memory_is_abundant(self):
        a, targets, installed, active, calls, boot, shutdown, _ = self.setup_queue()
        run_queue(a, targets, Mock(), installed, 'task', True, False,
                  lambda s: s in active, boot, shutdown, lambda: 100*GIB, simultaneous=None)
        self.assertEqual(calls, [['p0', 'p1', 'p2'], ['p3', 'p4']])

    def test_fixed_pair_never_starts_one_when_second_cannot_boot(self):
        a, targets, installed, active, calls, boot, shutdown, _ = self.setup_queue()
        def fail_second(name, serial, port):
            if active:
                raise RuntimeError('Falha ao abrir segundo celular')
            boot(name, serial, port)
        with self.assertRaisesRegex(RuntimeError, 'Falha ao abrir segundo celular'):
            run_queue(a, targets, Mock(), installed, 'task', True, False,
                      lambda s: s in active, fail_second, shutdown, lambda: GIB, simultaneous=2)
        self.assertEqual(calls, [])
        self.assertEqual(a.update.call_args.kwargs['busy'], False)

    def test_fixed_pair_repeat_fills_odd_batch_with_eligible_phone(self):
        a, targets, installed, active, calls, boot, shutdown, memory = self.setup_queue()
        totals = {name: 0 for name in targets}
        original = a._run_cycle
        def save(batch, *args, **kwargs):
            eligible_count = sum(seconds < 7200 for seconds in totals.values())
            self.assertEqual(len(batch), min(2, eligible_count))
            original(batch, *args, **kwargs)
            for name in batch:
                totals[name] += 3600
        a._run_cycle = save
        run_queue(a, targets, Mock(), installed, 'task', True, True,
                  lambda s: s in active, boot, shutdown, memory,
                  usage=lambda name: totals[name], simultaneous=2)
        self.assertTrue(all(seconds == 7200 for seconds in totals.values()))

    def test_all_devices_once_and_saved_batches_close(self):
        data = self.setup_queue()
        self.execute(data)
        self.assertEqual(data[4], [['p0', 'p1'], ['p2', 'p3'], ['p4']])
        self.assertEqual(data[6].call_count, 4)
        self.assertEqual(data[3], {'s4'})

    def test_failure_does_not_shutdown_or_advance(self):
        data = self.setup_queue(True)
        with self.assertRaises(RuntimeError): self.execute(data)
        self.assertEqual(len(data[4]), 1)
        data[6].assert_not_called()

    def test_wrong_video_rejected_before_boot(self):
        data = self.setup_queue()
        data[2]['s4']['assetId'] = 'different'
        with self.assertRaises(ValueError): self.execute(data)
        self.assertFalse(data[3])

    def test_cancel_after_save_does_not_start_next_batch(self):
        data = self.setup_queue()
        original = data[0]._run_cycle
        def cancelled(*args, **kwargs):
            original(*args, **kwargs)
            data[0].e.cancelar_sync.set()
        data[0]._run_cycle = cancelled
        with self.assertRaises(InterruptedError): self.execute(data)
        self.assertEqual(len(data[4]), 1)
        data[6].assert_not_called()

    def test_no_memory_does_not_boot(self):
        data = list(self.setup_queue())
        data[-1] = lambda: GIB
        with self.assertRaises(RuntimeError): self.execute(data)
        self.assertFalse(data[3])


if __name__ == '__main__': unittest.main()
