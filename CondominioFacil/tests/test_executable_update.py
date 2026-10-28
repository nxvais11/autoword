import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from executable_update import prepare_update,launch_update,ASSET,UpdateError

class ExecutableUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.binary=b'MZinstalador sintetico'
        self.sha=hashlib.sha256(self.binary).hexdigest()
        self.release={'tag_name':'v0.9.2','assets':[{'name':ASSET,'id':1,'digest':'sha256:'+self.sha}]}
    def tearDown(self): self.tmp.cleanup()
    def prepare(self):
        with patch('executable_update.latest_release',return_value=self.release),patch('executable_update.fetch',return_value=self.binary):
            return prepare_update(self.root,'nxvais11/autoword','0.9.1')
    def test_download_verified_and_no_documents_or_settings_changed(self):
        marker=self.root/'responsaveis.json';marker.write_text('preservar')
        result=self.prepare()
        self.assertEqual(Path(result['path']).read_bytes(),self.binary)
        self.assertEqual(marker.read_text(),'preservar')
        self.assertFalse(list(self.root.rglob('*.tmp')))
    def test_latest_version_does_not_download(self):
        with patch('executable_update.latest_release',return_value=self.release),patch('executable_update.fetch') as fetch:
            self.assertIsNone(prepare_update(self.root,'nxvais11/autoword','0.9.2'))
            fetch.assert_not_called()
    def test_corrupt_installer_is_not_saved_or_executed(self):
        self.release['assets'][0]['digest']='sha256:'+'0'*64
        with self.assertRaises(UpdateError):self.prepare()
        self.assertFalse(list(self.root.rglob('*.exe')))
    def test_launch_waits_for_current_process_and_quotes_paths_through_environment(self):
        result=self.prepare()
        with patch('executable_update.subprocess.Popen') as popen:
            launch_update(result,self.root,self.root/'Path with spaces'/'AutoWord.exe')
        args,kw=popen.call_args
        self.assertIn('Wait-Process',args[0][-1])
        self.assertNotIn(str(self.root),args[0][-1])
        self.assertEqual(kw['env']['AUTOWORD_UPDATE_SETUP'],result['path'])
    def test_modified_or_external_installer_is_rejected(self):
        result=self.prepare();Path(result['path']).write_bytes(b'alterado')
        with patch('executable_update.subprocess.Popen') as popen:
            with self.assertRaises(UpdateError):launch_update(result,self.root,self.root/'AutoWord.exe')
            result['path']=str(self.root/'fora.exe')
            with self.assertRaises(UpdateError):launch_update(result,self.root,self.root/'AutoWord.exe')
            popen.assert_not_called()
