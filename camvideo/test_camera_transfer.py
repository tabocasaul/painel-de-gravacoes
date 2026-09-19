import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from camera_transfer import Transfers


class TransferTests(unittest.TestCase):
    def test_concurrent_records_survive_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            transfer=Transfers('adb',directory,lambda:{})
            threads=[threading.Thread(target=transfer.record,args=(f'emulator-{n}','clip.mov',200,100,'asset')) for n in range(8)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
            reloaded=Transfers('adb',directory,lambda:{})
            self.assertEqual(len(reloaded.installed),8)
            self.assertTrue(all(r['confirmed'] for r in reloaded.installed.values()))

    def test_failure_during_push_preserves_previous_video(self):
        with tempfile.TemporaryDirectory() as directory:
            transfer=Transfers('adb',directory,lambda:{})
            transfer.record('emulator-1','old.mov',100,50,'old')
            path=Path(directory)/'new.i420';path.write_bytes(b'123456')
            with patch.object(transfer,'send_blocks',side_effect=RuntimeError('ADB disconnected')):
                with self.assertRaises(RuntimeError):transfer.send('emulator-1',str(path),'new.mov',3,'new')
            self.assertEqual(transfer.installed['emulator-1']['name'],'old.mov')

    def test_incomplete_receiver_never_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            transfer=Transfers('adb',directory,lambda:{})
            path=Path(directory)/'new.i420';path.write_bytes(b'123456')
            with patch.object(transfer,'run',return_value='4') as run,patch.object(transfer,'send_blocks'):
                with self.assertRaisesRegex(RuntimeError,'incompleto'):transfer.send('emulator-1',str(path),'new.mov',3)
                self.assertFalse(any(call.kwargs.get('root') for call in run.call_args_list))
            self.assertEqual(transfer.installed,{})

    def test_unconfirmed_commit_is_persisted_as_unconfirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            transfer=Transfers('adb',directory,lambda:{})
            transfer.record('emulator-1','new.mov',100,50,'new',confirmed=False)
            row=Transfers('adb',directory,lambda:{}).installed['emulator-1']
            self.assertEqual(row['name'],'new.mov')
            self.assertFalse(row['confirmed'])

    def test_checkpoint_ignores_other_video_and_preserves_committed_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            transfer=Transfers('adb',directory,lambda:{})
            with patch.object(transfer,'run',side_effect=['other 4','8']):
                self.assertEqual(transfer.checkpoint('emulator-1','expected',8),0)
            with patch.object(transfer,'run',side_effect=['expected 4','6']):
                self.assertEqual(transfer.checkpoint('emulator-1','expected',8),4)
            with patch.object(transfer,'run',side_effect=['expected 9','9']):
                self.assertEqual(transfer.checkpoint('emulator-1','expected',8),0)

    def test_block_retry_does_not_duplicate_committed_bytes(self):
        import hashlib,re
        with tempfile.TemporaryDirectory() as directory:
            transfer=Transfers('adb',directory,lambda:{})
            path=Path(directory)/'new.i420';path.write_bytes(b'abcdefgh')
            commits=[]
            def run(serial,*args,**kwargs):
                if args[:2]==('shell','cat'):raise RuntimeError('no checkpoint')
                if args[:2]==('shell','sha256sum'):
                    return hashlib.sha256((Path(directory)/'chunk-emulator-1.bin').read_bytes()).hexdigest()+' chunk'
                if kwargs.get('root') and 'cat ' in args[0]:
                    commits.append(int(re.search(r'-eq (\d+)',args[0]).group(1)))
                return ''
            with patch.object(transfer,'run',side_effect=run),patch.object(transfer,'push_block',side_effect=[RuntimeError('disconnect'),None,None]) as push,patch('camera_transfer.BLOCK_BYTES',4),patch('camera_transfer.time.sleep'):
                transfer.send_blocks('emulator-1',str(path),'asset',Path(directory)/'log')
            self.assertEqual(commits,[4,8])
            self.assertEqual(push.call_count,3)
            self.assertEqual(transfer.rows['emulator-1']['bytes'],8)

if __name__=='__main__':unittest.main()
