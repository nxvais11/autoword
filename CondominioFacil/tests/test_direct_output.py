import base64
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
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
        self.root = Path(self.tmp.name).resolve()
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
    def test_original_without_date_or_other_changes_is_not_rewritten(self):
        original='Documento sem data. Artigo 1350. Data: ___/___/___'
        self.source.write_text(original,encoding='utf-8')
        before=self.source.read_bytes()
        docs=inspect_condo(self.word,self.condos[0],11,2026,[],(1,),check_resignations=False)
        self.assertEqual(docs[0]['changes'],[])
        self.assertTrue(docs[0]['notices'])
        log=[]
        generate(self.word,self.condos,{str(self.folder):docs},self.root,11,2026,log.append,threading.Event(),
                 targets=output_targets(self.condos,11,2026),overwrite_sources=True)
        self.assertEqual(self.word.writes,0);self.assertEqual(self.source.read_bytes(),before)
        self.assertTrue(any('nenhuma data' in line for line in log))

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
    def test_separate_runs_keep_same_named_documents_in_distinct_destinations(self):
        other=self.root/'B'
        other.mkdir()
        (other/self.source.name).write_text('AGOSTO/2026 — B',encoding='utf-8')
        destination=self.root/'saida'
        for folder in (self.folder,other):
            condos=discover(folder)
            docs=inspect_condo(self.word,condos[0],11,2026,[],(1,),check_resignations=False)
            targets=output_targets(condos,11,2026,destination)
            generate(self.word,condos,{str(folder):docs},self.root,11,2026,lambda text:None,
                     threading.Event(),targets=targets)
        first=destination/'A'/'2026-11'/self.source.name
        second=destination/'B'/'2026-11'/self.source.name
        self.assertIn('NOVEMBRO/2026',first.read_text(encoding='utf-8'))
        self.assertEqual(second.read_text(encoding='utf-8'),'NOVEMBRO/2026 — B')

    def test_second_replace_failure_rolls_back_or_retains_recovery(self):
        annex=self.folder/(FILES[2]+'.doc')
        originals={p:p.read_bytes() for p in (self.source,annex)}
        real_replace=os.replace
        for restore_blocked in (False,True):
            with self.subTest(restore_blocked=restore_blocked):
                calls=[]
                def replace(source,destination):
                    calls.append(destination)
                    if destination==annex or (restore_blocked and len(calls)==3):
                        raise PermissionError('arquivo em uso')
                    return real_replace(source,destination)
                docs=inspect_condo(self.word,self.condos[0],11,2026,[],(1,2),check_resignations=False)
                messages=[]
                with patch('word_service.os.replace',side_effect=replace):
                    generate(self.word,self.condos,{str(self.folder):docs},self.root,11,2026,messages.append,
                             threading.Event(),targets=output_targets(self.condos,11,2026),
                             overwrite_sources=True,cache=self.cache,models=self.models)
                self.assertEqual(annex.read_bytes(),originals[annex])
                self.assertEqual(self.cache,{})
                self.assertEqual(self.models,{})
                if restore_blocked:
                    self.assertIn('1 documento(s) gravado(s)',messages[-1])
                    recovery=next(self.root.rglob('recuperacao'))
                    self.assertEqual((recovery/self.source.name).read_bytes(),originals[self.source])
                    self.assertTrue((recovery/'restaurar.json').is_file())
                    self.assertIn(str(recovery),messages[0])
                else:
                    self.assertIn('Publicação revertida',messages[0])
                    self.assertEqual(self.source.read_bytes(),originals[self.source])
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

