"""Importação e monitoramento de responsáveis, sem dependências adicionais."""
import csv
import hashlib
import io
import json
import posixpath
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from engine import Change, normalize, roster

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def identification_text(value, code):
    """Máscaras de identificação com zeros e separadores literais do Excel."""
    if not re.fullmatch(r'\d+',value):
        return value
    parts, i = [], 0
    code = code.split(';',1)[0]
    while i < len(code):
        char = code[i]
        if char=='0':
            parts.append(None)
        elif char=='"':
            end = code.find('"',i+1)
            if end<0:
                return value
            parts.append(code[i+1:end])
            i=end
        elif char=='\\' and i+1<len(code):
            i+=1
            parts.append(code[i])
        elif char in '- /()':
            parts.append(char)
        else:
            return value
        i+=1
    width = parts.count(None)
    if not width or len(value)>width:
        return value
    digits = iter(value.zfill(width))
    return ''.join(next(digits) if p is None else p for p in parts)

def _xlsx_sheets(z):
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    targets = {e.attrib['Id']: e.attrib['Target'] for e in rels}
    result = {}
    for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS):
        rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        target = targets[rid]
        result[sheet.attrib['name']] = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
    return result

def sheet_names(path):
    if Path(path).suffix.lower() == '.xlsx':
        with zipfile.ZipFile(path) as z:
            return list(_xlsx_sheets(z))
    return ['']

def _xlsx_rows(path, sheet):
    with zipfile.ZipFile(path) as z:
        sheets = _xlsx_sheets(z)
        selected = sheet or next(iter(sheets))
        if selected not in sheets:
            raise ValueError('A aba selecionada não existe mais: '+selected)
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(t.text or '' for t in e.findall('.//s:t', NS))
                      for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        formats, styles = {}, []
        if 'xl/styles.xml' in z.namelist():
            style_root = ET.fromstring(z.read('xl/styles.xml'))
            formats = {int(e.attrib['numFmtId']): e.attrib['formatCode'] for e in style_root.findall('s:numFmts/s:numFmt', NS)}
            styles = [int(e.attrib.get('numFmtId', 0)) for e in style_root.findall('s:cellXfs/s:xf', NS)]
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        props = wb.find('s:workbookPr', NS)
        epoch = datetime(1904, 1, 1) if props is not None and props.attrib.get('date1904') in ('1','true') else datetime(1899,12,30)
        rows = []
        for row in ET.fromstring(z.read(sheets[selected])).findall('s:sheetData/s:row', NS):
            values = {}
            for c in row.findall('s:c', NS):
                letters = re.match(r'[A-Z]+', c.attrib['r'])[0]
                index = 0
                for char in letters:
                    index = index*26+ord(char)-64
                kind = c.attrib.get('t')
                v = c.find('s:v', NS)
                value = v.text or '' if v is not None else ''
                if c.find('s:f', NS) is not None and (v is None or v.text is None):
                    raise ValueError(f'Fórmula sem resultado salvo em {c.attrib["r"]}. Recalcule e salve no Excel.')
                if kind == 's':
                    value = shared[int(value)]
                elif kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in c.findall('.//s:t', NS))
                elif kind == 'b':
                    value = 'TRUE' if value == '1' else 'FALSE'
                elif kind == 'e':
                    raise ValueError(f'Erro de célula em {c.attrib["r"]}: {value}')
                elif value and kind not in ('str', 'd'):
                    style = int(c.attrib.get('s', 0))
                    fmt = styles[style] if style < len(styles) else 0
                    code = formats.get(fmt, '')
                    date_code = re.sub(r'"[^"]*"|\\.|\[[^]]*\]','',code).lower()
                    if fmt in range(14, 23) or re.search(r'[dy]',date_code):
                        value = (epoch+timedelta(days=float(value))).isoformat(sep=' ').removesuffix(' 00:00:00')
                    else:
                        value = identification_text(value,code)
                values[index-1] = value
            if values:
                rows.append((int(row.attrib['r']), [values.get(i,'') for i in range(max(values)+1)]))
        return rows

