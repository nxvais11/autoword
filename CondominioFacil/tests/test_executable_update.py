import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from executable_update import prepare_update,launch_update,find_update,download_update,consume_install_error,ASSET,UpdateError

class ExecutableUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()
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

    def test_offer_does_not_download_and_click_downloads_the_exact_offered_asset(self):
        with patch('executable_update.latest_release',return_value=self.release),patch('executable_update.fetch') as fetch:
            offer=find_update('nxvais11/autoword','0.9.1');fetch.assert_not_called()
        with patch('executable_update.latest_release',side_effect=AssertionError('no second release lookup')),patch('executable_update.fetch',return_value=self.binary) as fetch:
            result=download_update(self.root,'nxvais11/autoword',offer)
        self.assertEqual(result['version'],'v0.9.2');self.assertIn('/releases/assets/1',fetch.call_args.args[0])

    def test_download_failure_preserves_the_existing_file_and_installed_data(self):
        result=self.prepare();before=Path(result['path']).read_bytes()
        offer=dict(version='v0.9.3',asset_id=2,sha256=self.sha)
        with patch('executable_update.fetch',side_effect=TimeoutError('network timeout')):
            with self.assertRaises(TimeoutError):download_update(self.root,'nxvais11/autoword',offer)
        self.assertEqual(Path(result['path']).read_bytes(),before)
        self.assertFalse((self.root/'updates'/'AutoWord-v0.9.3.exe').exists())

    def test_install_error_is_shown_once_and_helper_checks_exit_code(self):
        result=self.prepare()
        with patch('executable_update.subprocess.Popen') as popen:launch_update(result,self.root,self.root/'AutoWord.exe')
        script=popen.call_args.args[0][-1]
        self.assertIn('-Wait -PassThru',script);self.assertIn('ExitCode',script)
        self.assertIn('AUTOWORD_UPDATE_ERROR',script)
        self.assertIn("('/DIR=\"'+",script)
        marker=self.root/'updates'/'install-error.txt';marker.write_text('Falha de instalação',encoding='utf-8')
        self.assertEqual(consume_install_error(self.root),'Falha de instalação')
        self.assertEqual(consume_install_error(self.root),'')

    @unittest.skipUnless(sys.platform=='win32','Valida a sintaxe do PowerShell no Windows')
    def test_update_helper_has_valid_powershell_syntax(self):
        import os,subprocess
        result=self.prepare()
        with patch('executable_update.subprocess.Popen') as popen:launch_update(result,self.root,self.root/'AutoWord.exe')
        script=popen.call_args.args[0][-1]
        parser="$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseInput($env:AUTOWORD_TEST_SCRIPT,[ref]$t,[ref]$e)|Out-Null;if($e.Count){$e|Out-String|Write-Output;exit 1}"
        checked=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',parser],env=dict(os.environ,AUTOWORD_TEST_SCRIPT=script),capture_output=True,text=True,timeout=20)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
