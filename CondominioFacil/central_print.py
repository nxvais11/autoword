"""Impressão sequencial: Word com prévia, PDF original pelo Adobe."""
from contextlib import nullcontext
from pathlib import Path
from central_service import verify_plan
from print_service import print_receipt
from pdf_print import print_pdf,preflight


def execute_plan(rows,cancel,log,word_factory,pdf_sender=None):
    verify_plan(rows)
    if pdf_sender is None:
        printers={row['printer'] for row in rows if Path(row['path']).suffix.lower()=='.pdf'}
        if printers:preflight(printers)
        pdf_sender=print_pdf
    # Abre os destinos antes de enviar qualquer página.
    import win32print
    for printer in sorted({row['printer'] for row in rows}):
        handle=win32print.OpenPrinter(printer);win32print.ClosePrinter(handle)
    sent=0
    # Valida todos os PDFs antes de enviar a primeira página; nenhum arquivo extra.
    for row in rows:
        source=Path(row['path'])
        if source.suffix.lower()=='.pdf':
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(str(source)) as doc:
                if not len(doc):raise ValueError('PDF sem páginas: '+source.name)
                page=doc[0];bitmap=page.render(scale=.25);bitmap.close();page.close()
    verify_plan(rows)
    with (word_factory() if any(Path(r['path']).suffix.lower()!='.pdf' for r in rows) else nullcontext(None)) as word:
        for row in rows:
            if cancel.is_set():break
            verify_plan([row])
            source=Path(row['path'])
            log('Enviando '+row['label']+' → '+row['printer'])
            if source.suffix.lower()=='.pdf':
                if not pdf_sender(source,row['printer'],cancel,log):break
            else:
                receipt={'files':[{'path':str(source),'sha256':row['hash']}]}
                if not print_receipt(word,receipt,row['printer'],1,cancel):break
            sent+=1
    return sent
