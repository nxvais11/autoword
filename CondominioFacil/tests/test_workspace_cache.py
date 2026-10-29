import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_cache import load_cache,save_cache,cache_key


class WorkspaceCache(unittest.TestCase):
    def test_roundtrip_is_local_and_configuration_changes_invalidate_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'workspace_cache.json'
            value=dict(root='Z:/Condos',names=['ALFA'],condos=[dict(name='ALFA',folder='Z:/Condos/ALFA',files=[Path('Z:/Condos/ALFA/CAPA.doc'),None,None,None],errors=[],found=['CAPA.doc'])])
            save_cache(path,value['root'],{},value)
            with patch('workspace_cache.Path.resolve',side_effect=AssertionError('network')),patch('workspace_cache.Path.is_file',side_effect=AssertionError('network')):
                self.assertEqual(load_cache(path,value['root'],{}),value)
                self.assertIsNone(load_cache(path,'OUTRA PASTA',{}))
                self.assertIsNone(load_cache(path,value['root'],{'ALFA':['outro.doc']}))
            self.assertEqual(cache_key(value['root'],{}),cache_key(value['root'],{'__cache__':{'hash':'updated'}}))

    def test_corrupt_cache_is_ignored_and_interrupted_save_keeps_previous_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'workspace_cache.json';path.write_text('{broken')
            self.assertIsNone(load_cache(path,'Z:/Condos',{}))
            value=dict(root='Z:/Condos',names=[],condos=[]);save_cache(path,value['root'],{},value)
            before=path.read_bytes()
            with patch('workspace_cache.os.replace',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):save_cache(path,value['root'],{},dict(value,names=['NEW']))
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(list(Path(folder).iterdir()),[path])
