"""Gera ícone, executável onedir e instalador no Windows."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'CondominioFacil'

def icon(path):
    scale=4
    im=Image.new('RGBA',(256*scale,256*scale))
    d=ImageDraw.Draw(im)
    def points(values): return [(x*scale,y*scale) for x,y in values]
    d.rounded_rectangle((0,0,1024,1024),radius=192,fill='#365f7d')
    d.polygon(points([(65,38),(150,38),(192,81),(192,218),(65,218)]),fill='white')
    d.polygon(points([(150,38),(150,81),(192,81)]),fill='#dce3ea')
    for y,end in ((107,169),(130,147)):
        d.line(points([(86,y),(end,y)]),fill='#a5b4c9',width=9*scale)
    d.ellipse((122*scale,140*scale,220*scale,238*scale),fill='#397365')
    d.line(points([(145,188),(163,206),(198,167)]),fill='white',width=12*scale,joint='curve')
    im.resize((256,256),Image.Resampling.LANCZOS).save(path,format='ICO',sizes=[(n,n) for n in (16,24,32,48,64,128,256)])

def check_executable(exe):
    report=ROOT/'build'/'smoke-error.txt'
    report.parent.mkdir(parents=True,exist_ok=True);report.unlink(missing_ok=True)
    result=subprocess.run([str(exe),'--smoke-test','--smoke-report',str(report)],timeout=60)
    if result.returncode:
        raise RuntimeError(report.read_text(encoding='utf-8') if report.exists() else f'Falha ao abrir o executável: {result.returncode}')
    if report.exists():print(report.read_text(encoding='utf-8'))

def build(version):
    icon(APP/'autoword.ico')
    (APP/'version.py').write_text(f'VERSION = {version!r}\n',encoding='utf-8')
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--noupx','--name','AutoWord',
          '--icon',str(APP/'autoword.ico'),'--distpath',str(ROOT/'dist/windows'),'--workpath',str(ROOT/'build/pyinstaller'),
          '--specpath',str(ROOT/'build'),'--paths',str(APP)]
    for name in ('autoword.ico','update_config.json','requirements.txt','pdf_ocr.ps1'):
        args+=['--add-data',str(APP/name)+':.']
    for name in ('win32com.client','pythoncom','pywintypes','win32timezone','win32file','win32api','win32event','win32print','win32cred','win32gui','win32con','PIL.ImageWin','pypdfium2','unittest.mock'):
        args+=['--hidden-import',name]
    args += ['--collect-all','pypdfium2_raw','--collect-all','pypdfium2']
    # pdfminer carrega tabelas de caracteres/fontes dinamicamente.
    args += ['--collect-all','pdfplumber','--collect-all','pdfminer']
    subprocess.run(args+[str(APP/'launcher.py')],check=True)
    exe=ROOT/'dist/windows/AutoWord/AutoWord.exe'
    check_executable(exe)
    compiler=shutil.which('ISCC') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    subprocess.run([compiler,'/DAppVersion='+version,str(ROOT/'scripts/installer.iss')],check=True)
    setup=ROOT/'dist/AutoWord-Setup.exe'
    with tempfile.TemporaryDirectory() as folder:
        destination=Path(folder)/'Installed AutoWord'
        for attempt in range(2):
            subprocess.run([str(setup),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/DIR='+str(destination)],check=True,timeout=120)
            check_executable(destination/'AutoWord.exe')
            marker=destination/'arquivo_do_usuario.txt'
            if attempt:
                assert marker.read_text()=='preservar'
            else:
                marker.write_text('preservar')
    return setup

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--version',required=True)
    print(build(parser.parse_args().version))
