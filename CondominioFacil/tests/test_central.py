import copy
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pypdf import PdfWriter
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
from central_service import DEFAULTS,owner,search,selected_plan,verify_plan,compare_texts,compare_reports,digest
from central_print import print_pdf,execute_plan
from engine import FILES


def pdf(path,text='Document for testing only'):
    writer=PdfWriter();page=writer.add_blank_page(width=595,height=842)
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})})})
    stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 20 800 Td ('+text+') Tj ET').encode('ascii'))
    page[NameObject('/Contents')]=stream
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as output:writer.write(output)


class Central(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.cfg=copy.deepcopy(DEFAULTS)
        self.cfg.update(root=str(self.root/'Condos'),statements=str(self.root/'Extratos'),reports=str(self.root/'Pessoais'),main_printer='HP TEST',report_printer='EPSON TEST')
        for name in ('ALFA','ALFA JARDIM'):
            home=Path(self.cfg['root'])/name
            closing=home/'FECHAMENTO DE LIVRO';closing.mkdir(parents=True)
            for stem in FILES:(closing/(stem+'.doc')).write_text('Documento de fechamento')
            legal=home/'JURIDICO';legal.mkdir();(legal/'relatorio de obrigacoes.docx').write_text('Word atual')
            pdf(Path(self.cfg['reports'])/('RELATORIO DE OBRIGACOES '+name+'.pdf'))
        self.month=Path(self.cfg['statements'])/'2026'/'09';self.month.mkdir(parents=True)
        for name in ('ALFA.pdf','ALFA poup.pdf','ALFA JARDIM.pdf'):pdf(self.month/name)
    def tearDown(self):self.tmp.cleanup()
    def lookup(self):return search(self.cfg,'ALFA',9,2026)
    def test_compound_names_and_token_boundaries(self):
        names=['ALFA','ALFA JARDIM']
        self.assertEqual(owner('extrato ALFA JARDIM poup',names),'ALFA JARDIM')
        self.assertEqual(owner('CONDOMINIO DO EDIFICIO ALFA',names),'ALFA')
        self.assertIsNone(owner('ALFABETICO',names))
        self.assertIsNone(owner('ALFA E BETA',['ALFA','BETA']))
    def test_only_selected_month_and_condo_including_all_account_types(self):
        pdf(Path(self.cfg['statements'])/'2026'/'08'/'ALFA.pdf')
        result=self.lookup();statements=[r for r in result['rows'] if r['group']=='statement']
        self.assertEqual([r['path'].name for r in statements],['ALFA.pdf','ALFA poup.pdf'])
        self.assertTrue(all(r['checked'] for r in statements))
        self.assertFalse(result['rows'][-1]['checked'])
        self.assertEqual([r['label'] for r in result['rows'][:4]],['Capa do livro','Aprovação de contas','Anexo I','Anexo II'])
    def test_generic_statement_identified_by_header(self):
        pdf(self.month/'Extrato Mensal_Setembro2026.pdf','CONDOMINIO DO EDIFICIO ALFA JARDIM')
        result=self.lookup()
        self.assertFalse(any(r['path'] and r['path'].name.startswith('Extrato Mensal') for r in result['rows']))
        pdf(self.month/'Extrato Mensal_Setembro2026.pdf','CONDOMINIO DO EDIFICIO ALFA')
        self.assertTrue(any(r['path'] and r['path'].name.startswith('Extrato Mensal') for r in self.lookup()['rows']))
    def test_reports_have_no_competence_and_ambiguous_legal_requires_binding(self):
        first=self.lookup();next_month=search(self.cfg,'ALFA',10,2026)
        self.assertEqual(first['word'],next_month['word'])
        legal=Path(self.cfg['root'])/'ALFA'/'JURIDICO'
        extra=legal/'relatorio de obrigacoes V2.docx';extra.write_text('Outra versão')
        self.assertIsNone(self.lookup()['word'])
        self.cfg['overrides']={'ALFA':{'report_word':str(extra)}}
        self.assertEqual(self.lookup()['word'],extra)
    def test_manual_statement_bindings_do_not_leak_to_other_months(self):
        chosen=self.month/'manual.pdf';pdf(chosen)
        self.cfg['overrides']={'ALFA':{'statements:2026-09':[str(chosen)]}}
        self.assertEqual([r['path'] for r in self.lookup()['rows'] if r['group']=='statement'],[chosen])
        self.assertIsNone(next(r['path'] for r in search(self.cfg,'ALFA',10,2026)['rows'] if r['group']=='statement'))
    def test_optional_obligations_and_printer_routing_with_exact_order(self):
        result=self.lookup();selected={i for i,r in enumerate(result['rows']) if r['checked']}
        rows=selected_plan(result,selected)
        self.assertTrue(all(row['printer']=='HP TEST' for row in rows))
        selected.add(len(result['rows'])-1)
        with self.assertRaisesRegex(ValueError,'Compare'):selected_plan(result,selected)
        with self.assertRaises(ValueError):selected_plan(result,selected,'',{'hashes':{}})
        comparison={'hashes':{str(result['word']):digest(result['word'])}}
        rows=selected_plan(result,selected,'word',comparison)
        self.assertEqual(rows[-1]['printer'],'EPSON TEST');self.assertEqual(rows[-1]['path'],result['word'])
        result['word'].write_text('modificado')
        with self.assertRaisesRegex(ValueError,'mud'):verify_plan(rows)
    def test_missing_unselected_item_does_not_block_other_groups(self):
        result=self.lookup();result['rows'][0]['path']=None
        rows=selected_plan(result,{4})
        self.assertEqual(len(rows),1)
        with self.assertRaises(ValueError):selected_plan(result,{0,4})
    def test_whitespace_is_ignored_but_swapped_values_and_dates_are_detected(self):
        self.assertTrue(compare_texts('SEGURO 30/09/2026 OK','seguro\n30/09/2026   ok')['equal'])
        self.assertFalse(compare_texts('ITEM A 12 ITEM B 31','ITEM A 31 ITEM B 12')['equal'])
        self.assertFalse(compare_texts('VENCIMENTO 01/09/2026','VENCIMENTO 01/10/2026')['equal'])
    def test_comparison_exports_read_only_and_detects_changed_original(self):
        result=self.lookup();personal=result['rows'][-1]['path'];word=result['word']
        before=personal.read_bytes(),word.read_bytes()
        def export(service,source,target):target.write_bytes(personal.read_bytes())
        with tempfile.TemporaryDirectory() as folder,patch('central_service.export_word',side_effect=export):
            comparison=compare_reports(Mock(),personal,word,folder)
        self.assertTrue(comparison['equal']);self.assertEqual(before,(personal.read_bytes(),word.read_bytes()))
    def test_pdf_gdi_sends_one_copy_simplex_without_changing_defaults(self):
        mode=SimpleNamespace(Fields=0,Duplex=2,Copies=5,Orientation=1)
        wp=Mock();wp.GetPrinter.return_value={'pDevMode':mode};wp.DocumentProperties.return_value=1
        wp.GetDeviceCaps.return_value=1000
        gui=Mock();gui.CreateDC.return_value=123
        const=SimpleNamespace(DM_DUPLEX=1,DM_COPIES=2,DM_ORIENTATION=4,DM_IN_BUFFER=8,DM_OUT_BUFFER=16,HORZRES=20,VERTRES=21)
        path=self.month/'ALFA.pdf'
        with patch.dict(sys.modules,{'win32print':wp,'win32gui':gui,'win32con':const}),patch('PIL.ImageWin.Dib') as dib:
            self.assertTrue(print_pdf(path,'HP TEST',threading.Event()))
            dib.return_value.draw.assert_called_once()
        self.assertEqual(mode.Duplex,1);self.assertEqual(mode.Copies,1)
        wp.SetPrinter.assert_not_called();wp.StartDoc.assert_called_once();wp.EndDoc.assert_called_once();gui.DeleteDC.assert_called_once_with(123)
    def test_sequence_cancel_and_no_changes_or_temporary_folders_left(self):
        result=self.lookup();rows=selected_plan(result,{4,5});cancel=threading.Event();sent=[]
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        wp=Mock();factory=Mock();factory.return_value.__enter__=Mock(return_value=Mock());factory.return_value.__exit__=Mock()
        def sender(path,printer,stop,log):sent.append((path.name,printer));cancel.set();return True
        with patch.dict(sys.modules,{'win32print':wp}):
            count=execute_plan(rows,cancel,lambda text:None,factory,sender)
        self.assertEqual(count,1);self.assertEqual(len(sent),1)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

if __name__=='__main__':unittest.main()
