"""Entrada sem console: verifica atualizações antes de abrir o aplicativo."""
import json
import os
import subprocess
import sys
import time
import threading
from pathlib import Path
from updater import UpdateError,fetch,install_latest,repo_url,saved_token,store_token

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'CondominioFacil'
STATE=DATA/'atualizacao.json'

def config():
    return json.loads((ROOT/'update_config.json').read_text(encoding='utf-8'))

def dependency_install():
    subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')],
        check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def automatic_update():
    cfg=config()
    token=saved_token(cfg['repository'])
    if cfg.get('private') and not token:
        return 'Atualizações aguardam conexão em Opções → Atualizações.'
    try:
        state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    except (ValueError,OSError):
        state={}
    if time.time()-state.get('checked_at',0)<6*60*60:
        return state.get('message','')
    previous=(ROOT/'requirements.txt').read_bytes()
    def dependencies():
        if (ROOT/'requirements.txt').read_bytes()!=previous:
            dependency_install()
    try:
        version,changed=install_latest(ROOT,cfg['repository'],token,dependencies)
        message=f'Atualizado automaticamente para {version}.' if changed else f'Versão {version} atualizada.'
        state={'checked_at':time.time(),'message':message}
    except Exception as exc:
        message=str(exc) if isinstance(exc,UpdateError) else 'Atualização indisponível; mantida a versão instalada.'
        state={'checked_at':time.time()-5*60*60,'message':message}
    try:
        DATA.mkdir(parents=True,exist_ok=True)
        temporary=STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
        temporary.replace(STATE)
    except OSError:
        pass
    return message

def configure_updates(parent):
    from tkinter import simpledialog,messagebox
    cfg=config()
    if not cfg.get('private'):
        STATE.unlink(missing_ok=True)
        messagebox.showinfo('Atualizações automáticas','Repositório público: '+cfg['repository']+'\nNão é necessário token. A próxima abertura verificará novas versões.',parent=parent)
        return
    token=simpledialog.askstring('Conectar atualizações privadas',
        'Repositório: '+cfg['repository']+'\nInforme um token GitHub com acesso somente de leitura ao conteúdo deste repositório.\nEle ficará no Gerenciador de Credenciais do Windows, fora dos arquivos do aplicativo.',
        show='*',parent=parent)
    if not token:
        return
    try:
        fetch(repo_url(cfg['repository'])+'/releases?per_page=1',token.strip(),limit=1024*1024)
        store_token(cfg['repository'],token.strip())
        STATE.unlink(missing_ok=True)
        messagebox.showinfo('Atualizações ativadas','As versões publicadas serão instaladas automaticamente na próxima abertura.',parent=parent)
    except Exception as exc:
        messagebox.showerror('Não foi possível conectar',str(exc),parent=parent)

def smoke_test():
    # Executado no CI sem Word, rede ou acesso aos cadastros do usuário.
    import tempfile
    from unittest.mock import patch
    from app import App
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        with patch('app.CONFIG',root/'responsaveis.json'),patch('app.MAPPINGS',root/'arquivos.json'),patch('app.DATA',root):
            from central_ui import save_settings
            from central_service import DEFAULTS
            save_settings(root/'central.json',dict(DEFAULTS,root=str(root),statements=str(root),reports=str(root)))
            app=App()
            assert app.workspace_active and app.central_panel.winfo_exists()
            import pypdfium2 as pdfium
            with pdfium.PdfDocument.new() as document:
                page=document.new_page(100,100)
                bitmap=page.render(scale=1)
                image=bitmap.to_pil()
                assert image.size==(100,100)
                image.close();bitmap.close();page.close()
            app.after(600,app.destroy)
            app.mainloop()
    return 0

def main():
    if '--smoke-test' in sys.argv:
        return smoke_test()
    import win32api,win32event
    from tkinter import messagebox
    handle=win32event.CreateMutex(None,False,'Local\\CondominioFacil')
    try:
        if win32api.GetLastError()==183:
            messagebox.showinfo('Condomínio Fácil','O aplicativo já está aberto.')
            return
        try:
            status='' if getattr(sys,'frozen',False) else automatic_update()
        except Exception:
            status='Atualizações indisponíveis; mantida a versão instalada.'
        from app import App
        app=App()
        app.log(status)
        if getattr(sys,'frozen',False):
            from executable_update import prepare_update
            from version import VERSION
            def check():
                try:
                    receipt=prepare_update(DATA,config()['repository'],VERSION)
                    if receipt:
                        app.events.put(('installer_ready',receipt))
                except Exception as exc:
                    app.events.put(('log','Atualização indisponível: '+str(exc)))
            threading.Thread(target=check,daemon=True).start()
        app.mainloop()
        if getattr(app,'pending_installer',None):
            from executable_update import launch_update
            launch_update(app.pending_installer,DATA,sys.executable)
    finally:
        win32api.CloseHandle(handle)

if __name__=='__main__':
    if '--smoke-test' in sys.argv:
        sys.exit(smoke_test())
    try:
        main()
    except Exception as exc:
        from tkinter import messagebox
        messagebox.showerror('Erro ao abrir Condomínio Fácil',str(exc))
