"""Usado pelo Actions após os testes; não requer upload manual do ZIP."""
import json
import os
import subprocess
from pathlib import Path
from build_release import APP,build,source_version,version_tuple

def gh(*args,check=True):
    return subprocess.run(['gh',*args],check=check,text=True,capture_output=True)

def main():
    repository=os.environ['GITHUB_REPOSITORY']
    base=source_version((APP/'version.py').read_text(encoding='utf-8'))
    major,minor,_=version_tuple(base)
    version=f'{major}.{minor}.{int(os.environ["GITHUB_RUN_NUMBER"])}'
    tag='v'+version
    if gh('release','view',tag,'--repo',repository,check=False).returncode==0:
        print('Versão já publicada: '+tag)
        return
    artifact=Path('dist/CondominioFacil.zip')
    build(artifact,version,repository)
    from build_windows import build as build_windows
    installer=build_windows(version)
    latest=gh('release','view','--repo',repository,'--json','tagName',check=False)
    set_latest=True
    if latest.returncode==0:
        set_latest=version_tuple(version)>version_tuple(json.loads(latest.stdout)['tagName'])
    gh('release','create',tag,str(artifact),str(installer),'--repo',repository,'--target',os.environ['GITHUB_SHA'],
       '--title','AutoWord '+version,'--notes','Versão publicada automaticamente após aprovação dos testes.',
       '--latest='+str(set_latest).lower())
    print('Publicado: '+tag)

if __name__=='__main__':
    main()
