import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from document_period import inspect_periods,periods,period_summary

class Periods(unittest.TestCase):
    def test_dates_repeated_accent_and_divergence(self):
        self.assertEqual(periods('MARÇO/2026 março / 2026 31 de Março de 2026'),[('marco',2026)])
        self.assertEqual(periods('SETEMBRO/2026 31 de Outubro de 2026'),[('setembro',2026),('outubro',2026)])

    def test_actual_file_not_selected_month_cached_and_invalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'capa.doc';path.write_text('AGOSTO/2026')
            service=Mock();service.read.side_effect=lambda p:p.read_text()
            factory=Mock();factory.return_value.__enter__=Mock(return_value=service)
            factory.return_value.__exit__=Mock(return_value=False)
            result={'period':'2026-11','rows':[dict(group='closing',path=path,label='Capa')]}
            cache={};before=path.read_bytes()
            inspect_periods(result,cache,factory)
            self.assertEqual(period_summary(result),'Competência dos Words: Agosto/2026')
            self.assertEqual(before,path.read_bytes())
            inspect_periods(result,cache,factory);self.assertEqual(factory.call_count,1)
            path.write_text('SETEMBRO/2026');inspect_periods(result,cache,factory)
            self.assertEqual(period_summary(result),'Competência dos Words: Setembro/2026')
            self.assertEqual(factory.call_count,2)

    def test_docx_without_word_missing_and_different_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=[]
            for name,text in [('Capa','AGOSTO/2026'),('Anexo','SETEMBRO/2026')]:
                path=Path(tmp)/(name+'.docx')
                with ZipFile(path,'w') as archive:
                    archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:document>')
                rows.append(dict(group='closing',path=path,label=name))
            factory=Mock(side_effect=AssertionError('não abrir Word'))
            result={'rows':rows};inspect_periods(result,word_factory=factory)
            self.assertIn('Competências diferentes',period_summary(result))
            rows.append(dict(group='closing',path=None,label='Aprovação'))
            inspect_periods(result,word_factory=factory)
            self.assertIn('Aprovação: arquivo não localizado',period_summary(result))
            factory.assert_not_called()

    def test_unidentified_read_error_cancel_and_changed_during_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'capa.doc';path.write_text('Sem data')
            service=Mock();factory=Mock()
            factory.return_value.__enter__=Mock(return_value=service)
            factory.return_value.__exit__=Mock(return_value=False)
            result={'rows':[dict(group='closing',path=path,label='Capa')]}
            service.read.return_value='Sem data';inspect_periods(result,word_factory=factory)
            self.assertIn('competência não identificada',period_summary(result))
            service.read.side_effect=ValueError('Protegido');inspect_periods(result,word_factory=factory)
            self.assertIn('Protegido',period_summary(result))
            def change(p):p.write_text('OUTUBRO/2026');return 'AGOSTO/2026'
            service.read.side_effect=change;cache={};inspect_periods(result,cache,factory)
            self.assertIn('mudou durante',period_summary(result));self.assertFalse(cache)
            cancel=threading.Event();cancel.set();inspect_periods(result,word_factory=factory,cancel=cancel)
            self.assertIn('cancelada',period_summary(result))
