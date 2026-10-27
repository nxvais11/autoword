"""Atualizações de Releases do GitHub. Não lê nem substitui documentos do usuário."""
import ast
import hashlib
import io
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ASSET_NAME = 'CondominioFacil.zip'
MAX_BYTES = 32*1024*1024
EXTRA_FILES = {'INICIAR.bat','INICIAR.vbs','requirements.txt','LEIA-ME.md','update_config.json','pdf_ocr.ps1'}
REQUIRED = {'app.py','launcher.py','updater.py','version.py','engine.py','word_service.py','responsible_sheet.py','resignations.py','pdf_ocr.ps1','update_config.json','requirements.txt'}

class UpdateError(Exception):
    pass

def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',value)
    if not match:
        raise UpdateError('A versão publicada tem formato inválido.')
    return tuple(map(int,match.groups()))

def source_version(text):
    try:
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
                value = ast.literal_eval(node.value)
                version_tuple(value)
                return value
    except (SyntaxError,ValueError,TypeError):
        pass
    raise UpdateError('O pacote não informa uma versão válida.')

def credential_key(repository):
    return 'CondominioFacil/GitHub/'+repository

def saved_token(repository):
    try:
        import win32cred
        blob = win32cred.CredRead(credential_key(repository),win32cred.CRED_TYPE_GENERIC)['CredentialBlob']
        return blob.decode('utf-16-le') if isinstance(blob,bytes) else blob
    except Exception:
        return None

def store_token(repository,token):
    import win32cred
    win32cred.CredWrite({'Type':win32cred.CRED_TYPE_GENERIC,'TargetName':credential_key(repository),
        'UserName':'github-readonly','CredentialBlob':token.encode('utf-16-le'),
        'Persist':win32cred.CRED_PERSIST_LOCAL_MACHINE},0)

class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme!='https' or not (url.hostname in ('github.com','api.github.com') or (url.hostname or '').endswith('.githubusercontent.com')):
            raise UpdateError('Redirecionamento fora do serviço de atualizações.')
        result = super().redirect_request(req,fp,code,msg,headers,newurl)
        if result is not None:
            result.remove_header('Authorization')
        return result

def fetch(url,token=None,accept='application/vnd.github+json',timeout=3,limit=MAX_BYTES):
    req = urllib.request.Request(url,headers={'Accept':accept,'User-Agent':'CondominioFacil-updater','Cache-Control':'no-cache'})
    if token:
        # Headers não redirecionáveis: o token não segue para URLs de download assinadas.
        req.add_unredirected_header('Authorization','Bearer '+token)
    try:
        with urllib.request.build_opener(GitHubRedirect()).open(req,timeout=timeout) as response:
            data = response.read(limit+1)
        if len(data)>limit:
            raise UpdateError('O pacote ultrapassa o limite de tamanho.')
        return data
    except urllib.error.HTTPError as exc:
        raise UpdateError(f'GitHub retornou HTTP {exc.code}. Confira o repositório e a autorização de leitura.') from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise UpdateError('Não foi possível conectar ao GitHub. O aplicativo instalado continua disponível.') from None

def repo_url(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise UpdateError('Repositório inválido.')
    return 'https://api.github.com/repos/'+repository

def latest_release(repository,token=None):
    try:
        release = json.loads(fetch(repo_url(repository)+'/releases/latest',token,limit=1024*1024))
        version_tuple(release['tag_name'])
        if release.get('draft') or release.get('prerelease'):
            raise UpdateError('A versão ainda não foi publicada como estável.')
        return release
    except (KeyError,TypeError,ValueError):
        raise UpdateError('Resposta de versão inválida do GitHub.') from None

def download_release(repository,release,token=None):
    assets = [a for a in release.get('assets',[]) if a.get('name')==ASSET_NAME]
    if len(assets)!=1:
        raise UpdateError('O pacote da versão não foi encontrado de forma única.')
    asset = assets[0]
    digest = asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest):
        raise UpdateError('O GitHub não forneceu a impressão SHA-256 do pacote.')
    asset_id = asset.get('id')
    if type(asset_id) is not int or asset_id<=0:
        raise UpdateError('Identificador de pacote inválido.')
    data = fetch(repo_url(repository)+f'/releases/assets/{asset_id}',token,
                 accept='application/octet-stream',timeout=15)
    if hashlib.sha256(data).hexdigest()!=digest.split(':',1)[1].lower():
        raise UpdateError('A integridade do pacote não confere. A atualização foi cancelada.')
    return data

def package_files(data,version,repository):
    files = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            total = 0
            for info in z.infolist():
                if info.is_dir():
                    if info.filename!='CondominioFacil/':
                        raise UpdateError('Pasta não permitida no pacote.')
                    continue
                if not info.filename.startswith('CondominioFacil/'):
                    raise UpdateError('Estrutura de atualização inválida.')
                name = info.filename[len('CondominioFacil/'):]
                if not (re.fullmatch(r'[a-z][a-z0-9_]*\.py',name) or name in EXTRA_FILES):
                    raise UpdateError('O pacote contém arquivo não permitido: '+name)
                if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
                    raise UpdateError('Nome reservado no pacote.')
                if (info.external_attr>>16)&0o170000 == 0o120000:
                    raise UpdateError('Links simbólicos não são permitidos.')
                if name.casefold() in {n.casefold() for n in files}:
                    raise UpdateError('Arquivo repetido no pacote.')
                total+=info.file_size
                if total>MAX_BYTES:
                    raise UpdateError('Pacote descompactado muito grande.')
                files[name]=z.read(info)
        if not REQUIRED.issubset(files):
            raise UpdateError('O pacote está incompleto.')
        if version_tuple(source_version(files['version.py'].decode('utf-8'))) != version_tuple(version):
            raise UpdateError('A versão interna não corresponde à versão publicada.')
        config = json.loads(files['update_config.json'])
        if config.get('repository')!=repository:
            raise UpdateError('O pacote tenta mudar o repositório de atualizações.')
        return files
    except (zipfile.BadZipFile,UnicodeError,KeyError,ValueError) as exc:
        raise UpdateError('Pacote de atualização inválido.') from exc

def apply_package(root,files,after_install=None):
    root=Path(root).resolve()
    originals={}
    for name in files:
        path=root/name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise UpdateError('O destino de atualização não é um arquivo regular.')
        originals[name]=path.read_bytes() if path.exists() else None
    changed=[]
    with tempfile.TemporaryDirectory(prefix='.condominio_update_',dir=root.parent) as folder:
        stage=Path(folder)
        for name,data in files.items():
            (stage/name).write_bytes(data)
        try:
            for name in sorted(files,key=lambda name:(name=='version.py',name)):
                os.replace(stage/name,root/name)
                changed.append(name)
            if after_install:
                after_install()
        except Exception:
            for name in reversed(changed):
                if originals[name] is None:
                    (root/name).unlink(missing_ok=True)
                else:
                    (root/name).write_bytes(originals[name])
            raise
    # Evita reutilizar bytecode antigo com mesmo tamanho/data de modificação.
    import importlib.util
    for name in files:
        if name.endswith('.py'):
            Path(importlib.util.cache_from_source(str(root/name))).unlink(missing_ok=True)

def install_latest(root,repository,token=None,after_install=None):
    root=Path(root)
    current=source_version((root/'version.py').read_text(encoding='utf-8'))
    release=latest_release(repository,token)
    if version_tuple(release['tag_name'])<=version_tuple(current):
        return current,False
    data=download_release(repository,release,token)
    files=package_files(data,release['tag_name'],repository)
    apply_package(root,files,after_install)
    return source_version(files['version.py'].decode('utf-8')),True
