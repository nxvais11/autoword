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

NAMED = '|'.join(MONTHS)
REFERENCE = re.compile(r'\b(' + NAMED + r')([ \t]*/[ \t]*)(20\d{2})\b', re.I)
LONG_DATE = re.compile(r'\b(\d{1,2})([ \t]+de[ \t]+)(' + NAMED + r')([ \t]+de[ \t]+)(20\d{2})\b', re.I)

def plan(text, kind, month, year, rules=()):
    if not 1 <= month <= 12 or not 2000 <= year <= 2099:
        raise ValueError('Mês/ano fora do intervalo 2000–2099.')
    refs = list(REFERENCE.finditer(text))
    dates = list(LONG_DATE.finditer(text)) if kind == 0 else []
    expected = 3 if kind == 0 else 1
    if len(refs) != expected or (kind == 0 and len(dates) != 1):
        raise ValueError(f'Padrão diferente: {len(refs)} referências MÊS/ANO (esperado {expected}); '
                         f'{len(dates)} datas por extenso (esperado {1 if kind == 0 else 0}). Revisar arquivo.')
    baselines = {(normalize(m[1]), int(m[3])) for m in refs}
    baselines.update((normalize(m[3]), int(m[5])) for m in dates)
    if len(baselines) != 1:
        raise ValueError('As referências de mês/ano divergem dentro do documento. Revisar arquivo.')
    changes = []
    for m in refs:
        changes.append(Change(m.start(), m.end(), m[0],
                       case_like(MONTHS[month-1], m[1]) + m[2] + str(year), 'Competência'))
    for m in dates:
        changes.append(Change(m.start(), m.end(), m[0],
                       str(calendar.monthrange(year, month)[1]) + m[2] +
                       case_like(MONTHS[month-1], m[3]) + m[4] + str(year), 'Data'))
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
    return changes, next(iter(baselines))

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
