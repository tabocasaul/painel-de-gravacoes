import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch
from panel_watchdog import watch


class WatchdogTests(unittest.TestCase):
    def test_dead_owner_restarts_with_recovery_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/'state.json';path.write_text(json.dumps({'enabled':True,'ownerPid':123}))
            kernel=Mock();kernel.OpenProcess.return_value=456;kernel.WaitForSingleObject.return_value=0
            with patch('panel_watchdog.ctypes.windll.kernel32',kernel),patch('panel_watchdog.time.sleep'),patch('panel_watchdog.subprocess.Popen') as popen:
                watch(str(path),123,'C:/app/modern_server.pyw')
            self.assertIn('--supervisor-resume',popen.call_args.args[0])
            kernel.TerminateProcess.assert_not_called()

    def test_user_stop_or_other_owner_prevents_restart(self):
        for state in ({'enabled':False,'ownerPid':123},{'enabled':True,'ownerPid':987}):
            with tempfile.TemporaryDirectory() as folder:
                path=pathlib.Path(folder)/'state.json';path.write_text(json.dumps(state))
                kernel=Mock();kernel.OpenProcess.return_value=456
                with patch('panel_watchdog.ctypes.windll.kernel32',kernel),patch('panel_watchdog.time.sleep'),patch('panel_watchdog.subprocess.Popen') as popen:
                    watch(str(path),123,'C:/app/modern_server.pyw')
                popen.assert_not_called();kernel.TerminateProcess.assert_not_called()
