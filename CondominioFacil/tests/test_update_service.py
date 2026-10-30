import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from update_service import UpdateService

class UpdateServiceTests(unittest.TestCase):
    def setUp(self):
        self.events=queue.Queue();self.service=UpdateService('local','nxvais11/autoword','0.12.0',self.events.put)
        self.offer=dict(version='v0.12.99',asset_id=1,sha256='a'*64)
    def tearDown(self):self.service.stop()
    def idle(self):
        deadline=time.monotonic()+2
        while (self.service.checking or self.service.downloading) and time.monotonic()<deadline:time.sleep(.005)
        self.assertFalse(self.service.checking);self.assertFalse(self.service.downloading)
    def test_check_only_notifies_and_does_not_download_until_clicked(self):
        with patch('update_service.find_update',return_value=self.offer),patch('update_service.download_update') as download:
            self.assertTrue(self.service.check())
            kind,value=self.events.get(timeout=2);self.idle()
            self.assertEqual(kind,'update_available');self.assertEqual(value,self.offer)
            download.assert_not_called()
    def test_slow_check_does_not_overlap_or_emit_after_stop(self):
        started=threading.Event();release=threading.Event()
        def check(*args):started.set();release.wait(2);return self.offer
        with patch('update_service.find_update',side_effect=check):
            try:
                self.service.check();self.assertTrue(started.wait(1))
                self.assertFalse(self.service.check());self.service.stop()
            finally:release.set();self.idle()
        self.assertTrue(self.events.empty())
    def test_download_is_single_and_failed_download_can_be_retried(self):
        self.service.offer=self.offer
        with patch('update_service.download_update',side_effect=ValueError('SHA-256 inválido')):
            self.assertTrue(self.service.download())
            self.assertEqual(self.events.get(timeout=2)[0],'update_downloading')
            self.assertEqual(self.events.get(timeout=2)[0],'update_download_error');self.idle()
            self.assertFalse(self.service.ready)
        started=threading.Event();release=threading.Event()
        receipt=dict(path='setup.exe',version=self.offer['version'],sha256=self.offer['sha256'])
        def download(*args):started.set();release.wait(2);return receipt
        with patch('update_service.download_update',side_effect=download) as send:
            try:
                self.service.download();self.assertTrue(started.wait(1));self.assertFalse(self.service.download())
            finally:release.set()
            self.assertEqual(self.events.get(timeout=2)[0],'update_downloading')
            self.assertEqual(self.events.get(timeout=2),('installer_ready',receipt));self.idle()
            self.assertFalse(self.service.check());send.assert_called_once()
    def test_check_failure_is_reported_and_a_later_check_recovers(self):
        with patch('update_service.find_update',side_effect=ValueError('rede indisponível')):
            self.service.check();self.assertEqual(self.events.get(timeout=2)[0],'update_check_error');self.idle()
        with patch('update_service.find_update',return_value=self.offer):
            self.service.check();self.assertEqual(self.events.get(timeout=2)[0],'update_available');self.idle()
