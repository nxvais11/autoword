"""Localização determinística, comparação textual e plano da central por condomínio."""
import difflib
import json
import re
import unicodedata
from pathlib import Path
from pypdf import PdfReader
from word_service import discover,digest,print_layout,document_kind,filename_key,CLOSING_FOLDERS

DEFAULTS={'root':r'Z:\_CONDOMÍNIOS ATIVOS','statements':r'Z:\OFX E EXTRATOS','reports':'',
          'main_printer':'','report_printer':'','include_report':False,'overrides':{},
          'update_kinds':[0,1,2,3],'destination':'','create_subfolder':False}
ORDER=(1,0,2,3)
LABELS=('Aprovação de contas','Capa do livro','Anexo I','Anexo II')

def norm(value):
    value=unicodedata.normalize('NFKD',str(value)).casefold()
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in value if not unicodedata.combining(c))).strip()

def identity(value):
    value=norm(value)
    return re.sub(r'^(?:(?:condominio|do|da|de|edificio|residencial) )+','',value)

def owner(text,names):
    hay=' '+norm(text)+' '
    matched=[n for n in names if identity(n) and ' '+identity(n)+' ' in hay]
    longest=[n for n in matched if not any(n!=other and ' '+identity(n)+' ' in ' '+identity(other)+' ' for other in matched)]
    return longest[0] if len(longest)==1 else None

def catalog(settings):
    root=Path(settings['root'])
    names=[]
    for home in root.iterdir():
        if not home.is_dir() or home.is_symlink() or home.name.startswith('.'):continue
        try:
            entries=list(home.iterdir())
            closing=any(p.is_dir() and not p.is_symlink() and filename_key(p.name) in CLOSING_FOLDERS for p in entries)
            documents=any(p.is_file() and not p.name.startswith('~$') and p.suffix.lower() in ('.doc','.docx')
                          and document_kind(p.stem) is not None for p in entries)
            if closing or documents:names.append(home.name)
        except OSError:
            continue
    return sorted(names,key=norm)

def pdf_text(path,first=False):
    reader=PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('PDF protegido por senha.')
    if not first and reader.get_fields():raise ValueError('PDF com formulário: confira os valores manualmente.')
    pages=reader.pages[:1] if first else reader.pages
    texts=[]
    if not pages:raise ValueError('PDF sem páginas.')
    for page in pages:
        text=page.extract_text(extraction_mode='layout') or ''
        if len(re.sub(r'\s','',text))<15:
            raise ValueError('PDF digitalizado ou sem texto legível: comparação/identificação exige conferência manual.')
        texts.append(text)
    return '\n'.join(texts)

def tokens(text):
    text=unicodedata.normalize('NFKC',text).casefold().replace('\u00ad','')
    text=re.sub('[\u2010-\u2015\u2212]','-',text)
    text=text.replace('’',"'").replace('‘',"'").replace('“','"').replace('”','"')
    return re.findall(r'\w+|[^\w\s]',text)

def compare_texts(saved,current):
    left,right=tokens(saved),tokens(current)
    if not left or not right:raise ValueError('Texto insuficiente para comparar.')
    if left==right:return {'equal':True,'diff':'Nenhuma diferença textual identificada. Formatação e assinaturas gráficas não são comparadas.'}
    matcher=difflib.SequenceMatcher(None,left,right,autojunk=False)
    differences=[]
    for op,a,b,c,d in matcher.get_opcodes():
        if op=='equal':continue
        context=' '.join(left[max(0,a-8):a])
        differences.append(f'Contexto: {context}\nPDF salvo: '+(' '.join(left[a:b]) or '(ausente)')+'\nWord atual: '+(' '.join(right[c:d]) or '(ausente)'))
    return {'equal':False,'diff':'\n\n'.join(differences)}

def export_word(word,source,destination):
    doc=word.open(source,read_only=True)
    try:
        if doc.Revisions.Count:raise ValueError('Word contém alterações controladas pendentes; revise manualmente.')
        with print_layout(word):
            doc.ExportAsFixedFormat(OutputFileName=str(destination),ExportFormat=17,
                                   OpenAfterExport=False,OptimizeFor=0,BitmapMissingFonts=True)
    finally:doc.Close(0)
    if not Path(destination).is_file():raise ValueError('Word não produziu o PDF temporário.')

def compare_reports(word,pdf,source,workspace):
    before={str(p):digest(Path(p)) for p in (pdf,source)}
    target=Path(workspace)/'comparacao.pdf'
    export_word(word,source,target)
    result=compare_texts(pdf_text(pdf),pdf_text(target))
    if any(digest(Path(p))!=sha for p,sha in before.items()):raise ValueError('Relatório alterado durante a comparação. Consulte novamente.')
    result['hashes']=before
    return result

