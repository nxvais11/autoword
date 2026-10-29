"""Impressão do PDF original pelo Adobe, sem rasterização pelo AutoWord."""
import os
import subprocess
import time
from pathlib import Path


def acrobat_executable():
    import winreg
    names=('Acrobat.exe','AcroRd32.exe')
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            for name in names:
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths'+'\\'+name,0,winreg.KEY_READ|view) as key:
                        path=Path(str(winreg.QueryValue(key,None)).strip('"'))
                    if path.is_file():return path
                except OSError:pass
    for root in {os.environ.get('ProgramFiles',''),os.environ.get('ProgramFiles(x86)','')}:
        if not root:continue
        for suffix in ('Adobe/Acrobat DC/Acrobat/Acrobat.exe','Adobe/Acrobat Reader DC/Reader/AcroRd32.exe'):
            path=Path(root)/suffix
            if path.is_file():return path
    raise ValueError('Adobe Acrobat/Reader não encontrado. Instale-o para imprimir PDFs pela Central.')


def printer_info(printer):
    import win32print
    handle=win32print.OpenPrinter(printer)
    try:
        info=win32print.GetPrinter(handle,2)
        mode=info.get('pDevMode')
        # /t usa as preferências do driver; não altera o padrão do Windows.
        if mode is None:raise ValueError('Não foi possível confirmar cópias e frente/verso da impressora '+printer+'.')
        if mode.Copies not in (0,1) or mode.Duplex not in (0,1):
            raise ValueError(f'{printer}: configure uma cópia e somente frente nas preferências da impressora antes de imprimir PDFs.')
        if not info.get('pDriverName') or not info.get('pPortName'):
            raise ValueError('Driver/porta não identificados para '+printer+'.')
        return info
    finally:win32print.ClosePrinter(handle)


def preflight(printers):
    acrobat_executable()
    for printer in printers:printer_info(printer)


def close_print_instance(process,log=lambda text:None):
    """Fecha somente o processo /n iniciado para esta impressão, após o spool."""
    try:
        if process.poll() is not None:return
        import win32gui,win32process
        def close_window(hwnd,_):
            try:
                if win32process.GetWindowThreadProcessId(hwnd)[1]==process.pid:
                    win32gui.PostMessage(hwnd,0x0010,0,0)  # WM_CLOSE apenas neste PID.
            except Exception:pass  # Uma janela pode desaparecer durante a enumeração.
        win32gui.EnumWindows(close_window,None)
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # O spool já recebeu o PDF; nunca encerra outro Acrobat pelo nome.
            process.terminate();process.wait(timeout=2)
    except Exception:
        # Não transforma um envio confirmado em falha com risco de reimpressão.
        log('PDF enviado à fila. Não foi possível fechar a instância de impressão do Adobe; feche essa janela manualmente.')


def print_pdf(path,printer,cancel,log=lambda text:None,*,timeout=90):
    """Aguarda o trabalho correspondente entrar e terminar de carregar na fila."""
    import win32print
    source=Path(path).resolve(strict=True)
    exe=acrobat_executable();info=printer_info(printer)
    handle=win32print.OpenPrinter(printer)
    process=None;confirmed=False
    try:
        before={j['JobId'] for j in win32print.EnumJobs(handle,0,9999,1)}
        if cancel.is_set():return False
        # Lista de argumentos: caminhos, nomes e portas não passam por um shell.
        options={'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)}
        if os.name=='nt':
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            options['startupinfo']=startup
        # /n isola esta impressão das janelas já abertas pelo usuário.
        # /h /s /o evitam a janela principal, a abertura de arquivo e o splash.
        process=subprocess.Popen([str(exe),'/n','/h','/s','/o','/t',str(source),printer,info['pDriverName'],info['pPortName']],**options)
        log(source.name+': aguardando o Adobe enviar à fila de '+printer)
        deadline=time.monotonic()+timeout;job_id=None
        names=[source.name.casefold(),source.stem.casefold()]
        try:
            from pypdf import PdfReader
            title=str((PdfReader(source).metadata or {}).get('/Title','')).strip().casefold()
            if len(title)>=8:names.append(title)
        except Exception:pass
        while time.monotonic()<deadline:
            if cancel.is_set():
                raise ValueError('Cancelamento solicitado após abrir o Adobe. Confira a fila: o documento pode ter sido enviado. Não há reenvio automático.')
            jobs=win32print.EnumJobs(handle,0,9999,1)
            if job_id is None:
                matches=[j for j in jobs if j['JobId'] not in before and any(n in (j.get('pDocument') or '').casefold() for n in names)]
                if len(matches)>1:raise ValueError('Mais de um trabalho correspondente encontrado. Confira a fila antes de continuar.')
                if matches:job_id=matches[0]['JobId']
            if job_id is not None:
                job=next((j for j in jobs if j['JobId']==job_id),None)
                if job is None:confirmed=True;return True
                status=job.get('Status',0)
                errors=(win32print.JOB_STATUS_ERROR|win32print.JOB_STATUS_OFFLINE|win32print.JOB_STATUS_PAPEROUT|win32print.JOB_STATUS_BLOCKED_DEVQ|win32print.JOB_STATUS_USER_INTERVENTION)
                if status&errors:raise ValueError('A impressora sinalizou um problema. Confira a fila antes de continuar; nenhum reenvio automático será feito.')
                if not status&win32print.JOB_STATUS_SPOOLING:
                    log(source.name+': recebido pela fila de '+printer)
                    confirmed=True
                    return True
            cancel.wait(.1)
        raise ValueError('Não foi possível confirmar o PDF na fila da impressora. Confira o Adobe e a fila antes de tentar novamente; o documento pode já ter sido enviado.')
    finally:
        try:
            if confirmed and process is not None:close_print_instance(process,log)
        finally:win32print.ClosePrinter(handle)
