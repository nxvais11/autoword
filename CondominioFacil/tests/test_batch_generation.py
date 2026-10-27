import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import FILES
from word_service import Word, discover, inspect_condo, generate, output_targets
from test_engine import APPROVAL, FakeWord

def make_docs(folder):
    folder.mkdir(parents=True)
    for i,name in enumerate(FILES):
        (folder/(name+'.doc')).write_text(APPROVAL if i==0 else 'AGOSTO/2026',encoding='utf-8')

class BatchGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
    def tearDown(self):
        self.tmp.cleanup()
    def test_discovers_nested_condominiums_and_ignores_month_archives(self):
        for name in ('ALLURE','AMMAR HILAL'):
            folder = self.root/name/'FECHAMENTO DE LIVROS'
            make_docs(folder)
            make_docs(folder/'2026-10')
        condos = discover(self.root)
        self.assertEqual([c['name'] for c in condos],['ALLURE','AMMAR HILAL'])
        self.assertTrue(all(not c['errors'] for c in condos))
        self.assertTrue(all(Path(c['folder']).name=='FECHAMENTO DE LIVROS' for c in condos))
        single = discover(self.root/'ALLURE')
        self.assertEqual(single[0]['name'],'ALLURE')
        self.assertEqual(len(single),1)
    def test_ambiguous_closing_folders_are_blocked(self):
        make_docs(self.root/'A'/'FECHAMENTO DE LIVRO')
        make_docs(self.root/'A'/'FECHAMENTO DE LIVROS')
        condo = discover(self.root)[0]
        self.assertTrue(condo['errors'])
        self.assertTrue(all(p is None for p in condo['files']))
    def test_saved_manual_names_keep_condominium_identity(self):
        folder = self.root/'ALLURE'/'FECHAMENTO DE LIVROS'
        make_docs(folder)
        paths = []
        for i,p in enumerate(sorted(folder.iterdir())):
            renamed = p.with_name(f'documento{i}.doc')
            p.rename(renamed)
            paths.append(str(renamed))
        condos = discover(self.root,{str(folder):paths})
        self.assertEqual(condos[0]['name'],'ALLURE')
        self.assertFalse(condos[0]['errors'])
    def test_70_condominiums_without_prior_preview_and_failure_isolated(self):
        for i in range(70):
            make_docs(self.root/f'Condominio {i:02}'/'FECHAMENTO DE LIVROS')
        broken = self.root/'Condominio 17'/'FECHAMENTO DE LIVROS'/(FILES[1]+'.doc')
        broken.write_text('Campo de competência inválido',encoding='utf-8')
        condos = discover(self.root)
        self.assertEqual(len(condos),70)
        word = FakeWord()
        prepared,messages,finished = [],[],[]
        def prepare(service,condo):
            prepared.append(condo['name'])
            return inspect_condo(service,condo,11,2026,[])
        generate(word,condos,{},self.root,11,2026,messages.append,threading.Event(),
            targets=output_targets(condos,11,2026),overwrite_sources=True,prepare=prepare,
            on_generated=lambda c,t,d:finished.append(c['name']))
        self.assertEqual(len(prepared),70)
        self.assertEqual(len(finished),69)
        self.assertNotIn('Condominio 17',finished)
        self.assertTrue(any('69/70' in m and '276 documento' in m for m in messages))
        self.assertTrue(any('Condominio 17: REVISAR' in m for m in messages))
        self.assertEqual(broken.read_text(),'Campo de competência inválido')
        self.assertIn('NOVEMBRO/2026',(self.root/'Condominio 69'/'FECHAMENTO DE LIVROS'/(FILES[1]+'.doc')).read_text())
        self.assertFalse(list(self.root.rglob('.temporario_*')))
        self.assertFalse(list(self.root.rglob('relatorio.*')))
    def test_preview_is_reused_when_available(self):
        make_docs(self.root/'A')
        condos = discover(self.root)
        docs = inspect_condo(FakeWord(),condos[0],11,2026,[])
        def unexpected(*args):
            self.fail('A prévia válida não precisa ser refeita.')
        generate(FakeWord(),condos,{condos[0]['folder']:docs},self.root,11,2026,lambda s:None,
                 threading.Event(),targets=output_targets(condos,11,2026),overwrite_sources=True,prepare=unexpected)
    def test_preview_accepts_equivalent_directory_spelling(self):
        make_docs(self.root/'A')
        condos=discover(self.root)
        docs=inspect_condo(FakeWord(),condos[0],11,2026,[])
        alias=str(self.root/'A'/'..'/'A')
        finished=[]
        generate(FakeWord(),condos,{alias:docs},self.root,11,2026,lambda s:None,threading.Event(),
                 targets=output_targets(condos,11,2026),overwrite_sources=True,
                 on_generated=lambda c,t,d:finished.append(c['name']))
        self.assertEqual(finished,['A'])
    def test_ui_generation_does_not_require_verify_button(self):
        from app import App
        make_docs(self.root/'A')
        make_docs(self.root/'B')
        condos = discover(self.root)
        value = lambda x:SimpleNamespace(get=lambda:x)
        jobs = []
        fake = SimpleNamespace(selected=lambda:condos,period=lambda:(11,2026),folder=value(str(self.root)),
            destination=value(''),create_subfolder=value(False),chosen_kinds=lambda:(0,1,2,3),preview={},
            sheet_monitor=None,sheet_polling=False,sheet_error=None,config={},sheet_groups={},sheet_mapping={},
            source_models={},generation_cache={},events=queue.Queue(),cancel=threading.Event(),
            record_job=lambda *args:jobs.append(args),start=lambda task:task())
        class SessionWord(FakeWord):
            sessions = 0
            def __enter__(self):
                type(self).sessions+=1
                return self
            def __exit__(self,*args): pass
        with patch('app.Word',SessionWord),patch('app.messagebox.showinfo') as info:
            App.run_generation(fake)
        info.assert_not_called()
        self.assertEqual(SessionWord.sessions,1)
        self.assertEqual(len(jobs),2)
        self.assertTrue(all('NOVEMBRO/2026' in c['files'][1].read_text() for c in condos))

