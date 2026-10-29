"""Controle local de livros e envios; não cria arquivos nas pastas dos condomínios."""
import copy
import json
import os
import threading
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def file_id(row):
    key=row['key'] if 'key' in row else str(Path(row['path']).resolve()).casefold()
    return key+'|'+row['sha256' if 'sha256' in row else 'hash']


class BookHistory:
    _locks={}
    _locks_guard=threading.Lock()
    def __init__(self,path):
        self.path=Path(path);self.backup=self.path.with_suffix('.json.bak');self.previous_backup=self.path.with_suffix('.json.previous.bak');self.roots={};self.recovery_notice=''
        with self._locks_guard:
            self.lock=self._locks.setdefault(str(self.path.absolute()).casefold(),threading.RLock())
        with self.lock:self._reload()
    @staticmethod
    def _read(path):
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('books'),dict):raise ValueError('Controle de livros inválido. O arquivo foi preservado.')
        if not isinstance(data.get('recent',{}),dict) or not isinstance(data.get('root_aliases',{}),dict):raise ValueError('Controle de livros inválido. O arquivo foi preservado.')
        for book in data['books'].values():
            if not isinstance(book,dict) or not all(k in book for k in ('name','period','root','updated','sent')):
                raise ValueError('Registro de livro inválido. O arquivo foi preservado.')
        data.setdefault('recent',{});data.setdefault('manual_minutes',None);data.setdefault('root_aliases',{})
        return data
    @staticmethod
    def _atomic(path,text):
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(dir=path.parent);temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as output:
                output.write(text if isinstance(text,bytes) else text.encode('utf-8'));output.flush();os.fsync(output.fileno())
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    def _reload(self):
        if self.path.exists():
            try:self.data=self._read(self.path)
            except (ValueError,UnicodeError):
                if not self.backup.exists():raise
                recovered=self._read(self.backup)
                preserved=self.path.with_name('livros.corrompido-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
                self._atomic(preserved,self.path.read_bytes())
                self._atomic(self.path,json.dumps(recovered,ensure_ascii=False,indent=2))
                self.data=recovered
                self.recovery_notice='O controle mensal foi recuperado do backup local. O arquivo inválido foi preservado para análise.'
        elif self.backup.exists():
            self.data=self._read(self.backup)
            self._atomic(self.path,json.dumps(self.data,ensure_ascii=False,indent=2))
            self.recovery_notice='O controle mensal foi recuperado do backup local porque o arquivo principal estava ausente.'
        else:self.data={'books':{},'recent':{},'manual_minutes':None,'root_aliases':{}}
    @contextmanager
    def _access(self):
        with self.lock:
            self._reload()
            yield
    def _root(self,root):
        key=str(root)
        if key not in self.roots:
            # Um mapeamento de rede pode resolver como UNC quando conectado e
            # como letra de unidade quando desconectado. A identidade aprendida
            # permanece estável; nunca transfere livros entre pastas por palpite.
            alias=os.path.normcase(os.path.abspath(root)).casefold()
            self.roots[key]=self.data.get('root_aliases',{}).get(alias) or str(Path(root).resolve()).casefold()
        alias=os.path.normcase(os.path.abspath(root)).casefold()
        self.data.setdefault('root_aliases',{})[alias]=self.roots[key]
        return self.roots[key]
    def prepare_root(self,root):
        # Executado na carga em segundo plano, nunca durante a montagem da janela.
        with self._access():
            value=self._root(root);self._save();return value
    def root_ready(self,root):
        # Uma leitura do cache não aguarda a thread que pode estar consultando a rede.
        return str(root) in self.roots
    def _key(self,root,name,period):return json.dumps([self._root(root),name,period],ensure_ascii=False)
    def _book(self,root,name,period):
        return self.data['books'].setdefault(self._key(root,name,period),dict(name=name,period=period,root=self._root(root),updated=[],sent={},complete=False,seconds=0,operations=0))
    def _save(self):
        text=json.dumps(self.data,ensure_ascii=False,indent=2)
        if self.path.exists():
            previous=self.path.read_text(encoding='utf-8')
            self._read(self.path)  # Não substitui um arquivo corrompido por dados da memória.
            if previous==text:
                if not self.backup.exists():self._atomic(self.backup,text)
                return
            self._atomic(self.previous_backup,previous)
        self._atomic(self.path,text)
        self._atomic(self.backup,text)
    def get(self,root,name,period):
        with self._access():return copy.deepcopy(self.data['books'].get(self._key(root,name,period),{}))
    def touch(self,root,name):
        with self._access():
            key=self._root(root);recent=self.data['recent'].get(key,[])
            self.data['recent'][key]=[name]+[n for n in recent if n!=name][:7];self._save()
    def ordered_names(self,root,names):
        with self._access():
            recent=[n for n in self.data['recent'].get(self._root(root),[]) if n in names]
            return recent+[n for n in names if n not in recent]
    def updated(self,root,name,period,kinds):
        with self._access():
            book=self._book(root,name,period);book['updated']=sorted(set(book['updated'])|set(kinds));book['complete']=False;self._save()
    def print_event(self,root,name,period,event,row):
        with self._access():
            book=self._book(root,name,period)
            book['sent'][file_id(row)]=dict(label=row['label'],path=str(row['path']),printer=row['printer'],state=event,at=datetime.now().isoformat(timespec='seconds'))
            book['complete']=False;self._save()
    def duplicates(self,root,name,period,rows):
        book=self.get(root,name,period)
        return [row for row in rows if file_id(row) in book.get('sent',{})]
    def finish(self,root,name,period,seconds,error=''):
        with self._access():
            book=self._book(root,name,period);book['seconds']+=max(0,seconds);book['operations']+=1;book['last_error']=error;self._save()
    def complete(self,root,name,period,value):
        with self._access():
            self._book(root,name,period)['complete']=bool(value);self._save()
    def set_baseline(self,minutes):
        if minutes is not None and not 0<minutes<=480:raise ValueError('Informe um tempo manual entre 0 e 480 minutos, ou deixe vazio.')
        with self._access():self.data['manual_minutes']=minutes;self._save()

    def recovery_options(self,period):
        options=[]
        with self.lock:
            for path in (self.path,self.backup,self.previous_backup):
                if not path.exists():continue
                data=self._read(path)
                roots={b['root'] for b in data['books'].values() if b['period']==period}
                for root in sorted(roots):
                    count=sum(b['root']==root and b['period']==period for b in data['books'].values())
                    options.append(dict(path=str(path),root=root,count=count))
        return options

    def restore_month(self,option,root,period,names):
        """Recuperação explícita, limitada ao mês e aos condomínios visíveis."""
        with self._access():
            source=Path(option['path'])
            if source not in (self.path,self.backup,self.previous_backup):raise ValueError('Origem de recuperação inválida.')
            data=self._read(source)
            books=[b for b in data['books'].values() if b['root']==option['root'] and b['period']==period and b['name'] in names]
            if not books:raise ValueError('Não há registros compatíveis para recuperar nesta competência.')
            for saved in books:
                target=self._book(root,saved['name'],period)
                target['updated']=sorted(set(target['updated'])|set(saved['updated']))
                target['sent']={**saved['sent'],**target['sent']}
                target['complete']=target.get('complete',False) or saved.get('complete',False)
                for field in ('seconds','operations'):target[field]=max(target.get(field,0),saved.get(field,0))
                if not target.get('last_error'):target['last_error']=saved.get('last_error','')
            self._save();return len(books)
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
