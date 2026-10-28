"""Central simples por condomínio, com trabalho de rede e Word fora da interface."""
import copy
import json
import os
import queue
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from central_service import DEFAULTS,LABELS,catalog,search,compare_reports,selected_plan,digest
from central_print import execute_plan
from word_service import Word
from print_service import available_printers


def load_settings(path):
    value=copy.deepcopy(DEFAULTS)
    if Path(path).exists():
        saved=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(saved,dict):raise ValueError('Configuração da central inválida.')
        value.update(saved)
    return value


def save_settings(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)


def settings_dialog(parent,path,on_saved=None):
    try:settings=load_settings(path)
    except Exception as exc:messagebox.showerror('Configuração',str(exc),parent=parent);return
    dialog=tk.Toplevel(parent);dialog.title('Central — pastas e impressoras');dialog.transient(parent);dialog.grab_set()
    body=ttk.Frame(dialog,padding=16);body.pack(fill='both',expand=True)
    values={}
    for field,label in [('root','Pasta principal dos condomínios'),('statements','Extratos (pasta acima dos anos)'),('reports','Pasta dos PDFs pessoais de obrigações')]:
        ttk.Label(body,text=label).pack(anchor='w',pady=(8,3));row=ttk.Frame(body);row.pack(fill='x')
        value=tk.StringVar(value=settings[field]);values[field]=value
        ttk.Entry(row,textvariable=value,width=85).pack(side='left',fill='x',expand=True)
        def browse(v=value):
            chosen=filedialog.askdirectory(parent=dialog)
            if chosen:v.set(chosen)
        ttk.Button(row,text='Escolher…',command=browse).pack(side='right',padx=5)
    # A enumeração de impressoras também pode envolver a rede.
    printer_names=[]
    combos=[]
    for field,label in [('main_printer','Fechamento e extratos'),('report_printer','Relatório de obrigações')]:
        ttk.Label(body,text='Impressora — '+label).pack(anchor='w',pady=(10,3))
        value=tk.StringVar(value=settings[field]);values[field]=value
        combo=ttk.Combobox(body,textvariable=value,values=[],width=85);combo.pack(fill='x');combos.append(combo)
    errors=queue.Queue()
    def printers():
        try:errors.put(('ok',available_printers()[0]))
        except Exception as exc:errors.put(('error',str(exc)))
    threading.Thread(target=printers,daemon=True).start()
    def poll():
        if not dialog.winfo_exists():return
        try:
            kind,result=errors.get_nowait()
            if kind=='ok':
                printer_names.extend(result)
                for combo in combos:combo.configure(values=result)
                for field,needle in [('main_printer','e50145'),('report_printer','l3150')]:
                    if not values[field].get():values[field].set(next((n for n in result if needle in n.casefold()),''))
        except queue.Empty:dialog.after(100,poll)
    dialog.after(100,poll)
    include=tk.BooleanVar(value=settings['include_report'])
    ttk.Checkbutton(body,text='Marcar obrigações por padrão (pode desmarcar antes de imprimir)',variable=include).pack(anchor='w',pady=12)
    ttk.Label(body,text='Uma cópia, somente frente. A ordem do fechamento é fixa: capa, aprovação, anexo I, anexo II, extratos.',wraplength=650).pack(anchor='w')
    def save():
        try:
            updated=dict(settings,**{k:v.get().strip() for k,v in values.items()},include_report=include.get())
            if not updated['root'] or not updated['statements']:raise ValueError('Informe as pastas principais de condomínios e extratos.')
            save_settings(path,updated)
            dialog.destroy()
            if isinstance(parent,tk.Toplevel):parent.grab_set()
            if on_saved:on_saved()
        except Exception as exc:messagebox.showerror('Configuração não salva',str(exc),parent=dialog)
    ttk.Button(body,text='Salvar',style='Primary.TButton',command=save).pack(anchor='e',pady=16)
    def close():
        dialog.destroy()
        if isinstance(parent,tk.Toplevel):parent.grab_set()
    dialog.protocol('WM_DELETE_WINDOW',close)
    return dialog


