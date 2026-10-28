"""Envio sequencial de PDFs ao Windows, uma cópia só frente, sem alterar padrões."""
import tempfile
from contextlib import nullcontext
from pathlib import Path
from central_service import verify_plan
from print_service import print_receipt
from word_service import digest


def print_pdf(path,printer,cancel,log=lambda text:None):
    import pypdfium2 as pdfium
    import win32print,win32gui,win32con
    from PIL import ImageWin
    handle=win32print.OpenPrinter(printer)
    dc=None;started=False
    try:
        mode=win32print.GetPrinter(handle,2)['pDevMode']
        if mode is None:raise ValueError('Impressora sem configuração de driver disponível.')
        with pdfium.PdfDocument(str(path)) as pdf:
            pdf.init_forms()
            if not len(pdf):raise ValueError('PDF sem páginas.')
            first=pdf[0]
            width,height=first.get_size();first.close()
            mode.Fields |= win32con.DM_DUPLEX|win32con.DM_COPIES|win32con.DM_ORIENTATION
            mode.Duplex=1;mode.Copies=1;mode.Orientation=2 if width>height else 1
            result=win32print.DocumentProperties(0,handle,printer,mode,mode,win32con.DM_IN_BUFFER|win32con.DM_OUT_BUFFER)
            if result!=1 or mode.Duplex!=1 or mode.Copies!=1:
                raise ValueError('O driver não confirmou uma cópia somente frente.')
            dc=win32gui.CreateDC('WINSPOOL',printer,mode)
            w=win32print.GetDeviceCaps(dc,win32con.HORZRES);h=win32print.GetDeviceCaps(dc,win32con.VERTRES)
            if w<=0 or h<=0:raise ValueError('Área imprimível inválida.')
            if cancel.is_set():return False
            win32print.StartDoc(dc,(Path(path).name,None,None,0));started=True
            for i in range(len(pdf)):
                if cancel.is_set():
                    win32print.AbortDoc(dc);started=False
                    return False
                page=pdf[i]
                try:
                    pw,ph=page.get_size()
                    bitmap=page.render(scale=min(300/72,6000/max(pw,ph)))
                    try:
                        image=bitmap.to_pil().convert('RGB')
                        try:
                            factor=min(w/image.width,h/image.height)
                            dw,dh=int(image.width*factor),int(image.height*factor)
                            x,y=(w-dw)//2,(h-dh)//2
                            win32print.StartPage(dc)
                            ImageWin.Dib(image).draw(dc,(x,y,x+dw,y+dh))
                            win32print.EndPage(dc)
                        finally:image.close()
                    finally:bitmap.close()
                finally:page.close()
                log(f'{Path(path).name}: página {i+1}/{len(pdf)} enviada')
            win32print.EndDoc(dc);started=False
            return True
    finally:
        if started and dc:
            try:win32print.AbortDoc(dc)
            except Exception:pass
        if dc:win32gui.DeleteDC(dc)
        win32print.ClosePrinter(handle)


def execute_plan(rows,cancel,log,word_factory,pdf_sender=print_pdf):
    verify_plan(rows)
    # Abre os destinos antes de enviar qualquer página.
    import win32print
    for printer in sorted({row['printer'] for row in rows}):
        handle=win32print.OpenPrinter(printer);win32print.ClosePrinter(handle)
    sent=0
    with tempfile.TemporaryDirectory(prefix='autoword_impressao_') as folder:
        prepared=[]
        manager=nullcontext(None)
        with manager as word:
            for i,row in enumerate(rows):
                if cancel.is_set():return sent
                source=Path(row['path']);target=Path(folder)/f'{i+1:02} - {source.stem}.pdf'
                target=source
                if source.suffix.lower()=='.pdf':
                    target=Path(folder)/(f'{i+1:02} - '+source.name)
                    target.write_bytes(source.read_bytes())
                if source.suffix.lower()=='.pdf':
                    import pypdfium2 as pdfium
                    with pdfium.PdfDocument(str(target)) as doc:
                        if not len(doc):raise ValueError('PDF sem páginas: '+source.name)
                        page=doc[0];bitmap=page.render(scale=.25);bitmap.close();page.close()
                prepared.append(target)
        verify_plan(rows)
        with (word_factory() if any(p.suffix.lower()!='.pdf' for p in prepared) else nullcontext(None)) as word:
          for row,target in zip(rows,prepared):
              if cancel.is_set():break
              verify_plan([row])
              log('Enviando '+row['label']+' → '+row['printer'])
              if target.suffix.lower()=='.pdf':
                  if not pdf_sender(target,row['printer'],cancel,log):break
              else:
                  receipt={'files':[{'path':str(target),'sha256':digest(target)}]}
                  if not print_receipt(word,receipt,row['printer'],1,cancel):break
              sent+=1
    return sent
