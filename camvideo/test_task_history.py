import unittest
from task_history import task_usage, priority, daily_task_rows


class UsageTests(unittest.TestCase):
    def test_tasks_and_phones_have_independent_daily_limits(self):
        history = {'dias': {'2026-09-10': {'a': {
            'dishes': {'nome': 'Lavar louça', 'segundos': 7200},
            'other': {'nome': 'Varrer', 'segundos': 600}}}}}
        rows = daily_task_rows(history, ['a', 'b'], '2026-09-10')
        self.assertFalse(rows[0]['phones'][0]['available'])
        self.assertTrue(rows[0]['phones'][1]['available'])
        self.assertTrue(rows[1]['phones'][0]['available'])
        tomorrow = daily_task_rows(history, ['a', 'b'], '2026-09-11')
        self.assertEqual(len(tomorrow), 2)
        self.assertTrue(all(p['seconds'] == 0 and p['available']
                            for row in tomorrow for p in row['phones']))
        self.assertEqual(task_usage(history, 'a', 'Lavar louça'), 7200)

    def test_day_rollover_retains_total_and_aliases(self):
        history = {'dias': {
            '2026-09-09': {'phone': {'old': {'nome': 'Lavar Louça na Pia', 'segundos': 3600}}},
            '2026-09-10': {'phone': {'new': {'nome': 'Lavar Louças na Pia', 'segundos': 1800}}}}}
        self.assertEqual(task_usage(history, 'phone', 'lavar louca na pia'), 5400)
        self.assertEqual(task_usage(history, 'phone', 'lavar louca na pia', '2026-09-10'), 1800)
        self.assertEqual(task_usage(history, 'phone', 'lavar louca no tanque'), 0)

    def test_less_today_then_lifetime_and_skip_limit(self):
        targets = dict.fromkeys(['full', 'more', 'zeroOld', 'zeroNew', 'tooShort'])
        today = dict(full=7200, more=1800, zeroOld=0, zeroNew=0, tooShort=7150)
        total = dict(full=7200, more=1800, zeroOld=5000, zeroNew=0, tooShort=7150)
        ordered, skipped = priority(targets, today.get, total.get)
        self.assertEqual(list(ordered), ['zeroNew', 'zeroOld', 'more'])
        self.assertEqual(set(skipped), {'full', 'tooShort'})


if __name__ == '__main__': unittest.main()
