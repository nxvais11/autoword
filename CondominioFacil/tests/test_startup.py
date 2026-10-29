import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from book_history import BookHistory,file_id

class Startup(unittest.TestCase):
    def test_loading_the_interface_does_not_import_pdf_engine(self):
        folder=str(Path(__file__).resolve().parents[1])
        code="import sys;sys.path.insert(0,sys.argv[1]);import central_ui;assert not {'pypdf','pdfplumber','pdfminer'} & sys.modules.keys()"
        result=subprocess.run([sys.executable,'-c',code,folder],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_file_identity_with_key_never_resolves_a_network_path(self):
        with patch('book_history.Path.resolve',side_effect=AssertionError('network access')):
            self.assertEqual(file_id(dict(key='closing0',path='Z:/NETWORK/file.doc',hash='abc')),'closing0|abc')
    def test_root_readiness_check_does_not_wait_for_network_worker(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            history=BookHistory(Path(folder)/'livros.json')
            started=threading.Event();finish=threading.Event()
            def work():
                with history.lock:
                    started.set();finish.wait(3)
            thread=threading.Thread(target=work);thread.start()
            try:
                self.assertTrue(started.wait(1))
                with patch('book_history.Path.resolve',side_effect=AssertionError('network access')):
                    self.assertFalse(history.root_ready('Z:/NETWORK'))
            finally:finish.set();thread.join(3)
