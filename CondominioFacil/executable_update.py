"""Atualização do executável pelo instalador oficial, após encerrar o processo."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from updater import fetch,latest_release,repo_url,version_tuple,UpdateError

ASSET='AutoWord-Setup.exe'
LIMIT=200*1024*1024

def prepare_update(data,repository,current):
    release=latest_release(repository)
    if version_tuple(release['tag_name'])<=version_tuple(current):
        return None
    assets=[a for a in release.get('assets',[]) if a.get('name')==ASSET]
    if len(assets)!=1:
        raise UpdateError('Instalador da nova versão indisponível.')
    asset=assets[0]
    import re
    expected=asset.get('digest','')
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',expected) or type(asset.get('id')) is not int:
        raise UpdateError('Instalador sem integridade verificável.')
    folder=Path(data)/'updates'
    path=folder/('AutoWord-'+release['tag_name']+'.exe')
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==expected.split(':')[1].lower():
        return {'path':str(path),'sha256':expected.split(':')[1].lower(),'version':release['tag_name']}
    content=fetch(repo_url(repository)+f'/releases/assets/{asset["id"]}',accept='application/octet-stream',timeout=60,limit=LIMIT)
    sha=hashlib.sha256(content).hexdigest()
    if sha!=expected.split(':')[1].lower() or not content.startswith(b'MZ'):
        raise UpdateError('A integridade do instalador não confere.')
    folder=Path(data)/'updates'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/('AutoWord-'+release['tag_name']+'.exe')
    temporary=path.with_suffix('.tmp')
    temporary.write_bytes(content)
    os.replace(temporary,path)
    return {'path':str(path),'sha256':sha,'version':release['tag_name']}

def launch_update(receipt,data,executable):
    path=Path(receipt['path']).resolve()
    if path.parent!=(Path(data)/'updates').resolve() or path.suffix.lower()!='.exe':
        raise UpdateError('Caminho do instalador inválido.')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:
        raise UpdateError('O instalador foi alterado. Abra o aplicativo para baixar novamente.')
    env=dict(os.environ,AUTOWORD_UPDATE_PID=str(os.getpid()),AUTOWORD_UPDATE_SETUP=str(path),AUTOWORD_UPDATE_DIR=str(Path(executable).resolve().parent))
    script="Wait-Process -Id ([int]$env:AUTOWORD_UPDATE_PID) -ErrorAction SilentlyContinue; Start-Process -FilePath $env:AUTOWORD_UPDATE_SETUP -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/AUTOWORDUPDATE=1',('/DIR=\"'+$env:AUTOWORD_UPDATE_DIR+'\"'))"
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
