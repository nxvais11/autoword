"""Regras de atualização; não depende do Windows nem do Word."""
import calendar
import re
import unicodedata
from dataclasses import dataclass

MONTHS = ('janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro').split()
FILES = ('APROVAÇÃO DE CONTAS', 'CAPA LIVRO', 'Prestação de Contas ANEXO I', 'Prestação de Contas ANEXO II')

def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value) if not unicodedata.combining(c)).casefold().strip()

@dataclass(frozen=True)
class Change:
    start: int
    end: int
    old: str
    new: str
    kind: str

def case_like(value, example):
    return value.upper() if example.isupper() else value.title() if example.istitle() else value

NAMED = '|'.join(MONTHS).replace('março',r'mar[çc]o')
HSPACE = r'[ \t\xa0\u202f]'
REFERENCE = re.compile(r'\b(' + NAMED + r')(' + HSPACE + r'*(?:/|-)' + HSPACE + r'*|' + HSPACE + r'+de' + HSPACE + r'+)(20\d{2})\b', re.I)
LONG_DATE = re.compile(r'\b(\d{1,2})(' + HSPACE + r'+de' + HSPACE + r'+)(' + NAMED + r')(' + HSPACE + r'+de' + HSPACE + r'+)(20\d{2})\b', re.I)
NUMERIC_DATE = re.compile(r'(?<![\w/.\-])(\d{1,2})(' + HSPACE + r'*([/-])' + HSPACE + r'*)(\d{1,2})(' + HSPACE + r'*\3' + HSPACE + r'*)(20\d{2})(?![\w/\-])')
NUMERIC_REFERENCE = re.compile(r'(?<![\w/.\-])(\d{1,2})(' + HSPACE + r'*[/-]' + HSPACE + r'*)(20\d{2})(?![\w/\-])')


def date_fields(text):
    dates=list(LONG_DATE.finditer(text))
    numeric=[m for m in NUMERIC_DATE.finditer(text) if 1<=int(m[1])<=31 and 1<=int(m[4])<=12]
    spans=[(m.start(),m.end()) for m in dates+numeric]
    def separate(m):return not any(m.start()<end and start<m.end() for start,end in spans)
    refs=[m for m in REFERENCE.finditer(text) if separate(m)]
    numbers=[m for m in NUMERIC_REFERENCE.finditer(text) if 1<=int(m[1])<=12 and separate(m)]
    return refs,dates,numeric,numbers


def date_baselines(text):
    refs,dates,numeric,numbers=date_fields(text)
    values={(normalize(m[1]),int(m[3])) for m in refs}
    values.update((normalize(m[3]),int(m[5])) for m in dates)
    values.update((normalize(MONTHS[int(m[4])-1]),int(m[6])) for m in numeric)
    values.update((normalize(MONTHS[int(m[1])-1]),int(m[3])) for m in numbers)
    return values


def plan(text, kind, month, year, rules=()):
    if not 1 <= month <= 12 or not 2000 <= year <= 2099:
        raise ValueError('Mês/ano fora do intervalo 2000–2099.')
    refs,dates,numeric,numbers=date_fields(text)
    baselines=date_baselines(text)
    # A atualização normaliza todas as referências reconhecidas para o destino,
    # mesmo quando a origem contém competências diferentes.
    changes = []
    for m in refs:
        changes.append(Change(m.start(), m.end(), m[0],
                       case_like(MONTHS[month-1], m[1]) + m[2] + str(year), 'Competência'))
    for m in dates:
        changes.append(Change(m.start(), m.end(), m[0],
                       str(calendar.monthrange(year, month)[1]) + m[2] +
                       case_like(MONTHS[month-1], m[3]) + m[4] + str(year), 'Data'))
    for m in numeric:
        value=(str(calendar.monthrange(year,month)[1])+m[2]+str(month).zfill(len(m[4]))+m[5]+str(year))
        changes.append(Change(m.start(),m.end(),m[0],value,'Data'))
    for m in numbers:
        value=str(month).zfill(len(m[1]))+m[2]+str(year)
        changes.append(Change(m.start(),m.end(),m[0],value,'Competência'))
    if kind == 0:
        for rule in rules:
            if not rule.get('enabled', True) or f'{year:04}-{month:02}' < rule['since']:
                continue
            for field in ('name', 'unit'):
                old, new = rule['old_'+field], rule['new_'+field]
                if old == new:
                    continue
                if not old or not new:
                    raise ValueError('Nome e apartamento não podem ficar vazios.')
                # Unidade é substituída somente no bloco de assinatura do responsável.
                if field == 'unit':
                    continue
                hits = list(re.finditer(r'(?<!\w)' + re.escape(old) + r'(?!\w)', text))
                if len(hits) != 1:
                    raise ValueError(f'Responsável "{old}": esperado 1 nome, encontrados {len(hits)}.')
                m = hits[0]
                changes.append(Change(m.start(), m.end(), old, new, 'Responsável'))
            if rule['old_unit'] != rule['new_unit']:
                name_hits = list(re.finditer(re.escape(rule['old_name']), text))
                if len(name_hits) != 1:
                    raise ValueError('Não foi possível localizar a assinatura para alterar apartamento.')
                pos = name_hits[0].end()
                match = re.match(r'[^\r\n]{0,100}?\bapto\.?[ \t]*(\S+)', text[pos:], re.I)
                if not match or match[1] != rule['old_unit']:
                    raise ValueError('Apartamento de origem não confere com o cadastro.')
                changes.append(Change(pos+match.start(1), pos+match.end(1), match[1], rule['new_unit'], 'Apartamento'))
    changes.sort(key=lambda c: c.start)
    for a, b in zip(changes, changes[1:]):
        if a.end > b.start:
            raise ValueError('Há alterações sobrepostas. Confira o cadastro de responsáveis.')
    return changes, next(iter(baselines)) if len(baselines) == 1 else None

def apply_text(text, changes):
    for c in reversed(changes):
        if text[c.start:c.end] != c.old:
            raise ValueError('O conteúdo mudou desde a conferência.')
        text = text[:c.start] + c.new + text[c.end:]
    return text

def utf16_offset(text, offset):
    return len(text[:offset].encode('utf-16-le')) // 2

def roster(text):
    result = []
    for line in re.split(r'[\r\n]', text):
        m = re.match(r'^\s*(?:(Síndic[oa]\s*(?:\(a\))?|Subsíndic[oa]\s*(?:\(a\))?|Conselheir[oa]s?\s*(?:\(as?\))?)\s+)?(.+?)\s+apto\.?\s*(\S+)', line, re.I)
        if m:
            result.append({'role': (m[1] or 'Conselheiro(a)').strip(), 'old_name': m[2].strip(),
                           'old_unit': m[3], 'new_name': m[2].strip(), 'new_unit': m[3],
                           'since': '2000-01', 'enabled': True})
    return result

