import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from console_messages import search_message,operation_message,preview_message
from engine import Change


class ConsoleMessages(unittest.TestCase):
    def fixture(self):
        return dict(name='ALFA',period='2026-09',document_periods=[dict(label='Capa',periods=[('agosto',2026)],issue='')],
                    rows=[dict(group='closing',key='closing1',path=Path('CAPA.doc'),label='Capa',printer='HP'),
                          dict(group='obligations',path=None,label='Relatório de obrigações',printer='EPSON')],
                    warnings=['PDF pessoal: 0 candidatos. Vincule o correto.','Word do Jurídico: 0 candidatos. Vincule o correto.'])

    def test_optional_missing_reports_do_not_crowd_summary_but_remain_in_details(self):
        result=self.fixture();value=search_message(result,{0})
        self.assertIn('1/1 documentos localizados',value['summary'])
        self.assertNotIn('candidatos',value['summary'])
        self.assertIn('PDF pessoal: 0 candidatos',value['details'])
        self.assertIn('Word do Jurídico: 0 candidatos',value['details'])
        value=search_message(result,{0,1})
        self.assertIn('Vincule os arquivos ausentes',value['summary'])
        self.assertIn('Relatório de obrigações',value['summary'])

    def test_overdue_obligations_and_unknown_warnings_are_preserved_without_flooding(self):
        result=self.fixture();result['due_obligations']=[f'SERVIÇO {i}: 08/2026' for i in range(12)]
        result['due_notice']='Confira todos:\n'+'\n'.join(result['due_obligations'])
        result['warnings']+=[result['due_notice'],'Extrato ambíguo: confira os nomes em Opções.']
        value=search_message(result,{0})
        self.assertIn('12 até esta competência',value['summary'])
        self.assertNotIn('SERVIÇO 11',value['summary'])
        self.assertIn('SERVIÇO 11',value['details'])
        self.assertIn('Extrato ambíguo',value['summary'])
        self.assertEqual(value,search_message(result,{0}))

    def test_partial_send_never_says_completed_or_repeats_success_instructions(self):
        row=dict(key='closing1',hash='abc',label='Capa')
        second=dict(key='closing2',hash='def',label='Anexo I')
        tracking=dict(name='ALFA',period='2026-09',sent=[row],planned=[row,second],words=2)
        value=operation_message(tracking,5,'Impressora indisponível.\nDetalhe técnico: fila 123','')
        self.assertIn('Operação não concluída',value['summary'])
        self.assertIn('Envios confirmados: 1/2',value['summary'])
        self.assertIn('Sem envio confirmado: Anexo I',value['summary'])
        self.assertNotIn('fila 123',value['summary'])
        self.assertIn('fila 123',value['details'])

    def test_preview_groups_repeated_changes_without_discarding_names_or_dates(self):
        change=Change(0,1,'AGOSTO/2026','SETEMBRO/2026','Competência')
        responsible=Change(1,2,'Nome anterior','Nome novo','Responsável')
        value=preview_message('ALFA',9,2026,Path('destino'),[dict(path=Path('APROVAÇÃO.doc'),changes=[change]*4+[responsible])])
        self.assertEqual(value['summary'].count('Competência'),1)
        self.assertNotIn('AGOSTO/2026',value['summary'])
        self.assertIn('AGOSTO/2026 → SETEMBRO/2026',value['details'])
        self.assertIn('Nome anterior → Nome novo',value['details'])
