"""Conferência de serviços, datas e periodicidade no Word original."""
import re
import unicodedata
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from word_service import Word, digest


def normalize(text):
    text=unicodedata.normalize('NFKD',str(text)).casefold()
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in text if not unicodedata.combining(c))).strip()


def report_date(value):
    """Retorna data e precisão; mês/ano não inventa um dia para conferir prazos."""
    from datetime import date
    compact=re.sub(r'\s+','',str(value))
    match=re.fullmatch(r'(?:(\d{1,2})[/-])?(\d{1,2})[/-](\d{4})',compact)
    if not match:raise ValueError('data não reconhecida')
    day,month,year=match.groups()
    try:return date(int(year),int(month),int(day) if day else 1),bool(day)
    except ValueError:raise ValueError('data inválida') from None


def report_term(value):
    text=normalize(re.sub(r'(?<=\d)\s+(?=\d)','',str(value)))
    months={'mensal':1,'bimestral':2,'trimestral':3,'quadrimestral':4,
            'semestral':6,'anual':12,'bienal':24,'trienal':36,
            'quadrienal':48,'quinquenal':60}
    if text in months:return months[text],'months'
    match=re.fullmatch(r'(?:a cada )?(\d+)\s*(dias?|mes|meses|anos?)',text)
    if not match or int(match[1])<=0:raise ValueError('prazo não reconhecido; informe a periodicidade')
    count=int(match[1]);unit=match[2]
    return (count,'days') if unit.startswith('dia') else (count*12 if unit.startswith('ano') else count,'months')


def next_date(realized,term):
    import calendar
    from datetime import date,timedelta
    count,unit=term
    if unit=='days':return realized+timedelta(days=count)
    total=realized.year*12+realized.month-1+count
    year,month=divmod(total,12);month+=1
    return date(year,month,min(realized.day,calendar.monthrange(year,month)[1]))


def analyze_rows(tables,month,year):
    from datetime import date,timedelta
    date(year,month,1)
    due=[];issues=[];checks=[];found=False
    aliases={'servico':'service','servicos':'service','realizacao':'realized',
             'data realizacao':'realized','data da realizacao':'realized','prazo':'term',
             'proxima realizacao':'next','data proxima realizacao':'next'}
    labels={'service':'Serviços','realized':'Realização','term':'Prazo','next':'Próxima realização'}
    empty=lambda v:not str(v).strip() or bool(re.fullmatch(r'[-–—]+',str(v).strip()))
    for table in tables:
        columns=None
        for row in table:
            headers=[normalize(c) for c in row]
            if any(aliases.get(h)=='next' for h in headers):
                columns={aliases[h]:i for i,h in enumerate(headers) if h in aliases};found=True
                missing=[label for key,label in labels.items() if key not in columns]
                if missing:issues.append('Colunas ausentes no relatório: '+', '.join(missing)+'. Não foi possível conferir todos os prazos.')
                continue
            if columns is None or not row:continue
            if normalize(row[0]).startswith('observacoes'):break
            if len(row)<=max(columns.values()):
                if any(not empty(c) for c in row):issues.append('Linha incompleta no relatório: '+str(row[0]).strip()+'. Confira as quatro colunas.')
                continue
            values={key:str(row[index]).strip() for key,index in columns.items()}
            if all(empty(value) for value in values.values()):continue
            service=values.get('service') or '(serviço não informado)'
            realized=values.get('realized','');term=values.get('term','');following=values['next']
            context=f'{service} — realização: {realized or "não informada"}; prazo: {term or "não informado"}; próxima: {following or "não informada"}'
            check=dict(service=service,realized=realized,term=term,next=following,status='sem data',expected='')
            checks.append(check)
            automatic=normalize(following)=='renovacao automatica'
            following_date=realized_date=None
            precise_next=precise_realized=False
            row_issues=[]
            if 'service' in columns and not values.get('service'):row_issues.append('Informe o serviço desta linha.')
            if not empty(following) and not automatic:
                try:following_date,precise_next=report_date(following)
                except ValueError as exc:row_issues.append('Próxima realização: '+str(exc)+'.')
            if not empty(realized):
                try:realized_date,precise_realized=report_date(realized)
                except ValueError as exc:row_issues.append('Realização: '+str(exc)+'.')
            if following_date and (following_date.year,following_date.month)<(year,month):
                due.append(context+f' — PENDENTE: data anterior à competência {month:02}/{year}. Solicite a correção do relatório.')
                check['status']='pendente'
            if automatic:
                check['status']='renovação automática'
            elif following_date and realized_date and 'term' in columns:
                try:
                    interval=report_term(term)
                    if interval[1]=='days' and not precise_realized:
                        raise ValueError('prazo em dias exige a data completa da realização')
                    expected=next_date(realized_date,interval)
                    check['expected']=expected.strftime('%d/%m/%Y' if precise_realized else '%m/%Y')
                    if precise_realized and precise_next:
                        # Relatórios também usam o último dia da vigência inclusiva.
                        compatible=following_date==expected or (interval[1]=='months' and following_date==expected-timedelta(days=1))
                    else:compatible=(following_date.year,following_date.month)==(expected.year,expected.month)
                    if not compatible:row_issues.append('Prazo incompatível: próxima realização esperada em '+check['expected']+'. Confira e corrija os dados.')
                    elif check['status']!='pendente':check['status']='prazo compatível'
                except (ValueError,OverflowError) as exc:row_issues.append('Não foi possível conferir o prazo: '+str(exc)+'.')
            elif not automatic and following_date and 'realized' in columns and empty(realized):
                row_issues.append('Informe a realização para conferir o prazo.')
            elif not automatic and realized_date and empty(following):
                row_issues.append('Informe a próxima realização para conferir o prazo.')
            if row_issues:
                if check['status']!='pendente':check['status']='corrigir inconsistência'
                issues.extend(context+' — '+problem for problem in row_issues)
    if not found:issues.append('Coluna Próxima realização não localizada no Word original.')
    return dict(due=list(dict.fromkeys(due)),issues=list(dict.fromkeys(issues)),checks=checks)


def due_rows(tables,month,year):
    result=analyze_rows(tables,month,year)
    return result['due'],result['issues']


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
    """Cruza as colunas do Word original, sem editar o relatório."""
    old=set(result.get('obligation_issues',[]))|{result.get('due_notice','')}
    result['warnings']=[w for w in result.get('warnings',[]) if w not in old]
    path=result.get('word');due=[];issues=[];checks=[]
    if not path:issues=['Word original não localizado; conferência das obrigações não realizada.']
    else:
        try:
            before=digest(Path(path))
            analysis=analyze_rows(read_tables(path),month,year)
            due,issues,checks=analysis['due'],analysis['issues'],analysis['checks']
            if digest(Path(path))!=before:
                due=[];checks=[];issues=['Word mudou durante a leitura. Consulte novamente.']
        except Exception as exc:
            due=[];checks=[];issues=['Não foi possível conferir as obrigações: '+str(exc)]
    result['due_obligations']=due
    result['obligation_issues']=issues
    result['obligation_checks']=checks
    result['due_notice']=(f'Pendências anteriores à competência {month:02}/{year}. Solicite a correção do relatório antes de imprimir.\n'+'\n'.join(due)) if due else ''
    parts=[result['due_notice']] if due else []
    if issues:parts.append('Inconsistências ou dados que precisam de conferência/correção:\n'+'\n'.join(issues))
    result['obligation_notice']='\n\n'.join(parts) if path else ''
    if result['due_notice']:result['warnings'].insert(0,result['due_notice'])
    result['warnings'].extend(issues)
    return result
