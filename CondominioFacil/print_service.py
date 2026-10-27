"""Imprime exclusivamente os resultados de uma atualização individual concluída."""
from pathlib import Path
from word_service import digest

def receipt_for(condo, target, docs, month, year):
    files = []
    for doc in docs:
        path = (Path(target)/doc['path'].name).resolve(strict=True)
        if path.suffix.lower() not in ('.doc', '.docx') or not path.is_file():
            raise ValueError('Resultado de atualização inválido para impressão.')
        files.append({'path':str(path), 'sha256':digest(path)})
    if not files or len({f['path'].casefold() for f in files}) != len(files):
        raise ValueError('Nenhum resultado válido para impressão.')
    return dict(folder=condo['folder'], name=condo['name'], month=month, year=year, files=files)

def validate_receipt(receipt):
    if not receipt or not receipt.get('files'):
        raise ValueError('Atualize um único condomínio antes de imprimir.')
    for item in receipt['files']:
        path = Path(item['path'])
        if not path.is_file() or path.is_symlink() or digest(path) != item['sha256']:
            raise ValueError('Um documento mudou ou foi removido. Atualize o condomínio novamente antes de imprimir.')

def available_printers():
    import win32print
    names = sorted({row[2] for row in win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)})
    try:
        default = win32print.GetDefaultPrinter()
    except Exception:
        default = ''
    return names, default if default in names else names[0] if names else ''

def print_receipt(word, receipt, printer, copies=1, cancel=None, progress=None):
    if not printer or not isinstance(copies, int) or not 1 <= copies <= 99:
        raise ValueError('Escolha a impressora e informe de 1 a 99 cópias.')
    validate_receipt(receipt)  # Valida todos antes de enviar a primeira página.
    setup = word.app.Dialogs(97)  # wdDialogFilePrintSetup, sem alterar a impressora padrão.
    setup.Printer = printer
    setup.DoNotSetAsSysDefault = True
    setup.Execute()
    sent = 0
    for item in receipt['files']:
        if cancel is not None and cancel.is_set():
            break
        validate_receipt(receipt)
        path = Path(item['path'])
        doc = word.open(path, read_only=True)
        try:
            if progress:
                progress(sent+1, len(receipt['files']), path.name)
            doc.PrintOut(Background=False, Copies=copies, Collate=True, PrintToFile=False)
            sent += 1
        finally:
            doc.Close(0)
    return sent
