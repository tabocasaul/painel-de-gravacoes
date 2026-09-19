"""Resume accepted uploads with fake Android calls and temporary journals only."""
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from loop_supervisor import accepted_upload_pending
import test_quick_recovery as recovery_fixture


class UploadResumeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=recovery_fixture.QuickRecoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.supervisor=self.fixture.supervisor
        self.engine=self.fixture.engine
        self.clock=[0.0]
        self.timer=patch('loop_supervisor.time.monotonic',side_effect=lambda:self.clock[0])
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.supervisor.recover_on_open=Mock()

    def raw(self, accepted=True, status='ended', task='Colher Ervas', session='capture-a', upload='uploading'):
        return json.dumps([dict(sessionId=session,accepted=accepted,status=status,taskId='task-a',taskName=task),
            dict(sessionId=session,id='upload-a',durationMs=120000,status=upload)],
            ensure_ascii=False,separators=(',',':')).encode('utf-8')

    def recover(self):return self.supervisor.recover_quick('serial-a')

    def test_uploading_receipt_reopens_app_without_tapping_or_crediting_or_clearing(self):
        self.engine._shell_root_bytes.return_value=self.raw()
        before=self.supervisor.state()
        self.assertFalse(self.recover())
        self.supervisor.recover_on_open.assert_called_once_with('serial-a',3)
        self.assertEqual(self.supervisor.state(),before)
        self.assertEqual(self.fixture.history(),{})
        self.assertFalse(self.fixture.taps())
        self.assertEqual(self.engine._adb.call_count,1)
        self.fixture.assert_no_long_recovery()

    def test_opening_is_rate_limited_but_later_upload_confirmation_is_immediate_and_once(self):
        self.engine._shell_root_bytes.return_value=self.raw()
        self.assertFalse(self.recover())
        self.clock[0]=12
        self.assertFalse(self.recover())
        self.supervisor.recover_on_open.assert_called_once()
        self.clock[0]=31
        self.assertFalse(self.recover())
        self.assertEqual(self.supervisor.recover_on_open.call_count,2)
        self.engine._shell_root_bytes.return_value=self.raw(upload='done')
        self.assertTrue(self.recover())
        self.assertEqual(self.supervisor.state()['pending'],{})
        self.assertEqual(len(self.fixture.history()['supervisorSessions']),1)
        self.assertEqual(self.fixture.history()['supervisorSessions']['capture-a_1']['seconds'],120)
        self.assertTrue(self.recover())
        self.assertEqual(len(self.fixture.history()['supervisorSessions']),1)
        self.assertEqual(self.supervisor.recover_on_open.call_count,2)

    def test_already_done_receipt_credits_without_reopening(self):
        self.engine._shell_root_bytes.return_value=self.raw(upload='done')
        self.assertTrue(self.recover())
        self.supervisor.recover_on_open.assert_not_called()

    def test_unaccepted_started_and_other_session_receipts_never_reopen(self):
        for raw in (self.raw(accepted=False),self.raw(status='started'),self.raw(session='other-session'),
                    self.raw(accepted=False,session='capture-a')+self.raw(session='other-session')):
            with self.subTest(raw=raw):
                self.engine._shell_root_bytes.return_value=raw
                before=self.supervisor.state()
                self.assertFalse(self.recover())
                self.supervisor.recover_on_open.assert_not_called()
                self.assertEqual(self.supervisor.state(),before)

    def test_wrong_or_neighbour_task_never_reopens_or_credits(self):
        for raw in (self.raw(task='Other task'),
                    self.raw().replace(b'"taskId":"task-a","taskName":"Colher Ervas"',b'"other":"field"')+
                    self.raw(session='other-session')):
            with self.subTest(raw=raw):
                self.engine._shell_root_bytes.return_value=raw
                before=self.supervisor.state()
                self.assertFalse(self.recover())
                self.supervisor.recover_on_open.assert_not_called()
                self.assertEqual(self.supervisor.state(),before)
                self.assertFalse(self.fixture.taps())

    def test_default_no_callback_preserves_pending_without_legacy_ui_taps(self):
        self.supervisor.recover_on_open=None
        self.engine._shell_root_bytes.return_value=self.raw()
        self.fixture.xml='<hierarchy><node package="com.bakerdata.minute" resource-id="record-accept" clickable="true" bounds="[1,2][4,5]"/></hierarchy>'
        before=self.supervisor.state()
        self.assertFalse(self.recover())
        self.assertFalse(self.fixture.taps())
        self.assertEqual(self.supervisor.state(),before)

    def test_launch_timeout_keeps_journal_and_does_not_loop_or_fall_back_to_taps(self):
        self.engine._shell_root_bytes.return_value=self.raw()
        self.supervisor.recover_on_open.side_effect=subprocess.TimeoutExpired('am start',3)
        before=self.supervisor.state()
        self.assertFalse(self.recover())
        self.assertFalse(self.recover())
        self.supervisor.recover_on_open.assert_called_once()
        self.assertEqual(self.supervisor.state(),before)
        self.assertFalse(self.fixture.taps())

    def test_callback_uses_remaining_budget_and_cancel_propagates(self):
        def root(*args,**kwargs):
            self.clock[0]+=6.5
            return self.raw()
        self.engine._shell_root_bytes.side_effect=root
        self.assertFalse(self.recover())
        self.supervisor.recover_on_open.assert_called_once_with('serial-a',1.5)
        self.clock[0]=40
        self.fixture.auto.check_cancel.side_effect=InterruptedError('User cancelled')
        with self.assertRaises(InterruptedError):self.recover()
        self.assertIn('serial-a',self.supervisor.state()['pending'])

    def test_pending_helper_requires_valid_uploads_of_exact_accepted_ended_session(self):
        self.assertTrue(accepted_upload_pending(self.raw(),'capture-a_0'))
        self.assertTrue(accepted_upload_pending(self.raw(upload='pending'),'capture-a_0'))
        for raw in (self.raw(upload='done'),self.raw(accepted=False),self.raw(status='started'),
                    self.raw().replace(b'120000',b'"NaN"'),self.raw().replace(b'120000',b'0'),
                    self.raw().replace(b'120000',b'999999999'),self.raw(session='different')):
            with self.subTest(raw=raw):self.assertFalse(accepted_upload_pending(raw,'capture-a_0'))


if __name__=='__main__':unittest.main()
