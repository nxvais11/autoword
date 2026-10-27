import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import apply_text,FILES
from resignations import parse_text,read_pdf,file_hash,validate_events,removal_changes,combine_changes,propose_signature
from word_service import inspect_condo,discover,generate,output_targets
from test_engine import APPROVAL,FakeWord

class Parsing(unittest.TestCase):
    def test_abbreviated_email_date_is_retained_without_picking_reply_date(self):
        data=parse_text('Impressão 05/05/2026. Em 28 de abr. de 2026, remetente escreveu: minha renúncia.')
        self.assertEqual(data['date_candidates'],['2026-05-05','2026-04-28'])
        self.assertEqual(data['since'],'')
    def test_signature_proposal_does_not_confirm_identity(self):
        from engine import roster
        name,warning=propose_signature('Pessoa Nome Completo','31',roster(APPROVAL))
        self.assertEqual(name,'Pessoa Conselho Dois')
        self.assertIn('Confira',warning)
    def test_effective_date_is_not_previous_appointment_date(self):
        text='DECLARAÇÃO DE RENÚNCIA. Eu, Pessoa Exemplo, inscrito no CPF. Unidade nº 82. Cargo de Conselheiro Fiscal. Ciente das atribuições desde a data de 20 de agosto de 2026. Cidade, 28 de agosto de 2026.'
        data=parse_text(text)
        self.assertEqual(data['name'],'Pessoa Exemplo')
        self.assertEqual(data['unit'],'82')
        self.assertEqual(data['since'],'')
        self.assertEqual(data['date_candidates'],['2026-08-20','2026-08-28'])
    def test_receipt_date_is_required_not_election_or_signing_date(self):
        text='Eu, Sr. Pessoa Exemplo, proprietário da unidade 071. RENÚNCIA ao cargo de Conselheiro Fiscal Suplente. Eleito em 18 de dezembro de 2025. A presente renúncia passa a produzir efeitos a partir da data de seu recebimento. Cidade, 01 de setembro de 2026.'
        data=parse_text(text)
        self.assertEqual(data['name'],'Pessoa Exemplo')
        self.assertEqual(data['since'],'')
        self.assertIn('recebimento',data['warning'])
        self.assertIn('Suplente',data['role'])
    def test_original_email_sender_not_administrator_or_reply_date(self):
        text='05/05/2026 E-mail\nAdministrador Exemplo\nAcusamos recebimento.\nEm 28 de abr. de 2026, remetente escreveu:\nVenho comunicar minha renúncia de membro do conselho. Podem acionar o suplente.\nPessoa Exemplo\nApt 113\n'
        data=parse_text(text)
        self.assertEqual(data['name'],'Pessoa Exemplo')
        self.assertEqual(data['since'],'')
        self.assertEqual(data['unit'],'113')
        self.assertNotIn('substituto',data)
    def test_explicit_effective_date_is_only_a_proposal(self):
        data=parse_text('Eu, Pessoa Exemplo, renuncio ao cargo de Conselheiro Fiscal a partir desta data 10/03/2026.')
        self.assertEqual(data['since'],'2026-03-10')
        self.assertNotIn('confirmed',data)
    def test_scanned_pdf_uses_windows_ocr_without_command_injection(self):
        fake_reader=SimpleNamespace(is_encrypted=False,pages=[SimpleNamespace(extract_text=lambda:'')])
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder).resolve()/"nome com ' aspas.pdf"
            source.write_bytes(b'fixture')
            result=SimpleNamespace(returncode=0,stdout=json.dumps({'pages':['RENÚNCIA de Pessoa Exemplo']}))
            with patch('pypdf.PdfReader',return_value=fake_reader),\
                 patch('resignations.os',SimpleNamespace(name='nt',environ=os.environ)),\
                 patch('resignations.subprocess.run',return_value=result) as run:
                text,mode=read_pdf(source)
            self.assertEqual(mode,'ocr')
            self.assertIn('RENÚNCIA',text)
            self.assertEqual(run.call_args.kwargs['env']['CONDOMINIO_PDF_PATH'],str(source))
            self.assertNotIn(str(source),run.call_args.args[0])
            self.assertNotIn('-ExecutionPolicy',run.call_args.args[0])

