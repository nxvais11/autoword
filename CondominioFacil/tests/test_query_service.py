import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from query_service import run_isolated,QueryInterrupted,smoke_query,consult


def blocked(send,path,partial=False):
    Path(path).write_text(str(os.getpid()))
    send(('progress','Lendo COSTA AMALFITANA/CAPA.doc'))
    if partial:send(('partial',dict(name='COSTA AMALFITANA',warnings=[],rows=[])))
    time.sleep(30)


def failed(send):
    send(('progress','Lendo arquivo protegido.doc'))
    raise ValueError('Arquivo indisponível')


class IsolatedQuery(unittest.TestCase):
    def test_timeout_releases_reader_identifies_file_and_next_query_works(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'pid')
            started=time.monotonic()
            with self.assertRaisesRegex(QueryInterrupted,'COSTA AMALFITANA/CAPA.doc'):
                run_isolated(blocked,(path,),timeout=.8,total_timeout=8)
            self.assertLess(time.monotonic()-started,8)
            self.assertTrue(Path(path).exists())
            self.assertEqual(run_isolated(smoke_query,total_timeout=8),'ok')
            import multiprocessing
            self.assertFalse(any(p.pid==int(Path(path).read_text()) for p in multiprocessing.active_children()))

    def test_cancel_interrupts_blocked_native_call_without_waiting_for_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'pid');cancel=threading.Event();progress=[]
            def update(text):progress.append(text);cancel.set()
            with self.assertRaisesRegex(QueryInterrupted,'cancelada'):
                run_isolated(blocked,(path,),cancel,update,total_timeout=8)
            self.assertTrue(progress)
            self.assertEqual(run_isolated(smoke_query,total_timeout=8),'ok')

    def test_partial_results_stay_marked_incomplete_and_errors_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_isolated(blocked,(str(Path(folder)/'pid'),True),timeout=.8,total_timeout=8)
            self.assertIn('COSTA AMALFITANA/CAPA.doc',result['query_incomplete'])
            self.assertIn(result['query_incomplete'],result['warnings'])
            with self.assertRaisesRegex(QueryInterrupted,'Arquivo indisponível'):
                run_isolated(failed,total_timeout=8)

    def test_real_lookup_reads_docx_in_child_without_modifying_sources(self):
        from zipfile import ZipFile
        from central_service import DEFAULTS
        from engine import FILES
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);name='COSTA AMALFITANA'
            closing=root/name/'FECHAMENTO DE LIVRO';closing.mkdir(parents=True)
            for stem in FILES:
                with ZipFile(closing/(stem+'.docx'),'w') as archive:
                    archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>SETEMBRO/2026</w:t></w:r></w:p></w:document>')
            files={p:p.read_bytes() for p in closing.iterdir()}
            settings=dict(DEFAULTS,root=str(root),statements=str(root/'Extratos'))
            cache={};progress=[]
            result=consult(settings,name,9,2026,{},[name],cache,threading.Event(),progress.append)
            self.assertEqual(result['name'],name)
            self.assertEqual([e['periods'] for e in result['document_periods']],[[('setembro',2026)]]*4)
            self.assertTrue(cache);self.assertTrue(progress)
            self.assertEqual(files,{p:p.read_bytes() for p in closing.iterdir()})
