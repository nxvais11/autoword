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

    def test_two_live_views_cannot_overwrite_each_others_books(self):
        other=BookHistory(self.path)
        self.history.updated(self.root,'ALFA','2026-09',[0])
        other.complete(self.root,'BETA','2026-09',True)
        self.history.finish(self.root,'ALFA','2026-09',12)
        fresh=BookHistory(self.path)
        self.assertTrue(fresh.get(self.root,'BETA','2026-09')['complete'])
        self.assertEqual(other.get(self.root,'ALFA','2026-09')['seconds'],12)

    def test_network_resolution_change_keeps_the_saved_root_identity(self):
        with patch('book_history.Path.resolve',return_value=Path('/server/share')):
            self.history.prepare_root('Z:/Condos')
            self.history.complete('Z:/Condos','ALFA','2026-09',True)
        again=BookHistory(self.path)
        with patch('book_history.Path.resolve',side_effect=AssertionError('network unavailable')):
            again.prepare_root('Z:/Condos')
            self.assertTrue(again.get('Z:/Condos','ALFA','2026-09')['complete'])

    def test_missing_or_corrupt_primary_recovers_backup_and_preserves_bad_file(self):
        h=self.history;h.complete(self.root,'ALFA','2026-09',True)
        h.touch(self.root,'ALFA')  # Backup contém o livro concluído.
        self.assertTrue(h.backup.exists())
        self.path.unlink()
        restored=BookHistory(self.path)
        self.assertTrue(restored.get(self.root,'ALFA','2026-09')['complete'])
        self.assertTrue(restored.recovery_notice)
        self.path.write_text('{broken',encoding='utf-8')
        restored=BookHistory(self.path)
        self.assertTrue(restored.get(self.root,'ALFA','2026-09')['complete'])
        self.assertEqual(next(self.path.parent.glob('livros.corrompido-*.json')).read_text(),'{broken')

    def test_failed_replace_does_not_erase_disk_history_or_poison_next_save(self):
        h=self.history;h.complete(self.root,'ALFA','2026-09',True)
        before=self.path.read_bytes()
        with patch('book_history.os.replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):h.complete(self.root,'BETA','2026-09',True)
        self.assertEqual(self.path.read_bytes(),before)
        h.touch(self.root,'ALFA')
        self.assertFalse(h.get(self.root,'BETA','2026-09'))
        self.assertTrue(h.get(self.root,'ALFA','2026-09')['complete'])

    def test_explicit_restore_rebinds_only_chosen_month_and_merges_existing_work(self):
        h=self.history;old=self.root/'old';new=self.root/'new'
        h.updated(old,'ALFA','2026-09',[0]);h.print_event(old,'ALFA','2026-09','sent',self.row)
        h.complete(old,'ALFA','2026-09',True)
        h.complete(old,'BETA','2026-09',True);h.complete(old,'ALFA','2026-10',True)
        h.updated(new,'ALFA','2026-09',[1])
        option=next(o for o in h.recovery_options('2026-09') if o['path']==str(self.path) and o['root']==str(old.resolve()).casefold())
        before=self.doc.read_bytes()
        self.assertEqual(h.restore_month(option,new,'2026-09',['ALFA']),1)
        book=h.get(new,'ALFA','2026-09')
        self.assertEqual(book['updated'],[0,1]);self.assertTrue(book['complete']);self.assertEqual(len(book['sent']),1)
        self.assertFalse(h.get(new,'BETA','2026-09'));self.assertFalse(h.get(new,'ALFA','2026-10'))
        self.assertTrue(h.get(old,'ALFA','2026-09')['complete'])
        self.assertEqual(before,self.doc.read_bytes())
        self.assertEqual(h.restore_month(option,new,'2026-09',['ALFA']),1)
        self.assertEqual(len(h.get(new,'ALFA','2026-09')['sent']),1)

    def test_restore_from_backup_does_not_discard_new_current_records(self):
        h=self.history;h.complete(self.root,'ALFA','2026-09',True)
        h.complete(self.root,'BETA','2026-09',True)
        option=next(o for o in h.recovery_options('2026-09') if o['path']==str(h.backup))
        h.restore_month(option,self.root,'2026-09',['ALFA','BETA'])
        self.assertTrue(h.get(self.root,'ALFA','2026-09')['complete'])
        self.assertTrue(h.get(self.root,'BETA','2026-09')['complete'])
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
