"""Leitura local de renúncias e exclusão de assinaturas confirmadas pelo usuário."""
import calendar
import hashlib
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path
from engine import MONTHS,Change,normalize,roster

def key(value):
    return ' '.join(normalize(value).split())

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_pdf(path):
    from pypdf import PdfReader
    path=Path(path).resolve()
    reader=PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('PDF protegido por senha; leitura não realizada.')
    if not 1<=len(reader.pages)<=30:
        raise ValueError('A renúncia deve ter entre 1 e 30 páginas.')
    pages=[page.extract_text() or '' for page in reader.pages]
    if all(len(text.strip())>=30 for text in pages):
        return '\n'.join(pages),'texto'
    if os.name!='nt':
        raise ValueError('PDF digitalizado: OCR local disponível no Windows. Os dados podem ser informados manualmente.')
    env=os.environ.copy()
    env['CONDOMINIO_PDF_PATH']=str(path)
    script=Path(__file__).with_name('pdf_ocr.ps1').read_text(encoding='utf-8')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-STA','-Command',script],
        env=env,capture_output=True,encoding='utf-8-sig',errors='replace',timeout=180,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ValueError('OCR do Windows indisponível ou não concluiu a leitura. Confira idioma de OCR ou informe os dados manualmente.')
    recognized=json.loads(result.stdout)['pages']
    if isinstance(recognized,str):
        recognized=[recognized]
    if len(recognized)!=len(pages):
        raise ValueError('O OCR não retornou todas as páginas.')
    return '\n'.join(text if len(text.strip())>=30 else recognized[i] for i,text in enumerate(pages)),'ocr'

def dates(text):
    result=[]
    months={normalize(m):i for i,m in enumerate(MONTHS,1)}
    months.update({normalize(m[:3]):i for i,m in enumerate(MONTHS,1)})
    pattern=r'(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)|\b(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]{3,9})\.?\s+de\s+(20\d{2})\b'
    for m in re.finditer(pattern,text,re.I):
        try:
            value=date(int(m[3] or m[6]),int(m[2]) if m[2] else months[normalize(m[5])],int(m[1] or m[4]))
            if value.isoformat() not in result:
                result.append(value.isoformat())
        except (ValueError,KeyError):
            continue
    return result

def parse_text(text):
    flat=' '.join(text.split())
    name=''
    m=re.search(r'\bEu\s*,?\s*(?:(?:Sr|Sra)\.?\s+)?(.{4,90}?)(?:,|\s+inscrit[oa]\b|\s+propriet[aá]ri[oa]\b)',flat,re.I)
    if m:
        name=m[1].strip()
    if not name:
        m=re.search(r'(?m)^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .]{4,80})\s*\n\s*(?:Apt|Apto|Unidade)\.?\s*(\d+)',text,re.I)
        if m:
            name=m[1].strip()
    unit=re.search(r'\b(?:unidade|apto?|apartamento)\s*(?:n[ºo°.]?\s*)?([0-9]{1,5}[A-Za-z]?)\b',flat,re.I)
    role=re.search(r'(?:cargo\s+de\s+)(conselheir[oa](?:\s+fiscal)?(?:\s+suplente)?|s[ií]ndic[oa]|subs[ií]ndic[oa])\b',flat,re.I)
    if not role and 'conselho' in key(flat):
        role_value='Conselheiro(a)'
    else:
        role_value=role[1].strip() if role else ''
    all_dates=dates(flat)
    since=''
    reason='Confirme a data de início dos efeitos; não será adotada automaticamente uma data de posse, impressão ou resposta de e-mail.'
    if re.search(r'(?:a\s+partir|efeitos).*?(?:recebimento|protocolo)',flat,re.I):
        reason='O documento vincula os efeitos ao recebimento/protocolo. Informe essa data, não a data de assinatura.'
    else:
        effective=re.search(r'(?:a\s+partir\s+(?:desta\s+data\s*)?|efeitos\s+a\s+partir\s+de\s+)(.{0,45})',flat,re.I)
        if effective:
            values=dates(effective[1])
            if len(values)==1:
                since=values[0]
                reason='Data de efeitos localizada no texto; confirme a leitura.'
    return {'name':name,'role':role_value,'unit':unit[1] if unit else '',
            'since':since,'date_candidates':all_dates,'warning':reason,
            'has_renunciation':bool(re.search(r'ren[uú]ncia|renuncio',flat,re.I))}

def load_pdf(path,condos=()):
    before=file_hash(path)
    text,mode=read_pdf(path)
    if file_hash(path)!=before:
        raise ValueError('O PDF mudou durante a leitura. Leia novamente.')
    result=parse_text(text)
    result['condo_candidates']=[c['folder'] for c in condos if re.search(r'(?<!\w)'+re.escape(key(c['name']))+r'(?!\w)',key(text))]
    result.update(path=str(Path(path).resolve()),sha256=before,mode=mode,confirmed=False)
    # O texto bruto, CPFs e e-mails não são guardados no cadastro da aplicação.
    return result

