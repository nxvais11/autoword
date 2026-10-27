"""Word COM em uma instância exclusiva. Os originais são abertos somente para leitura."""
import hashlib
import base64
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from engine import FILES, normalize, plan, apply_text, utf16_offset
from responsible_sheet import sheet_changes
from resignations import validate_events,removal_changes,combine_changes,find_pdfs

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def filename_key(name):
    return re.sub(r'[\s_-]+', ' ', normalize(name)).strip()

def document_kind(stem):
    """Classifica nomes completos conhecidos; não usa busca parcial ou similaridade."""
    name = filename_key(stem)
    if name == filename_key(FILES[0]):
        return 0
    if re.fullmatch(r'capa(?: (?:(?:do|de) )?livros?)?',name):
        return 1
    annex = re.fullmatch(r'(?:prestacao (?:de )?contas )?anexo ?(ii|i|1|2)',name)
    if annex:
        return 2 if annex[1] in ('i','1') else 3
    return None

def word_files(folder):
    return sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.is_symlink()
                  and p.suffix.lower() in ('.doc', '.docx') and not p.name.startswith('~$'))

CLOSING_FOLDERS = {'fechamento de livro','fechamento de livros','fechamento livro','fechamento livros','prestacao de contas'}

def _children(folder):
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.is_symlink()
                  and not p.name.startswith('.') and not re.fullmatch(r'20\d{2}[-_]\d{2}(?:[_ ].*)?',p.name))

def select_files(folder, paths):
    """Vinculação explícita: um arquivo distinto por tipo, todos na mesma pasta."""
    folder = Path(folder).resolve()
    if len(paths) != 4:
        raise ValueError('Selecione os quatro documentos.')
    files = [Path(path).resolve(strict=True) for path in paths]
    if len({str(path).casefold() for path in files}) != 4:
        raise ValueError('Cada tipo precisa de um arquivo diferente.')
    for path in files:
        if path.parent != folder or not path.is_file() or path.suffix.lower() not in ('.doc', '.docx') or path.name.startswith('~$'):
            raise ValueError('Escolha arquivos .doc ou .docx da mesma pasta do condomínio. Não selecione arquivos temporários ~$.')
    return {'folder': str(folder), 'name': folder.name, 'files': files, 'errors': [],
            'found': [p.name for p in word_files(folder)]}

def discover(root, mappings=None, progress=None):
    root = Path(root).resolve()
    # A seleção pode ser a pasta principal ou a pasta do próprio condomínio.
    # Mesmo nomes diferentes ficam visíveis para vinculação manual.
    root_files = word_files(root)
    children = _children(root)
    direct = any(document_kind(p.stem) is not None for p in root_files)
    closing_children = [p for p in children if filename_key(p.name) in CLOSING_FOLDERS]
    owners = [root] if direct or closing_children or (root_files and not children) else children
    result = []
    for owner in owners:
        folder = owner
        discovery_error = None
        try:
            candidates = root_files if owner==root else word_files(owner)
        except OSError as exc:
            candidates,discovery_error = [],str(exc)
        nested = []
        if not discovery_error and not any(document_kind(p.stem) is not None for p in candidates):
            try:
                nested = [p for p in _children(owner) if filename_key(p.name) in CLOSING_FOLDERS]
                if len(nested)==1:
                    folder = nested[0]
                    candidates = word_files(folder)
            except OSError as exc:
                candidates,discovery_error = [],str(exc)
        files, errors = [], []
        if discovery_error:
            errors.append('Não foi possível acessar a pasta: '+discovery_error)
        if len(nested)>1:
            errors.append('Mais de uma pasta de fechamento encontrada. Selecione a pasta correta individualmente.')
            candidates = []
        for kind,stem in enumerate(FILES):
            matches = [p for p in candidates if document_kind(p.stem) == kind]
            if len(matches) != 1:
                details = ' ('+'; '.join(p.name for p in matches)+')' if matches else ''
                errors.append(f'{stem}: encontrados {len(matches)} arquivos; esperado 1.{details}')
            files.append(matches[0] if len(matches) == 1 else None)
        condo = {'folder': str(folder), 'name': folder.name, 'files': files, 'errors': errors,
                 'found': [p.name for p in candidates]}
        mapping=None
        if mappings:
            mapping=mappings.get(str(folder))
            if mapping is None:
                mapping=next((v for k,v in mappings.items() if not k.startswith('__') and Path(k).resolve()==folder),None)
        if mapping is not None:
            try:
                condo = select_files(folder, mapping)
            except Exception as exc:
                condo['errors'].append('Seleção manual salva precisa de revisão: '+str(exc))
        condo['name'] = owner.name if folder!=owner else owner.parent.name if filename_key(owner.name) in CLOSING_FOLDERS else owner.name
        if progress:
            progress(condo['name'])
        result.append(condo)
    if not result:
        raise ValueError('Nenhum condomínio encontrado. Selecione a pasta que contém os quatro '
                         'arquivos Word ou a pasta principal com as subpastas dos condomínios. '
                         'Confira os nomes dos arquivos e suas extensões .doc ou .docx.')
    return result

