"""Monta um pacote de programa sem documentos, configurações locais ou credenciais."""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
APP=PROJECT/'CondominioFacil'
sys.path.insert(0,str(APP))
from updater import EXTRA_FILES,package_files,source_version,version_tuple

def build(output,version=None,repository=None):
    version=version or source_version((APP/'version.py').read_text(encoding='utf-8'))
    version_tuple(version)
    config=json.loads((APP/'update_config.json').read_text(encoding='utf-8'))
    if repository:
        config['repository']=repository
    files={p.name:p.read_bytes() for p in sorted(APP.iterdir())
           if p.is_file() and (re.fullmatch(r'[a-z][a-z0-9_]*\.py',p.name) or p.name in EXTRA_FILES)}
    files['version.py']=(f'VERSION = {version!r}\n').encode('utf-8')
    files['update_config.json']=(json.dumps(config,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in sorted(files.items()):
            z.writestr('CondominioFacil/'+name,content)
    package_files(output.read_bytes(),version,config['repository'])
    return version

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='dist/CondominioFacil.zip')
    parser.add_argument('--version')
    parser.add_argument('--repository')
    args=parser.parse_args()
    print(build(args.output,args.version,args.repository))
