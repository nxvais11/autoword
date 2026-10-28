import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App
from engine import FILES
from print_service import existing_receipt, receipt_for, print_receipt
from word_service import discover, inspect_condo
from test_engine import APPROVAL, FakeWord


class Printing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.condos = []
        for name in ('Edifício A', 'Edifício B'):
            folder = self.root/name
            folder.mkdir()
            for i, stem in enumerate(FILES):
                (folder/(stem+'.doc')).write_text(APPROVAL if i==0 else 'AGOSTO/2026', encoding='utf-8')
        self.condos = discover(self.root)
        self.docs = [{'path':p} for p in self.condos[0]['files']]
        self.receipt = receipt_for(self.condos[0], Path(self.condos[0]['folder']), self.docs, 11, 2026)

    def tearDown(self):
        self.tmp.cleanup()

    def test_prints_only_generated_results_read_only_without_extra_files(self):
        # O resultado está em outro destino e contém apenas os tipos escolhidos.
        target = self.root/'Saída'
        target.mkdir()
        source = self.docs[1]['path']
        (target/source.name).write_bytes(source.read_bytes())
        (target/'outro.doc').write_text('não imprimir')
        receipt = receipt_for(self.condos[0], target, [self.docs[1]], 11, 2026)
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        document = Mock()
        setup = Mock()
        word = SimpleNamespace(app=SimpleNamespace(Dialogs=Mock(return_value=setup),Options=Mock()), open=Mock(return_value=document))
        self.assertEqual(print_receipt(word, receipt, 'Impressora de teste', 2), 1)
        word.open.assert_called_once_with((target/source.name).resolve(), read_only=True)
        document.PrintOut.assert_called_once_with(Background=False, Copies=2, Collate=True, PrintToFile=False)
        document.Close.assert_called_once_with(0)
        self.assertTrue(setup.DoNotSetAsSysDefault)
        self.assertEqual(before, {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_modified_result_blocks_entire_print_before_first_page(self):
        Path(self.receipt['files'][-1]['path']).write_text('alterado')
        word = Mock()
        with self.assertRaisesRegex(ValueError, 'mudou'):
            print_receipt(word, self.receipt, 'Teste')
        word.open.assert_not_called()
        word.app.Dialogs.assert_not_called()

    def test_cancellation_stops_before_sending_and_close_on_printer_error(self):
        cancel = threading.Event()
        cancel.set()
        word = Mock()
        self.assertEqual(print_receipt(word, self.receipt, 'Teste', cancel=cancel), 0)
        word.open.assert_not_called()
        document = Mock()
        document.PrintOut.side_effect = RuntimeError('Impressora indisponível')
        word.open.return_value = document
        with self.assertRaisesRegex(RuntimeError, 'indisponível'):
            print_receipt(word, self.receipt, 'Teste')
        document.Close.assert_called_once_with(0)

    def test_invalid_copies_do_not_send_any_job(self):
        word = Mock()
        for copies in (0, 100, '2'):
            with self.assertRaises(ValueError):
                print_receipt(word, self.receipt, 'Teste', copies)
        word.open.assert_not_called()

    def test_existing_documents_can_print_without_updating_or_matching_month(self):
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        receipt = existing_receipt(self.condos[0], (1,3))
        self.assertIsNone(receipt['month'])
        self.assertEqual([Path(item['path']).name for item in receipt['files']],
                         [self.condos[0]['files'][i].name for i in (1,3)])
        document = Mock()
        word = SimpleNamespace(app=SimpleNamespace(Dialogs=Mock(return_value=Mock()),Options=Mock()), open=Mock(return_value=document))
        self.assertEqual(print_receipt(word,receipt,'Teste'),2)
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_missing_or_unselected_documents_cannot_be_added_to_existing_print(self):
        condo = dict(self.condos[0], files=list(self.condos[0]['files']))
        condo['files'][0] = None
        self.assertEqual(len(existing_receipt(condo,(1,))['files']),1)
        for kinds in ((),(0,),(4,)):
            with self.assertRaises(ValueError):
                existing_receipt(condo,kinds)

    def run_generation(self, condos, broken=False, cancel_after=False):
        value = lambda x:SimpleNamespace(get=lambda:x)
        events = queue.Queue()
        cancel = threading.Event()
        fake = SimpleNamespace(selected=lambda:condos, period=lambda:(11,2026),
            folder=value(str(self.root)), destination=value(''), create_subfolder=value(False),
            chosen_kinds=lambda:(0,1,2,3), preview={}, sheet_monitor=None,
            sheet_polling=False, sheet_error=None, config={}, sheet_groups={}, sheet_mapping={},
            source_models={}, generation_cache={}, events=events, cancel=cancel,
            record_job=lambda *args:cancel.set() if cancel_after else None,
            start=lambda task:task())
        class SessionWord(FakeWord):
            def __enter__(self): return self
            def __exit__(self, *args): pass
        if broken:
            condos[0]['files'][1].write_text('competência ausente')
        with patch('app.Word', SessionWord):
            App.run_generation(fake)
        items = []
        while not events.empty():
            items.append(events.get_nowait())
        return items

    def test_individual_success_creates_print_receipt_for_exact_results(self):
        events = self.run_generation(self.condos[:1])
        receipts = [value for kind,value in events if kind=='print_ready']
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]['folder'], self.condos[0]['folder'])
        self.assertEqual(len(receipts[0]['files']), 4)
        self.assertTrue(all('NOVEMBRO/2026' in Path(item['path']).read_text()
                            for item in receipts[0]['files']))

    def test_batch_never_enables_print_even_if_one_condo_succeeds(self):
        events = self.run_generation(self.condos, broken=True)
        self.assertFalse(any(kind=='print_ready' for kind,_ in events))

    def test_failed_or_canceled_individual_never_enables_print(self):
        self.assertFalse(any(kind=='print_ready' for kind,_ in self.run_generation(self.condos[:1], broken=True)))
        # Usa o segundo condomínio intacto.
        self.assertFalse(any(kind=='print_ready' for kind,_ in self.run_generation(self.condos[1:], cancel_after=True)))

    def test_pdf_no_longer_blocks_spreadsheet_workflow(self):
        (Path(self.condos[0]['folder'])/'renuncia.pdf').write_bytes(b'pdf de teste')
        docs = inspect_condo(FakeWord(), self.condos[0], 11, 2026, [], check_resignations=False)
        self.assertEqual(len(docs), 4)
        self.assertTrue(all(not doc['resignation_events'] for doc in docs))


if __name__ == '__main__':
    unittest.main()
