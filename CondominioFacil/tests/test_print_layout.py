"""Regressões: formas do cabeçalho presentes durante impressão e exportação."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from central_service import export_word
from print_service import print_receipt
from word_service import digest, print_layout


class PrintLayout(unittest.TestCase):
    def setUp(self):
        self.options = SimpleNamespace(PrintDrawingObjects=False, PrintBackgrounds=False, PrintDraft=True)
        self.document = Mock()
        self.document.Revisions.Count = 0
        self.word = SimpleNamespace(app=SimpleNamespace(Options=self.options, Dialogs=Mock(), Visible=False, ScreenUpdating=False),
                                    open=Mock(return_value=self.document))

    def assert_graphics_enabled(self):
        self.assertTrue(self.options.PrintDrawingObjects)
        self.assertTrue(self.options.PrintBackgrounds)
        self.assertFalse(self.options.PrintDraft)

    def assert_preferences_restored(self):
        self.assertFalse(self.options.PrintDrawingObjects)
        self.assertFalse(self.options.PrintBackgrounds)
        self.assertTrue(self.options.PrintDraft)

    def test_direct_print_includes_graphics_and_restores_preferences_even_on_error(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                source = Path(folder)/'APROVACAO.doc'
                source.write_bytes(b'original document with header border')
                original = source.read_bytes()
                receipt = {'files': [{'path': str(source), 'sha256': digest(source)}]}
                def send(**kwargs):
                    self.assert_graphics_enabled()
                    self.assertTrue(self.word.app.Visible)
                    self.assertTrue(self.word.app.ScreenUpdating)
                    self.document.PrintPreview.assert_called()
                    self.document.Activate.assert_called()
                    self.assertEqual(self.document.ActiveWindow.View.Type, 3)
                    self.document.Repaginate.assert_called()
                    if fail:
                        raise RuntimeError('printer unavailable')
                self.document.PrintOut.side_effect = send
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'printer unavailable'):
                        print_receipt(self.word, receipt, 'TEST')
                else:
                    self.assertEqual(print_receipt(self.word, receipt, 'TEST'), 1)
                self.assert_preferences_restored()
                self.assertFalse(self.word.app.Visible)
                self.assertFalse(self.word.app.ScreenUpdating)
                self.document.ClosePrintPreview.assert_called()
                self.assertEqual(source.read_bytes(), original)
                self.word.open.assert_called_with(source, read_only=True)
                self.document.Close.assert_called_with(0)
                self.document.Save.assert_not_called()

    def test_pdf_export_includes_graphics_with_print_quality_and_restores_on_error(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                source, target = Path(folder)/'CAPA.doc', Path(folder)/'temporario.pdf'
                source.write_bytes(b'original with rectangle')
                def export(**kwargs):
                    self.assert_graphics_enabled()
                    self.assertEqual(kwargs['OptimizeFor'], 0)
                    self.assertTrue(kwargs['BitmapMissingFonts'])
                    if fail:
                        raise RuntimeError('export unavailable')
                    Path(kwargs['OutputFileName']).write_bytes(b'pdf output')
                self.document.ExportAsFixedFormat.side_effect = export
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'export unavailable'):
                        export_word(self.word, source, target)
                    self.assertFalse(target.exists())
                else:
                    export_word(self.word, source, target)
                    self.assertTrue(target.exists())
                self.assert_preferences_restored()
                self.word.open.assert_called_with(source, read_only=True)
                self.document.Close.assert_called_with(0)
                self.document.Save.assert_not_called()
                self.assertEqual(source.read_bytes(), b'original with rectangle')

    def test_partial_configuration_failure_restores_previously_changed_options(self):
        class Options:
            PrintDrawingObjects = False
            @property
            def PrintBackgrounds(self):
                raise RuntimeError('configuration unavailable')
        self.word.app.Options = Options()
        with self.assertRaisesRegex(RuntimeError, 'configuration unavailable'):
            with print_layout(self.word):
                self.fail('Must not print with incomplete configuration')
        self.assertFalse(self.word.app.Options.PrintDrawingObjects)

    def test_existing_print_preferences_remain_enabled_after_output(self):
        self.options.PrintDrawingObjects = True
        self.options.PrintBackgrounds = True
        self.options.PrintDraft = False
        with print_layout(self.word):
            self.assert_graphics_enabled()
        self.assert_graphics_enabled()
