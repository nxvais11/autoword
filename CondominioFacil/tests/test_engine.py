import calendar
import sys
import threading
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import plan, apply_text, roster, utf16_offset, FILES
from word_service import discover, inspect_condo, generate, select_files

APPROVAL = ('Guarulhos, 31 de Agosto de 2026.\rTERMO AGOSTO/2026\r'
            'Receitas AGOSTO/2026\rPasta AGOSTO/2026\r'
            'Síndico (a)            Pessoa Sindico           apto 12    Data: ___/___/___\r'
            'Conselheiros (as)  Pessoa Conselho Um       apto 01    Data: ___/___/___\r'
            '  Pessoa Conselho Dois       apto 31    Data: ___/___/___\r'
            '  Pessoa Conselho Tres           apto 21    Data: ___/___/___\r'
            'Artigo 1350; valor 31; endereço 12.\r')

class Dates(unittest.TestCase):
    def test_all_months_and_leap_years(self):
        for year in (2026, 2028, 2000, 2099):
            for month in range(1,13):
                changes, _ = plan(APPROVAL, 0, month, year)
                text = apply_text(APPROVAL, changes)
                self.assertTrue(text.startswith(f'Guarulhos, {calendar.monthrange(year, month)[1]} de '))
                self.assertIn('Data: ___/___/___', text)
                self.assertIn('Artigo 1350; valor 31; endereço 12.', text)
                self.assertEqual(len(changes), 4)

    def test_case_and_spacing(self):
        text = apply_text('agosto / 2026', plan('agosto / 2026', 1, 9, 2027)[0])
        self.assertEqual(text, 'setembro / 2027')

    def test_mismatched_references(self):
        with self.assertRaises(ValueError):
            plan(APPROVAL.replace('Pasta AGOSTO', 'Pasta JULHO'), 0, 11, 2026)

    def test_wrong_count(self):
        for text in ('Sem data', 'AGOSTO/2026 AGOSTO/2026', '08/2026'):
            with self.assertRaises(ValueError):
                plan(text, 1, 11, 2026)

    def test_utf16(self):
        self.assertEqual(utf16_offset('😀a', 1), 2)

    def test_changed_text(self):
        changes, _ = plan('AGOSTO/2026', 1, 11, 2026)
        with self.assertRaises(ValueError):
            apply_text('JULHO/2026', changes)

class Responsible(unittest.TestCase):
    def setUp(self):
        self.rule = {'old_name':'Pessoa Sindico', 'new_name':'Maria Silva', 'old_unit':'12',
                     'new_unit':'88', 'since':'2026-11', 'enabled':True}

    def test_import_four_signatures(self):
        rows = roster(APPROVAL)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['old_name'], 'Pessoa Sindico')
        self.assertEqual(rows[1]['old_name'], 'Pessoa Conselho Um')

    def test_effective_date_and_scoped_unit(self):
        before = apply_text(APPROVAL, plan(APPROVAL, 0, 10, 2026, [self.rule])[0])
        after = apply_text(APPROVAL, plan(APPROVAL, 0, 11, 2026, [self.rule])[0])
        self.assertIn('Pessoa Sindico', before)
        self.assertIn('Maria Silva', after)
        self.assertIn('apto 88', after)
        self.assertIn('endereço 12', after)

    def test_unit_only(self):
        self.rule['new_name'] = self.rule['old_name']
        after = apply_text(APPROVAL, plan(APPROVAL, 0, 11, 2026, [self.rule])[0])
        self.assertIn('apto 88', after)

    def test_duplicate_and_missing_name(self):
        for original in (APPROVAL+'Pessoa Sindico', APPROVAL.replace('Pessoa Sindico','Outro nome')):
            with self.assertRaises(ValueError):
                plan(original, 0, 11, 2026, [self.rule])

    def test_disabled_rule(self):
        self.rule['enabled'] = False
        self.assertEqual(len(plan(APPROVAL, 0, 11, 2026, [self.rule])[0]), 4)

    def test_overlapping_rules(self):
        with self.assertRaises(ValueError):
            plan(APPROVAL, 0, 11, 2026, [self.rule, self.rule])

class FakeWord:
    """Exercita apenas orquestração; não simula formatação ou a API COM."""
    def read(self, path):
        return Path(path).read_text(encoding='utf-8')
    def write_copy(self, source, destination, text, changes, template=None):
        Path(destination).write_text(apply_text(text, changes), encoding='utf-8')

