import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'CondominioFacil'))
sys.path.insert(0,str(PROJECT/'scripts'))
import updater
import launcher
from build_release import build

REPO='nxvais11/autoword'

class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packaged=tempfile.TemporaryDirectory()
        path=Path(cls.packaged.name)/'CondominioFacil.zip'
        build(path,'0.5.1',REPO)
        cls.data=path.read_bytes()
    @classmethod
    def tearDownClass(cls):
        cls.packaged.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()/'app'
        self.root.mkdir()
        (self.root/'version.py').write_text("VERSION = '0.5.0'\n")
        (self.root/'app.py').write_text('codigo anterior')
        (self.root/'cadastro.json').write_text('cadastro intocado')
        (self.root/'APROVAÇÃO.doc').write_bytes(b'documento intocado')
        (self.root/'.venv').mkdir()
        (self.root/'.venv'/'marcador').write_text('ambiente intocado')
    def tearDown(self):
        self.tmp.cleanup()
    def release(self,**extra):
        result={'tag_name':'v0.5.1','assets':[{'name':'CondominioFacil.zip','id':7,
            'digest':'sha256:'+hashlib.sha256(self.data).hexdigest()}]}
        result.update(extra)
        return result
    def repack(self,extra):
        with zipfile.ZipFile(io.BytesIO(self.data)) as old:
            files={name:old.read(name) for name in old.namelist()}
        files.update(extra)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as new:
            for name,data in files.items():
                new.writestr(name,data)
        return out.getvalue()
    def test_package_excludes_documents_examples_tests_and_local_settings(self):
        with zipfile.ZipFile(io.BytesIO(self.data)) as z:
            names=z.namelist()
        self.assertTrue(all('/tests/' not in n and '/Exemplos/' not in n for n in names))
        self.assertTrue(all(not n.endswith(('.doc','.docx','.pdf','.csv','.xlsx')) for n in names))
        self.assertFalse(any(n.endswith(('arquivos.json','responsaveis.json','atualizacao.json')) for n in names))
        self.assertEqual(updater.source_version(updater.package_files(self.data,'v0.5.1',REPO)['version.py'].decode()),'0.5.1')
    def test_install_preserves_documents_settings_and_environment(self):
        with patch('updater.latest_release',return_value=self.release()),patch('updater.download_release',return_value=self.data):
            version,changed=updater.install_latest(self.root,REPO)
        self.assertEqual((version,changed),('0.5.1',True))
        self.assertEqual((self.root/'APROVAÇÃO.doc').read_bytes(),b'documento intocado')
        self.assertEqual((self.root/'cadastro.json').read_text(),'cadastro intocado')
        self.assertEqual((self.root/'.venv'/'marcador').read_text(),'ambiente intocado')
        self.assertFalse(list(self.root.parent.glob('.condominio_update_*')))
    def test_no_download_for_same_or_older_version(self):
        for tag in ('v0.5.0','v0.4.1'):
            with patch('updater.latest_release',return_value=self.release(tag_name=tag)),patch('updater.download_release') as download:
                self.assertEqual(updater.install_latest(self.root,REPO),('0.5.0',False))
                download.assert_not_called()
    def test_integrity_failure_does_not_apply(self):
        with patch('updater.fetch',return_value=b'corrompido'):
            with self.assertRaisesRegex(updater.UpdateError,'integridade'):
                updater.download_release(REPO,self.release())
        self.assertEqual((self.root/'app.py').read_text(),'codigo anterior')
    def test_digest_required_before_download(self):
        release=self.release()
        release['assets'][0]['digest']=None
        with patch('updater.fetch') as fetch:
            with self.assertRaises(updater.UpdateError):
                updater.download_release(REPO,release)
            fetch.assert_not_called()
    def test_documents_settings_and_path_traversal_rejected(self):
        for name in ('CondominioFacil/responsaveis.json','CondominioFacil/APROVAÇÃO.doc',
                     'CondominioFacil/../app.py','fora/app.py','CondominioFacil/con.py'):
            with self.subTest(name=name):
                with self.assertRaises(updater.UpdateError):
                    updater.package_files(self.repack({name:b'nao permitir'}),'0.5.1',REPO)
    def test_repository_and_version_cannot_be_swapped(self):
        with self.assertRaisesRegex(updater.UpdateError,'versão interna'):
            updater.package_files(self.data,'0.5.2',REPO)
        with self.assertRaisesRegex(updater.UpdateError,'repositório'):
            updater.package_files(self.data,'0.5.1','outra/conta')
    def test_dependency_failure_rolls_back_program(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        files=updater.package_files(self.data,'0.5.1',REPO)
        def fail():
            raise OSError('falha simulada')
        with self.assertRaises(OSError):
            updater.apply_package(self.root,files,fail)
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()},before)
        self.assertFalse(list(self.root.parent.glob('.condominio_update_*')))
    def test_partial_file_failure_rolls_back_program(self):
        real_replace=os.replace
        calls=[]
        def replace(source,dest):
            calls.append(1)
            if len(calls)==2:
                raise OSError('falha simulada')
            return real_replace(source,dest)
        files=updater.package_files(self.data,'0.5.1',REPO)
        with patch('updater.os.replace',side_effect=replace):
            with self.assertRaises(OSError):
                updater.apply_package(self.root,files)
        self.assertEqual((self.root/'app.py').read_text(),'codigo anterior')
        self.assertEqual(updater.source_version((self.root/'version.py').read_text()),'0.5.0')
    def test_token_is_not_forwarded_on_redirect(self):
        req=urllib.request.Request('https://api.github.com/repos/a/b/releases/assets/7')
        req.add_unredirected_header('Authorization','Bearer not-a-real-token')
        redirected=updater.GitHubRedirect().redirect_request(req,None,302,'Found',{},'https://release-assets.githubusercontent.com/object')
        self.assertNotIn('Authorization',dict(redirected.header_items()))
        with self.assertRaises(updater.UpdateError):
            updater.GitHubRedirect().redirect_request(req,None,302,'Found',{},'https://evil.example/object')
    def test_asset_uses_expected_repository_not_arbitrary_download_url(self):
        release=self.release()
        release['assets'][0]['browser_download_url']='https://evil.example/pacote.zip'
        with patch('updater.fetch',return_value=self.data) as fetch:
            self.assertEqual(updater.download_release(REPO,release),self.data)
        self.assertEqual(fetch.call_args.args[0],'https://api.github.com/repos/'+REPO+'/releases/assets/7')
    def test_token_is_saved_only_in_windows_credential_manager(self):
        writes=[]
        fake=SimpleNamespace(CRED_TYPE_GENERIC=1,CRED_PERSIST_LOCAL_MACHINE=2,
            CredWrite=lambda data,flags:writes.append(data),
            CredRead=lambda key,kind:{'CredentialBlob':'not-a-real-token'.encode('utf-16-le')})
        with patch.dict(sys.modules,{'win32cred':fake}):
            updater.store_token(REPO,'not-a-real-token')
            self.assertEqual(updater.saved_token(REPO),'not-a-real-token')
        self.assertEqual(writes[0]['TargetName'],'CondominioFacil/GitHub/'+REPO)
        self.assertFalse(any('token' in p.name for p in self.root.iterdir()))
    def test_checks_are_cached_to_avoid_delaying_each_open(self):
        state=Path(self.tmp.name).resolve()/'atualizacao.json'
        with patch('launcher.ROOT',self.root),patch('launcher.DATA',Path(self.tmp.name).resolve()),patch('launcher.STATE',state),\
             patch('launcher.config',return_value={'repository':REPO,'private':True}),\
             patch('launcher.saved_token',return_value='not-a-real-token'),\
             patch('launcher.install_latest',return_value=('0.5.1',True)) as install:
            (self.root/'requirements.txt').write_text('')
            launcher.automatic_update()
            launcher.automatic_update()
            self.assertEqual(install.call_count,1)
        self.assertNotIn('not-a-real-token',state.read_text())

if __name__=='__main__':
    unittest.main()
