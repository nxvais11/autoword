import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pdf_print import print_pdf,printer_info

class AdobePrinting(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'Relatorio obrigacoes TESTE.pdf';self.make_pdf()
        self.wp=Mock()
        self.wp.GetPrinter.return_value=dict(pDriverName='TEST Driver',pPortName='TEST_PORT',pDevMode=SimpleNamespace(Copies=1,Duplex=1))
        self.wp.JOB_STATUS_SPOOLING=8
        self.wp.JOB_STATUS_ERROR=2;self.wp.JOB_STATUS_OFFLINE=128;self.wp.JOB_STATUS_PAPEROUT=64
        self.wp.JOB_STATUS_BLOCKED_DEVQ=512;self.wp.JOB_STATUS_USER_INTERVENTION=1024
        self.cancel=threading.Event()
    def make_pdf(self):
        from test_central import pdf
        pdf(self.path,'SERVICOS S')
    def tearDown(self):self.tmp.cleanup()
    def job(self,**kwargs):return dict(JobId=42,pDocument=self.path.name,Status=0,**kwargs)
    def test_original_pdf_goes_to_adobe_with_exact_printer_driver_port_no_raster_or_default_change(self):
        before=self.path.read_bytes()
        self.wp.EnumJobs.side_effect=[[],[self.job()]]
        with patch.dict(sys.modules,{'win32print':self.wp}),patch('pdf_print.acrobat_executable',return_value=Path('Adobe/Acrobat.exe')),patch('pdf_print.subprocess.Popen') as start:
            self.assertTrue(print_pdf(self.path,'EPSON TEST',self.cancel))
        args=start.call_args.args[0]
        self.assertEqual(args,[str(Path('Adobe/Acrobat.exe')),'/t',str(self.path.resolve()),'EPSON TEST','TEST Driver','TEST_PORT'])
        self.assertEqual(before,self.path.read_bytes())
        self.wp.SetDefaultPrinter.assert_not_called();self.wp.SetPrinter.assert_not_called()
    def test_waits_until_spooling_finishes_and_ignores_other_documents(self):
        loading=self.job();loading['Status']=8
        self.wp.EnumJobs.side_effect=[[],[dict(JobId=7,pDocument='OTHER.pdf',Status=0)],[loading],[self.job()]]
        with patch.dict(sys.modules,{'win32print':self.wp}),patch('pdf_print.acrobat_executable',return_value=Path('Adobe.exe')),patch('pdf_print.subprocess.Popen'):
            self.assertTrue(print_pdf(self.path,'EPSON TEST',self.cancel))
        self.assertEqual(self.wp.EnumJobs.call_count,4)
    def test_does_not_retry_when_confirmation_is_missing(self):
        self.wp.EnumJobs.return_value=[]
        with patch.dict(sys.modules,{'win32print':self.wp}),patch('pdf_print.acrobat_executable',return_value=Path('Adobe.exe')),patch('pdf_print.subprocess.Popen') as start:
            with self.assertRaisesRegex(ValueError,'pode já ter sido enviado'):
                print_pdf(self.path,'EPSON TEST',self.cancel,timeout=0)
            start.assert_called_once()
    def test_wrong_copy_or_duplex_defaults_block_pdf_before_send(self):
        self.wp.GetPrinter.return_value['pDevMode'].Duplex=2
        with patch.dict(sys.modules,{'win32print':self.wp}),patch('pdf_print.subprocess.Popen') as start:
            with self.assertRaisesRegex(ValueError,'somente frente'):printer_info('EPSON TEST')
            start.assert_not_called()
    def test_cancellation_after_send_stops_without_resubmitting(self):
        self.wp.EnumJobs.return_value=[]
        with patch.dict(sys.modules,{'win32print':self.wp}),patch('pdf_print.acrobat_executable',return_value=Path('Adobe.exe')),patch('pdf_print.subprocess.Popen',side_effect=lambda *args,**kwargs:self.cancel.set()) as start:
            with self.assertRaisesRegex(ValueError,'pode ter sido enviado'):print_pdf(self.path,'EPSON TEST',self.cancel)
            start.assert_called_once()
