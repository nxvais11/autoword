import csv
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from responsible_sheet import read_table, associate, SheetMonitor, sheet_changes, identification_text
from engine import FILES, apply_text
from word_service import discover, inspect_condo, generate
from test_engine import FakeWord, APPROVAL

class Association(unittest.TestCase):
    def test_exact_headers_accent_case_spaces_and_unmatched(self):
        condos = [{'name':'Edifício Érica Cristine','folder':'/erica'}]
        row = {' Condomínio ': ' EDIFICIO  ERICA CRISTINE ', 'Nome completo':'Maria', 'CPF / RG':'001'}
        groups,warnings = associate([(2,row),(3,{' Condomínio ':'Sem pasta'})],condos,' Condomínio ')
        self.assertEqual(groups['/erica'][0],row)
        self.assertEqual(len(warnings),1)
        self.assertIn('Linha 3',warnings[0])
        self.assertIn(' Condomínio ',groups['/erica'][0])
    def test_ambiguous_name_is_not_guessed(self):
        groups,warnings = associate([(2,{'Condo':'A'})],[{'name':'A','folder':'/1'},{'name':'A','folder':'/2'}],'Condo')
        self.assertFalse(groups)
        self.assertIn('ambíguo',warnings[0])
    def test_explicit_code_to_folder(self):
        row = {'Código':'007','Nome':'Maria'}
        condos = [{'name':'Condominio A','folder':'/a'}]
        groups,_ = associate([(2,row)],condos,'Código',{'007':'/a'})
        self.assertEqual(groups['/a'][0]['Código'],'007')
        self.assertFalse(associate([(2,row)],condos,'Código',{'007':'/inexistente'})[0])
    def test_unknown_condominium_column(self):
        with self.assertRaises(ValueError):
            associate([(2,{'Nome':'A'})],[],'Condomínio')

class Placeholders(unittest.TestCase):
    def test_all_fields_keep_column_names(self):
        row = {'Nome completo':'Maria','Cargo':'Síndica','CPF / RG':'00123','Mandato até':'2027-12'}
        text = '{{Nome completo}} / {{CPF / RG}} / {{Mandato até}}'
        changed = sheet_changes(text,[row],{'role':'Cargo'})
        self.assertEqual(apply_text(text,changed),'Maria / 00123 / 2027-12')
        self.assertEqual(row['CPF / RG'],'00123')
    def test_multiple_responsibles_selector(self):
        rows = [{'Nome':'Maria','Cargo':'Síndica','CPF':'001','ID':'1'},
                {'Nome':'José','Cargo':'Conselheiro','CPF':'002','ID':'2'}]
        text = '{{Síndica|Nome}} {{ID=2|CPF}}'
        self.assertEqual(apply_text(text,sheet_changes(text,rows,{'role':'Cargo'})),'Maria 002')
        with self.assertRaisesRegex(ValueError,'ambíguo'):
            sheet_changes('{{Nome}}',rows,{'role':'Cargo'})
    def test_missing_column_is_clear_error(self):
        with self.assertRaisesRegex(ValueError,'sem coluna'):
            sheet_changes('{{CPF}}',[{'Nome':'A'}],{})
    def test_legacy_names_units_and_role(self):
        row = {'Nome':'Maria Silva','Cargo':'Síndica','Apto':'88'}
        changes = sheet_changes(APPROVAL,[row],{'name':'Nome','role':'Cargo','unit':'Apto'},legacy=True)
        text = apply_text(APPROVAL,changes)
        self.assertIn('Maria Silva',text)
        self.assertIn('Síndica',text)
        self.assertIn('apto 88',text)
        self.assertIn('endereço 12',text)
    def test_council_ambiguous_requires_original_name(self):
        row = {'Nome':'Maria','Cargo':'Conselheiro','Original':'Pessoa Conselho Dois'}
        with self.assertRaisesRegex(ValueError,'única'):
            sheet_changes(APPROVAL,[row],{'name':'Nome','role':'Cargo'},legacy=True)
        changes = sheet_changes(APPROVAL,[row],{'name':'Nome','role':'Cargo','old_name':'Original'},legacy=True)
        self.assertIn('Maria',apply_text(APPROVAL,changes))
    def test_template_signature_does_not_overlap_marker(self):
        text = 'Síndico (a) {{Nome}}    apto {{Apto}} Data ___/___/___'
        row = {'Nome':'Maria','Cargo':'Síndica','Apto':'88'}
        changes = sheet_changes(text,[row],{'name':'Nome','role':'Cargo','unit':'Apto'},legacy=True)
        self.assertEqual(apply_text(text,changes),'Síndico (a) Maria    apto 88 Data ___/___/___')

