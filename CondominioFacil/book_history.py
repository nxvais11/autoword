"""Controle local de livros e envios; não cria arquivos nas pastas dos condomínios."""
import copy
import json
import os
import threading
from datetime import datetime
from pathlib import Path


def file_id(row):
    return row.get('key',str(Path(row['path']).resolve()).casefold())+'|'+row['sha256' if 'sha256' in row else 'hash']


class BookHistory:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock();self.roots={}
        self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'books':{},'recent':{},'manual_minutes':None}
        if not isinstance(self.data,dict) or not isinstance(self.data.get('books'),dict):raise ValueError('Controle de livros inválido. O arquivo foi preservado.')
        self.data.setdefault('recent',{});self.data.setdefault('manual_minutes',None)
    def _root(self,root):
        key=str(root)
        if key not in self.roots:self.roots[key]=str(Path(root).resolve()).casefold()
        return self.roots[key]
    def _key(self,root,name,period):return json.dumps([self._root(root),name,period],ensure_ascii=False)
    def _book(self,root,name,period):
        return self.data['books'].setdefault(self._key(root,name,period),dict(name=name,period=period,root=self._root(root),updated=[],sent={},complete=False,seconds=0,operations=0))
    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,self.path)
    def get(self,root,name,period):
        with self.lock:return copy.deepcopy(self.data['books'].get(self._key(root,name,period),{}))
    def touch(self,root,name):
        with self.lock:
            key=self._root(root);recent=self.data['recent'].get(key,[])
            self.data['recent'][key]=[name]+[n for n in recent if n!=name][:7];self._save()
    def ordered_names(self,root,names):
        with self.lock:
            recent=[n for n in self.data['recent'].get(self._root(root),[]) if n in names]
            return recent+[n for n in names if n not in recent]
    def updated(self,root,name,period,kinds):
        with self.lock:
            book=self._book(root,name,period);book['updated']=sorted(set(book['updated'])|set(kinds));book['complete']=False;self._save()
    def print_event(self,root,name,period,event,row):
        with self.lock:
            book=self._book(root,name,period)
            book['sent'][file_id(row)]=dict(label=row['label'],path=str(row['path']),printer=row['printer'],state=event,at=datetime.now().isoformat(timespec='seconds'))
            book['complete']=False;self._save()
    def duplicates(self,root,name,period,rows):
        book=self.get(root,name,period)
        return [row for row in rows if file_id(row) in book.get('sent',{})]
    def finish(self,root,name,period,seconds,error=''):
        with self.lock:
            book=self._book(root,name,period);book['seconds']+=max(0,seconds);book['operations']+=1;book['last_error']=error;self._save()
    def complete(self,root,name,period,value):
        with self.lock:
            self._book(root,name,period)['complete']=bool(value);self._save()
    def set_baseline(self,minutes):
        if minutes is not None and not 0<minutes<=480:raise ValueError('Informe um tempo manual entre 0 e 480 minutos, ou deixe vazio.')
        with self.lock:self.data['manual_minutes']=minutes;self._save()
    @staticmethod
    def status(book):
        if book.get('complete'):return 'Concluído'
        if book.get('last_error') or any(v['state']=='attempt' for v in book.get('sent',{}).values()):return 'Revisar envio'
        if any(v['state']=='sent' for v in book.get('sent',{}).values()):return 'Enviado à impressão'
        if book.get('updated'):return 'Atualizado'
        return 'Pendente'
    def totals(self,root,names,period):
        books=[self.get(root,name,period) for name in names]
        complete=[b for b in books if b.get('complete')]
        seconds=sum(b.get('seconds',0) for b in books)
        eligible=[b for b in complete if b.get('operations') and (b.get('updated') or any(v['state']=='sent' for v in b.get('sent',{}).values()))]
        baseline=self.data.get('manual_minutes')
        saving=None if baseline is None else max(0,len(eligible)*baseline*60-sum(b.get('seconds',0) for b in eligible))
        return dict(complete=len(complete),total=len(names),seconds=seconds,saving=saving,saving_count=len(eligible))
