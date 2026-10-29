"""Regressões de comparação: texto girado, páginas sem texto e formulários."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject,ArrayObject,TextStringObject
from central_service import pdf_text,compare_texts
from test_central import pdf


class PDFReading(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def make_pdf(self,name,value):
        base=self.root/'base.pdf';pdf(base,'REGULAR CONTENT FOR COMPARISON')
        reader=PdfReader(base);writer=PdfWriter();page=writer.add_page(reader.pages[0])
        stream=DecodedStreamObject()
        stream.set_data(('BT /F1 12 Tf 20 800 Td (REGULAR CONTENT FOR COMPARISON) Tj ET\n'
                         'BT /F1 12 Tf 0 1 -1 0 100 100 Tm ('+value+') Tj ET').encode('ascii'))
        page[NameObject('/Contents')]=writer._add_object(stream)
        target=self.root/name
        with target.open('wb') as output:writer.write(output)
        return target

    def test_difference_in_rotated_text_is_not_silently_ignored(self):
        left=self.make_pdf('left.pdf','PREVIOUS 2026')
        right=self.make_pdf('right.pdf','CURRENT 2027')
        before=left.read_bytes(),right.read_bytes()
        self.assertFalse(compare_texts(pdf_text(left),pdf_text(right))['equal'])
        self.assertEqual(before,(left.read_bytes(),right.read_bytes()))

    def test_first_page_lookup_does_not_load_full_document_parser(self):
        source=self.root/'statement.pdf';pdf(source,'CONDOMINIO DO EDIFICIO TESTE')
        with patch('pdfplumber.open',side_effect=AssertionError('full parser')):
            self.assertIn('CONDOMINIO',pdf_text(source,first=True))

    def test_blank_page_among_readable_pages_blocks_comparison(self):
        source=self.root/'mixed.pdf';pdf(source)
        writer=PdfWriter();writer.append(source);writer.add_blank_page(595,842)
        with source.open('wb') as output:writer.write(output)
        with self.assertRaisesRegex(ValueError,'digitalizado'):pdf_text(source)

    def test_password_and_forms_are_still_rejected(self):
        source=self.root/'source.pdf';pdf(source)
        writer=PdfWriter();writer.append(source);writer.encrypt('secret')
        protected=self.root/'protected.pdf'
        with protected.open('wb') as output:writer.write(output)
        with self.assertRaisesRegex(ValueError,'senha'):pdf_text(protected)
        writer=PdfWriter();writer.append(source)
        field=DictionaryObject({NameObject('/FT'):NameObject('/Tx'),NameObject('/T'):TextStringObject('Status'),NameObject('/V'):TextStringObject('PENDENTE')})
        writer._root_object[NameObject('/AcroForm')]=DictionaryObject({NameObject('/Fields'):ArrayObject([writer._add_object(field)])})
        form=self.root/'form.pdf'
        with form.open('wb') as output:writer.write(output)
        with self.assertRaisesRegex(ValueError,'formulário'):pdf_text(form)

    def test_empty_password_pdf_can_be_compared(self):
        source=self.root/'source.pdf';pdf(source)
        writer=PdfWriter();writer.append(source);writer.encrypt('')
        protected=self.root/'protected.pdf'
        with protected.open('wb') as output:writer.write(output)
        self.assertTrue(compare_texts(pdf_text(source),pdf_text(protected))['equal'])

    def test_parser_page_count_disagreement_blocks_comparison(self):
        source=self.root/'source.pdf';pdf(source)
        with patch('pdfplumber.open') as opening:
            opening.return_value.__enter__.return_value.pages=[]
            with self.assertRaisesRegex(ValueError,'incompleta'):pdf_text(source)