class WordLocalSaving(unittest.TestCase):
    def test_local_processing_does_not_reopen_saved_document(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source,dest = root/'origem.doc',root/'saida.doc'
            source.write_text('AGOSTO/2026')
            paths = []
            class Document:
                Content = SimpleNamespace(Text='AGOSTO/2026')
                Saved = True
                def Save(self):
                    self.path.write_text(self.Content.Text)
                def Close(self,*args): pass
            def open_doc(path,*args):
                paths.append(Path(path))
                doc = Document()
                doc.path = Path(path)
                return doc
            service = Word()
            service.open = open_doc
            service.read = lambda *args:self.fail('Não deve reabrir o documento já confirmado pelo Word.')
            service.write_copy(source,dest,'AGOSTO/2026',[])
            self.assertEqual(dest.read_text(),'AGOSTO/2026')
            self.assertEqual(len(paths),1)
            self.assertNotEqual(paths[0].parent,root)
            self.assertFalse(paths[0].exists())
    def test_failed_save_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source,dest = root/'origem.doc',root/'saida.doc'
            source.write_text('AGOSTO/2026')
            dest.write_text('Existente')
            class Document:
                Content = SimpleNamespace(Text='AGOSTO/2026')
                Saved = False
                def Save(self): pass
                def Close(self,*args): pass
            service = Word()
            service.open = lambda *args:Document()
            with self.assertRaisesRegex(ValueError,'confirmou'):
                service.write_copy(source,dest,'AGOSTO/2026',[])
            self.assertEqual(dest.read_text(),'Existente')

if __name__=='__main__':
    unittest.main()
