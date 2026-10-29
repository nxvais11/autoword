import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from obligations import due_rows,check_obligations

class Obligations(unittest.TestCase):
    def test_column_month_year_and_split_digits(self):
        tables=[[['SERVIÇOS','REALIZAÇÃO','PROXIMA REALIZAÇÃO'],
                 ['SEGURO','09/2026','30/07/2027'],
                 ['EXTINTORES','01/2020','0 9 /202 6'],
                 ['MANDATO','09/2026','11/09/2027'],
                 ['CONTRATO','','RENOVAÇÃO AUTOMÁTICA']]]
        due,issues=due_rows(tables,9,2026)
        self.assertEqual(due,['EXTINTORES: 0 9 /202 6']);self.assertEqual(issues,[])
    def test_missing_column_and_invalid_dates_require_review(self):
        self.assertTrue(due_rows([[['SERVIÇOS','REALIZAÇÃO'],['SEGURO','09/2026']]],9,2026)[1])
        due,issues=due_rows([[['SERVIÇOS','PRÓXIMA REALIZAÇÃO'],['A','31/09/2026'],['B','SETEMBRO']]],9,2026)
        self.assertFalse(due);self.assertEqual(len(issues),2)
    def test_unchecked_report_still_warns_and_does_not_change_selection(self):
        result={'name':'TESTE','word':'original.doc','rows':[{'checked':False}],'warnings':[]}
        with patch('obligations.digest',return_value='hash'),patch('obligations.read_tables',return_value=[[['SERVIÇOS','PRÓXIMA REALIZAÇÃO'],['SEGURO','09/2026']]]):
            check_obligations(result,9,2026)
        self.assertTrue(result['due_notice']);self.assertFalse(result['rows'][0]['checked'])
    def test_unreadable_original_is_not_reported_as_no_due_items(self):
        result={'word':None,'warnings':[]}
        check_obligations(result,9,2026)
        self.assertTrue(result['warnings']);self.assertFalse(result['due_notice'])

    def test_prior_months_and_prior_years_included_but_future_excluded(self):
        tables=[[['SERVIÇOS','PRÓXIMA REALIZAÇÃO'],
                 ['ATUAL','30/09/2026'],['ANTERIOR','08/2026'],
                 ['ANO ANTERIOR','31/12/2025'],['FUTURO','10/2026'],
                 ['ANO FUTURO','09/2027'],['AUTOMÁTICO','Renovação automática'],
                 ['SEM DATA','-']]]
        due,issues=due_rows(tables,9,2026)
        self.assertEqual(due,['ATUAL: 30/09/2026',
            'ANTERIOR: 08/2026 — anterior à competência',
            'ANO ANTERIOR: 31/12/2025 — anterior à competência'])
        self.assertEqual(issues,[])
        due,_=due_rows(tables,1,2026)
        self.assertEqual(due,['ANO ANTERIOR: 31/12/2025 — anterior à competência'])

    def test_past_obligation_warns_even_unchecked_and_does_not_edit_files(self):
        result={'word':'original.doc','rows':[{'checked':False}],'warnings':[]}
        with patch('obligations.digest',return_value='hash'),patch('obligations.read_tables',
                return_value=[[['SERVIÇOS','PRÓXIMA REALIZAÇÃO'],['SEGURO','12/2025']]]):
            check_obligations(result,9,2026)
        self.assertIn('até 09/2026',result['due_notice'])
        self.assertIn('SEGURO: 12/2025 — anterior à competência',result['due_notice'])
        self.assertFalse(result['rows'][0]['checked'])