def search(settings,name,month,year,mappings=None,names=None):
    names=catalog(settings) if names is None else list(names)
    if name not in names:raise ValueError('Condomínio não encontrado na pasta principal configurada.')
    home=Path(settings['root'])/name
    overrides=settings.get('overrides',{}).get(name,{})
    warnings=[]
    try:
        condos=discover(home,mappings or {})
        condo=condos[0] if len(condos)==1 else None
    except (OSError,ValueError) as exc:
        condo=None;warnings.append('Fechamento: '+str(exc))
    rows=[]
    for kind in ORDER:
        path=Path(overrides[f'closing{kind}']) if overrides.get(f'closing{kind}') else condo['files'][kind] if condo else None
        rows.append({'group':'closing','label':LABELS[kind],'key':f'closing{kind}','path':path,'checked':True})
    period=f'{year}-{month:02}'
    explicit=overrides.get('statements:'+period)
    statements=[]
    if explicit:
        statements=[Path(p) for p in explicit]
    else:
        folder=Path(settings['statements'])/str(year)/f'{month:02}'
        try:
            for path in sorted(folder.iterdir(),key=lambda p:norm(p.name)):
                if not path.is_file() or path.suffix.lower()!='.pdf':continue
                identified=owner(path.stem,names)
                if identified is None:
                    try:
                        header='\n'.join(pdf_text(path,True).splitlines()[:25])[:1600]
                        identified=owner(header,names)
                    except Exception as exc:
                        warnings.append(path.name+': identificação pendente — '+str(exc))
                if identified==name:statements.append(path)
        except OSError as exc:warnings.append('Extratos: '+str(exc))
    if not statements:rows.append({'group':'statement','label':'Extrato não localizado','key':'statements:'+period,'path':None,'checked':True})
    for path in statements:rows.append({'group':'statement','label':'Extrato · '+path.name,'key':'statements:'+period,'path':path,'checked':True})
    reports=[];originals=[]
    for key,folder,extensions in [('report_pdf',Path(settings['reports']) if settings['reports'] else None,('.pdf',)),('report_word',home/'JURIDICO',('.doc','.docx'))]:
        candidates=[]
        if overrides.get(key):candidates=[Path(overrides[key])]
        elif folder:
            try:
                candidates=[p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions and 'obrig' in norm(p.stem)
                            and (key=='report_word' or owner(p.stem,names)==name)]
            except OSError as exc:warnings.append(key+': '+str(exc))
        if len(candidates)!=1:
            warnings.append(('PDF pessoal' if key=='report_pdf' else 'Word do Jurídico')+f': {len(candidates)} candidatos. Vincule o correto.')
        if key=='report_pdf':reports=candidates
        else:originals=candidates
    rows.append({'group':'obligations','label':'Relatório de obrigações','key':'report_pdf','path':reports[0] if len(reports)==1 else None,'checked':settings.get('include_report',False)})
    for row in rows:
        path=row['path']
        allowed=('.doc','.docx') if row['group']=='closing' else ('.pdf',)
        if path and (not path.is_file() or path.is_symlink() or path.suffix.lower() not in allowed):row['path']=None
        row['printer']=settings['report_printer'] if row['group']=='obligations' else settings['main_printer']
    return {'name':name,'period':period,'rows':rows,'word':originals[0] if len(originals)==1 else None,'warnings':warnings}

def selected_plan(result,selected,report_source='pdf',comparison=None):
    rows=[dict(row) for i,row in enumerate(result['rows']) if i in selected]
    if not rows:raise ValueError('Selecione pelo menos um documento.')
    for row in rows:
        if row['group']=='obligations':
            if not comparison:raise ValueError('Compare os relatórios antes de imprimir as obrigações.')
            if report_source=='word':row['path']=result['word']
            elif report_source!='pdf':raise ValueError('Escolha a versão do relatório.')
            row['comparison_hashes']=comparison['hashes']
        if not row['path']:raise ValueError(row['label']+': arquivo ausente ou ambíguo.')
        if not row['printer']:raise ValueError('Configure a impressora de '+row['label']+'.')
        row['hash']=digest(Path(row['path']))
    return rows

def verify_plan(rows):
    for row in rows:
        if digest(Path(row['path']))!=row['hash']:raise ValueError('Arquivo mudou; consulte novamente antes de imprimir.')
        for path,sha in row.get('comparison_hashes',{}).items():
            if digest(Path(path))!=sha:raise ValueError('Relatórios mudaram após a comparação. Compare novamente.')