class Batch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'origem'
        self.folder = self.root/'Condominio A'
        self.folder.mkdir(parents=True)
        for i, name in enumerate(FILES):
            (self.folder/(name+'.doc')).write_text(APPROVAL if i == 0 else 'Texto fixo AGOSTO/2026', encoding='utf-8')
        self.condos = discover(self.root)
    def tearDown(self):
        self.temp.cleanup()
    def test_success_and_original_unchanged(self):
        word = FakeWord()
        docs = inspect_condo(word, self.condos[0], 11, 2026, [])
        before = [d['path'].read_bytes() for d in docs]
        output = generate(word, self.condos, {str(self.folder):docs}, Path(self.temp.name)/'saida', 11, 2026, lambda s:None, threading.Event())
        self.assertEqual(len(list((output/'Condominio A').glob('*.doc'))), 4)
        self.assertEqual(before, [d['path'].read_bytes() for d in docs])
        self.assertEqual(sorted(p.suffix for p in output.rglob('*') if p.is_file()), ['.doc']*4)
    def test_source_changed(self):
        docs = inspect_condo(FakeWord(), self.condos[0], 11, 2026, [])
        docs[1]['path'].write_text('Mudou', encoding='utf-8')
        messages = []
        output = generate(FakeWord(), self.condos, {str(self.folder):docs}, Path(self.temp.name)/'saida', 11, 2026, messages.append, threading.Event())
        self.assertFalse((output/'Condominio A').exists())
        self.assertTrue(any('REVISAR' in s for s in messages))
        self.assertFalse(output.exists())
    def test_no_partial_condominium(self):
        class BrokenWord(FakeWord):
            def write_copy(self, source, destination, text, changes):
                super().write_copy(source, destination, text, changes)
                raise ValueError('Falha de gravação')
        docs = inspect_condo(FakeWord(), self.condos[0], 11, 2026, [])
        output = generate(BrokenWord(), self.condos, {str(self.folder):docs}, Path(self.temp.name)/'saida', 11, 2026, lambda s:None, threading.Event())
        self.assertFalse(output.exists())
        self.assertFalse(list(Path(self.temp.name).rglob('.temporario_*')))
    def test_cross_document_mismatch(self):
        self.condos[0]['files'][2].write_text('SETEMBRO/2026', encoding='utf-8')
        with self.assertRaises(ValueError):
            inspect_condo(FakeWord(), self.condos[0], 11, 2026, [])
    def test_ambiguous_file(self):
        (self.folder/(FILES[0]+'.docx')).write_text('duplicado')
        self.assertTrue(discover(self.root)[0]['errors'])
    def test_select_direct_docx_folder(self):
        for p in self.folder.glob('*.doc'):
            p.rename(p.with_suffix('.docx'))
        found = discover(self.folder)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['folder'], str(self.folder.resolve()))
        self.assertFalse(found[0]['errors'])
    def test_select_direct_doc_folder(self):
        self.assertFalse(discover(self.folder)[0]['errors'])
    def test_partial_direct_folder(self):
        (self.folder/(FILES[0]+'.doc')).unlink()
        self.assertTrue(discover(self.folder)[0]['errors'])
    def test_empty_folder_message(self):
        empty = Path(self.temp.name)/'vazia'
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, 'Nenhum condomínio'):
            discover(empty)
    def test_extra_spaces_and_underscores(self):
        path = self.folder/(FILES[1]+'.doc')
        path.rename(self.folder/'CAPA__  LIVRO.doc')
        self.assertFalse(discover(self.folder)[0]['errors'])
    def test_arbitrary_names_manual_selection(self):
        paths = []
        for i, p in enumerate(self.condos[0]['files']):
            renamed = p.with_name(f'documento diferente {i}.doc')
            p.rename(renamed)
            paths.append(str(renamed))
        found = discover(self.folder)
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0]['found']), 4)
        self.assertTrue(found[0]['errors'])
        selected = select_files(self.folder, paths)
        self.assertFalse(selected['errors'])
        self.assertEqual(len(inspect_condo(FakeWord(), selected, 11, 2026, [])), 4)
        saved = discover(self.folder, {str(self.folder):paths})
        self.assertFalse(saved[0]['errors'])
    def test_manual_reject_duplicate(self):
        paths = self.condos[0]['files'][:]
        paths[1] = paths[0]
        with self.assertRaisesRegex(ValueError, 'diferente'):
            select_files(self.folder, paths)
    def test_manual_reject_other_folder(self):
        paths = self.condos[0]['files'][:]
        elsewhere = Path(self.temp.name)/'fora.doc'
        elsewhere.write_text('Outro documento')
        paths[0] = elsewhere
        with self.assertRaisesRegex(ValueError, 'mesma pasta'):
            select_files(self.folder, paths)
    def test_missing_saved_mapping_blocks(self):
        paths = [str(p) for p in self.condos[0]['files']]
        paths[0] = str(self.folder/'sumiu.doc')
        self.assertTrue(discover(self.folder, {str(self.folder):paths})[0]['errors'])
    def test_ignore_word_lock_file(self):
        (self.folder/'~$CAPA LIVRO.doc').write_text('temporário')
        found = discover(self.folder)[0]
        self.assertFalse(found['errors'])
        self.assertEqual(len(found['found']), 4)
    def test_cancellation(self):
        cancel = threading.Event()
        cancel.set()
        messages = []
        output = generate(FakeWord(), self.condos, {}, Path(self.temp.name)/'saida', 11, 2026, messages.append, cancel)
        self.assertTrue(any('CANCELADO' in s for s in messages))
        self.assertFalse(output.exists())
    def test_existing_folder_only_selected_files_overwritten(self):
        target = self.folder/'2026-11'
        target.mkdir()
        unrelated = target/'contrato.doc'
        unrelated.write_bytes(b'nao alterar')
        untouched = target/(FILES[2]+'.doc')
        untouched.write_bytes(b'anexo nao solicitado')
        capa = target/(FILES[1]+'.doc')
        capa.write_bytes(b'capa anterior')
        docs = inspect_condo(FakeWord(),self.condos[0],11,2026,[],kinds=(1,))
        output = generate(FakeWord(),self.condos,{str(self.folder):docs},self.root,11,2026,
            lambda s:None,threading.Event(),existing_folder=self.folder)
        self.assertEqual(output,target)
        self.assertIn('NOVEMBRO/2026',capa.read_text())
        self.assertEqual(unrelated.read_bytes(),b'nao alterar')
        self.assertEqual(untouched.read_bytes(),b'anexo nao solicitado')
        self.assertEqual(sorted(p.name for p in self.folder.iterdir() if p.is_dir()),['2026-11'])
        self.assertFalse(list(self.root.rglob('relatorio.*')))
    def test_unrequested_missing_document_does_not_block(self):
        (self.folder/(FILES[0]+'.doc')).unlink()
        condo = discover(self.folder)[0]
        self.assertEqual(len(inspect_condo(FakeWord(),condo,11,2026,[],kinds=(1,))),1)
    def test_no_backup_or_extra_files_on_failed_overwrite(self):
        class BrokenWord(FakeWord):
            def write_copy(self,*args):
                raise OSError('Falha de gravação')
        target = self.folder/'2026-11'
        target.mkdir()
        dest = target/(FILES[1]+'.doc')
        dest.write_bytes(b'capa anterior')
        docs = inspect_condo(FakeWord(),self.condos[0],11,2026,[],kinds=(1,))
        generate(BrokenWord(),self.condos,{str(self.folder):docs},self.root,11,2026,
            lambda s:None,threading.Event(),existing_folder=self.folder)
        self.assertEqual(dest.read_bytes(),b'capa anterior')
        self.assertEqual([p.name for p in target.iterdir()],[dest.name])
        self.assertFalse(list(self.root.rglob('.temporario_*')))
    def test_spreadsheet_changed_during_write_does_not_publish(self):
        docs = inspect_condo(FakeWord(),self.condos[0],11,2026,[],kinds=(1,))
        calls = []
        def validate():
            calls.append(1)
            if len(calls)>1:
                raise ValueError('Planilha mudou')
        output = generate(FakeWord(),self.condos,{str(self.folder):docs},self.root,11,2026,
            lambda s:None,threading.Event(),existing_folder=self.folder,validate=validate)
        self.assertFalse(output.exists())

if __name__ == '__main__':
    unittest.main()
