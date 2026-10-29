import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from central_service import alphabetical_names,matching_names,statement_owners


class CondoSearch(unittest.TestCase):
    def test_alphabetical_order_ignores_accents_and_removes_duplicates(self):
        self.assertEqual(alphabetical_names(['ZETA','Érica','ALFA','Érica','beta']),('ALFA','beta','Érica','ZETA'))

    def test_partial_search_accepts_accents_case_and_multiple_words(self):
        names=['Jardim São Luís','ALFA','JARDIM SÃO JOSÉ','Érica Cristine']
        self.assertEqual(matching_names(names,'SAO JARDIM'),('JARDIM SÃO JOSÉ','Jardim São Luís'))
        self.assertEqual(matching_names(names,'erica'),('Érica Cristine',))
        self.assertEqual(matching_names(names,''),alphabetical_names(names))
        self.assertEqual(matching_names(names,'inexistente'),())

    def test_document_ownership_must_use_full_catalog_even_when_search_is_filtered(self):
        names=alphabetical_names(['ALFA JARDIM','ALFA'])
        self.assertEqual(statement_owners('EXTRATO ALFA JARDIM',names),{'ALFA JARDIM'})
        self.assertEqual(matching_names(names,'ALFA'),names)