def _xls_rows(path, sheet):
    # O formato binário antigo usa Excel instalado, através do pywin32 já utilizado pelo Word.
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = book = None
    try:
        app = win32com.client.DispatchEx('Excel.Application')
        app.Visible = False
        app.DisplayAlerts = False
        app.AutomationSecurity = 3
        book = app.Workbooks.Open(str(Path(path).resolve()), UpdateLinks=0, ReadOnly=True)
        ws = book.Worksheets(sheet) if sheet else book.Worksheets(1)
        used = ws.UsedRange
        rows = [(r, [str(ws.Cells(r,c).Text) for c in range(1, used.Column+used.Columns.Count)])
                for r in range(used.Row, used.Row+used.Rows.Count)]
        if any(re.fullmatch(r'#+',v) for _,row in rows for v in row):
            raise ValueError('Há células exibidas como ### no XLS. Amplie as colunas no Excel e salve novamente.')
        return rows
    finally:
        try:
            if book is not None:
                book.Close(False)
        finally:
            try:
                if app is not None:
                    app.Quit()
            finally:
                pythoncom.CoUninitialize()

def read_table(path, sheet=''):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in ('.csv', '.tsv'):
        data = path.read_bytes()
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = data.decode('cp1252')
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel_tab if suffix == '.tsv' else csv.excel
        raw = list(enumerate(csv.reader(io.StringIO(text), dialect), 1))
    elif suffix == '.xlsx':
        raw = _xlsx_rows(path, sheet)
    elif suffix == '.xls':
        raw = _xls_rows(path, sheet)
    else:
        raise ValueError('Escolha CSV, TSV, XLSX ou XLS.')
    raw = [(i, row) for i, row in raw if any(str(v).strip() for v in row)]
    if not raw:
        raise ValueError('A planilha está vazia.')
    headers = list(raw[0][1])
    while headers and not headers[-1]:
        headers.pop()
    if any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
        raise ValueError('Os cabeçalhos precisam ser únicos e não vazios; os nomes originais serão preservados.')
    records = []
    for line, values in raw[1:]:
        if len(values) > len(headers) and any(values[len(headers):]):
            raise ValueError(f'Linha {line}: há dados em colunas sem cabeçalho.')
        records.append((line, {h: str(values[i]) if i < len(values) else '' for i,h in enumerate(headers)}))
    return headers, records

def key(value):
    return ' '.join(normalize(str(value)).split())

def associate(records, condos, column, aliases=None):
    aliases = aliases or {}
    index = {}
    for condo in condos:
        index.setdefault(key(condo['name']), []).append(condo['folder'])
    folders = {c['folder'] for c in condos}
    groups, warnings = {}, []
    for line, row in records:
        if column not in row:
            raise ValueError('Coluna de condomínio ausente: '+column)
        value = row[column].strip()
        explicit = aliases.get(value)
        matches = ([explicit] if explicit in folders else []) if value in aliases else index.get(key(value), [])
        if len(matches) != 1 or not value:
            warnings.append(f'Linha {line}: condomínio "{value}" '+('ambíguo.' if len(matches)>1 else 'não associado.'))
            continue
        groups.setdefault(matches[0], []).append(row)
    return groups, warnings

def group_fingerprint(rows):
    # Reordenar linhas/colunas não altera a informação dos responsáveis.
    canonical = sorted({json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows})
    return hashlib.sha256('\n'.join(canonical).encode('utf-8')).hexdigest()

class SheetMonitor:
    def __init__(self, path, mapping, condos, previous_fingerprints=None):
        self.path, self.mapping, self.condos = Path(path), mapping, condos
        self.raw_hash = None
        self.groups = {}
        self.fingerprints = dict(previous_fingerprints or {})

    def require_current(self):
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.raw_hash:
            raise ValueError('A planilha mudou desde a conferência. Aguarde a atualização e confira novamente.')

    def poll(self):
        raw_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        if raw_hash == self.raw_hash:
            return self.groups, set(), []
        headers, records = read_table(self.path, self.mapping.get('sheet',''))
        for label in ('condo','name','role','unit','old_name'):
            column = self.mapping.get(label)
            if column and column not in headers:
                raise ValueError('A coluna configurada não existe mais: '+column)
        groups, warnings = associate(records, self.condos, self.mapping['condo'], self.mapping.get('aliases'))
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != raw_hash:
            raise ValueError('A planilha está sendo gravada. A atualização será tentada novamente.')
        fingerprints = {folder:group_fingerprint(rows) for folder,rows in groups.items()}
        changed = {folder for folder in self.fingerprints.keys() | fingerprints.keys()
                   if self.fingerprints.get(folder) != fingerprints.get(folder)}
        self.fingerprints = fingerprints
        self.groups, self.raw_hash = groups, raw_hash
        return groups, changed, warnings

