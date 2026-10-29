import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from obligations import due_rows,check_obligations,analyze_rows,report_term

HEADERS=['SERVIÇOS','REALIZAÇÃO','PRAZO','PRÓXIMA REALIZAÇÃO']

def tables(*rows):return [[HEADERS,*rows]]

class Obligations(unittest.TestCase):
    def test_only_months_strictly_before_competence_are_pending(self):
        data=tables(['ATUAL','30/09/2025','ANUAL','30/09/2026'],
                    ['ANTERIOR','08/2025','ANUAL','08/2026'],
                    ['ANO ANTERIOR','31/12/2024','ANUAL','31/12/2025'],
                    ['FUTURO','10/2025','ANUAL','10/2026'])
        due,issues=due_rows(data,9,2026)
        self.assertEqual(issues,[])
        self.assertEqual(len(due),2)
        self.assertTrue(any(item.startswith('ANTERIOR —') for item in due))
        self.assertTrue(any(item.startswith('ANO ANTERIOR —') for item in due))
        self.assertFalse(any(item.startswith('ATUAL —') or item.startswith('FUTURO —') for item in due))
        due,_=due_rows(data,1,2026)
        self.assertEqual(len(due),1);self.assertTrue(due[0].startswith('ANO ANTERIOR —'))

    def test_realization_term_next_date_are_cross_checked_with_service(self):
        due,issues=due_rows(tables(['RECARGA DE EXTINTORES','03/2026','ANUAL','03/2028']),9,2026)
        self.assertEqual(due,[]);self.assertEqual(len(issues),1)
        self.assertIn('RECARGA DE EXTINTORES',issues[0]);self.assertIn('realização: 03/2026',issues[0])
        self.assertIn('prazo: ANUAL',issues[0]);self.assertIn('próxima: 03/2028',issues[0])
        self.assertIn('esperada em 03/2027',issues[0])

    def test_past_and_inconsistent_are_separate_findings(self):
        result=analyze_rows(tables(['SEGURO','07/2026','ANUAL','08/2026']),9,2026)
        self.assertEqual(len(result['due']),1);self.assertEqual(len(result['issues']),1)
        self.assertEqual(result['checks'][0]['status'],'pendente')

    def test_split_digits_and_month_precision_do_not_invent_day_mismatches(self):
        due,issues=due_rows(tables(['EXTINTORES','09/2025','ANUAL','0 9 /202 6'],
                                 ['CERTIFICADO','09/2025','12 MESES','30/09/2026'],
                                 ['PINTURA','30/11/2025','05ANOS','11/2030']),9,2026)
        self.assertEqual((due,issues),([],[]))

    def test_inclusive_mandate_anniversary_and_calendar_edges(self):
        data=tables(['MANDATO','12/09/2025','02 ANOS','11/09/2027'],
                    ['SEGURO','30/07/2026','ANUAL','30/07/2027'],
                    ['MENSAL','31/01/2026','MENSAL','28/02/2026'],
                    ['BISSEXTO','29/02/2024','ANUAL','28/02/2025'])
        result=analyze_rows(data,1,2025)
        self.assertEqual(result['due'],[]);self.assertEqual(result['issues'],[])
        self.assertTrue(all(row['status']=='prazo compatível' for row in result['checks']))

    def test_supported_periodicities_and_days(self):
        self.assertEqual(report_term('SEMESTRAL'),(6,'months'))
        self.assertEqual(report_term('05 ANOS'),(60,'months'))
        self.assertEqual(report_term('a cada 30 dias'),(30,'days'))
        due,issues=due_rows(tables(['LIMPEZA','15/03/2026','SEMESTRAL','15/09/2026'],
                                 ['MANUTENÇÃO','01/09/2026','30 DIAS','01/10/2026']),9,2026)
        self.assertEqual((due,issues),([],[]))
        with self.assertRaises(ValueError):report_term('BIANUAL')
        with self.assertRaises(ValueError):report_term('0 MESES')

    def test_unknown_term_missing_dates_and_invalid_dates_require_correction_not_false_pending(self):
        for row in (['A','09/2026','CONFORME LAUDO','09/2027'],
                    ['B','09/2026','30 DIAS','10/2026'],
                    ['C','31/09/2026','ANUAL','09/2027'],
                    ['D','09/2026','ANUAL','SETEMBRO'],
                    ['E','-','ANUAL','09/2027'],
                    ['F','09/2026','ANUAL','-']):
            with self.subTest(row=row):
                due,issues=due_rows(tables(row),9,2026)
                self.assertEqual(due,[]);self.assertTrue(issues)

    def test_automatic_renewal_and_rows_without_dates_do_not_invent_pending_dates(self):
        due,issues=due_rows(tables(['CONTRATO','30/05/2025','ANUAL','RENOVAÇÃO AUTOMÁTICA'],
                                 ['AVCB','-','05 ANOS','-']),9,2026)
        self.assertEqual((due,issues),([],[]))

    def test_column_order_and_repeated_headers(self):
        header=['PRAZO','PROXIMA REALIZAÇÃO','SERVIÇO','REALIZAÇÃO']
        data=[[header,['ANUAL','08/2026','SEGURO','08/2025'],header,['ANUAL','09/2026','CERTIFICADO','09/2025']]]
        due,issues=due_rows(data,9,2026)
        self.assertEqual(issues,[]);self.assertEqual(len(due),1);self.assertTrue(due[0].startswith('SEGURO —'))

    def test_missing_columns_and_incomplete_rows_are_not_reported_as_fully_checked(self):
        self.assertTrue(due_rows([[['SERVIÇOS','REALIZAÇÃO'],['SEGURO','09/2026']]],9,2026)[1])
        due,issues=due_rows([[['SERVIÇOS','PRÓXIMA REALIZAÇÃO'],['SEGURO','08/2026']]],9,2026)
        self.assertTrue(due);self.assertTrue(any('Colunas ausentes' in issue for issue in issues))
        due,issues=due_rows([[HEADERS,['SEGURO','09/2026']]],9,2026)
        self.assertEqual(due,[]);self.assertTrue(issues)

    def test_unchecked_report_still_requests_correction_and_does_not_change_selection(self):
        result={'word':'original.doc','rows':[{'checked':False}],'warnings':['Outro aviso']}
        with patch('obligations.digest',return_value='hash'),patch('obligations.read_tables',return_value=tables(['SEGURO','08/2025','ANUAL','08/2026'])):
            check_obligations(result,9,2026)
        self.assertIn('anteriores à competência 09/2026',result['due_notice'])
        self.assertIn('Solicite a correção',result['due_notice'])
        self.assertFalse(result['rows'][0]['checked']);self.assertIn('Outro aviso',result['warnings'])

    def test_future_inconsistency_requests_correction_without_saying_pending(self):
        result={'word':'original.doc','warnings':[]}
        with patch('obligations.digest',return_value='hash'),patch('obligations.read_tables',return_value=tables(['CERTIFICADO','09/2026','ANUAL','09/2028'])):
            check_obligations(result,9,2026)
        self.assertFalse(result['due_notice']);self.assertFalse(result['due_obligations'])
        self.assertIn('esperada em 09/2027',result['obligation_notice'])
        self.assertNotIn('PENDENTE',result['obligation_notice'])

    def test_rechecking_another_month_removes_old_findings_and_does_not_duplicate_warnings(self):
        result={'word':'original.doc','warnings':['Outro aviso']}
        with patch('obligations.digest',return_value='hash'),patch('obligations.read_tables',return_value=tables(['SEGURO','08/2025','ANUAL','08/2026'])):
            check_obligations(result,9,2026);check_obligations(result,9,2026)
            self.assertEqual(len(result['warnings']),2)
            check_obligations(result,8,2026)
        self.assertEqual(result['warnings'],['Outro aviso']);self.assertFalse(result['due_notice'])

    def test_unreadable_or_changed_original_is_never_a_successful_check(self):
        result={'word':None,'warnings':[]};check_obligations(result,9,2026)
        self.assertTrue(result['warnings']);self.assertFalse(result['due_notice'])
        result={'word':'original.doc','warnings':[]}
        with patch('obligations.digest',side_effect=['before','after']),patch('obligations.read_tables',return_value=tables(['SEGURO','08/2025','ANUAL','08/2026'])):
            check_obligations(result,9,2026)
        self.assertEqual(result['due_obligations'],[]);self.assertEqual(result['obligation_checks'],[])
        self.assertIn('mudou durante',result['obligation_notice'])
