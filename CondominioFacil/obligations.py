"""Leitura somente da coluna Próxima realização do Word original."""
import re
import unicodedata
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from word_service import Word, digest


def normalize(text):
    text=unicodedata.normalize('NFKD',str(text)).casefold()
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in text if not unicodedata.combining(c))).strip()


def due_rows(tables,month,year):
    due=[];issues=[];found=False
    for table in tables:
        column=None
        for row in table:
            headers=[normalize(c) for c in row]
            if 'proxima realizacao' in headers:
                column=headers.index('proxima realizacao');found=True;continue
            if column is None:continue
            if len(row)<=column:
                issues.append('Linha sem acesso à coluna Próxima realização.');continue
            value=row[column].strip()
            compact=re.sub(r'\s+','',value)
            if not compact or compact=='-' or normalize(value)=='renovacao automatica':continue
            match=re.fullmatch(r'(?:(\d{1,2})/)?(\d{1,2})/(\d{4})',compact)
            if not match:
                issues.append(f'{row[0]}: data não reconhecida ({value}).');continue
            day,m,y=match.groups();m=int(m);y=int(y)
            try:
                from datetime import date
                date(y,m,int(day) if day else 1)
            except ValueError:
                issues.append(f'{row[0]}: data inválida ({value}).');continue
            if (y,m)<=(year,month):
                suffix=' — anterior à competência' if (y,m)<(year,month) else ''
                due.append(f'{row[0].strip()}: {value}'+suffix)
    if not found:issues.append('Coluna Próxima realização não localizada no Word original.')
    return list(dict.fromkeys(due)),list(dict.fromkeys(issues))


def read_tables(path):
    if Path(path).suffix.lower()=='.docx':
        with ZipFile(path) as archive:
            root=ET.fromstring(archive.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        return [[[''.join(t.text or '' for t in cell.findall('.//w:t',ns))
                  for cell in row.findall('w:tc',ns)] for row in table.findall('w:tr',ns)]
                for table in root.findall('.//w:tbl',ns)]
    with Word() as service:
        doc=service.open(path,read_only=True)
        try:
            tables=[]
            for table in doc.Tables:
                rows=[]
                for row in table.Rows:
                    rows.append([cell.Range.Text.rstrip('\r\x07') for cell in row.Cells])
                tables.append(rows)
            return tables
        finally:doc.Close(0)


def check_obligations(result,month,year):
    """Aviso independente de o relatório estar selecionado para impressão."""
    path=result.get('word');due=[];issues=[]
    if not path:issues=['Word original não localizado; Próxima realização não verificada.']
    else:
        try:
            before=digest(Path(path))
            due,issues=due_rows(read_tables(path),month,year)
            if digest(Path(path))!=before:
                due=[];issues=['Word mudou durante a leitura. Consulte novamente.']
        except Exception as exc:issues=['Não foi possível verificar Próxima realização: '+str(exc)]
    result['due_obligations']=due
    result['due_notice']=(f'Há obrigações com Próxima realização até {month:02}/{year}, incluindo meses anteriores. Revise o Word original antes de imprimir.\n'+'\n'.join(due)) if due else ''
    if result['due_notice']:result['warnings'].insert(0,result['due_notice'])
    result['warnings'].extend(issues)
    return result