class Applying(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name).resolve()/'A'
        self.folder.mkdir()
        for i,name in enumerate(FILES):
            (self.folder/(name+'.doc')).write_text(APPROVAL if i==0 else 'AGOSTO/2026',encoding='utf-8')
        self.pdf=self.folder/'renuncia.pdf'
        self.pdf.write_bytes(b'fonte ficticia para teste de metadados')
        self.event={'path':str(self.pdf),'sha256':file_hash(self.pdf),'name':'Pessoa Conselho Um',
                    'original_name':'Pessoa Conselho Um','unit':'1','role':'Conselheiro Fiscal',
                    'since':'2026-11-05','confirmed':True}
        self.condos=discover(self.folder)
    def tearDown(self):
        self.tmp.cleanup()
    def test_before_and_after_effective_month(self):
        self.assertEqual(validate_events([self.event],10,2026),[])
        active=validate_events([self.event],11,2026)
        text=apply_text(APPROVAL,removal_changes(APPROVAL,active))
        self.assertNotIn('Pessoa Conselho Um',text)
        self.assertIn('Pessoa Conselho Dois',text)
        self.assertIn('Pessoa Conselho Tres',text)
        self.assertIn('Conselheiros',text)
    def test_pending_or_modified_pdf_blocks_applying(self):
        self.event['confirmed']=False
        with self.assertRaisesRegex(ValueError,'confirmação'):
            validate_events([self.event],11,2026)
        self.event['confirmed']=True
        self.pdf.write_bytes(b'alterado')
        with self.assertRaisesRegex(ValueError,'alterado'):
            validate_events([self.event],11,2026)
    def test_new_pdf_is_flagged_without_guessing(self):
        with self.assertRaisesRegex(ValueError,'Novo PDF'):
            inspect_condo(FakeWord(),self.condos[0],11,2026,[])
        docs=inspect_condo(FakeWord(),self.condos[0],11,2026,[],resignations=[self.event])
        self.assertNotIn('Pessoa Conselho Um',apply_text(docs[0]['text'],docs[0]['changes']))
    def test_unselected_approval_does_not_require_pdf_processing(self):
        self.assertEqual(len(inspect_condo(FakeWord(),self.condos[0],11,2026,[],kinds=(1,))),1)
    def test_duplicate_statements_remove_only_once(self):
        changes=removal_changes(APPROVAL,[self.event,self.event])
        self.assertEqual(len(changes),1)
    def test_wrong_unit_blocks_removal(self):
        self.event['unit']='99'
        with self.assertRaisesRegex(ValueError,'apartamento'):
            removal_changes(APPROVAL,[self.event])
    def test_explicit_replacement_is_preserved(self):
        from engine import plan
        rule={'old_name':'Pessoa Conselho Um','new_name':'Pessoa Substituta','old_unit':'01','new_unit':'90','since':'2026-11'}
        changes=plan(APPROVAL,0,11,2026,[rule])[0]
        notices=[]
        removals=removal_changes(APPROVAL,[self.event],changes,notices)
        self.assertFalse(removals)
        self.assertIn('Pessoa Substituta',apply_text(APPROVAL,changes))
        self.assertTrue(notices)
    def test_person_not_in_model_does_not_remove_another_signature(self):
        self.event['original_name']='Outra Pessoa'
        notices=[]
        self.assertEqual(removal_changes(APPROVAL,[self.event],notices=notices),[])
        self.assertTrue(notices)
    def test_repeated_direct_updates_keep_resignation_and_historical_month(self):
        word=FakeWord()
        models={}
        cache={}
        for month in (11,12):
            docs=inspect_condo(word,self.condos[0],month,2026,[],models=models,resignations=[self.event])
            generate(word,self.condos,{str(self.folder):docs},self.folder,month,2026,lambda s:None,threading.Event(),
                     targets=output_targets(self.condos,month,2026),overwrite_sources=True,models=models,cache=cache)
            self.assertNotIn('Pessoa Conselho Um',self.condos[0]['files'][0].read_text())
        historical=inspect_condo(word,self.condos[0],10,2026,[],models=models,resignations=[self.event])
        self.assertIn('Pessoa Conselho Um',apply_text(historical[0]['text'],historical[0]['changes']))
    def test_pdf_changed_during_generation_is_not_published(self):
        class ChangingWord(FakeWord):
            def write_copy(inner,*args,**kwargs):
                super().write_copy(*args,**kwargs)
                self.pdf.write_bytes(b'mudou durante a geracao')
        original=self.condos[0]['files'][0].read_bytes()
        docs=inspect_condo(FakeWord(),self.condos[0],11,2026,[],resignations=[self.event])
        messages=[]
        generate(ChangingWord(),self.condos,{str(self.folder):docs},self.folder,11,2026,messages.append,threading.Event(),
                 targets=output_targets(self.condos,11,2026),overwrite_sources=True)
        self.assertEqual(self.condos[0]['files'][0].read_bytes(),original)
        self.assertTrue(any('alterado' in message for message in messages))

if __name__=='__main__':
    unittest.main()