class Word:
    def __enter__(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        self.app = None
        self.old_update_links = None
        try:
            self.app = win32com.client.DispatchEx('Word.Application')
            self.app.Visible = False
            self.app.ScreenUpdating = False
            self.app.DisplayAlerts = 0
            self.app.AutomationSecurity = 3  # Desabilita macros nos arquivos abertos.
            self.old_update_links = self.app.Options.UpdateLinksAtOpen
            self.app.Options.UpdateLinksAtOpen = False
            return self
        except Exception:
            if self.app is not None:
                if self.old_update_links is not None:
                    self.app.Options.UpdateLinksAtOpen = self.old_update_links
                self.app.Quit(0)
            pythoncom.CoUninitialize()
            raise

    def __exit__(self, *args):
        import pythoncom
        try:
            try:
                if self.old_update_links is not None:
                    self.app.Options.UpdateLinksAtOpen = self.old_update_links
            finally:
                self.app.Quit(0)
        finally:
            pythoncom.CoUninitialize()

    def open(self, path, read_only=True):
        doc = self.app.Documents.Open(FileName=str(Path(path).resolve()), ReadOnly=read_only,
            AddToRecentFiles=False, ConfirmConversions=False,
            PasswordDocument='__sem_senha__', WritePasswordDocument='__sem_senha__',
            NoEncodingDialog=True, OpenAndRepair=False)
        return doc

    def read(self, path):
        doc = self.open(path)
        try:
            if doc.ProtectionType != -1:
                raise ValueError('Documento protegido para edição.')
            if doc.Revisions.Count:
                raise ValueError('Documento contém alterações controladas pendentes. Revisar no Word.')
            # Campos dentro de caixas de texto ou cabeçalhos precisam de revisão específica.
            from engine import REFERENCE, LONG_DATE
            for story in doc.StoryRanges:
                if story.StoryType == 1:
                    continue
                current = story
                while current is not None:
                    if REFERENCE.search(current.Text) or LONG_DATE.search(current.Text):
                        raise ValueError('Há datas em cabeçalho, rodapé ou caixa de texto. Revisão necessária.')
                    current = current.NextStoryRange
            return doc.Content.Text
        finally:
            doc.Close(0)

    def write_copy(self, source, destination, original_text, changes, template=None):
        # O Word trabalha no disco local, evitando salvar e repaginar sobre a rede.
        with tempfile.TemporaryDirectory(prefix='condominio_word_') as workspace:
            local = Path(workspace)/Path(source).name
            self._write_local(source,local,original_text,changes,template)
            shutil.copyfile(local,destination)

    def _write_local(self, source, destination, original_text, changes, template=None):
        if template is not None:
            Path(destination).write_bytes(base64.b64decode(template))
        else:
            shutil.copy2(source, destination)
        os.chmod(destination, 0o600)
        doc = self.open(destination, False)
        try:
            if doc.Content.Text != original_text:
                raise ValueError('Conteúdo da cópia difere da conferência.')
            doc.TrackRevisions = False
            for c in reversed(changes):
                if c.old == c.new:
                    continue
                r = doc.Range(utf16_offset(original_text, c.start), utf16_offset(original_text, c.end))
                if r.Text != c.old:
                    raise ValueError('Posição de alteração divergiu no Word.')
                r.Text = c.new
            expected_text = apply_text(original_text,changes)
            if doc.Content.Text != expected_text:
                raise ValueError('A verificação do conteúdo final falhou.')
            doc.Save()
            if not doc.Saved or doc.Content.Text != expected_text:
                raise ValueError('O Word não confirmou a gravação do conteúdo esperado.')
        finally:
            doc.Close(0)
        if not Path(destination).is_file() or not Path(destination).stat().st_size:
            raise ValueError('O Word não produziu um documento válido para publicação.')

def inspect_condo(word, condo, month, year, rules, kinds=(0,1,2,3), sheet_rows=None, sheet_mapping=None, models=None, resignations=()):
    docs, baselines = [], set()
    if not kinds:
        raise ValueError('Selecione pelo menos um documento.')
    active_events=[]
    if 0 in kinds:
        known={Path(e['path']).resolve() for e in resignations}
        if any(path not in known for path in find_pdfs(condo)):
            raise ValueError('Novo PDF de renúncia encontrado. Leia e confirme em Opções → Renúncias em PDF.')
        active_events=validate_events(resignations,month,year)
    for kind in sorted(set(kinds)):
        path = condo['files'][kind]
        if path is None:
            raise ValueError(FILES[kind]+': arquivo ausente ou ambíguo. Selecione o arquivo manualmente.')
        before = digest(path)
        saved = (models or {}).get(str(path))
        if saved and saved['current_hash'] == before:
            text = saved['text']
        else:
            saved = None
            text = word.read(path)
        changes, baseline = plan(text, kind, month, year, [] if sheet_rows is not None else rules)
        if sheet_rows is not None:
            changes += sheet_changes(text, sheet_rows, sheet_mapping or {}, legacy=kind==0)
        notices=[]
        if kind==0:
            changes=combine_changes(changes,removal_changes(text,active_events,changes,notices))
        changes.sort(key=lambda c:c.start)
        if any(a.end>b.start for a,b in zip(changes, changes[1:])):
            raise ValueError('Campos de planilha e datas sobrepostos. Revise os marcadores no modelo.')
        if digest(path) != before:
            raise ValueError('Arquivo alterado durante a conferência. Tente novamente.')
        baselines.add(baseline)
        docs.append({'path': path, 'hash': before, 'text': text, 'changes': changes, 'kind':kind,
                     'model_hash':saved['template_hash'] if saved else before,
                     'template':saved['data'] if saved else None,'notices':notices,
                     'resignation_events':list(resignations) if kind==0 else []})
    if len(baselines) != 1:
        raise ValueError('Os documentos selecionados estão em competências diferentes.')
    return docs

def document_signature(doc):
    inputs = doc.get('model_hash',doc['hash']), tuple((c.start,c.end,c.old,c.new) for c in doc['changes'] if c.old != c.new)
    return hashlib.sha256(repr(inputs).encode('utf-8')).hexdigest()

def output_targets(condos, month, year, destination=None, create_subfolder=False):
    result = {}
    for condo in condos:
        folder = Path(destination).resolve() if destination else Path(condo['folder']).resolve()
        if destination and len(condos)>1:
            folder = folder/condo['name']
        result[condo['folder']] = folder/f'{year}-{month:02}' if create_subfolder else folder
    if len({str(p).casefold() for p in result.values()}) != len(result):
        raise ValueError('Dois condomínios apontam para a mesma pasta de saída.')
    return result

def generate(word, condos, preview, output_parent, month, year, log, cancel,
             existing_folder=None, targets=None, cache=None, on_generated=None, validate=None, automatic=False,
             overwrite_sources=False, models=None, prepare=None, progress=None):
    """Gera somente os documentos selecionados. Nenhum relatório é gravado.

    targets reutiliza destinos já gerados; cache evita regravar resultados iguais.
    Uma cópia temporária por documento alterado protege o destino até o Word salvar.
    """
    if existing_folder is not None and len(condos) != 1:
        raise ValueError('Escolha apenas um condomínio para salvar na pasta existente selecionada.')
    base = Path(existing_folder or output_parent).resolve()
    if existing_folder is not None and not base.is_dir():
        raise ValueError('A pasta existente selecionada não existe.')
    output = base/f'{year}-{month:02}' if existing_folder is not None else base/f'{year}-{month:02}_{datetime.now():%Y%m%d_%H%M%S_%f}'
    cache = cache if cache is not None else {}
    models = models if models is not None else {}
    completed = reviewed = canceled = written = 0
    for index,condo in enumerate(condos,1):
        if cancel.is_set():
            canceled += 1
            log(f"{condo['name']}: CANCELADO — não processado.")
            continue
        stage = None
        created_dirs = []
        try:
            if progress:
                progress(index,len(condos),condo['name'])
            if validate:
                validate()
            docs = preview.get(condo['folder'])
            if docs is None:
                docs=next((value for folder,value in preview.items() if Path(folder).resolve()==Path(condo['folder']).resolve()),None)
            if docs is None and prepare is not None:
                docs = prepare(word,condo)
            if not docs:
                raise ValueError('Sem conferência aprovada; consulte os avisos.')
            for d in docs:
                validate_events(d.get('resignation_events',[]),month,year)
                for notice in d.get('notices',[]):
                    log(condo['name']+': '+notice)
            target = Path(targets[condo['folder']]).resolve() if targets else output if existing_folder is not None else output/condo['name']
            # Sobrescrita de origem é explícita e limitada ao próprio documento selecionado.
            sources = {p.resolve() for p in condo['files'] if p is not None}
            for d in docs:
                dest = (target/d['path'].name).resolve()
                if dest in sources and (not overwrite_sources or dest != d['path'].resolve()):
                    raise ValueError('O destino coincide com um documento original sem autorização de substituição.')
            if target.is_symlink():
                raise ValueError('A subpasta de saída não pode ser um link simbólico.')
            pending = []
            for d in docs:
                if digest(d['path']) != d['hash']:
                    raise ValueError('Original alterado após a conferência. Confira novamente.')
                dest = target/d['path'].name
                if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                    raise ValueError('Destino não é um arquivo regular: '+str(dest))
                previous = cache.get(str(dest))
                if previous and previous[0] == document_signature(d) and dest.is_file() and (automatic or digest(dest) == previous[1]):
                    continue
                pending.append(d)
            if pending:
                snapshots = {str(d['path']): {'data':d.get('template') or base64.b64encode(d['path'].read_bytes()).decode('ascii'),
                    'text':d['text'],'template_hash':d.get('model_hash',d['hash'])}
                    for d in pending if (target/d['path'].name).resolve() == d['path'].resolve()}
                # O temporário fica fora dos originais e é removido inclusive em falhas.
                staging_parent = target.parent
                while not staging_parent.is_dir():
                    staging_parent = staging_parent.parent
                stage = Path(tempfile.mkdtemp(prefix='.temporario_', dir=staging_parent))
                for d in pending:
                    template = d.get('template') or snapshots.get(str(d['path']),{}).get('data')
                    if template:
                        word.write_copy(d['path'], stage/d['path'].name, d['text'], d['changes'],template=template)
                    else:
                        word.write_copy(d['path'], stage/d['path'].name, d['text'], d['changes'])
                if any(digest(d['path']) != d['hash'] for d in docs):
                    raise ValueError('Original mudou durante a geração.')
                if validate:
                    validate()
                for d in docs:
                    validate_events(d.get('resignation_events',[]),month,year)
                parent = target
                while not parent.exists():
                    created_dirs.append(parent)
                    parent = parent.parent
                target.mkdir(parents=True, exist_ok=True)
                for d in pending:
                    dest = target/d['path'].name
                    os.replace(stage/d['path'].name, dest)
                    written_hash = digest(dest)
                    cache[str(dest)] = document_signature(d), written_hash
                    if str(d['path']) in snapshots:
                        models[str(d['path'])] = dict(snapshots[str(d['path'])],current_hash=written_hash)
            if on_generated:
                on_generated(condo, target, docs)
            completed += 1
            written += len(pending)
            log(f"{condo['name']}: {len(pending)} documento(s) gerado(s); {len(docs)-len(pending)} sem mudança.")
        except Exception as exc:
            reviewed += 1
            log(f"{condo['name']}: REVISAR — {exc}")
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
            for directory in created_dirs:
                try:
                    directory.rmdir()  # Remove somente diretórios recém-criados que ficaram vazios.
                except OSError:
                    pass
    # Não deixa lotes vazios após erro/cancelamento.
    if existing_folder is None and not targets and output.is_dir() and not any(output.iterdir()):
        output.rmdir()
    log(f'Concluído: {completed}/{len(condos)} condomínios processados; {written} documento(s) gravado(s); '
        f'{reviewed} para revisão; {canceled} cancelado(s).')
    if targets:
        return Path(next(iter(targets.values())))
    return output
