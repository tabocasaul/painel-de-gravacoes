import importlib.machinery
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

panel=importlib.machinery.SourceFileLoader('panel_test',str(Path(__file__).with_name('modern_server.pyw'))).load_module()

class UploadTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        panel.VIDEOS=self.directory.name
        panel.S.update(busy=False)
        self.server=panel.PanelServer(('127.0.0.1',0),panel.H)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.directory.cleanup()

    def test_second_panel_cannot_share_listening_port(self):
        with self.assertRaises(OSError):
            other=panel.PanelServer(self.server.server_address,panel.H)
            other.server_close()

    def test_state_identifies_backend(self):
        self.assertEqual(panel.snap()['backendPid'],panel.os.getpid())
        self.assertEqual(panel.snap()['backendVersion'],5)

    def test_complete_upload_is_published_atomically(self):
        payload=b'video test bytes'*1000
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.request('POST','/api/upload',payload,{'X-Filename':'test.mp4'})
        response=connection.getresponse();self.assertEqual(response.status,200)
        self.assertEqual(json.loads(response.read())['name'],'test.mp4');connection.close()
        self.assertEqual((Path(self.directory.name)/'test.mp4').read_bytes(),payload)
        self.assertEqual(panel.S['progress'],100);self.assertFalse(panel.S['busy'])

    def test_interrupted_upload_keeps_old_file_and_releases_busy(self):
        path=Path(self.directory.name)/'test.mp4';path.write_bytes(b'old')
        connection=socket.create_connection(('127.0.0.1',self.server.server_port))
        connection.sendall(b'POST /api/upload HTTP/1.1\r\nHost: localhost\r\nX-Filename: test.mp4\r\nContent-Length: 100000\r\n\r\nshort')
        connection.shutdown(socket.SHUT_WR)
        connection.recv(4096);connection.close()
        end=time.monotonic()+2
        while panel.S['busy'] and time.monotonic()<end:time.sleep(.01)
        self.assertEqual(path.read_bytes(),b'old')
        self.assertFalse(Path(str(path)+'.uploading').exists())
        self.assertFalse(panel.S['busy']);self.assertEqual(panel.S['level'],'error')

    def test_upload_rejected_while_installing(self):
        panel.S['busy']=True
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.request('POST','/api/upload',b'bytes',{'X-Filename':'test.mp4'})
        response=connection.getresponse();self.assertEqual(response.status,409);response.read();connection.close()
        self.assertFalse((Path(self.directory.name)/'test.mp4').exists())

if __name__=='__main__':unittest.main()
