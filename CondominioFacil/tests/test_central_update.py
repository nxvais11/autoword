import copy
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from central_service import DEFAULTS,search,selected_plan
from central_update import prepare_closing,run_update
from test_central import pdf
from test_engine import FakeWord,APPROVAL
from engine import FILES

class Session(FakeWord):
    def __enter__(self):return self
    def __exit__(self,*args):pass

class CentralUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.folder=self.root/'Condominios'/'TESTE'/'FECHAMENTO DE LIVRO';self.folder.mkdir(parents=True)
        for k,stem in enumerate(FILES):(self.folder/(stem+'.doc')).write_text(APPROVAL if k==0 else 'AGOSTO/2026',encoding='utf-8')
        (self.folder/'outro.doc').write_bytes(b'untouched')
        pdf(self.root/'Extratos'/'2026'/'11'/'TESTE.pdf','CONDOMINIO TESTE')
        self.settings=copy.deepcopy(DEFAULTS)
        self.settings.update(root=str(self.root/'Condominios'),statements=str(self.root/'Extratos'),main_printer='HP TEST')
        self.result=search(self.settings,'TESTE',11,2026)
        self.state=dict(config={},sheet_groups={},sheet_mapping={},source_models={},generation_cache={},sheet_monitor=None)
        self.cancel=threading.Event();self.printer=Mock(return_value=5)
        self.log=[]
    def tearDown(self):self.tmp.cleanup()
    def run_update(self,**kwargs):
        return run_update(self.result,self.settings,11,2026,self.state,self.cancel,self.log.append,word_factory=Session,printer=self.printer,**kwargs)
    def test_updates_all_words_then_prints_in_book_order_and_correct_month(self):
        rows=selected_plan(self.result,{0,1,2,3,4})
        def send(plan,*args):
            self.assertEqual([r['key'] for r in plan],['closing1','closing0','closing2','closing3','statements:2026-11'])
            for row in plan[:4]:self.assertIn('NOVEMBRO/2026',Path(row['path']).read_text())
            self.assertIn('30 de Novembro de 2026',(self.folder/(FILES[0]+'.doc')).read_text())
            self.assertTrue(all(r['printer']=='HP TEST' for r in plan))
            return len(plan)
        self.printer.side_effect=send
        updated,count=self.run_update(print_rows=rows)
        self.assertEqual(count,5);self.assertEqual(updated['output'],str(self.folder))
        self.assertEqual((self.folder/'outro.doc').read_bytes(),b'untouched')
        self.assertEqual(len(list(self.root.rglob('*.doc'))),5)
    def test_mixed_periods_are_normalized_before_printing(self):
        approval=self.folder/(FILES[0]+'.doc')
        approval.write_text(APPROVAL.replace('Pasta AGOSTO/2026','Pasta JULHO/2025')
                            .replace('31 de Agosto de 2026','30 de Junho de 2025'),encoding='utf-8')
        (self.folder/(FILES[2]+'.doc')).write_text('DEZEMBRO/2027',encoding='utf-8')
        self.result=search(self.settings,'TESTE',11,2026)
        rows=selected_plan(self.result,{0,1,2,3})
        def send(plan,*args):
            from document_period import periods
            for row in plan:
                self.assertEqual(periods(Path(row['path']).read_text()),[('novembro',2026)])
            self.assertIn('30 de Novembro de 2026',approval.read_text())
            return len(plan)
        self.printer.side_effect=send
        _,count=self.run_update(print_rows=rows)
        self.assertEqual(count,4)
        self.printer.assert_called_once()
        self.assertEqual((self.folder/'outro.doc').read_bytes(),b'untouched')

    def test_only_update_needs_no_printer_or_statement_and_preserves_other_files(self):
        self.settings['main_printer']=''
        self.result['rows'][4]['path']=None
        updated,count=self.run_update()
        self.assertEqual(count,0);self.printer.assert_not_called()
        self.assertEqual(len(updated['updated_kinds']),4)
        self.assertFalse(list(self.root.rglob('.temporario_*')))
    def test_optional_preview_does_not_modify_files(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        _,docs,_=prepare_closing(Session(),self.result,self.settings,11,2026,self.state)
        self.assertEqual(len(docs),4)
        self.assertEqual(before,{p:p.read_bytes() for p in before})
    def test_failed_word_never_prints_or_publishes_other_words(self):
        (self.folder/(FILES[3]+'.doc')).write_text('Sem competência')
        before={p:p.read_bytes() for p in self.folder.iterdir()}
        rows=selected_plan(self.result,{0,1,2,3,4})
        with self.assertRaises(ValueError):self.run_update(print_rows=rows)
        self.printer.assert_not_called();self.assertEqual(before,{p:p.read_bytes() for p in before})
    def test_save_failure_never_prints(self):
        class Broken(Session):
            def write_copy(self,*args,**kwargs):raise RuntimeError('cannot save')
        rows=selected_plan(self.result,{0,1,2,3,4})
        with self.assertRaisesRegex(ValueError,'nenhum documento'):
            run_update(self.result,self.settings,11,2026,self.state,self.cancel,self.log.append,
                       print_rows=rows,word_factory=Broken,printer=self.printer)
        self.printer.assert_not_called()
    def test_subfolder_prints_new_results_and_reuses_original_sources_next_time(self):
        self.settings['create_subfolder']=True
        before={p:p.read_bytes() for p in self.folder.iterdir()}
        updated,count=self.run_update(print_rows=selected_plan(self.result,{0,1,2,3,4}))
        plan=self.printer.call_args[0][0]
        self.assertTrue(all(Path(r['path']).parent==self.folder/'2026-11' for r in plan[:4]))
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.result=updated
        second,_=self.run_update()
        self.assertEqual(second['output'],str(self.folder/'2026-11'))
        self.assertFalse((self.folder/'2026-11'/'2026-11').exists())
    def test_cancel_after_update_never_prints(self):
        updated,count=self.run_update(print_rows=selected_plan(self.result,{0,1,2,3}),on_generated=lambda *args:self.cancel.set())
        self.assertEqual(count,0);self.printer.assert_not_called()
    def test_unselected_word_is_not_updated_and_cannot_be_accidentally_printed(self):
        self.settings['update_kinds']=[1]
        before=(self.folder/(FILES[0]+'.doc')).read_bytes()
        with self.assertRaisesRegex(ValueError,'todos os Words'):
            self.run_update(print_rows=selected_plan(self.result,{0,1}))
        self.printer.assert_not_called()
        self.run_update()
        self.assertEqual((self.folder/(FILES[0]+'.doc')).read_bytes(),before)
    def test_report_or_statement_changed_during_update_stops_printing(self):
        rows=selected_plan(self.result,{0,1,2,3,4})
        def change(*args):Path(rows[-1]['path']).write_bytes(b'changed externally')
        with self.assertRaisesRegex(ValueError,'mudou'):
            self.run_update(print_rows=rows,on_generated=change)
        self.printer.assert_not_called()
    def test_uses_same_manual_responsible_rules_and_checks_sheet_readiness(self):
        self.state['config'][str(self.folder)]=[dict(old_name='Pessoa Sindico',new_name='Novo Responsavel',old_unit='12',new_unit='99',since='2026-11',enabled=True)]
        self.run_update()
        self.assertIn('Novo Responsavel',(self.folder/(FILES[0]+'.doc')).read_text())
        self.state['sheet_monitor']=Mock()
        with self.assertRaisesRegex(ValueError,'Nenhuma linha'):self.run_update()
        self.state['sheet_monitor'].require_current.assert_called()
