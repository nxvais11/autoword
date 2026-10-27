import base64
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import FILES
from word_service import discover, inspect_condo, generate, output_targets
from test_engine import FakeWord, APPROVAL

class CountingWord(FakeWord):
    def __init__(self):
        self.writes = 0
    def write_copy(self,*args,**kwargs):
        self.writes += 1
        return super().write_copy(*args,**kwargs)

class DirectOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root/'A'
        self.folder.mkdir()
        for i,name in enumerate(FILES):
            text = APPROVAL if i==0 else 'AGOSTO/2026'
            if i==1:
                text += ' {{Nome}} CPF {{CPF}}'
            (self.folder/(name+'.doc')).write_text(text,encoding='utf-8')
        self.condos = discover(self.folder)
        self.mapping = {'name':'','role':''}
        self.models, self.cache = {},{}
        self.word = CountingWord()
        self.source = self.folder/(FILES[1]+'.doc')
    def tearDown(self):
        self.tmp.cleanup()
    def update(self,month=11,rows=None,allow=True,automatic=False,word=None):
        rows = rows or [{'Nome':'Maria','CPF':'001'}]
        docs = inspect_condo(self.word,self.condos[0],month,2026,[],(1,),rows,self.mapping,models=self.models)
        messages = []
        generate(word or self.word,self.condos,{str(self.folder):docs},self.root,month,2026,
                 messages.append,threading.Event(),targets=output_targets(self.condos,month,2026),
                 overwrite_sources=allow,models=self.models,cache=self.cache,automatic=automatic)
        return messages
    def test_direct_overwrite_without_any_extra_file_or_folder(self):
        unrelated = self.folder/'contrato.txt'
        unrelated.write_bytes(b'intacto')
        before = {p.name:p.read_bytes() for p in self.folder.iterdir()}
        self.update()
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()),sorted(before))
        self.assertFalse(any(p.is_dir() for p in self.folder.iterdir()))
        self.assertEqual(self.source.read_text(),'NOVEMBRO/2026 Maria CPF 001')
        for p in self.folder.iterdir():
            if p != self.source:
                self.assertEqual(p.read_bytes(),before[p.name])
    def test_direct_overwrite_requires_explicit_authorization(self):
        original = self.source.read_bytes()
        messages = self.update(allow=False)
        self.assertEqual(self.source.read_bytes(),original)
        self.assertTrue(any('REVISAR' in m for m in messages))
    def test_subfolder_optional_and_preserves_source(self):
        original = self.source.read_bytes()
        docs = inspect_condo(self.word,self.condos[0],11,2026,[],(1,),[{'Nome':'Maria','CPF':'001'}],self.mapping)
        targets = output_targets(self.condos,11,2026,create_subfolder=True)
        generate(self.word,self.condos,{str(self.folder):docs},self.root,11,2026,lambda s:None,threading.Event(),targets=targets)
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual((self.folder/'2026-11'/self.source.name).read_text(),'NOVEMBRO/2026 Maria CPF 001')
        self.assertEqual([p.name for p in self.folder.iterdir() if p.is_dir()],['2026-11'])
    def test_overwrite_retains_model_for_new_month_and_new_responsible_after_restart(self):
        original = self.source.read_bytes()
        self.update()
        self.models = json.loads(json.dumps(self.models))
        self.cache = json.loads(json.dumps(self.cache))
        self.assertEqual(base64.b64decode(self.models[str(self.source)]['data']),original)
        self.update(month=12,rows=[{'Nome':'João','CPF':'002'}],automatic=True)
        self.assertEqual(self.source.read_text(),'DEZEMBRO/2026 João CPF 002')
        self.assertEqual(self.word.writes,2)
    def test_unchanged_direct_update_does_not_rewrite(self):
        self.update()
        modified = self.source.stat().st_mtime_ns
        self.update(automatic=True)
        self.assertEqual(self.word.writes,1)
        self.assertEqual(self.source.stat().st_mtime_ns,modified)
    def test_failed_overwrite_preserves_document_and_leaves_no_template_or_temp(self):
        class BrokenWord(FakeWord):
            def write_copy(self,*args,**kwargs):
                raise OSError('Falha')
        original = self.source.read_bytes()
        self.update(word=BrokenWord())
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual(self.models,{})
        self.assertFalse(list(self.root.rglob('.temporario_*')))
    def test_manual_edit_invalidates_saved_model(self):
        self.update()
        self.source.write_text('NOVEMBRO/2026 Texto editado no Word',encoding='utf-8')
        docs = inspect_condo(self.word,self.condos[0],12,2026,[],(1,),models=self.models)
        self.assertEqual(docs[0]['text'],'NOVEMBRO/2026 Texto editado no Word')
        self.assertIsNone(docs[0]['template'])
    def test_batch_defaults_to_each_condominium_folder(self):
        condos = self.condos+[{'folder':str(self.root/'B'),'name':'B'}]
        targets = output_targets(condos,11,2026)
        self.assertEqual(targets[str(self.folder)],self.folder)
        self.assertEqual(targets[str(self.root/'B')],self.root/'B')
        selected = output_targets(condos,11,2026,self.root/'Saida',True)
        self.assertEqual(selected[str(self.folder)],self.root/'Saida'/'A'/'2026-11')

if __name__=='__main__':
    unittest.main()
