import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import FILES
from word_service import document_kind, discover, inspect_condo, generate, output_targets
from test_engine import APPROVAL, FakeWord

class FlexibleFilenames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
    def tearDown(self):
        self.tmp.cleanup()
    def make_files(self,folder,names):
        folder.mkdir(parents=True)
        for i,name in enumerate(names):
            (folder/name).write_text(APPROVAL if i==0 else 'AGOSTO/2026',encoding='utf-8')
    def test_known_aliases_roman_arabic_and_separators(self):
        aliases = {0:['APROVAÇÃO DE CONTAS','aprovacao_de_contas'],
                   1:['CAPA','Capa Livro','CAPA DO LIVRO','capa de livro','capa_de_livros'],
                   2:['ANEXO 1','anexo I','ANEXO1','anexo-i','Prestação de Contas ANEXO 1',FILES[2]],
                   3:['ANEXO 2','anexo II','ANEXO2','anexo_ii','Prestação de Contas ANEXO 2',FILES[3]]}
        for kind,names in aliases.items():
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(document_kind(name),kind)
    def test_unrelated_and_archived_names_are_not_guessed(self):
        for name in ('ANEXO 10','ANEXO III','ANEXO 12','CAPA CONTRATO','CAPA ANTIGA',
                     'ANEXO 1 cópia','Contrato ANEXO 2','minhaCAPA','ANEXO 21'):
            with self.subTest(name=name):
                self.assertIsNone(document_kind(name))
    def test_short_names_in_nested_condominium(self):
        folder = self.root/'ALLURE'/'FECHAMENTO DE LIVROS'
        names = ['APROVAÇÃO DE CONTAS.doc','CAPA.doc','Anexo 1.doc','anexo II.docx']
        self.make_files(folder,names)
        found = discover(self.root)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['name'],'ALLURE')
        self.assertFalse(found[0]['errors'])
        self.assertEqual([p.name for p in found[0]['files']],names)
    def test_short_names_with_other_subfolders_are_recognized_directly(self):
        self.make_files(self.root/'A',['APROVAÇÃO DE CONTAS.doc','CAPA.doc','Anexo1.doc','Anexo2.doc'])
        (self.root/'A'/'Contratos').mkdir()
        found = discover(self.root/'A')
        self.assertEqual(len(found),1)
        self.assertFalse(found[0]['errors'])
    def test_two_aliases_for_same_kind_are_ambiguous_unless_mapped(self):
        folder = self.root/'A'
        self.make_files(folder,['APROVAÇÃO DE CONTAS.doc','CAPA.doc','Anexo1.doc','Anexo2.doc'])
        (folder/'CAPA LIVRO.doc').write_text('AGOSTO/2026')
        found = discover(folder)[0]
        self.assertIsNone(found['files'][1])
        self.assertTrue(any('CAPA.doc' in e and 'CAPA LIVRO.doc' in e for e in found['errors']))
        chosen = [folder/'APROVAÇÃO DE CONTAS.doc',folder/'CAPA.doc',folder/'Anexo1.doc',folder/'Anexo2.doc']
        resolved = discover(folder,{str(folder):[str(p) for p in chosen]})[0]
        self.assertFalse(resolved['errors'])
        self.assertEqual(resolved['files'],chosen)
    def test_dedicated_closing_folder_precedes_loose_word_in_condo_root(self):
        home=self.root/'AMÉRICA - I';folder=home/'FECHAMENTO DE LIVROS'
        names=[stem+'.doc' for stem in FILES];self.make_files(folder,names)
        (home/'CAPA.doc').write_text('Documento avulso')
        for root in (self.root,home,folder):
            found=discover(root)
            self.assertEqual(len(found),1)
            self.assertEqual(found[0]['name'],'AMÉRICA - I')
            self.assertEqual(Path(found[0]['folder']),folder)
            self.assertFalse(found[0]['errors'])
        # Um vínculo explícito e válido na raiz continua sendo respeitado.
        chosen=[]
        for k in range(4):
            path=home/(f'documento escolhido {k}.doc');path.write_text('AGOSTO/2026');chosen.append(str(path))
        mapping={str(home/'..'/'AMÉRICA - I'):chosen}
        found=discover(home,mapping)[0]
        self.assertEqual(found['files'],[Path(p) for p in chosen]);self.assertFalse(found['errors'])

    def test_loose_root_word_does_not_resolve_ambiguous_dedicated_folders(self):
        home=self.root/'A'
        for child in ('FECHAMENTO DE LIVRO','FECHAMENTO DE LIVROS'):
            self.make_files(home/child,[stem+'.doc' for stem in FILES])
        (home/'CAPA.doc').write_text('Outro documento')
        found=discover(home)[0]
        self.assertTrue(all(p is None for p in found['files']))
        self.assertTrue(any('Mais de uma pasta' in error for error in found['errors']))

    def test_unavailable_bindings_of_other_condos_cannot_block_auto_discovery(self):
        home=self.root/'AMÉRICA - I';folder=home/'FECHAMENTO DE LIVROS'
        self.make_files(folder,[stem+'.doc' for stem in FILES])
        unrelated=self.root/'OUTRO CONDOMINIO'/'FECHAMENTO DE LIVROS'
        related=self.root/'REDE ANTIGA'/'AMÉRICA - I'/'FECHAMENTO DE LIVROS'
        original=Path.resolve
        def resolve(path,*args,**kwargs):
            if path==unrelated:raise AssertionError('Não deve acessar a rede de outro condomínio')
            if path==related:raise OSError('Compartilhamento antigo indisponível')
            return original(path,*args,**kwargs)
        with patch.object(Path,'resolve',resolve):
            found=discover(home,{str(unrelated):[],str(related):[]})[0]
        self.assertFalse(found['errors']);self.assertTrue(all(found['files']))

    def test_generation_preserves_short_names_and_does_not_create_canonical_duplicates(self):
        folder = self.root/'A'
        names = ['APROVAÇÃO DE CONTAS.doc','CAPA.doc','Anexo1.doc','Anexo2.doc']
        self.make_files(folder,names)
        condos = discover(self.root)
        word = FakeWord()
        generate(word,condos,{},self.root,11,2026,lambda msg:None,threading.Event(),
                 targets=output_targets(condos,11,2026),overwrite_sources=True,
                 prepare=lambda w,c:inspect_condo(w,c,11,2026,[]))
        self.assertEqual(sorted(p.name for p in folder.iterdir()),sorted(names))
        self.assertTrue(all('NOVEMBRO/2026' in (folder/name).read_text() for name in names))
    def test_saved_mapping_accepts_equivalent_directory_spelling(self):
        folder=self.root/'A'
        names=['primeiro.doc','segundo.doc','terceiro.doc','quarto.doc']
        self.make_files(folder,names)
        alias=str(folder/'..'/'A')
        found=discover(folder,{alias:[str(folder/name) for name in names]})
        self.assertFalse(found[0]['errors'])

if __name__=='__main__':
    unittest.main()

