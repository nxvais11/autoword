import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from book_history import BookHistory
from central_print import execute_plan
from word_service import digest

class History(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.path=self.root/'app'/'livros.json';self.history=BookHistory(self.path)
        self.doc=self.root/'condo'/'CAPA.doc';self.doc.parent.mkdir();self.doc.write_bytes(b'word')
        self.row=dict(key='closing1',group='closing',path=self.doc,hash=digest(self.doc),label='Capa',printer='HP TEST')
    def tearDown(self):self.tmp.cleanup()
    def test_month_condo_root_isolation_and_restart(self):
        h=self.history
        h.updated(self.root,'ALFA','2026-09',[0,1]);h.print_event(self.root,'ALFA','2026-09','sent',self.row)
        h.complete(self.root,'ALFA','2026-09',True)
        again=BookHistory(self.path)
        self.assertEqual(again.status(again.get(self.root,'ALFA','2026-09')),'Concluído')
        for root,name,period in [(self.root,'ALFA','2026-10'),(self.root,'BETA','2026-09'),(self.root/'other','ALFA','2026-09')]:
            self.assertEqual(again.status(again.get(root,name,period)),'Pendente')
        self.assertEqual(list(self.doc.parent.iterdir()),[self.doc])
    def test_duplicate_hash_tracks_logical_doc_across_destinations_and_uncertain_attempts(self):
        h=self.history;h.print_event(self.root,'ALFA','2026-09','attempt',self.row)
        moved=dict(self.row,path=self.doc.parent/'2026-09'/'CAPA.doc')
        self.assertEqual(h.duplicates(self.root,'ALFA','2026-09',[moved]),[moved])
        self.assertFalse(h.duplicates(self.root,'ALFA','2026-09',[dict(moved,hash='new contents')]))
        self.assertEqual(h.status(h.get(self.root,'ALFA','2026-09')),'Revisar envio')
        h.print_event(self.root,'ALFA','2026-09','sent',self.row)
        self.assertEqual(h.status(h.get(self.root,'ALFA','2026-09')),'Enviado à impressão')
    def test_recents_are_unique_scoped_and_filtered(self):
        h=self.history
        for name in ['ALFA','BETA','ALFA','OLD']:h.touch(self.root,name)
        self.assertEqual(h.ordered_names(self.root,['ALFA','BETA','GAMA']),['ALFA','BETA','GAMA'])
        self.assertEqual(h.ordered_names(self.root/'other',['BETA','ALFA']),['BETA','ALFA'])
    def test_time_requires_user_reference_and_does_not_count_retries_as_extra_books(self):
        h=self.history
        h.updated(self.root,'ALFA','2026-09',[0]);h.finish(self.root,'ALFA','2026-09',30)
        h.finish(self.root,'ALFA','2026-09',45)
        self.assertIsNone(h.totals(self.root,['ALFA'],'2026-09')['saving'])
        h.set_baseline(5);h.complete(self.root,'ALFA','2026-09',True)
        totals=h.totals(self.root,['ALFA'],'2026-09')
        self.assertEqual(totals['saving'],225);self.assertEqual(totals['complete'],1)
        h.complete(self.root,'BETA','2026-09',True)
        totals=h.totals(self.root,['ALFA','BETA'],'2026-09')
        self.assertEqual(totals['complete'],2);self.assertEqual(totals['saving_count'],1)
        for value in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):h.set_baseline(value)
    def test_completion_is_manual_and_new_updates_reopen_it(self):
        h=self.history;h.updated(self.root,'ALFA','2026-09',[0])
        self.assertEqual(h.status(h.get(self.root,'ALFA','2026-09')),'Atualizado')
        h.complete(self.root,'ALFA','2026-09',True);h.updated(self.root,'ALFA','2026-09',[1])
        self.assertEqual(h.status(h.get(self.root,'ALFA','2026-09')),'Atualizado')
    def test_invalid_storage_is_preserved(self):
        self.path.parent.mkdir(exist_ok=True);self.path.write_text('{broken')
        with self.assertRaises(ValueError):BookHistory(self.path)
        self.assertEqual(self.path.read_text(),'{broken')
    def test_partial_print_records_success_and_uncertain_file_before_failure(self):
        second=self.doc.with_name('ANEXO.doc');second.write_bytes(b'annex')
        rows=[self.row,dict(self.row,key='closing2',path=second,hash=digest(second),label='Anexo')]
        word=Mock();factory=Mock();factory.return_value.__enter__=Mock(return_value=word);factory.return_value.__exit__=Mock(return_value=False)
        def event(kind,row):self.history.print_event(self.root,'ALFA','2026-09',kind,row)
        with patch.dict(sys.modules,{'win32print':Mock()}),patch('central_print.print_receipt',side_effect=[1,RuntimeError('printer error')]):
            with self.assertRaisesRegex(RuntimeError,'printer error'):
                execute_plan(rows,threading.Event(),lambda text:None,factory,on_event=event)
        book=BookHistory(self.path).get(self.root,'ALFA','2026-09')
        self.assertEqual(sorted(r['state'] for r in book['sent'].values()),['attempt','sent'])
        self.assertEqual(self.history.status(book),'Revisar envio')