class CentralDialog(tk.Toplevel):
    def __init__(self,parent,path):
        super().__init__(parent)
        self.parent=parent;self.path=Path(path);self.settings=load_settings(path)
        self.result=None;self.comparison=None;self.checked=set();self.busy=False;self.events=queue.Queue();self.cancel=parent.cancel
        self.title('Central de impressão por condomínio');self.geometry(f'1080x{min(680,self.winfo_screenheight()-100)}');self.minsize(900,580)
        self.transient(parent);self.grab_set()
        self.name=tk.StringVar();self.month=tk.StringVar(value=parent.month.get());self.year=tk.StringVar(value=parent.year.get())
        self.version=tk.StringVar(value='pdf');self.status=tk.StringVar(value='Carregando nomes dos condomínios…')
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1);body.rowconfigure(2,weight=1)
        row=ttk.Frame(body);row.grid(row=0,column=0,sticky='ew')
        ttk.Label(row,text='Condomínio').pack(side='left')
        self.names=ttk.Combobox(row,textvariable=self.name,state='readonly',width=38);self.names.pack(side='left',padx=8)
        from engine import MONTHS
        self.months=MONTHS
        self.month_box=ttk.Combobox(row,textvariable=self.month,values=[m.title() for m in MONTHS],state='readonly',width=13);self.month_box.pack(side='left',padx=5)
        self.year_box=ttk.Spinbox(row,textvariable=self.year,from_=2000,to=2099,width=6);self.year_box.pack(side='left')
        self.controls=[self.names,self.month_box,self.year_box]
        self.action(row,'Buscar arquivos',self.query).pack(side='left',padx=8)
        self.action(row,'Configurações',self.configure_paths).pack(side='right')
        ttk.Label(body,text='Marque os documentos na primeira coluna. Todos os extratos encontrados entram selecionados.',style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=10)
        host=ttk.Frame(body);host.grid(row=2,column=0,sticky='nsew')
        self.tree=ttk.Treeview(host,columns=('check','group','file','printer'),show='headings',selectmode='browse')
        for key,title,width in [('check','Imprimir',65),('group','Documento / ordem',195),('file','Arquivo',460),('printer','Impressora',280)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=50,stretch=key in ('file','printer'))
        self.tree.pack(side='left',fill='both',expand=True);scroll=ttk.Scrollbar(host,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<Button-1>',self.click);self.tree.bind('<space>',self.toggle)
        row=ttk.Frame(body);row.grid(row=3,column=0,sticky='ew',pady=10)
        self.action(row,'Todos os extratos',lambda:self.check_statements(True)).pack(side='left')
        self.action(row,'Desmarcar extratos',lambda:self.check_statements(False)).pack(side='left',padx=6)
        self.action(row,'Abrir arquivo',self.open_file).pack(side='left',padx=6)
        self.action(row,'Vincular arquivo…',self.link).pack(side='left',padx=6)
        self.action(row,'Vincular Word Jurídico…',lambda:self.link(True)).pack(side='left')
        row=ttk.Frame(body);row.grid(row=4,column=0,sticky='ew',pady=4)
        self.action(row,'Comparar obrigações',self.compare).pack(side='left')
        self.action(row,'Abrir Word Jurídico',lambda:self.open_file(True)).pack(side='left',padx=6)
        self.action(row,'Conferi manualmente',self.manual_review).pack(side='left')
        self.pdf_radio=ttk.Radiobutton(row,text='Usar PDF pessoal',variable=self.version,value='pdf',command=self.redraw);self.pdf_radio.pack(side='left',padx=10)
        self.word_radio=ttk.Radiobutton(row,text='Usar Word atual',variable=self.version,value='word',command=self.redraw);self.word_radio.pack(side='left')
        self.controls.extend((self.pdf_radio,self.word_radio))
        self.details=tk.Text(body,height=5,wrap='word',state='disabled',font=('Segoe UI',10));self.details.grid(row=5,column=0,sticky='ew',pady=6)
        footer=ttk.Frame(body);footer.grid(row=6,column=0,sticky='ew')
        ttk.Label(footer,textvariable=self.status,wraplength=740).pack(side='left',fill='x',expand=True)
        self.print_button=self.action(footer,'Imprimir selecionados',self.print_selected);self.print_button.configure(style='Primary.TButton');self.print_button.pack(side='right')
        self.cancel_button=ttk.Button(footer,text='Cancelar',command=self.cancel.set,state='disabled');self.cancel_button.pack(side='right',padx=8)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.names.bind('<<ComboboxSelected>>',lambda e:self.query())
        self.month_box.bind('<<ComboboxSelected>>',lambda e:self.invalidate())
        self.year.trace_add('write',lambda *args:self.invalidate())
        self.after(100,self.poll)
        self.reload()

    def action(self,parent,text,command):
        button=ttk.Button(parent,text=text,command=command);self.controls.append(button);return button

    def invalidate(self):
        if self.busy:return
        self.result=None;self.comparison=None;self.checked.clear();self.tree.delete(*self.tree.get_children());self.version.set('pdf')
        self.status.set('Clique em Buscar arquivos para a seleção atual.')

    def configure_paths(self):
        if not self.busy:settings_dialog(self,self.path,self.reload)

    def reload(self):
        self.settings=load_settings(self.path);self.invalidate()
        self.run(lambda:catalog(self.settings),'catalog')

    def context(self):
        return self.name.get(),self.months.index(self.month.get().lower())+1,int(self.year.get())

    def query(self):
        if self.busy:return
        try:
            name,month,year=self.context()
            if not name or not 2000<=year<=2099:raise ValueError('Selecione o condomínio e uma competência válida.')
        except Exception as exc:messagebox.showerror('Seleção',str(exc),parent=self);return
        self.invalidate()
        settings=copy.deepcopy(self.settings);mappings=copy.deepcopy(self.parent.mappings)
        self.run(lambda:search(settings,name,month,year,mappings),'search')

    def run(self,work,kind):
        if self.busy:return
        self.busy=True;self.parent.busy=True;self.cancel.clear()
        for widget in self.controls:widget.configure(state='disabled')
        self.cancel_button.configure(state='normal');self.status.set('Processando…')
        def worker():
            try:self.events.put((kind,work()))
            except Exception as exc:self.events.put(('error',str(exc)))
            finally:self.events.put(('done',None))
        threading.Thread(target=worker,daemon=False).start()

    def poll(self):
        try:
            for _ in range(40):
                kind,value=self.events.get_nowait()
                if kind=='catalog':
                    self.names.configure(values=value)
                    current=self.parent.selected()
                    candidate=current[0]['name'] if len(current)==1 else self.name.get()
                    if candidate in value:self.name.set(candidate)
                    self.status.set('Selecione o nome do condomínio e busque os arquivos.')
                elif kind=='search':
                    self.result=value;self.checked={i for i,row in enumerate(value['rows']) if row['checked']}
                    self.redraw();self.show_details('\n'.join(value['warnings']) or 'Arquivos localizados. Selecione o que deseja imprimir.')
                    self.status.set('Extratos: todos selecionados por padrão. Obrigações são opcionais e exigem conferência.')
                elif kind=='comparison':
                    self.comparison=value;self.version.set('pdf' if value['equal'] else '');self.redraw();self.show_details(value['diff']);self.status.set('Textos equivalentes: será usado o PDF pessoal.' if value['equal'] else 'Há diferenças. Confira e escolha PDF pessoal ou Word atual antes de imprimir.')
                elif kind=='printed':self.status.set(value);self.show_details(value)
                elif kind=='log':self.status.set(value)
                elif kind=='error':
                    self.show_details(value);self.status.set('Não foi possível concluir. Confira os detalhes.');messagebox.showerror('Central de impressão',value,parent=self)
                elif kind=='done':
                    self.busy=False;self.parent.busy=False
                    for widget in self.controls:widget.configure(state='normal')
                    self.names.configure(state='readonly');self.month_box.configure(state='readonly');self.cancel_button.configure(state='disabled')
        except queue.Empty:pass
        if self.winfo_exists():self.after(100,self.poll)

    def redraw(self):
        if not self.result:return
        self.tree.delete(*self.tree.get_children())
        for i,row in enumerate(self.result['rows']):
            path=self.result['word'] if row['group']=='obligations' and self.version.get()=='word' else row['path']
            self.tree.insert('','end',iid=str(i),values=('✓' if i in self.checked else '',row['label'],str(path) if path else 'NÃO LOCALIZADO — vincule ou desmarque',row['printer']))

    def click(self,event):
        if self.tree.identify_column(event.x)=='#1':
            row=self.tree.identify_row(event.y)
            if row:self.toggle(index=int(row))

    def toggle(self,event=None,index=None):
        if self.busy or not self.result:return 'break'
        if index is None:
            selected=self.tree.selection()
            if not selected:return 'break'
            index=int(selected[0])
        if index in self.checked:self.checked.remove(index)
        else:self.checked.add(index)
        self.redraw();return 'break'

    def check_statements(self,include):
        if not self.result:return
        for i,row in enumerate(self.result['rows']):
            if row['group']=='statement':
                if include:self.checked.add(i)
                else:self.checked.discard(i)
        self.redraw()

    def show_details(self,text):
        self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('end',text);self.details.configure(state='disabled')

    def report_paths(self):
        if not self.result:raise ValueError('Busque os arquivos primeiro.')
        pdf=next(r['path'] for r in self.result['rows'] if r['group']=='obligations')
        word=self.result['word']
        if not pdf or not word:raise ValueError('Vincule o PDF pessoal e o Word do Jurídico antes de conferir.')
        return pdf,word

    def compare(self):
        try:pdf,word=self.report_paths()
        except Exception as exc:messagebox.showinfo('Comparação',str(exc),parent=self);return
        self.comparison=None
        def work():
            with tempfile.TemporaryDirectory(prefix='autoword_comparacao_') as folder:
                with Word() as service:return compare_reports(service,pdf,word,folder)
        self.run(work,'comparison')

    def manual_review(self):
        try:pdf,word=self.report_paths()
        except Exception as exc:messagebox.showinfo('Conferência',str(exc),parent=self);return
        if not messagebox.askyesno('Conferência manual','Você abriu e conferiu os dois relatórios? Esta confirmação permite imprimir mesmo sem comparação automática completa.',parent=self):return
        self.comparison={'equal':False,'hashes':{str(p):digest(Path(p)) for p in (pdf,word)},'diff':'Conferência manual confirmada pelo usuário.'}
        self.version.set('')
        self.show_details(self.comparison['diff']+' Escolha PDF pessoal ou Word atual.')

    def open_file(self,word=False):
        if not self.result:return
        path=self.result['word'] if word else self.result['rows'][int(self.tree.selection()[0])]['path'] if self.tree.selection() else None
        if not word and self.tree.selection() and self.result['rows'][int(self.tree.selection()[0])]['group']=='obligations' and self.version.get()=='word':path=self.result['word']
        if path:
            try:os.startfile(str(path))
            except Exception as exc:messagebox.showerror('Abrir arquivo',str(exc),parent=self)

    def link(self,word=False):
        if not self.result:return
        if word:key='report_word';group='word'
        else:
            selected=self.tree.selection()
            if not selected:messagebox.showinfo('Vincular','Selecione a linha do documento na lista.',parent=self);return
            row=self.result['rows'][int(selected[0])];key=row['key'];group=row['group']
        pdf=group in ('statement','obligations')
        if group=='statement':paths=filedialog.askopenfilenames(parent=self,title='Selecione os extratos deste condomínio e competência',filetypes=[('PDF','*.pdf')])
        else:
            chosen=filedialog.askopenfilename(parent=self,title='Vincular arquivo',filetypes=[('PDF','*.pdf')] if pdf else [('Word','*.doc *.docx')]);paths=[chosen] if chosen else []
        if not paths:return
        try:
            self.settings.setdefault('overrides',{}).setdefault(self.result['name'],{})[key]=list(paths) if group=='statement' else paths[0]
            save_settings(self.path,self.settings);self.query()
        except Exception as exc:messagebox.showerror('Associação não salva',str(exc),parent=self)

    def print_selected(self):
        if not self.result:return
        try:
            rows=selected_plan(self.result,self.checked,self.version.get(),self.comparison)
            summary='\n'.join(f"{i+1}. {row['label']} ({Path(row['path']).name}) → {row['printer']}" for i,row in enumerate(rows))
        except Exception as exc:messagebox.showerror('Impressão',str(exc),parent=self);return
        if not messagebox.askyesno('Confirmar impressão',summary+'\n\nUma cópia, somente frente. Enviar estes documentos?',parent=self):return
        def work():
            count=execute_plan(rows,self.cancel,lambda text:self.events.put(('log',text)),Word)
            return f'{count}/{len(rows)} documento(s) enviado(s). Confira a fila das impressoras; não há repetição automática em caso de falha.'
        self.run(work,'printed')

    def close(self):
        if self.busy:
            self.cancel.set();messagebox.showinfo('Aguarde','Cancelamento solicitado. Aguarde a operação atual terminar.',parent=self);return
        self.destroy()