def role_key(value):
    value = re.sub(r'\([^)]*\)', '', key(value)).strip()
    return {'sindica':'sindico', 'subsindica':'subsindico', 'conselheiros':'conselheiro',
            'conselheiras':'conselheiro', 'conselheira':'conselheiro'}.get(value, value)

def sheet_changes(text, rows, mapping, legacy=False):
    """Preenche marcadores exatos; assinaturas antigas requerem associação inequívoca."""
    changes = []
    role_column = mapping.get('role')
    unique_rows = {json.dumps(r, sort_keys=True, ensure_ascii=False): r for r in rows}
    rows = list(unique_rows.values())
    for token in re.finditer(r'\{\{([^{}]+)\}\}', text):
        label = token[1]
        matching = rows
        # Primeiro tenta o cabeçalho completo, inclusive se ele contiver |.
        column = label
        if not any(column in row for row in rows) and '|' in label:
            selector, column = label.split('|',1)
            if '=' in selector:
                selector_column, selector_value = selector.split('=',1)
                matching = [r for r in rows if selector_column in r and key(r[selector_column]) == key(selector_value)]
            else:
                matching = [r for r in rows if role_column and key(r.get(role_column,'')) == key(selector)]
        if not matching or not all(column in row for row in matching):
            raise ValueError('Marcador sem coluna/responsável correspondente: '+token[0])
        values = {row[column] for row in matching}
        if len(values) != 1:
            raise ValueError('Marcador ambíguo: '+token[0]+'. Use {{Cargo|Coluna}} e cargos distintos ou ajuste o modelo.')
        changes.append(Change(token.start(), token.end(), token[0], next(iter(values)), 'Planilha: '+column))
    if legacy and mapping.get('name'):
        signatures = [s for s in roster(text) if '{{' not in s['old_name']]
        has_name_marker = any(t[1] == mapping['name'] or t[1].endswith('|'+mapping['name'])
                              for t in re.finditer(r'\{\{([^{}]+)\}\}',text))
        used = set()
        for row in rows:
            new_name = row[mapping['name']].strip()
            new_role = row.get(role_column, '').strip() if role_column else ''
            original = row.get(mapping.get('old_name',''), '').strip()
            candidates = [s for s in signatures if (s['old_name'] == original if original else
                role_key(s['role']) == role_key(new_role) if new_role else s['old_name'] == new_name)]
            if not candidates and has_name_marker:
                continue  # Modelos com marcadores não precisam de blocos de assinatura antigos.
            if len(candidates) != 1:
                raise ValueError(f'Responsável "{new_name}": assinatura não associada de forma única. Mapeie a coluna de nome original ou use marcadores.')
            signature = candidates[0]
            if signature['old_name'] in used:
                raise ValueError('Mais de uma linha da planilha aponta para a mesma assinatura.')
            used.add(signature['old_name'])
            hits = list(re.finditer(r'(?<!\w)'+re.escape(signature['old_name'])+r'(?!\w)', text))
            if not new_name or len(hits) != 1:
                raise ValueError('Nome vazio ou repetido no documento: '+signature['old_name'])
            hit = hits[0]
            changes.append(Change(hit.start(), hit.end(), hit[0], new_name, 'Responsável da planilha'))
            unit_col = mapping.get('unit')
            if unit_col:
                unit = row[unit_col].strip()
                m = re.match(r'[^\r\n]{0,100}?\bapto\.?[ \t]*(\S+)', text[hit.end():], re.I)
                if not unit or not m:
                    raise ValueError('Apartamento vazio ou sem posição correspondente: '+new_name)
                changes.append(Change(hit.end()+m.start(1),hit.end()+m.end(1),m[1],unit,'Apartamento da planilha'))
            if new_role:
                start = max(text.rfind('\r',0,hit.start()), text.rfind('\n',0,hit.start()))+1
                prefix = text[start:hit.start()]
                old_role = signature['role']
                at = prefix.find(old_role)
                if at >= 0:
                    changes.append(Change(start+at,start+at+len(old_role),old_role,new_role,'Cargo da planilha'))
    changes.sort(key=lambda c:c.start)
    if any(a.end>b.start for a,b in zip(changes,changes[1:])):
        raise ValueError('Há campos de responsáveis sobrepostos. Revise os marcadores ou as associações.')
    return changes
