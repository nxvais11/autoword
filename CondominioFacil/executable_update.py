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

def find_update(repository,current):
    """Consulta somente metadados; o instalador é baixado após o clique no aviso."""
    from updater import saved_token
    release=latest_release(repository,saved_token(repository))
    if version_tuple(release['tag_name'])<=version_tuple(current):return None
    assets=[a for a in release.get('assets',[]) if a.get('name')==ASSET]
    if len(assets)!=1:raise UpdateError('Instalador da nova versão indisponível.')
    asset=assets[0]
    import re
    digest=asset.get('digest','')
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest) or type(asset.get('id')) is not int or asset['id']<=0:
        raise UpdateError('Instalador sem integridade verificável.')
    return dict(version=release['tag_name'],asset_id=asset['id'],sha256=digest.split(':')[1].lower())


def download_update(data,repository,offer):
    import re,tempfile
    from updater import saved_token
    version_tuple(offer['version'])
    if not re.fullmatch(r'[a-fA-F0-9]{64}',offer['sha256']) or type(offer['asset_id']) is not int or offer['asset_id']<=0:
        raise UpdateError('Dados da atualização inválidos.')
    sha=offer['sha256'].lower();folder=Path(data)/'updates'
    path=folder/('AutoWord-'+offer['version']+'.exe')
    if path.is_file():
        content=path.read_bytes()
        if content.startswith(b'MZ') and hashlib.sha256(content).hexdigest()==sha:
            return dict(path=str(path),sha256=sha,version=offer['version'])
    content=fetch(repo_url(repository)+f'/releases/assets/{offer["asset_id"]}',saved_token(repository),accept='application/octet-stream',timeout=60,limit=LIMIT)
    if hashlib.sha256(content).hexdigest()!=sha or not content.startswith(b'MZ'):
        raise UpdateError('A integridade do instalador não confere. Nada foi instalado.')
    folder.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=folder,suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as output:output.write(content);output.flush();os.fsync(output.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)
    return dict(path=str(path),sha256=sha,version=offer['version'])


def prepare_update(data,repository,current):
    offer=find_update(repository,current)
    return download_update(data,repository,offer) if offer else None


def consume_install_error(data):
    path=Path(data)/'updates'/'install-error.txt'
    try:
        text=path.read_text(encoding='utf-8-sig')[:2000];path.unlink()
        return text
    except FileNotFoundError:return ''
    except (OSError,UnicodeError):return 'Não foi possível consultar o resultado da atualização anterior.'


def launch_update(receipt,data,executable):
    path=Path(receipt['path']).resolve()
    if path.parent!=(Path(data)/'updates').resolve() or path.suffix.lower()!='.exe':
        raise UpdateError('Caminho do instalador inválido.')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:
        raise UpdateError('O instalador foi alterado. Abra o aplicativo para baixar novamente.')
    env=dict(os.environ,AUTOWORD_UPDATE_PID=str(os.getpid()),AUTOWORD_UPDATE_SETUP=str(path),AUTOWORD_UPDATE_DIR=str(Path(executable).resolve().parent),AUTOWORD_UPDATE_EXE=str(Path(executable).resolve()),AUTOWORD_UPDATE_ERROR=str(Path(data)/'updates'/'install-error.txt'))
    script=("$ErrorActionPreference='Stop'; "
            "Wait-Process -Id ([int]$env:AUTOWORD_UPDATE_PID) -ErrorAction SilentlyContinue; "
            "try { $p=Start-Process -FilePath $env:AUTOWORD_UPDATE_SETUP -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/AUTOWORDUPDATE=1',('/DIR=\"'+$env:AUTOWORD_UPDATE_DIR+'\"')) -Wait -PassThru; "
            "if ($p.ExitCode -notin @(0,3010)) { throw 'Installer failed' } } "
            "catch { try { [IO.File]::WriteAllText($env:AUTOWORD_UPDATE_ERROR,'Não foi possível instalar a atualização. Confira o acesso à pasta do aplicativo e tente novamente pelo aviso.') } catch {}; "
            "Start-Process -FilePath $env:AUTOWORD_UPDATE_EXE }")
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
