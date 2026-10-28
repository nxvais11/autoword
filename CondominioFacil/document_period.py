"""Consulta somente leitura da competência dos fechamentos; cache por conteúdo."""
from contextlib import ExitStack
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from engine import MONTHS, REFERENCE, LONG_DATE, normalize
from word_service import Word, digest


def periods(text):
    values={(normalize(m[1]),int(m[3])) for m in REFERENCE.finditer(text)}
    values.update((normalize(m[3]),int(m[5])) for m in LONG_DATE.finditer(text))
    return sorted(values,key=lambda p:(p[1],[normalize(m) for m in MONTHS].index(p[0])))


def inspect_periods(result,cache=None,word_factory=None,cancel=None):
    """Não consulta modelos antigos nem a competência escolhida; lê os arquivos atuais."""
    cache=cache if cache is not None else {}
    entries=[]
    with ExitStack() as stack:
        service=None
        for row in result['rows']:
            if row['group']!='closing':continue
            entry={'label':row['label'],'periods':[],'issue':''}
            entries.append(entry)
            path=row.get('path')
            if not path:
                entry['issue']='arquivo não localizado';continue
            if cancel is not None and cancel.is_set():
                entry['issue']='consulta cancelada';continue
            try:
                path=Path(path);before=digest(path);key=(str(path),before)
                if key in cache:
                    entry['periods']=cache[key];continue
                if path.suffix.lower()=='.docx':
                    with ZipFile(path) as archive:
                        root=ET.fromstring(archive.read('word/document.xml'))
                    ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                    text='\n'.join(''.join(t.text or '' for t in p.iter(ns+'t')) for p in root.iter(ns+'p'))
                else:
                    if service is None:service=stack.enter_context((word_factory or Word)())
                    text=service.read(path)
                found=periods(text)
                if digest(path)!=before:raise ValueError('arquivo mudou durante a leitura; busque novamente')
                entry['periods']=found
                cache[key]=found
            except Exception as exc:entry['issue']='não foi possível ler: '+str(exc)
    result['document_periods']=entries
    return result


def period_summary(result):
    entries=result.get('document_periods',[])
    if not entries:return 'Competência dos Words: não identificada.'
    unique={tuple(p) for e in entries for p in e['periods']}
    incomplete=any(e['issue'] or not e['periods'] for e in entries)
    def label(p):return f'{MONTHS[[normalize(m) for m in MONTHS].index(p[0])].title()}/{p[1]}'
    if len(unique)==1 and not incomplete:
        return 'Competência dos Words: '+label(next(iter(unique)))
    parts=[]
    for e in entries:
        value=e['issue'] or ', '.join(label(p) for p in e['periods']) or 'competência não identificada'
        parts.append(e['label']+': '+value)
    prefix='Competências diferentes nos Words.' if len(unique)>1 else 'Competência dos Words: leitura incompleta.'
    return prefix+'\n'+'\n'.join(parts)