class Monitoring(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root/'responsaveis.csv'
        self.condos = [{'name':'A','folder':str(self.root/'A')},{'name':'B','folder':str(self.root/'B')}]
        self.rows = [{'Condomínio':'A','Nome':'Maria','CPF':'001','Extra':'x'},
                     {'Condomínio':'B','Nome':'José','CPF':'002','Extra':'x'}]
        self.mapping = {'condo':'Condomínio','name':'','role':''}
        self.write()
        self.monitor = SheetMonitor(self.path,self.mapping,self.condos)
    def tearDown(self):
        self.temp.cleanup()
    def write(self):
        with self.path.open('w',encoding='utf-8-sig',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=list(self.rows[0]),delimiter=';')
            writer.writeheader()
            writer.writerows(self.rows)
    def test_touch_and_same_data_do_not_change(self):
        _,changed,_ = self.monitor.poll()
        self.assertEqual(len(changed),2)
        os.utime(self.path,None)
        self.assertFalse(self.monitor.poll()[1])
        self.rows.reverse()
        self.write()
        self.assertFalse(self.monitor.poll()[1])
    def test_only_changed_condominium(self):
        self.monitor.poll()
        self.rows[0]['Nome'] = 'Outra Maria'
        self.write()
        groups,changed,_ = self.monitor.poll()
        self.assertEqual(changed,{self.condos[0]['folder']})
        self.assertEqual(groups[self.condos[0]['folder']][0]['Nome'],'Outra Maria')
    def test_restart_recovers_state_without_reimport_or_regeneration(self):
        self.monitor.poll()
        saved = dict(self.monitor.fingerprints)
        restarted = SheetMonitor(self.path,self.mapping,self.condos,saved)
        groups,changed,_ = restarted.poll()
        self.assertEqual(len(groups),2)
        self.assertFalse(changed)
        self.rows[0]['CPF']='009'
        self.write()
        restarted = SheetMonitor(self.path,self.mapping,self.condos,saved)
        self.assertEqual(restarted.poll()[1],{self.condos[0]['folder']})
    def test_removed_rows_are_affected_not_silently_kept(self):
        self.monitor.poll()
        self.rows = self.rows[1:]
        self.write()
        groups,changed,_ = self.monitor.poll()
        self.assertEqual(changed,{self.condos[0]['folder']})
        self.assertNotIn(self.condos[0]['folder'],groups)
    def test_failure_does_not_commit_snapshot(self):
        self.monitor.poll()
        original = self.monitor.raw_hash
        self.path.write_text('Nome;CPF\nMaria;001\n',encoding='utf-8')
        with self.assertRaises(ValueError):
            self.monitor.poll()
        self.assertEqual(self.monitor.raw_hash,original)
        with self.assertRaises(ValueError):
            self.monitor.require_current()
        self.write()
        self.assertFalse(self.monitor.poll()[1])
    def test_csv_encoding_and_headers_preserved(self):
        self.path.write_bytes(' Condomínio ;Nome completo;CPF\nA;José;001234\n'.encode('cp1252'))
        headers,records = read_table(self.path)
        self.assertEqual(headers,[' Condomínio ','Nome completo','CPF'])
        self.assertEqual(records[0][1]['Nome completo'],'José')
        self.assertEqual(records[0][1]['CPF'],'001234')
    def test_duplicate_headers_rejected(self):
        self.path.write_text('Nome;Nome\nA;B\n')
        with self.assertRaisesRegex(ValueError,'únicos'):
            read_table(self.path)
    def test_changed_column_order_does_not_regenerate(self):
        self.monitor.poll()
        with self.path.open('w',encoding='utf-8',newline='') as f:
            w = csv.DictWriter(f,fieldnames=list(reversed(self.rows[0])),delimiter=';')
            w.writeheader()
            w.writerows(self.rows)
        self.assertFalse(self.monitor.poll()[1])
    def test_end_to_end_only_affected_document_is_written(self):
        class CountingWord(FakeWord):
            def __init__(self):
                self.writes = []
            def write_copy(self,source,*args):
                self.writes.append(str(source))
                return super().write_copy(source,*args)
        for condo in self.condos:
            folder = Path(condo['folder'])
            folder.mkdir()
            for i,name in enumerate(FILES):
                text = APPROVAL if i==0 else 'AGOSTO/2026'
                if i==1:
                    text+=' {{Nome}} {{CPF}}'
                (folder/(name+'.doc')).write_text(text,encoding='utf-8')
        condos = discover(self.root)
        # A planilha está na pasta principal; discover só considera Word como seleção direta.
        groups,_,_ = self.monitor.poll()
        word,cache = CountingWord(),{}
        targets = {c['folder']:Path(c['folder'])/'2026-11' for c in condos}
        preview = {c['folder']:inspect_condo(word,c,11,2026,[],(0,1),groups[c['folder']],self.mapping) for c in condos}
        generate(word,condos,preview,self.root,11,2026,lambda s:None,threading.Event(),targets=targets,cache=cache)
        self.assertEqual(len(word.writes),4)
        cache = json.loads(json.dumps(cache))  # A configuração restaurada continua evitando regravações.
        word.writes.clear()
        generate(word,condos,preview,self.root,11,2026,lambda s:None,threading.Event(),targets=targets,cache=cache,automatic=True)
        self.assertEqual(word.writes,[])
        before = {str(p):p.stat().st_mtime_ns for t in targets.values() for p in t.iterdir()}
        word.writes.clear()
        self.rows[0]['CPF']='009'
        self.write()
        groups,changed,_ = self.monitor.poll()
        affected = [c for c in condos if c['folder'] in changed]
        preview = {c['folder']:inspect_condo(word,c,11,2026,[],(0,1),groups[c['folder']],self.mapping) for c in affected}
        generate(word,affected,preview,self.root,11,2026,lambda s:None,threading.Event(),targets=targets,cache=cache,automatic=True)
        self.assertEqual(word.writes,[str(Path(self.condos[0]['folder'])/(FILES[1]+'.doc'))])
        for target in targets.values():
            for p in target.iterdir():
                if p != targets[self.condos[0]['folder']]/(FILES[1]+'.doc'):
                    self.assertEqual(p.stat().st_mtime_ns,before[str(p)])
        word.writes.clear()
        self.rows[0]['Extra']='não aparece em documento algum'
        self.write()
        groups,changed,_ = self.monitor.poll()
        affected = [c for c in condos if c['folder'] in changed]
        preview = {c['folder']:inspect_condo(word,c,11,2026,[],(0,1),groups[c['folder']],self.mapping) for c in affected}
        generate(word,affected,preview,self.root,11,2026,lambda s:None,threading.Event(),targets=targets,cache=cache,automatic=True)
        self.assertEqual(word.writes,[])
        self.assertFalse(list(self.root.rglob('relatorio.*')))
        self.assertFalse(list(self.root.rglob('.temporario_*')))

class XlsxReader(unittest.TestCase):
    def test_identification_masks_preserve_zeroes(self):
        self.assertEqual(identification_text('12345','000"."000"."000"-"00'),'000.000.123-45')
        self.assertEqual(identification_text('12345',r'000\.000\.000\-00'),'000.000.123-45')
        self.assertEqual(identification_text('123','000000'),'000123')
        self.assertEqual(identification_text('123','0.00'),'123')
    def test_inline_shared_and_padded_identification(self):
        # OOXML mínimo em memória; não depende de Excel nem cria planilhas de saída.
        parts = {
            'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Responsáveis" r:id="r1"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels':'<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
            'xl/sharedStrings.xml':'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Condomínio</t></si><si><t>CPF</t></si></sst>',
            'xl/styles.xml':'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts><numFmt numFmtId="164" formatCode="000000"/></numFmts><cellXfs><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>',
            'xl/worksheets/sheet1.xml':'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Érica</t></is></c><c r="B2" s="1"><v>123</v></c></row></sheetData></worksheet>'}
        class FakeZip:
            def __init__(self,*args): pass
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def namelist(self): return list(parts)
            def read(self,path): return parts[path].encode('utf-8')
        with patch('responsible_sheet.zipfile.ZipFile',FakeZip):
            headers,rows = read_table('planilha.xlsx','Responsáveis')
            self.assertEqual(headers,['Condomínio','CPF'])
            self.assertEqual(rows,[(2,{'Condomínio':'Érica','CPF':'000123'})])
            parts['xl/worksheets/sheet1.xml'] = parts['xl/worksheets/sheet1.xml'].replace('<v>123</v>','<f>1+2</f>')
            with self.assertRaisesRegex(ValueError,'Fórmula sem resultado'):
                read_table('planilha.xlsx')

if __name__=='__main__':
    unittest.main()