def propose_signature(name,unit,signatures):
    exact=[s for s in signatures if key(s['old_name'])==key(name)]
    if len(exact)==1:
        return exact[0]['old_name'],''
    if name.strip() and unit:
        candidates=[s for s in signatures if s['old_unit'].lstrip('0')==unit.lstrip('0')
                    and key(s['old_name']).split()[0]==key(name).split()[0]]
        if len(candidates)==1:
            return candidates[0]['old_name'],'Nome proposto pelo primeiro nome e unidade. Confira a correspondência antes de marcar Conferido.'
    return name,'Não foi possível associar de forma única à assinatura. Confira o nome exato no Word.'

def validate_events(events,month,year):
    end=date(year,month,calendar.monthrange(year,month)[1])
    active=[]
    for event in events:
        if file_hash(event['path'])!=event['sha256']:
            raise ValueError('Um PDF de renúncia foi alterado. Leia e confirme novamente antes de aplicar.')
        if event.get('ignored'):
            continue
        if not event.get('confirmed'):
            raise ValueError('Há PDF de renúncia aguardando confirmação em Opções → Renúncias em PDF.')
        since=date.fromisoformat(event['since'])
        if since<=end:
            active.append(event)
    return active

def removal_changes(text,events,other_changes=(),notices=None):
    changes=[]
    signatures=roster(text)
    for event in events:
        original=event.get('original_name') or event['name']
        candidates=[s for s in signatures if key(s['old_name'])==key(original)]
        if not candidates:
            if notices is not None:
                notices.append('Renúncia: '+original+' não tem assinatura neste modelo; nenhuma outra foi removida.')
            continue  # A pessoa não tem assinatura neste modelo; nenhuma outra é retirada.
        if len(candidates)!=1:
            raise ValueError('Assinatura ambígua para a renúncia de '+original)
        signature=candidates[0]
        if event.get('unit') and signature['old_unit'].lstrip('0')!=event['unit'].lstrip('0'):
            raise ValueError('O apartamento da renúncia diverge da assinatura: '+original)
        hits=list(re.finditer(re.escape(signature['old_name']),text))
        if len(hits)!=1:
            raise ValueError('Nome repetido no modelo; a exclusão requer revisão: '+original)
        hit=hits[0]
        # Um substituto explicitamente cadastrado continua valendo: a renúncia é da pessoa anterior.
        replacement=next((c for c in other_changes if c.start==hit.start() and c.end==hit.end()
                          and key(c.new)!=key(hit[0]) and c.new.strip()),None)
        if replacement:
            if notices is not None:
                notices.append('Renúncia: substituto cadastrado preservado no lugar de '+original+'.')
            continue
        start=max(text.rfind('\r',0,hit.start()),text.rfind('\n',0,hit.start()))+1
        after=re.search(r'[\r\n]',text[hit.end():])
        end=hit.end()+after.end() if after else len(text)
        # Remove a linha de assinatura em branco associada, sem atravessar o próximo texto real.
        count=0
        while count<6 and end<len(text):
            line=re.match(r'([^\r\n]*)(?:\r\n|\r|\n|$)',text[end:])
            if not line or not line[0] or (line[1].strip() and not re.fullmatch(r'[_ \t]+',line[1])):
                break
            end+=len(line[0]);count+=1
        prefix=text[start:hit.start()]
        keep=prefix.strip()+'\r' if re.search(r'conselheir[oa]s\b',prefix,re.I) else ''
        changes.append(Change(start,end,text[start:end],keep,'Renúncia confirmada'))
    # Duas declarações da mesma pessoa não apagam duas vezes o mesmo bloco.
    return sorted({(c.start,c.end):c for c in changes}.values(),key=lambda c:c.start)

def combine_changes(changes,removals):
    filtered=[c for c in changes if not any(r.start<=c.start and c.end<=r.end for r in removals)]
    return sorted(filtered+removals,key=lambda c:c.start)

def find_pdfs(condo):
    folder=Path(condo['folder'])
    roots=[folder]
    if key(folder.name) in ('fechamento de livro','fechamento de livros','fechamento livro','fechamento livros','prestacao de contas'):
        roots.append(folder.parent)
    for root in list(roots):
        for sub in root.iterdir():
            if sub.is_dir() and not sub.is_symlink() and key(sub.name) in ('renuncias','assembleias','atas'):
                roots.append(sub)
    return sorted({p.resolve() for root in roots for p in root.iterdir()
                   if p.is_file() and not p.is_symlink() and p.suffix.lower()=='.pdf' and 'renuncia' in key(p.stem)})
