"""Lista local para abertura rápida; não substitui a validação dos documentos."""
import hashlib
import json
import os
import tempfile
from pathlib import Path


def cache_key(root,mappings):
    bindings={k:v for k,v in mappings.items() if not k.startswith('__')}
    value=json.dumps([str(root),bindings],sort_keys=True,ensure_ascii=False,default=str)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def load_cache(path,root,mappings):
    try:
        saved=json.loads(Path(path).read_text(encoding='utf-8'))
        if saved.get('schema')!=1 or saved.get('key')!=cache_key(root,mappings):return None
        value=saved['workspace']
        if not isinstance(value['names'],list) or not isinstance(value['condos'],list):return None
        if value['root']!=str(root) or not all(isinstance(n,str) for n in value['names']):return None
        for condo in value['condos']:
            if not isinstance(condo['name'],str) or not isinstance(condo['folder'],str):return None
            if not isinstance(condo['files'],list) or len(condo['files'])!=4 or not all(p is None or isinstance(p,str) for p in condo['files']):return None
            if not all(isinstance(condo[k],list) and all(isinstance(v,str) for v in condo[k]) for k in ('errors','found')):return None
            condo['files']=[Path(p) if p else None for p in condo['files']]
        return value
    except (OSError,ValueError,TypeError,KeyError,AttributeError):return None


def save_cache(path,root,mappings,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(dict(schema=1,key=cache_key(root,mappings),workspace=value),ensure_ascii=False,default=str)
    fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as output:output.write(text)
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)
